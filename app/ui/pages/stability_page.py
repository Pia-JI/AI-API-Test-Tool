"""功能页面：稳定性测试（连续 / 并发请求）。"""

from PyQt5.QtWidgets import (
    QCheckBox, QGroupBox, QHBoxLayout, QPlainTextEdit, QPushButton,
    QTableWidgetItem, QWidget,
)

from ... import report as report_mod
from ...api_client import KIND_LABELS
from ...tasks import stability_test_task
from ...workers import Worker
from ..widgets import common
from ..widgets.chart import BarChart
from ..widgets.model_selector import ModelSelector
from ..widgets.stat_card import StatBoard
from .base import BasePage

COUNT_PRESETS = ["5", "10", "20", "50"]


class StabilityPage(BasePage):
    title = "稳定性测试"
    description = "对指定模型连续（或并发）发送请求，统计成功率、失败率、延迟分位值、错误类型分布，以及是否触发限流或内容审核。"

    def _build(self):
        super(StabilityPage, self)._build()
        self.root.addWidget(common.page_header(self.title, self.description))

        params = QGroupBox("测试参数")
        form = common.new_form(margins=(10, 6, 10, 6))
        self.model_selector = ModelSelector(self.ctx)
        self.count_combo = common.ComboBox()
        self.count_combo.setEditable(True)
        self.count_combo.addItems(COUNT_PRESETS)
        self.count_combo.setCurrentText(str(int(self.ctx.config.setting("stability_count", 10))))
        self.concurrent_spin = common.SpinBox()
        self.concurrent_spin.setRange(1, 50)
        self.concurrent_spin.setValue(int(self.ctx.config.setting("stability_concurrency", 1)))
        self.timeout_spin = common.SpinBox()
        self.timeout_spin.setRange(1, 900)
        self.timeout_spin.setSuffix(" 秒")
        self.timeout_spin.setValue(int(self.ctx.config.setting("stability_timeout", 60)))
        self.prompt_edit = QPlainTextEdit(self.ctx.config.setting("stability_prompt", "请回复：测试"))
        self.prompt_edit.setFixedHeight(56)
        self.max_tokens_spin = common.SpinBox()
        self.max_tokens_spin.setRange(1, 32768)
        self.max_tokens_spin.setValue(int(self.ctx.config.setting("stability_max_tokens", 32)))
        self.stream_check = QCheckBox("使用流式输出")
        self.stream_check.setChecked(bool(self.ctx.config.setting("stability_stream", False)))
        common.form_row(form, "测试模型", self.model_selector, "下拉选择已获取的模型，也可手动输入")
        common.form_row(form, "测试次数", self.count_combo, "5 / 10 / 20 / 50 次")
        common.form_row(form, "并发数", self.concurrent_spin, "1 为串行")
        common.form_row(form, "超时时间", self.timeout_spin)
        common.form_row(form, "测试 Prompt", self.prompt_edit)
        common.form_row(form, "max_tokens", self.max_tokens_spin)
        common.form_row(form, "输出方式", self.stream_check)
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
        row.addWidget(self.start_button)
        row.addWidget(self.cancel_button)
        row.addWidget(self.report_button)
        row.addStretch(1)

        self.root.addWidget(params)
        self.root.addWidget(buttons)

        self.board = StatBoard([
            ("rate", "成功率", "%"), ("fail_rate", "失败率", "%"), ("avg", "平均延迟", " ms"),
            ("p50", "P50", " ms"), ("p95", "P95", " ms"), ("p99", "P99", " ms"),
            ("success", "成功次数", ""), ("failed", "失败次数", ""), ("total", "总请求数", ""),
            ("limit", "触发限流", ""), ("filter", "触发内容审核", ""), ("max", "最大延迟", " ms"),
        ], columns=6)
        self.root.addWidget(self.board)

        charts = QWidget()
        chart_row = QHBoxLayout(charts)
        chart_row.setContentsMargins(0, 0, 0, 0)
        chart_row.setSpacing(10)
        self.latency_chart = BarChart(min_height=200)
        self.latency_chart.set_data([], title="每次请求耗时（ms）")
        self.error_chart = BarChart(min_height=200)
        self.error_chart.set_data([], title="错误类型分布", color_key="error")
        chart_row.addWidget(self.latency_chart, 1)
        chart_row.addWidget(self.error_chart, 1)
        self.root.addWidget(charts)

        self.dist_table = common.make_table(["错误类型", "次数", "占比"], stretch_column=0)
        self.dist_table.setMaximumHeight(130)
        self.table = common.make_table(["序号", "结果", "耗时(ms)", "HTTP", "错误类型", "错误信息"])
        self.table.setMinimumHeight(130)
        tables = QWidget()
        table_row = QHBoxLayout(tables)
        table_row.setContentsMargins(0, 0, 0, 0)
        table_row.setSpacing(10)
        table_row.addWidget(self.table, 3)
        table_row.addWidget(self.dist_table, 2)
        self.root.addWidget(tables, 1)

        self._last = None

    def _bind(self):
        self.start_button.clicked.connect(self.start_test)
        self.cancel_button.clicked.connect(self.ctx.cancel)
        self.report_button.clicked.connect(self.export_last_report)
        self.ctx.models_changed.connect(self._sync_models)
        self.ctx.busy_changed.connect(self._sync_busy)
        self._sync_models(self.ctx.models)

    # ------------------------------------------------------------ 界面联动
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
        model = self.model_selector.current()
        if not model:
            self.warn("请选择或填写要测试的模型名称。")
            return
        try:
            count = max(1, int(float(self.count_combo.currentText().strip() or "10")))
        except ValueError:
            self.warn("测试次数必须是数字，例如 10。")
            return
        concurrency = self.concurrent_spin.value()
        timeout = self.timeout_spin.value()
        prompt = self.prompt_edit.toPlainText().strip() or "请回复：测试"
        max_tokens = self.max_tokens_spin.value()
        stream = self.stream_check.isChecked()
        self.ctx.config.update_settings(
            stability_count=count, stability_concurrency=concurrency, stability_timeout=timeout,
            stability_prompt=prompt, stability_max_tokens=max_tokens, stability_stream=stream,
        )
        self.table.setRowCount(0)
        self.dist_table.setRowCount(0)
        self.board.reset()
        self.latency_chart.set_data([], title="每次请求耗时（ms）")
        self.error_chart.set_data([], title="错误类型分布", color_key="error")
        self.report_button.setEnabled(False)

        worker = Worker(stability_test_task, client, model, count=count, concurrency=concurrency,
                        timeout=timeout, prompt=prompt, max_tokens=max_tokens, stream=stream)
        self.ctx.run(worker, on_success=lambda r: self._on_done(r, client), name="稳定性测试")

    def _on_done(self, result, client):
        rows = result.get("results") or []
        summary = result.get("summary") or {}
        config = result.get("config") or {}
        self._fill_table(rows)
        self._fill_summary(summary)
        self._fill_distribution(summary)
        self.latency_chart.set_data(
            [("第%d次" % r["index"], r.get("total_ms")) for r in rows if r.get("ok")],
            unit="ms", title="每次请求耗时（ms）",
        )
        self.error_chart.set_data(
            list((summary.get("error_distribution") or {}).items()),
            title="错误类型分布", color_key="error",
        )
        display_config = {
            "模型": config.get("model"), "测试次数": config.get("count"),
            "并发数": config.get("concurrency"), "超时时间(秒)": config.get("timeout"),
            "Prompt": config.get("prompt"), "max_tokens": config.get("max_tokens"),
            "流式": "是" if config.get("stream") else "否",
        }
        self._last = report_mod.build_stability_report(client.base_url, display_config, rows, summary)
        self.report_button.setEnabled(True)
        if self.ctx.config.setting("auto_save_report", True):
            self.save_report(self._last)
        client.close()

    def _fill_summary(self, summary):
        self.board.set_values({
            "rate": summary.get("success_rate"), "fail_rate": summary.get("fail_rate"),
            "avg": summary.get("avg_ms"), "p50": summary.get("p50_ms"),
            "p95": summary.get("p95_ms"), "p99": summary.get("p99_ms"),
            "success": summary.get("success"), "failed": summary.get("failed"),
            "total": summary.get("total"), "max": summary.get("max_ms"),
            "limit": "是" if summary.get("rate_limited") else "否",
            "filter": "是" if summary.get("content_filtered") else "否",
        }, roles={
            "rate": "ok" if (summary.get("success_rate") or 0) >= 99 else "warn",
            "limit": "error" if summary.get("rate_limited") else "ok",
            "filter": "error" if summary.get("content_filtered") else "ok",
        })

    def _fill_distribution(self, summary):
        distribution = summary.get("error_distribution") or {}
        total = sum(distribution.values()) or 1
        self.dist_table.setRowCount(0)
        for label, count in sorted(distribution.items(), key=lambda kv: -kv[1]):
            row = self.dist_table.rowCount()
            self.dist_table.insertRow(row)
            values = [label, count, "%.1f%%" % (100.0 * count / total)]
            for column, value in enumerate(values):
                self.dist_table.setItem(row, column, QTableWidgetItem(str(value)))
        self.dist_table.resizeColumnsToContents()
        if not distribution:
            self.dist_table.insertRow(0)
            self.dist_table.setItem(0, 0, QTableWidgetItem("无错误"))
            self.dist_table.setItem(0, 1, QTableWidgetItem("0"))
            self.dist_table.setItem(0, 2, QTableWidgetItem("0%"))

    def _fill_table(self, rows):
        self.table.setRowCount(0)
        for row_data in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            ok = row_data.get("ok")
            values = [
                row_data.get("index"),
                "成功" if ok else "失败",
                row_data.get("total_ms"),
                row_data.get("status") or "-",
                KIND_LABELS.get(row_data.get("error_kind"), "") if not ok else "",
                row_data.get("error") or "",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem("-" if value is None else str(value))
                item.setToolTip(str(value))
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()

    def export_last_report(self):
        if not self._last:
            self.info("请先完成一次稳定性测试。")
            return
        self.export_report_dialog(self._last, "导出稳定性测试报告")
