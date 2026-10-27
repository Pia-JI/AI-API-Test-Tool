"""本地模拟 OpenAI 兼容接口，用于在没有真实 API Key 的情况下自测。

用法：
    python tools/mock_api_server.py            # 默认监听 127.0.0.1:8899
    python tools/mock_api_server.py --port 9000 --latency 0.3 --fail-rate 0.2

然后在软件里把 Base URL 填成 http://127.0.0.1:8899/v1 ，API Key 随便填。
支持的端点：
    GET  /v1/models             模型列表（--no-models 可模拟 404 不支持）
    POST /v1/chat/completions   会话补全，支持 stream=true / false
"""

import argparse
import json
import random
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODELS = [
    {"id": "mock-fast-1", "object": "model", "created": 1700000000, "owned_by": "mock-lab"},
    {"id": "mock-slow-1", "object": "model", "created": 1690000000, "owned_by": "mock-lab"},
    {"id": "mock-chat-pro", "object": "model", "created": 1710000000, "owned_by": "mock-lab"},
]

ANSWER = (
    "人工智能是让机器具备感知、学习与推理能力，从而完成原本需要人类智能才能完成的任务的一门技术。"
    "它涵盖了机器学习、自然语言处理、计算机视觉等多个方向。"
)

OPTIONS = {"latency": 0.15, "fail_rate": 0.0, "no_models": False, "auth_required": True}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        print("[mock] " + fmt % args)

    # ------------------------------------------------------------ 工具
    def _check_auth(self):
        if not OPTIONS["auth_required"]:
            return True
        token = self.headers.get("Authorization", "")
        if not token.startswith("Bearer ") or len(token) <= len("Bearer "):
            self._json(401, {"error": {"message": "Incorrect API key provided", "type": "invalid_request_error"}})
            return False
        return True

    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _maybe_fail(self):
        if OPTIONS["fail_rate"] <= 0 or random.random() > OPTIONS["fail_rate"]:
            return False
        if random.random() < 0.5:
            self._json(429, {"error": {"message": "Rate limit reached for requests", "type": "rate_limit_error"}})
        else:
            self._json(500, {"error": {"message": "The server had an error processing your request", "type": "server_error"}})
        return True

    # ------------------------------------------------------------ GET
    def do_GET(self):
        if not self._check_auth():
            return
        time.sleep(OPTIONS["latency"])
        if self.path.startswith("/v1/models") or self.path.startswith("/models"):
            if OPTIONS["no_models"]:
                self._json(404, {"error": {"message": "Not found", "type": "invalid_request_error"}})
                return
            if self._maybe_fail():
                return
            self._json(200, {"object": "list", "data": MODELS})
            return
        self._json(404, {"error": {"message": "Unknown endpoint", "type": "invalid_request_error"}})

    # ------------------------------------------------------------ POST
    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        if not self._check_auth():
            return
        try:
            payload = json.loads(raw.decode("utf-8"))
        except ValueError:
            self._json(400, {"error": {"message": "Invalid JSON body", "type": "invalid_request_error"}})
            return
        model = payload.get("model", "mock-fast-1")
        if not any(m["id"] == model for m in MODELS):
            self._json(404, {"error": {"message": "The model does not exist", "type": "invalid_request_error"}})
            return
        if self._maybe_fail():
            return
        if payload.get("stream"):
            self._stream(model)
        else:
            self._plain(model, payload)

    def _plain(self, model, payload):
        time.sleep(OPTIONS["latency"] + (0.6 if "slow" in model else 0.0))
        prompt_tokens = max(1, len(json.dumps(payload.get("messages", []), ensure_ascii=False)) // 4)
        completion_tokens = max(1, len(ANSWER) // 2)
        self._json(200, {
            "id": "chatcmpl-mock", "object": "chat.completion", "created": int(time.time()), "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": ANSWER}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
                      "total_tokens": prompt_tokens + completion_tokens},
        })

    def _stream(self, model):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        time.sleep(OPTIONS["latency"] + (0.4 if "slow" in model else 0.0))
        pieces = [ANSWER[i:i + 6] for i in range(0, len(ANSWER), 6)]
        sent = 0
        try:
            for index, piece in enumerate(pieces):
                chunk = {
                    "id": "chatcmpl-mock", "object": "chat.completion.chunk", "created": int(time.time()),
                    "model": model,
                    "choices": [{"index": 0, "delta": {"content": piece},
                                 "finish_reason": "stop" if index == len(pieces) - 1 else None}],
                }
                self.wfile.write(("data: %s\n\n" % json.dumps(chunk, ensure_ascii=False)).encode("utf-8"))
                self.wfile.flush()
                sent += 1
                time.sleep(0.04)
            usage = {"prompt_tokens": 12, "completion_tokens": sent, "total_tokens": 12 + sent}
            self.wfile.write(("data: %s\n\n" % json.dumps({"choices": [], "usage": usage})).encode("utf-8"))
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass


def main():
    parser = argparse.ArgumentParser(description="本地模拟 OpenAI 兼容接口")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8899)
    parser.add_argument("--latency", type=float, default=0.15, help="每次请求的基础延迟（秒）")
    parser.add_argument("--fail-rate", type=float, default=0.0, help="模拟失败概率 0~1")
    parser.add_argument("--no-models", action="store_true", help="模拟不支持 /models 接口")
    parser.add_argument("--no-auth", action="store_true", help="不校验 API Key")
    args = parser.parse_args()
    OPTIONS.update({"latency": args.latency, "fail_rate": args.fail_rate,
                    "no_models": args.no_models, "auth_required": not args.no_auth})
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print("模拟接口已启动：http://%s:%d/v1  （Ctrl+C 停止）" % (args.host, args.port))
    print("模型：%s" % ", ".join(m["id"] for m in MODELS))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
