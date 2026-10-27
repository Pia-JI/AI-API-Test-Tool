"""无界面自检：不开图形界面，直接跑一遍核心流程。

两种用法：
    1. 开发时命令行自检：python tools/self_check.py --base-url ... --api-key ...
    2. 打包后验证 exe：AI-API-Toolbox.exe --self-check --base-url ... --api-key ...

返回码 0 表示全部通过，1 表示有失败项，2 表示参数错误。
"""

import argparse
import io
import os
import sys
import time

from . import report as report_mod
from .api_client import ApiClient, ApiError
from .tasks import fetch_models_task, latency_test_task, speed_test_task, stability_test_task


class ConsoleContext(object):
    """把 TaskContext 的输出转成回调（默认打印到控制台）。"""

    def __init__(self, log=print, verbose=True):
        self.cancelled = False
        self._log = log
        self.verbose = verbose

    def log(self, message):
        if self.verbose:
            self._log("  " + str(message))

    def progress(self, percent, message=""):
        pass

    def step(self, done, total, message=""):
        pass

    def check(self):
        pass


def run_check(base_url, api_key, model="", count=3, timeout=30, proxy="",
              export_dir="", log=print, verbose=True):
    """执行一次完整自检，返回退出码。"""
    client = ApiClient(base_url, api_key, timeout=timeout, proxy=proxy)
    ctx = ConsoleContext(log=log, verbose=verbose)
    reports = []
    failed = False

    log("自检目标：%s" % client.base_url)
    log("[1/4] 获取模型列表")
    models = []
    try:
        models = fetch_models_task(ctx, client)["models"]
    except ApiError as exc:
        failed = True
        log("  失败：%s" % exc.message)
    else:
        for item in models[:20]:
            log("  - %s（%s）" % (item["id"], item["owned_by"] or "-"))
        reports.append(report_mod.build_models_report(client.base_url, models))

    model = model or (models[0]["id"] if models else "")

    log("[2/4] 延迟测试（%d 次）" % count)
    latency = latency_test_task(ctx, client, count=count, concurrency=1,
                                timeout=timeout, target="models")
    log("  平均 %s ms / P95 %s ms / 成功率 %s%%" % (
        latency["summary"].get("avg_ms"), latency["summary"].get("p95_ms"),
        latency["summary"]["success_rate"]))
    if latency["summary"]["success"] == 0:
        failed = True
    reports.append(report_mod.build_latency_report(
        client.base_url,
        {"count": count, "concurrency": 1, "timeout": timeout, "target": "models"},
        latency["samples"], latency["summary"]))

    if model:
        log("[3/4] 模型速度测试：%s" % model)
        speed = speed_test_task(ctx, client, [model], "请用一句话介绍人工智能。",
                                max_tokens=128, timeout=timeout, stream=True, test_both=True)
        for row in speed["results"]:
            if row["ok"]:
                log("  %s：首 Token %s ms，%s tok/s，支持流式=%s，支持非流式=%s" % (
                    row["model"], row["ttft_ms"], row["tps"],
                    row["stream_supported"], row["non_stream_supported"]))
            else:
                failed = True
                log("  %s：失败 —— %s" % (row["model"], row["error"]))
        reports.append(report_mod.build_speed_report(
            client.base_url, {"max_tokens": 128, "stream": True}, speed["results"], speed["summary"]))

        log("[4/4] 稳定性测试：%s（%d 次，并发 2）" % (model, count))
        stability = stability_test_task(ctx, client, model, count=count, concurrency=2,
                                        timeout=timeout, max_tokens=32)
        log("  成功率 %s%%，错误分布 %s" % (
            stability["summary"]["success_rate"], stability["summary"]["error_distribution"]))
        reports.append(report_mod.build_stability_report(
            client.base_url, stability["config"], stability["results"], stability["summary"]))
    else:
        log("[3/4][4/4] 跳过：没有可用的模型名（可用 --model 手动指定）")

    if export_dir:
        for item in reports:
            paths = report_mod.export_all(item, export_dir)
            log("已导出：%s" % paths[0])
    client.close()
    log("自检完成，共生成 %d 份报告；结果：%s" % (len(reports), "有失败项" if failed else "全部通过"))
    return 1 if failed else 0


def main(argv=None):
    """命令行入口（控制台与打包后的 exe 都可用）。"""
    parser = argparse.ArgumentParser(description="AI API 工具箱自检")
    parser.add_argument("--base-url", required=True, help="例如 https://api.openai.com/v1")
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--model", default="", help="速度 / 稳定性测试使用的模型")
    parser.add_argument("--count", type=int, default=3, help="延迟与稳定性测试次数")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--proxy", default="")
    parser.add_argument("--export-dir", default="")
    parser.add_argument("--log-file", default="", help="把自检输出写入文件（打包后无控制台时使用）")
    args = parser.parse_args(argv)

    stream = None
    if args.log_file:
        directory = os.path.dirname(os.path.abspath(args.log_file))
        if directory:
            os.makedirs(directory, exist_ok=True)
        stream = io.open(args.log_file, "w", encoding="utf-8")

    def log(message):
        text = "%s  %s" % (time.strftime("%H:%M:%S"), message)
        if stream is not None:
            stream.write(text + "\n")
            stream.flush()
        try:
            print(text)
        except Exception:
            pass

    try:
        return run_check(args.base_url, args.api_key, model=args.model, count=args.count,
                         timeout=args.timeout, proxy=args.proxy, export_dir=args.export_dir, log=log)
    finally:
        if stream is not None:
            stream.close()


if __name__ == "__main__":
    sys.exit(main())
