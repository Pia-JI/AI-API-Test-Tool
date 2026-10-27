"""功能页面：网络延迟与稳定性测试。"""

from PyQt5.QtWidgets import (
    QGroupBox, QHBoxLayout, QPushButton, QTableWidgetItem, QWidget,
)

from ... import report as report_mod
from ...api_client import KIND_LABELS
from ...tasks import latency_test_task
from ...workers import Worker
from ..widgets import common
from ..widgets.chart import BarChart
from ..widgets.model_selector import ModelSelector
from ..widgets.stat_card import StatBoard
from .base import BasePage

TARGET_MODELS = "轻量请求（/models）"
TARGET_CHAT = "对话接口（/chat/completions）"


class LatencyPage(BasePage):
    title = "延迟测试"
    description = "连续向 API 发送多次轻量请求，统计平均 / 最小 / 最大延迟以及 P50、P90、P95、P99 分位值与成功率。"

    def _build(self):
        super(LatencyPage, self)._build()
        self.root.addWidget(common.page_header(self.title, self.description))

        # ---------------------------------------------------------- 参数
        params = QGroupBox("测试参数")
        form = common.new_form(margins=(10, 6, 10, 6))
        self.count_spin = common.SpinBox()
        self.count_spin.setRange(1, 500)
        self.count_spin.setValue(int(self.ctx.config.setting("latency_count", 10)))
        self.concurrent_spin = common.SpinBox()
        self.concurrent_spin.setRange(1, 50)
        self.concurrent_spin.setValue(int(self.ctx.config.setting("latency_concurrency", 1)))
        self.timeout_spin = common.SpinBox()
        self.timeout_spin.setRange(1, 600)
        self.timeout_spin.setSuffix(" 秒")
        self.timeout_spin.setValue(int(self.ctx.config.setting("latency_timeout", 30)))
        self.target_combo = common.ComboBox()
        self.target_combo.addItems([TARGET_MODELS, TARGET_CHAT])
        if self.ctx.config.setting("latency_target", "models") == "chat":
            self.target_combo.setCurrentIndex(1)
        self.model_selector = ModelSelector(self.ctx)
        common.form_row(form, "测试次数", self.count_spin, "建议 10 次以上")
        common.form_row(form, "并发数", self.concurrent_spin, "1 表示串行，越大越接近压测")
        common.form_row(form, "超时时间", self.timeout_spin)
        common.form_row(form, "请求目标", self.target_combo, "轻量请求几乎不消耗额度")
        common.form_row(form, "对话模型", self.model_selector, "仅「对话接口」模式使用，可下拉选择或手动输入")
        params.setLayout(form)

        buttons = QWidget()
        row = QHBoxLayout(buttons)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.start_button = QPushButton("开始测试")
        self.start_button.setProperty("role", "primary")
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setEnabled(False)
        self.report_button = QPushButton("生成并导出报告")
        self.report_button.setEnabled(False)
        self.report_button.setToolTip("测试完成后可把结果导出为 JSON / CSV / Markdown")
        row.addWidget(self.start_button)
        row.addWidget(self.cancel_button)
        row.addWidget(self.report_button)
        row.addStretch(1)

        self.root.addWidget(params)
        self.root.addWidget(buttons)

        # ---------------------------------------------------------- 统计
        self.board = StatBoard([
            ("avg", "平均延迟", " ms"), ("min", "最小延迟", " ms"), ("max", "最大延迟", " ms"),
            ("p50", "P50", " ms"), ("p90", "P90", " ms"), ("p95", "P95", " ms"),
            ("p99", "P99", " ms"), ("rate", "成功率", "%"), ("failed", "失败次数", ""),
            ("timeouts", "超时次数", ""), ("std", "波动(标准差)", " ms"), ("total", "请求总数", ""),
        ], columns=6)
        self.root.addWidget(self.board)

        self.chart = BarChart(min_height=180)
        self.chart.set_data([], title="每次请求耗时（ms）")
        self.root.addWidget(self.chart)

        self.table = common.make_table(["序号", "耗时(ms)", "HTTP 状态", "结果", "错误类型", "错误信息"])
        self.table.setMinimumHeight(160)
        self.root.addWidget(self.table, 1)

        self._last = None

    def _bind(self):
        self.start_button.clicked.connect(self.start_test)
        self.cancel_button.clicked.connect(self.ctx.cancel)
        self.report_button.clicked.connect(self.export_last_report)
        self.target_combo.currentIndexChanged.connect(self._sync_target)
        self.ctx.models_changed.connect(self._sync_models)
        self.ctx.busy_changed.connect(self._sync_busy)
        self._sync_target()
        self._sync_models(self.ctx.models)

    # ------------------------------------------------------------ 界面联动
    def _sync_target(self):
        is_chat = self.target_combo.currentIndex() == 1
        self.model_selector.setToolTip(
            "选择要测试的模型；当前请求目标为%s，仅「对话接口」模式会用到模型"
            % ("对话接口" if is_chat else "轻量请求")
        )
        if is_chat and not self.model_selector.current() and self.ctx.models:
            self.model_selector.set_current(self.ctx.models[0].get("id", ""))

    def _sync_models(self, models):
        self.model_selector.set_models([m.get("id", "") for m in models])

    def _sync_busy(self, busy):
        self.start_button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)

    # ------------------------------------------------------------ 测试
    def start_test(self):
        client = self.ctx.require_client()
        if client is None:
            self.warn("请先在顶部配置区填写 API 地址与 API Key，并点击「保存配置」。")
            return
        target = "chat" if self.target_combo.currentIndex() == 1 else "models"
        model = self.model_selector.current()
        if target == "chat" and not model:
            self.warn("使用「对话接口」模式时，请先填写或选择模型名称。")
            return

        count = self.count_spin.value()
        concurrency = self.concurrent_spin.value()
        timeout = self.timeout_spin.value()
        self.ctx.config.update_settings(
            latency_count=count, latency_concurrency=concurrency,
            latency_timeout=timeout, latency_target=target,
        )
        self.table.setRowCount(0)
        self.board.reset()
        self.chart.set_data([], title="每次请求耗时（ms）")
        self.report_button.setEnabled(False)

        worker = Worker(latency_test_task, client, count=count, concurrency=concurrency,
                        timeout=timeout, target=target, model=model or None)
        self.ctx.run(worker, on_success=lambda r: self._on_done(r, client, target, model,
                                                               count, concurrency, timeout),
                     name="延迟测试")

    def _on_done(self, result, client, target, model, count, concurrency, timeout):
        samples = result.get("samples") or []
        summary = result.get("summary") or {}
        self._fill_table(samples)
        self._fill_summary(summary)
        self.chart.set_data(
            [("第%d次" % s["index"], s.get("latency_ms")) for s in samples if s.get("ok")],
            unit="ms", title="每次请求耗时（ms）",
        )
        config = {
            "测试次数": count, "并发数": concurrency, "超时时间(秒)": timeout,
            "请求目标": "/models" if target == "models" else "/chat/completions",
            "对话模型": model or "-",
        }
        self._last = report_mod.build_latency_report(client.base_url, config, samples, summary)
        self.report_button.setEnabled(True)
        if self.ctx.config.setting("auto_save_report", True):
            self.save_report(self._last)
        client.close()

    def _fill_summary(self, summary):
        self.board.set_values({
            "avg": summary.get("avg_ms"), "min": summary.get("min_ms"), "max": summary.get("max_ms"),
            "p50": summary.get("p50_ms"), "p90": summary.get("p90_ms"), "p95": summary.get("p95_ms"),
            "p99": summary.get("p99_ms"), "rate": summary.get("success_rate"),
            "failed": summary.get("failed"), "timeouts": summary.get("timeouts"),
            "std": summary.get("std_ms"), "total": summary.get("total"),
        }, roles={"rate": "ok" if (summary.get("success_rate") or 0) >= 99 else "warn"})

    def _fill_table(self, samples):
        self.table.setRowCount(0)
        for sample in samples:
            row = self.table.rowCount()
            self.table.insertRow(row)
            ok = sample.get("ok")
            values = [
                sample.get("index"),
                sample.get("latency_ms"),
                sample.get("status") or "-",
                "成功" if ok else "失败",
                KIND_LABELS.get(sample.get("error_kind"), "") if not ok else "",
                sample.get("error") or "",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem("-" if value is None else str(value))
                item.setToolTip(str(value))
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()

    def export_last_report(self):
        if not self._last:
            self.info("请先完成一次延迟测试。")
            return
        self.export_report_dialog(self._last, "导出延迟测试报告")
