"""OpenAI 兼容接口的网络请求封装。

只依赖 requests，可被任意线程调用（内部使用独立的 Session，不做全局状态）。

主要能力：
    list_models()       调用 GET {base}/models 获取模型列表
    ping()              发送一次轻量请求，用于延迟 / 稳定性测试
    chat_completion()   调用 POST {base}/chat/completions，支持流式与非流式

所有异常都归一化为 ApiError，并带上 error_kind 便于统计错误类型分布。
"""

import json
import time

import requests
from requests.adapters import HTTPAdapter

# ------------------------------------------------------------------ 错误分类
KIND_TIMEOUT = "timeout"                 # 超时
KIND_AUTH = "auth"                       # 鉴权失败（401 / 403）
KIND_NOT_FOUND = "not_found"             # 接口或模型不存在（404）
KIND_RATE_LIMIT = "rate_limit"           # 触发限流（429）
KIND_SERVER = "server"                   # 服务端错误（5xx）
KIND_CLIENT = "client"                   # 请求参数等客户端错误（4xx）
KIND_NETWORK = "network"                 # DNS / 连接失败等网络异常
KIND_FORMAT = "format"                   # 返回内容无法解析
KIND_CONTENT_FILTER = "content_filter"   # 触发内容审核
KIND_UNKNOWN = "unknown"

KIND_LABELS = {
    KIND_TIMEOUT: "超时",
    KIND_AUTH: "鉴权失败",
    KIND_NOT_FOUND: "接口/模型不存在",
    KIND_RATE_LIMIT: "触发限流",
    KIND_SERVER: "服务端错误",
    KIND_CLIENT: "请求错误",
    KIND_NETWORK: "网络异常",
    KIND_FORMAT: "响应格式错误",
    KIND_CONTENT_FILTER: "触发内容审核",
    KIND_UNKNOWN: "未知错误",
}

_CONTENT_FILTER_HINTS = (
    "content_filter",
    "content filter",
    "content policy",
    "contentpolicyviolation",
    "csam",
    "safety",
    "risk control",
    "敏感",
    "审核",
    "违规",
)


class ApiError(Exception):
    """统一的接口异常。"""

    def __init__(self, kind, message, status=None, detail=None):
        super(ApiError, self).__init__(message)
        self.kind = kind
        self.message = message
        self.status = status
        self.detail = detail

    @property
    def label(self):
        return KIND_LABELS.get(self.kind, self.kind)


def normalize_base_url(url):
    """规整用户填写的 Base URL。

    - 去掉首尾空格与末尾斜杠
    - 缺少协议头时自动补 https://
    - 用户误填完整端点（/chat/completions、/models）时自动去掉
    """
    text = (url or "").strip().strip('"').strip("'")
    if not text:
        return ""
    if not text.lower().startswith(("http://", "https://")):
        text = "https://" + text
    text = text.rstrip("/")
    lowered = text.lower()
    for suffix in ("/chat/completions", "/completions", "/models"):
        if lowered.endswith(suffix):
            text = text[: -len(suffix)]
            break
    return text.rstrip("/")


def _harvest_error_message(payload):
    """从错误响应体中尽量抽出可读的错误说明。"""
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error.get("code") or error)
        if isinstance(error, str):
            return error
        for key in ("message", "msg", "detail", "error_msg"):
            if payload.get(key):
                return str(payload[key])
    if isinstance(payload, str) and payload.strip():
        return payload.strip()[:300]
    return ""


def _looks_like_content_filter(text):
    lowered = (text or "").lower()
    return any(hint in lowered for hint in _CONTENT_FILTER_HINTS)


def fmt_seconds(value):
    """把秒数格式化成易读文本（小于 10 秒保留一位小数）。"""
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return str(value)
    return ("%.1fs" % seconds) if seconds < 10 else ("%.0fs" % seconds)


def classify_status(status, message=""):
    """根据 HTTP 状态码与错误信息判定错误类型。"""
    if status in (401, 403):
        return KIND_AUTH
    if status == 404:
        return KIND_NOT_FOUND
    if status == 429:
        return KIND_RATE_LIMIT
    if status and status >= 500:
        return KIND_SERVER
    if status and 400 <= status < 500:
        if _looks_like_content_filter(message):
            return KIND_CONTENT_FILTER
        return KIND_CLIENT
    return KIND_UNKNOWN


def class_model_info(item):
    """把 /models 返回的单个条目转换为统一结构。"""
    if not isinstance(item, dict):
        return None
    model_id = item.get("id") or item.get("model") or item.get("name")
    if not model_id:
        return None
    created = item.get("created") or item.get("created_at")
    created_text = ""
    if isinstance(created, (int, float)) and created > 0:
        try:
            created_text = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(created))
        except (ValueError, OSError):
            created_text = str(created)
    elif isinstance(created, str):
        created_text = created
    return {
        "id": str(model_id),
        "owned_by": str(item.get("owned_by") or item.get("owner") or ""),
        "created": created,
        "created_text": created_text,
        "raw": item,
    }


class ChatResult(object):
    """一次对话请求的完整结果与指标。"""

    def __init__(self, model, stream):
        self.model = model
        self.requested_stream = stream
        self.ok = False
        self.error_kind = None
        self.error_message = ""
        self.status = None
        self.ttft_ms = None          # 首 Token 时间（毫秒），非流式无法测量
        self.total_ms = None         # 完整响应时间（毫秒）
        self.output_tokens = None    # 输出 Token 数
        self.tps = None              # 每秒输出 Token 数
        self.content = ""
        self.usage = None            # 接口返回的用量信息
        self.finish_reason = None
        self.content_filtered = False
        self.rate_limited = False
        self.extra = {}

    def to_dict(self):
        return {
            "model": self.model,
            "ok": self.ok,
            "stream": self.requested_stream,
            "error_kind": self.error_kind,
            "error": self.error_message,
            "status": self.status,
            "ttft_ms": self.ttft_ms,
            "total_ms": self.total_ms,
            "output_tokens": self.output_tokens,
            "tps": self.tps,
            "content": self.content,
            "usage": self.usage,
            "finish_reason": self.finish_reason,
            "content_filtered": self.content_filtered,
            "rate_limited": self.rate_limited,
        }


class ApiClient(object):
    """一个 API 配置对应一个 Client 实例。"""

    def __init__(self, base_url, api_key="", timeout=60, proxy="", user_agent="AI-API-Toolbox/1.0"):
        self.base_url = normalize_base_url(base_url)
        self.api_key = (api_key or "").strip()
        self.timeout = float(timeout or 60)
        self.proxy = (proxy or "").strip()
        self.user_agent = user_agent
        self._session = None

    # ------------------------------------------------------------------ 基础
    @property
    def session(self):
        if self._session is None:
            session = requests.Session()
            # 关闭自动重试：延迟测试需要真实反映单次请求耗时
            adapter = HTTPAdapter(pool_connections=32, pool_maxsize=32, max_retries=0)
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            self._session = session
        return self._session

    def close(self):
        if self._session is not None:
            try:
                self._session.close()
            except Exception:
                pass
            self._session = None

    def headers(self, extra=None):
        headers = {
            "Authorization": "Bearer %s" % self.api_key,
            "Content-Type": "application/json",
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }
        if extra:
            headers.update(extra)
        return headers

    def url(self, path):
        if not self.base_url:
            raise ApiError(KIND_CLIENT, "尚未配置 API 地址")
        return "%s/%s" % (self.base_url, path.lstrip("/"))

    def _request_kwargs(self, timeout=None):
        total = float(timeout or self.timeout)
        kwargs = {"timeout": (min(10.0, total), total)}
        if self.proxy:
            kwargs["proxies"] = {"http": self.proxy, "https": self.proxy}
        return kwargs

    def configured(self):
        return bool(self.base_url and self.api_key)

    # ------------------------------------------------------- 1) 模型列表
    def list_models(self, timeout=None):
        """获取模型列表。

        返回 [{"id":..., "owned_by":..., "created_text":..., "raw":...}, ...]
        接口不存在或返回结构异常时抛出 ApiError。
        """
        url = self.url("models")
        try:
            resp = self.session.get(url, headers=self.headers(), **self._request_kwargs(timeout))
        except requests.exceptions.Timeout:
            raise ApiError(KIND_TIMEOUT, "请求 /models 超时（%s）" % fmt_seconds(self.timeout))
        except requests.exceptions.RequestException as exc:
            raise ApiError(KIND_NETWORK, "网络异常：%s" % exc)

        if resp.status_code >= 400:
            if resp.status_code in (404, 405, 501):
                raise ApiError(
                    KIND_NOT_FOUND,
                    "该接口不支持 /models（HTTP %d），请手动填写模型名称后继续测试。" % resp.status_code,
                    status=resp.status_code,
                )
            message = _harvest_error_message(self._safe_json(resp)) or resp.text[:200]
            kind = classify_status(resp.status_code, message)
            raise ApiError(kind, "%s：%s" % (KIND_LABELS[kind], message), status=resp.status_code)

        payload = self._safe_json(resp)
        if payload is None:
            raise ApiError(KIND_FORMAT, "返回内容不是合法 JSON，无法解析模型列表", status=resp.status_code)

        items = payload.get("data") if isinstance(payload, dict) else payload
        if items is None and isinstance(payload, dict):
            items = payload.get("models")
        if not isinstance(items, list):
            raise ApiError(KIND_FORMAT, "返回结构不符合 OpenAI /models 规范，未找到模型列表", status=resp.status_code)

        models = []
        seen = set()
        for item in items:
            info = class_model_info(item)
            if info and info["id"] not in seen:
                seen.add(info["id"])
                models.append(info)
        models.sort(key=lambda m: m["id"].lower())
        return models

    @staticmethod
    def _safe_json(resp):
        try:
            return resp.json()
        except ValueError:
            return None

    # ------------------------------------------------------- 2) 轻量请求
    def ping(self, target="models", timeout=None, model=None):
        """发送一次轻量请求并计时。

        target: "models" 请求 /models；"chat" 请求 /chat/completions（max_tokens=1）
        返回 {"ok":bool, "latency_ms":float, "status":int, "error_kind":str, "error":str}
        """
        timeout = float(timeout or self.timeout)
        started = time.perf_counter()
        error_kind = None
        error_message = ""
        status = None
        timeout_hit = False
        ok = False

        try:
            if target == "chat":
                payload = {
                    "model": model or "gpt-3.5-turbo",
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 1,
                    "stream": False,
                }
                resp = self.session.post(
                    self.url("chat/completions"), headers=self.headers(), json=payload,
                    **self._request_kwargs(timeout)
                )
            else:
                resp = self.session.get(
                    self.url("models"), headers=self.headers(), **self._request_kwargs(timeout)
                )
            status = resp.status_code
            elapsed = (time.perf_counter() - started) * 1000.0
            if status < 400:
                ok = True
            else:
                message = _harvest_error_message(self._safe_json(resp)) or resp.text[:200]
                error_kind = classify_status(status, message)
                error_message = "%s：%s" % (KIND_LABELS[error_kind], message)
        except requests.exceptions.Timeout:
            elapsed = (time.perf_counter() - started) * 1000.0
            error_kind = KIND_TIMEOUT
            error_message = "请求超时（%s）" % fmt_seconds(timeout)
            timeout_hit = True
        except requests.exceptions.RequestException as exc:
            elapsed = (time.perf_counter() - started) * 1000.0
            error_kind = KIND_NETWORK
            error_message = "网络异常：%s" % exc

        return {
            "ok": ok,
            "latency_ms": round(elapsed, 2),
            "status": status,
            "error_kind": error_kind,
            "error": error_message,
            "timeout": timeout_hit,
        }

    # ------------------------------------------------------- 3) 对话请求
    def chat_completion(self, model, prompt, max_tokens=256, temperature=0.7,
                        stream=False, timeout=None, system_prompt=None, extra_params=None):
        """调用会话补全接口，返回 ChatResult。"""
        result = ChatResult(model, stream)
        body = {
            "model": model,
            "messages": self._build_messages(prompt, system_prompt),
            "max_tokens": int(max_tokens) if max_tokens else None,
            "temperature": float(temperature),
            "stream": bool(stream),
        }
        if stream:
            # 让部分服务商在流式响应中也返回 usage
            body["stream_options"] = {"include_usage": True}
        if extra_params:
            body.update(extra_params)
        body = {k: v for k, v in body.items() if v is not None}

        started = time.perf_counter()
        try:
            if stream:
                self._chat_stream(body, result, started, timeout)
            else:
                self._chat_once(body, result, started, timeout)
        except ApiError as exc:
            result.ok = False
            result.error_kind = exc.kind
            result.error_message = exc.message
            result.status = exc.status
            result.rate_limited = exc.kind == KIND_RATE_LIMIT
            result.content_filtered = exc.kind == KIND_CONTENT_FILTER
            result.total_ms = round((time.perf_counter() - started) * 1000.0, 2)
        except Exception as exc:  # 兜底，保证界面不会因为未知异常崩溃
            result.ok = False
            result.error_kind = KIND_UNKNOWN
            result.error_message = "未知错误：%s" % exc
            result.total_ms = round((time.perf_counter() - started) * 1000.0, 2)
        return result

    @staticmethod
    def _build_messages(prompt, system_prompt=None):
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _chat_once(self, body, result, started, timeout):
        """非流式请求。"""
        resp = self._post(body, timeout)
        payload = self._safe_json(resp)
        result.status = resp.status_code
        if payload is None:
            raise ApiError(KIND_FORMAT, "返回内容不是合法 JSON", status=resp.status_code)
        result.usage = payload.get("usage")
        choices = payload.get("choices") or []
        if not choices:
            raise ApiError(KIND_FORMAT, "响应中没有 choices 字段", status=resp.status_code)
        choice = choices[0] or {}
        message = choice.get("message") or {}
        content = message.get("content")
        if isinstance(content, list):  # 部分服务商返回分段内容
            content = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        result.content = content or ""
        result.finish_reason = choice.get("finish_reason")
        result.total_ms = round((time.perf_counter() - started) * 1000.0, 2)
        result.ok = True
        self._fill_token_metrics(result, stream=False)
        if result.finish_reason == "content_filter" or _looks_like_content_filter(result.content):
            result.content_filtered = True

    def _chat_stream(self, body, result, started, timeout):
        """流式请求：逐块读取 SSE，记录首 Token 时间。"""
        resp = self._post(body, timeout, stream=True)
        result.status = resp.status_code
        chunks = []
        ttft = None
        finish_reason = None
        usage = None
        for raw in resp.iter_lines(decode_unicode=False):
            if not raw:
                continue
            try:
                line = raw.decode("utf-8", "replace").strip()
            except Exception:
                continue
            if line.startswith("data:"):
                line = line[5:].strip()
            if not line or line == "[DONE]":
                if line == "[DONE]":
                    break
                continue
            try:
                payload = json.loads(line)
            except ValueError:
                continue
            if payload.get("usage"):
                usage = payload.get("usage")
            for choice in payload.get("choices") or []:
                if choice.get("finish_reason"):
                    finish_reason = choice.get("finish_reason")
                delta = choice.get("delta") or choice.get("message") or {}
                piece = delta.get("content")
                if isinstance(piece, list):
                    piece = "".join(p.get("text", "") for p in piece if isinstance(p, dict))
                if piece:
                    if ttft is None:
                        ttft = (time.perf_counter() - started) * 1000.0
                    chunks.append(piece)
        result.total_ms = round((time.perf_counter() - started) * 1000.0, 2)
        result.content = "".join(chunks)
        result.finish_reason = finish_reason
        result.usage = usage
        result.ttft_ms = round(ttft, 2) if ttft is not None else None
        result.ok = True
        self._fill_token_metrics(result, stream=True)
        if finish_reason == "content_filter" or _looks_like_content_filter(result.content):
            result.content_filtered = True

    def _post(self, body, timeout, stream=False):
        """统一的 POST 处理，含 HTTP 错误转 ApiError。"""
        try:
            resp = self.session.post(
                self.url("chat/completions"), headers=self.headers(), json=body,
                stream=stream, **self._request_kwargs(timeout)
            )
        except requests.exceptions.Timeout:
            raise ApiError(
                KIND_TIMEOUT,
                "请求超时：模型 %s 在 %s 内没有响应（可调大超时时间）" % (
                    body.get("model"), fmt_seconds(timeout or self.timeout)),
            )
        except requests.exceptions.RequestException as exc:
            raise ApiError(KIND_NETWORK, "网络异常：%s" % exc)

        if resp.status_code >= 400:
            text = ""
            try:
                text = resp.text[:500]
            except Exception:
                text = ""
            message = _harvest_error_message(self._parse_json_text(text)) or text
            kind = classify_status(resp.status_code, message)
            if resp.status_code == 404:
                message = "%s（请确认模型名是否正确）" % message
            raise ApiError(kind, "%s：%s" % (KIND_LABELS[kind], message), status=resp.status_code)
        return resp

    @staticmethod
    def _parse_json_text(text):
        try:
            return json.loads(text)
        except Exception:
            return None

    def _fill_token_metrics(self, result, stream):
        """填充输出 Token 数与每秒 Token 数。"""
        from .stats import estimate_tokens

        usage = result.usage if isinstance(result.usage, dict) else {}
        tokens = usage.get("completion_tokens") or usage.get("output_tokens")
        if tokens is None:
            tokens = estimate_tokens(result.content)
            result.extra["tokens_estimated"] = True
        else:
            result.extra["tokens_estimated"] = False
        result.output_tokens = int(tokens)

        total_ms = result.total_ms or 0.0
        if stream and result.ttft_ms is not None:
            # 流式：用首 Token 之后的生成耗时计算速度，更贴近真实体验
            generation_ms = max(total_ms - result.ttft_ms, 1.0)
        else:
            generation_ms = max(total_ms, 1.0)
        result.tps = round(result.output_tokens / (generation_ms / 1000.0), 2) if result.output_tokens else 0.0

    # ------------------------------------------------------- 4) 连接自检
    def test_connection(self):
        """返回 (是否成功, 提示信息)。"""
        if not self.base_url:
            return False, "请先填写 API 地址"
        if not self.api_key:
            return False, "请先填写 API Key"
        try:
            models = self.list_models(timeout=min(self.timeout, 30))
            return True, "连接成功，共获取到 %d 个模型" % len(models)
        except ApiError as exc:
            if exc.kind == KIND_NOT_FOUND:
                probe = self.ping(timeout=min(self.timeout, 30))
                if probe["ok"]:
                    return True, "连接成功（该服务商未提供 /models 接口）"
            return False, exc.message
