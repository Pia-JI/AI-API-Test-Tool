"""测试报告的结构化生成与导出（JSON / CSV / Markdown）。

统一的报告结构：
    {
      "kind": "latency",            # models / latency / speed / stability
      "title": "...",
      "created_at": "...",
      "api_url": "...",
      "models": [...],
      "config": {...},              # 本次测试使用的参数
      "summary": {...},             # 统计结果
      "summary_text": "...",        # 一行摘要，用于历史列表
      "rows": [...],                # 明细数据
      "errors": [...]               # 错误详情
    }
"""

import csv
import io
import json
import os
import time

from .stats import TIMEOUT_KIND
from .api_client import KIND_LABELS

KIND_TITLES = {
    "models": "模型列表",
    "latency": "延迟测试",
    "speed": "模型速度测试",
    "stability": "稳定性测试",
}


def _now_text():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _num(value, suffix=""):
    return "-" if value is None else "%s%s" % (value, suffix)


def _kind_label(kind):
    return KIND_LABELS.get(kind, kind or "-")


# ------------------------------------------------------------------ 报告构造
def build_latency_report(api_url, config, samples, summary):
    title = "延迟测试报告 @ %s" % (api_url or "-")
    return {
        "kind": "latency",
        "title": title,
        "created_at": _now_text(),
        "api_url": api_url,
        "models": [],
        "config": config,
        "summary": summary,
        "summary_text": "平均 %.0fms / P95 %.0fms / 成功率 %.1f%%（%d 次）" % (
            summary.get("avg_ms") or 0.0,
            summary.get("p95_ms") or 0.0,
            summary.get("success_rate") or 0.0,
            summary.get("total") or 0,
        ),
        "rows": samples,
        "errors": [s for s in samples if not s.get("ok")],
    }


def build_speed_report(api_url, config, results, summary):
    models = [r.get("model") for r in results]
    return {
        "kind": "speed",
        "title": "模型速度测试报告 @ %s" % (api_url or "-"),
        "created_at": _now_text(),
        "api_url": api_url,
        "models": models,
        "config": config,
        "summary": summary,
        "summary_text": "成功 %d/%d，平均 TTFT %s，平均速度 %s tok/s" % (
            summary.get("success") or 0,
            summary.get("model_count") or 0,
            _num(summary.get("avg_ttft_ms"), "ms"),
            _num(summary.get("avg_tps")),
        ),
        "rows": results,
        "errors": [r for r in results if not r.get("ok")],
    }


def build_stability_report(api_url, config, results, summary):
    return {
        "kind": "stability",
        "title": "稳定性测试报告 @ %s" % (api_url or "-"),
        "created_at": _now_text(),
        "api_url": api_url,
        "models": [config.get("model")] if config.get("model") else [],
        "config": config,
        "summary": summary,
        "summary_text": "成功率 %.1f%%，平均 %s，P95 %s，限流 %s" % (
            summary.get("success_rate") or 0.0,
            _num(summary.get("avg_ms"), "ms"),
            _num(summary.get("p95_ms"), "ms"),
            "是" if summary.get("rate_limited") else "否",
        ),
        "rows": results,
        "errors": [r for r in results if not r.get("ok")],
    }


def build_models_report(api_url, models):
    return {
        "kind": "models",
        "title": "模型列表 @ %s" % (api_url or "-"),
        "created_at": _now_text(),
        "api_url": api_url,
        "models": [m.get("id") for m in models],
        "config": {},
        "summary": {"total": len(models)},
        "summary_text": "共 %d 个模型" % len(models),
        "rows": [
            {
                "id": m.get("id"),
                "owned_by": m.get("owned_by"),
                "created_text": m.get("created_text"),
            }
            for m in models
        ],
        "errors": [],
    }


# ------------------------------------------------------------------ JSON
def to_json(report):
    return json.dumps(report, ensure_ascii=False, indent=2)


# ------------------------------------------------------------------ Markdown
def to_markdown(report):
    kind = report.get("kind", "unknown")
    lines = []
    lines.append("# %s" % report.get("title", "测试报告"))
    lines.append("")
    lines.append("| 项目 | 内容 |")
    lines.append("| --- | --- |")
    lines.append("| 报告类型 | %s |" % KIND_TITLES.get(kind, kind))
    lines.append("| 测试时间 | %s |" % report.get("created_at", "-"))
    lines.append("| API 地址 | %s |" % (report.get("api_url") or "-"))
    models = report.get("models") or []
    if models:
        lines.append("| 模型 | %s |" % ", ".join(str(m) for m in models))
    lines.append("")
    lines.extend(_markdown_config(report.get("config") or {}))
    lines.append("## 统计结果")
    lines.append("")
    lines.extend(_markdown_summary(kind, report.get("summary") or {}))
    lines.append("")
    lines.append("## 明细")
    lines.append("")
    lines.extend(_markdown_rows(kind, report.get("rows") or []))
    lines.append("")
    lines.append("> 由 AI API 工具箱自动生成")
    return "\n".join(lines)


def _markdown_config(config):
    if not config:
        return []
    lines = ["## 测试参数", "", "| 参数 | 值 |", "| --- | --- |"]
    for key, value in config.items():
        if isinstance(value, str) and len(value) > 120:
            value = value[:120] + "…"
        lines.append("| %s | %s |" % (key, value))
    lines.append("")
    return lines


def _markdown_summary(kind, summary):
    rows = []
    if kind == "latency":
        rows = [
            ("请求次数", summary.get("total")),
            ("成功 / 失败", "%s / %s" % (summary.get("success", 0), summary.get("failed", 0))),
            ("成功率", _num(summary.get("success_rate"), "%")),
            ("平均延迟", _num(summary.get("avg_ms"), " ms")),
            ("最小 / 最大延迟", "%s / %s ms" % (_num(summary.get("min_ms")), _num(summary.get("max_ms")))),
            ("P50 / P90", "%s / %s ms" % (_num(summary.get("p50_ms")), _num(summary.get("p90_ms")))),
            ("P95 / P99", "%s / %s ms" % (_num(summary.get("p95_ms")), _num(summary.get("p99_ms")))),
            ("波动（标准差）", _num(summary.get("std_ms"), " ms")),
            ("超时次数", summary.get("timeouts")),
        ]
    elif kind == "speed":
        rows = [
            ("测试模型数", summary.get("model_count")),
            ("成功 / 失败", "%s / %s" % (summary.get("success", 0), summary.get("failed", 0))),
            ("平均首 Token 时间", _num(summary.get("avg_ttft_ms"), " ms")),
            ("平均完整响应时间", _num(summary.get("avg_total_ms"), " ms")),
            ("平均输出速度", _num(summary.get("avg_tps"), " tok/s")),
            ("最快 / 最慢", "%s / %s tok/s" % (_num(summary.get("max_tps")), _num(summary.get("min_tps")))),
            ("平均输出 Token", summary.get("avg_output_tokens")),
            ("支持流式 / 非流式", "%s / %s" % (summary.get("stream_supported", 0), summary.get("non_stream_supported", 0))),
        ]
    elif kind == "stability":
        rows = [
            ("总请求数", summary.get("total")),
            ("成功 / 失败", "%s / %s" % (summary.get("success", 0), summary.get("failed", 0))),
            ("成功率", _num(summary.get("success_rate"), "%")),
            ("失败率", _num(summary.get("fail_rate"), "%")),
            ("平均延迟", _num(summary.get("avg_ms"), " ms")),
            ("P50 / P95 / P99", "%s / %s / %s ms" % (
                _num(summary.get("p50_ms")), _num(summary.get("p95_ms")), _num(summary.get("p99_ms")))),
            ("是否触发限流", "是（%d 次）" % summary.get("rate_limited_count", 0) if summary.get("rate_limited") else "否"),
            ("是否触发内容审核", "是（%d 次）" % summary.get("content_filtered_count", 0) if summary.get("content_filtered") else "否"),
        ]
    elif kind == "models":
        rows = [("模型数量", summary.get("total"))]
    lines = ["| 指标 | 值 |", "| --- | --- |"]
    lines.extend("| %s | %s |" % (k, "-" if v is None else v) for k, v in rows)
    dist = summary.get("error_distribution") or {}
    if dist:
        lines.append("")
        lines.append("**错误类型分布**")
        lines.append("")
        lines.append("| 错误类型 | 次数 |")
        lines.append("| --- | --- |")
        lines.extend("| %s | %s |" % (k, v) for k, v in sorted(dist.items(), key=lambda kv: -kv[1]))
    return lines


def _markdown_rows(kind, rows):
    if not rows:
        return ["（无明细数据）"]
    lines = []
    if kind == "latency":
        lines.append("| 序号 | 耗时(ms) | HTTP | 结果 | 错误 |")
        lines.append("| --- | --- | --- | --- | --- |")
        for item in rows:
            lines.append("| %s | %s | %s | %s | %s |" % (
                item.get("index"), _num(item.get("latency_ms")), item.get("status") or "-",
                "成功" if item.get("ok") else "失败", item.get("error") or "-"))
    elif kind == "speed":
        lines.append("| 模型 | 结果 | TTFT(ms) | 总时长(ms) | 输出Token | tok/s | 流式 | 非流式 | 错误 |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for item in rows:
            lines.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
                item.get("model"), "成功" if item.get("ok") else "失败",
                _num(item.get("ttft_ms")), _num(item.get("total_ms")), _num(item.get("output_tokens")),
                _num(item.get("tps")), "是" if item.get("stream_supported") else "否",
                "是" if item.get("non_stream_supported") else "否",
                (item.get("error") or "-").replace("|", "/")))
    elif kind == "stability":
        lines.append("| 序号 | 结果 | 耗时(ms) | HTTP | 错误类型 | 错误信息 |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for item in rows:
            lines.append("| %s | %s | %s | %s | %s | %s |" % (
                item.get("index"), "成功" if item.get("ok") else "失败", _num(item.get("total_ms")),
                item.get("status") or "-", _kind_label(item.get("error_kind")),
                (item.get("error") or "-").replace("|", "/")))
    else:
        lines.append("| 模型 ID | 所属者 | 创建时间 |")
        lines.append("| --- | --- | --- |")
        for item in rows:
            lines.append("| %s | %s | %s |" % (item.get("id"), item.get("owned_by") or "-", item.get("created_text") or "-"))
    return lines


# ------------------------------------------------------------------ CSV
def to_csv(report):
    kind = report.get("kind")
    rows = report.get("rows") or []
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["# %s" % (report.get("title") or "测试报告")])
    writer.writerow(["测试时间", report.get("created_at", ""), "API 地址", report.get("api_url", "")])
    if report.get("models"):
        writer.writerow(["模型", ", ".join(str(m) for m in report["models"])])
    writer.writerow([])
    if kind == "latency":
        writer.writerow(["序号", "耗时(ms)", "HTTP状态", "是否成功", "错误类型", "错误信息"])
        for item in rows:
            writer.writerow([item.get("index"), item.get("latency_ms"), item.get("status"),
                             "成功" if item.get("ok") else "失败",
                             _kind_label(item.get("error_kind")) if not item.get("ok") else "",
                             item.get("error") or ""])
    elif kind == "speed":
        writer.writerow(["模型", "是否成功", "首Token时间(ms)", "完整响应时间(ms)", "输出Token数",
                         "每秒Token数", "支持流式", "支持非流式", "完成原因", "错误"])
        for item in rows:
            writer.writerow([item.get("model"), "成功" if item.get("ok") else "失败",
                             item.get("ttft_ms"), item.get("total_ms"), item.get("output_tokens"),
                             item.get("tps"), "是" if item.get("stream_supported") else "否",
                             "是" if item.get("non_stream_supported") else "否",
                             item.get("finish_reason") or "", item.get("error") or ""])
    elif kind == "stability":
        writer.writerow(["序号", "是否成功", "耗时(ms)", "HTTP状态", "错误类型", "错误信息", "触发限流", "触发内容审核"])
        for item in rows:
            writer.writerow([item.get("index"), "成功" if item.get("ok") else "失败", item.get("total_ms"),
                             item.get("status"), _kind_label(item.get("error_kind")),
                             item.get("error") or "", "是" if item.get("rate_limited") else "否",
                             "是" if item.get("content_filtered") else "否"])
    else:
        writer.writerow(["模型 ID", "所属者", "创建时间"])
        for item in rows:
            writer.writerow([item.get("id"), item.get("owned_by") or "", item.get("created_text") or ""])
    return buffer.getvalue()


# ------------------------------------------------------------------ 导出
EXPORTERS = {
    "json": (to_json, "json"),
    "md": (to_markdown, "md"),
    "markdown": (to_markdown, "md"),
    "csv": (to_csv, "csv"),
}


def default_filename(report, ext):
    """生成默认文件名，例如 20261008-133000_延迟测试报告.json。"""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    kind = KIND_TITLES.get(report.get("kind"), "报告")
    return "%s_%s.%s" % (stamp, kind, ext)


def export_report(report, file_path, fmt=None):
    """按扩展名（或指定格式）导出报告，返回实际写入路径。"""
    ext = (fmt or os.path.splitext(file_path)[1].lstrip(".") or "json").lower()
    if ext not in EXPORTERS:
        raise ValueError("不支持的导出格式：%s（可选 json / csv / md）" % ext)
    func, _ = EXPORTERS[ext]
    text = func(report)
    directory = os.path.dirname(os.path.abspath(file_path))
    if directory and not os.path.isdir(directory):
        os.makedirs(directory, exist_ok=True)
    with open(file_path, "w", encoding="utf-8-sig" if ext == "csv" else "utf-8", newline="") as fp:
        fp.write(text)
    return file_path


def export_all(report, directory, prefix=None):
    """同时导出三种格式，返回生成的文件路径列表。"""
    os.makedirs(directory, exist_ok=True)
    stem = prefix or os.path.splitext(default_filename(report, "json"))[0]
    paths = []
    for ext in ("json", "csv", "md"):
        target = os.path.join(directory, "%s.%s" % (stem, ext))
        paths.append(export_report(report, target))
    return paths


def is_timeout_row(row):
    """辅助：明细行是否属于超时。"""
    return bool(row.get("timeout")) or row.get("error_kind") == TIMEOUT_KIND
