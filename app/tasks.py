"""后台任务的具体实现（每个函数都在独立线程中执行）。

任务函数签名：fn(ctx, ...)，其中 ctx 为 app.workers.TaskContext。
返回值为 dict，交给界面渲染。
"""

from concurrent.futures import ThreadPoolExecutor

from . import stats
from .api_client import KIND_TIMEOUT, KIND_LABELS, ApiError


def fetch_models_task(ctx, client):
    """获取模型列表。"""
    ctx.log("正在请求 %s/models ..." % client.base_url)
    ctx.progress(10, "请求中")
    ctx.check()
    models = client.list_models()
    ctx.progress(100, "完成")
    ctx.log("获取成功，共 %d 个模型" % len(models))
    return {"models": models}


def connection_test_task(ctx, client):
    """测试当前配置能否正常连通（自动兼容不支持 /models 的服务商）。"""
    ctx.log("正在测试连接：%s" % client.base_url)
    ctx.progress(30, "连接中")
    ok, message = client.test_connection()
    ctx.log(("连接成功：" if ok else "连接失败：") + message)
    ctx.progress(100, "完成")
    return {"ok": ok, "message": message}


def latency_test_task(ctx, client, count=10, concurrency=1, timeout=30, target="models", model=None):
    """网络延迟与稳定性测试：向 API 发送多次轻量请求并统计耗时。"""
    count = max(1, int(count))
    concurrency = max(1, int(concurrency))
    samples = [None] * count
    ctx.log("开始延迟测试：目标=%s，次数=%d，并发=%d，超时=%.0fs" % (target, count, concurrency, timeout))

    def one(index):
        ctx.check()
        probe = client.ping(target=target, timeout=timeout, model=model)
        probe["index"] = index + 1
        probe["target"] = target
        return index, probe

    done = 0
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(one, i) for i in range(count)]
        for future in futures:
            try:
                index, probe = future.result()
            except Exception as exc:
                # 线程池内的异常（含取消）统一处理，保证进度条能走完
                if ctx.cancelled:
                    break
                index = done
                probe = {
                    "index": index + 1, "ok": False, "latency_ms": None, "status": None,
                    "error_kind": "unknown", "error": str(exc), "timeout": False, "target": target,
                }
            samples[index] = probe
            done += 1
            ctx.step(done, count, "已完成 %d/%d 次请求" % (done, count))
            if probe.get("ok"):
                ctx.log("第 %d 次：%.0f ms（HTTP %s）" % (probe["index"], probe["latency_ms"], probe["status"]))
            else:
                ctx.log("第 %d 次：失败 —— %s" % (probe["index"], probe.get("error") or probe.get("error_kind")))
        ctx.check()

    samples = [s for s in samples if s]
    summary = stats.summarize_latency(samples)
    ctx.log("延迟测试完成：成功率 %.1f%%，平均 %.0f ms，P95 %.0f ms" % (
        summary["success_rate"], summary.get("avg_ms") or 0.0, summary.get("p95_ms") or 0.0))
    return {"samples": samples, "summary": summary}


def speed_test_task(ctx, client, models, prompt, max_tokens=256, temperature=0.7,
                    timeout=60, stream=True, test_both=True, system_prompt=None):
    """模型速度测试：记录首 Token 时间、完整响应时间、输出速度等指标。"""
    models = list(models or [])
    if not models:
        raise ValueError("请先选择要测试的模型")
    results = []
    total_steps = len(models) * (2 if (stream and test_both) else 1)
    done = 0
    ctx.log("开始速度测试：%d 个模型，最大输出 %s tokens，温度 %s" % (len(models), max_tokens, temperature))

    for model in models:
        ctx.check()
        ctx.log("→ 测试模型 %s ..." % model)
        stream_result = None
        plain_result = None

        if stream:
            stream_result = client.chat_completion(
                model, prompt, max_tokens=max_tokens, temperature=temperature,
                stream=True, timeout=timeout, system_prompt=system_prompt)
            done += 1
            ctx.step(done, total_steps, "已完成 %d/%d" % (done, total_steps))
            if stream_result.ok:
                ctx.log("   流式成功：首 Token %s ms，总耗时 %s ms，%.1f tok/s" % (
                    stream_result.ttft_ms, stream_result.total_ms, stream_result.tps or 0.0))
            else:
                ctx.log("   流式失败：%s" % stream_result.error_message)

        if (not stream) or test_both:
            plain_result = client.chat_completion(
                model, prompt, max_tokens=max_tokens, temperature=temperature,
                stream=False, timeout=timeout, system_prompt=system_prompt)
            done += 1
            ctx.step(done, total_steps, "已完成 %d/%d" % (done, total_steps))
            if plain_result.ok:
                ctx.log("   非流式成功：总耗时 %s ms，%.1f tok/s" % (plain_result.total_ms, plain_result.tps or 0.0))
            else:
                ctx.log("   非流式失败：%s" % plain_result.error_message)

        results.append(_merge_speed_result(model, stream_result, plain_result, stream))
        ctx.check()

    summary = stats.summarize_speed(results)
    ctx.log("速度测试完成：成功 %d/%d" % (summary["success"], summary["model_count"]))
    return {"results": results, "summary": summary}


def _merge_speed_result(model, stream_result, plain_result, prefer_stream):
    """把流式 / 非流式两次请求合并成一行结果。"""
    primary = None
    if prefer_stream:
        primary = stream_result if (stream_result and stream_result.ok) else plain_result
    else:
        primary = plain_result if (plain_result and plain_result.ok) else stream_result
    if primary is None:
        primary = stream_result or plain_result

    row = {
        "model": model,
        "ok": bool(primary and primary.ok),
        "error_kind": None,
        "error": "",
        "status": primary.status if primary else None,
        "ttft_ms": None,
        "total_ms": None,
        "output_tokens": None,
        "tps": None,
        "content": "",
        "usage": None,
        "finish_reason": None,
        "stream_supported": bool(stream_result and stream_result.ok),
        "non_stream_supported": bool(plain_result and plain_result.ok),
        "stream_used": bool(primary and primary.requested_stream),
        "content_filtered": False,
        "rate_limited": False,
    }
    if primary is not None:
        row.update({
            "status": primary.status,
            "ttft_ms": primary.ttft_ms,
            "total_ms": primary.total_ms,
            "output_tokens": primary.output_tokens,
            "tps": primary.tps,
            "content": primary.content,
            "usage": primary.usage,
            "finish_reason": primary.finish_reason,
            "content_filtered": primary.content_filtered,
            "rate_limited": primary.rate_limited,
            "tokens_estimated": primary.extra.get("tokens_estimated"),
        })
    if not row["ok"]:
        error_source = stream_result if (stream_result and not stream_result.ok) else plain_result
        if error_source is not None:
            row["error_kind"] = error_source.error_kind
            row["error"] = error_source.error_message
            row["status"] = error_source.status
            row["rate_limited"] = error_source.rate_limited
            row["content_filtered"] = error_source.content_filtered
        else:
            row["error_kind"] = "unknown"
            row["error"] = "未知错误"
    elif row["ttft_ms"] is None and row["stream_supported"] is False and stream_result is not None:
        row["error"] = "（该模型不支持流式输出，仅记录非流式指标）"
    return row


def stability_test_task(ctx, client, model, count=10, concurrency=1, timeout=60,
                        prompt="请回复：测试", max_tokens=32, temperature=0.7, stream=False):
    """稳定性测试：按并发数连续发送请求，统计成功率与错误类型分布。"""
    count = max(1, int(count))
    concurrency = max(1, int(concurrency))
    results = [None] * count
    ctx.log("开始稳定性测试：模型=%s，次数=%d，并发=%d，超时=%.0fs" % (model, count, concurrency, timeout))

    def one(index):
        ctx.check()
        outcome = client.chat_completion(
            model, prompt, max_tokens=max_tokens, temperature=temperature,
            stream=stream, timeout=timeout)
        row = outcome.to_dict()
        row["index"] = index + 1
        row["timeout"] = outcome.error_kind == KIND_TIMEOUT
        row["error_label"] = KIND_LABELS.get(outcome.error_kind, "") if not outcome.ok else ""
        row.pop("content", None)  # 稳定性测试不需要保留正文，节省内存
        return index, row

    done = 0
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(one, i) for i in range(count)]
        for future in futures:
            try:
                index, row = future.result()
            except ApiError as exc:
                if ctx.cancelled:
                    break
                index = done
                row = {"index": index + 1, "model": model, "ok": False, "error_kind": exc.kind,
                       "error": exc.message, "status": exc.status, "total_ms": None,
                       "timeout": exc.kind == KIND_TIMEOUT, "rate_limited": exc.kind == "rate_limit",
                       "content_filtered": exc.kind == "content_filter"}
            except Exception as exc:
                if ctx.cancelled:
                    break
                index = done
                row = {"index": index + 1, "model": model, "ok": False, "error_kind": "unknown",
                       "error": str(exc), "status": None, "total_ms": None, "timeout": False}
            results[index] = row
            done += 1
            ctx.step(done, count, "已完成 %d/%d 次请求" % (done, count))
            if row.get("ok"):
                ctx.log("第 %d 次：成功 %.0f ms" % (row["index"], row.get("total_ms") or 0.0))
            else:
                ctx.log("第 %d 次：失败 —— %s" % (row["index"], row.get("error") or ""))
        ctx.check()

    results = [r for r in results if r]
    summary = stats.summarize_stability(results)
    ctx.log("稳定性测试完成：成功率 %.1f%%%s%s" % (
        summary["success_rate"],
        "，触发限流" if summary["rate_limited"] else "",
        "，触发内容审核" if summary["content_filtered"] else ""))
    return {
        "results": results,
        "summary": summary,
        "config": {
            "model": model, "count": count, "concurrency": concurrency, "timeout": timeout,
            "prompt": prompt, "max_tokens": max_tokens, "temperature": temperature, "stream": stream,
        },
    }
