"""测试指标的统计计算。

包含三类统计：
    summarize_latency   网络延迟（平均 / 最小 / 最大 / P50 / P90 / P95 / P99 / 成功率）
    summarize_speed     模型速度（TTFT、输出速度、Token 用量）
    summarize_stability 稳定性（成功率、失败率、错误类型分布、限流与内容审核触发情况）
"""

import math
import statistics

TIMEOUT_KIND = "timeout"
RATE_LIMIT_KIND = "rate_limit"
CONTENT_FILTER_KIND = "content_filter"


def percentile(values, p):
    """线性插值法计算百分位数（与 numpy.percentile 默认行为一致）。"""
    data = sorted(v for v in values if v is not None)
    if not data:
        return None
    if len(data) == 1:
        return float(data[0])
    rank = (len(data) - 1) * (float(p) / 100.0)
    low = int(math.floor(rank))
    high = int(math.ceil(rank))
    if low == high:
        return float(data[low])
    return float(data[low] + (data[high] - data[low]) * (rank - low))


def _round(value, digits=2):
    return None if value is None else round(float(value), digits)


def summarize_latency(samples):
    """汇总延迟测试结果。

    samples: [{"index":1, "ok":True, "latency_ms":120.5, "status":200, "error_kind":None,
               "error":None, "timeout":False}, ...]
    """
    ok = [s for s in samples if s.get("ok")]
    latencies = [s.get("latency_ms") for s in ok if s.get("latency_ms") is not None]
    failed = [s for s in samples if not s.get("ok")]
    timeouts = [s for s in samples if s.get("timeout") or s.get("error_kind") == TIMEOUT_KIND]
    total = len(samples)
    return {
        "total": total,
        "success": len(ok),
        "failed": len(failed),
        "timeouts": len(timeouts),
        "success_rate": _round(100.0 * len(ok) / total, 2) if total else 0.0,
        "avg_ms": _round(statistics.fmean(latencies)) if latencies else None,
        "min_ms": _round(min(latencies)) if latencies else None,
        "max_ms": _round(max(latencies)) if latencies else None,
        "std_ms": _round(statistics.pstdev(latencies)) if len(latencies) > 1 else (0.0 if latencies else None),
        "p50_ms": _round(percentile(latencies, 50)),
        "p90_ms": _round(percentile(latencies, 90)),
        "p95_ms": _round(percentile(latencies, 95)),
        "p99_ms": _round(percentile(latencies, 99)),
        "error_distribution": error_distribution(failed),
    }


def summarize_speed(results):
    """汇总模型速度测试结果。

    results: [{"model":..., "ok":True, "ttft_ms":..., "total_ms":..., "output_tokens":...,
               "tps":..., "stream_supported":..., "non_stream_supported":...,
               "usage":..., "error_kind":..., "error":...}, ...]
    """
    ok = [r for r in results if r.get("ok")]
    ttfts = [r["ttft_ms"] for r in ok if r.get("ttft_ms") is not None]
    totals = [r["total_ms"] for r in ok if r.get("total_ms") is not None]
    tpss = [r["tps"] for r in ok if r.get("tps") is not None]
    tokens = [r["output_tokens"] for r in ok if r.get("output_tokens") is not None]
    return {
        "model_count": len(results),
        "success": len(ok),
        "failed": len(results) - len(ok),
        "success_rate": _round(100.0 * len(ok) / len(results), 2) if results else 0.0,
        "avg_ttft_ms": _round(statistics.fmean(ttfts)) if ttfts else None,
        "avg_total_ms": _round(statistics.fmean(totals)) if totals else None,
        "avg_tps": _round(statistics.fmean(tpss)) if tpss else None,
        "max_tps": _round(max(tpss)) if tpss else None,
        "min_tps": _round(min(tpss)) if tpss else None,
        "avg_output_tokens": _round(statistics.fmean(tokens), 1) if tokens else None,
        "stream_supported": sum(1 for r in results if r.get("stream_supported")),
        "non_stream_supported": sum(1 for r in results if r.get("non_stream_supported")),
        "error_distribution": error_distribution(results),
    }


def summarize_stability(results):
    """汇总稳定性测试结果。"""
    ok = [r for r in results if r.get("ok")]
    latencies = [r.get("total_ms") for r in ok if r.get("total_ms") is not None]
    failed = [r for r in results if not r.get("ok")]
    total = len(results)
    return {
        "total": total,
        "success": len(ok),
        "failed": len(failed),
        "success_rate": _round(100.0 * len(ok) / total, 2) if total else 0.0,
        "fail_rate": _round(100.0 * len(failed) / total, 2) if total else 0.0,
        "avg_ms": _round(statistics.fmean(latencies)) if latencies else None,
        "min_ms": _round(min(latencies)) if latencies else None,
        "max_ms": _round(max(latencies)) if latencies else None,
        "p50_ms": _round(percentile(latencies, 50)),
        "p95_ms": _round(percentile(latencies, 95)),
        "p99_ms": _round(percentile(latencies, 99)),
        "rate_limited": any(r.get("rate_limited") for r in results),
        "rate_limited_count": sum(1 for r in results if r.get("rate_limited")),
        "content_filtered": any(r.get("content_filtered") for r in results),
        "content_filtered_count": sum(1 for r in results if r.get("content_filtered")),
        "error_distribution": error_distribution(failed),
    }


def error_distribution(results):
    """统计失败请求的错误类型分布：{"429 触发限流": 2, "超时": 1, ...}"""
    from .api_client import KIND_LABELS

    counter = {}
    for item in results:
        if item.get("ok"):
            continue
        kind = item.get("error_kind") or "unknown"
        label = KIND_LABELS.get(kind, kind)
        if item.get("timeout") and kind != TIMEOUT_KIND:
            label = KIND_LABELS.get(TIMEOUT_KIND, "超时")
        status = item.get("status")
        if status:
            label = "%s %s" % (status, label)
        counter[label] = counter.get(label, 0) + 1
    return counter


def estimate_tokens(text):
    """粗略估算文本 Token 数（接口未返回 usage 时使用）。

    规则：CJK 字符约 1 Token/字，其余字符约 1 Token/4 字符。
    """
    if not text:
        return 0
    cjk = 0
    other = 0
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff" or "\u3040" <= ch <= "\u30ff" or "\uac00" <= ch <= "\ud7af":
            cjk += 1
        else:
            other += 1
    return int(cjk + math.ceil(other / 4.0))
