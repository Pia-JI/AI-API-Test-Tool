"""功能页面：模型速度测试。"""

import json

from PyQt5.QtWidgets import (
    QCheckBox, QGroupBox, QHBoxLayout, QPlainTextEdit, QPushButton,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ... import report as report_mod
from ...api_client import KIND_LABELS
from ...tasks import speed_test_task
from ...workers import Worker
from ..widgets import common
from ..widgets.chart import BarChart
from ..widgets.model_selector import ModelMultiSelector
from ..widgets.stat_card import StatBoard
from .base import BasePage

DEFAULT_PROMPT = "请用一句话介绍人工智能。"


class SpeedTestPage(BasePage):
    title = "模型速度测试"
    description = "对选中的模型发送固定的测试 Prompt，记录首 Token 时间、完整响应时间、输出 Token 数、每秒输出速度，以及是否支持流式 / 非流式输出。"

    def _build(self):
        super(SpeedTestPage, self)._build()
        self.root.addWidget(common.page_header(self.title, self.description))

        # ---------------------------------------------------------- 参数
        params = QGroupBox("测试参数")
        form = common.new_form(margins=(10, 6, 10, 6))
        self.prompt_edit = QPlainTextEdit(self.ctx.config.setting("speed_prompt", DEFAULT_PROMPT))
        self.prompt_edit.setFixedHeight(64)
        self.max_tokens_spin = common.SpinBox()
        self.max_tokens_spin.setRange(1, 32768)
        self.max_tokens_spin.setValue(int(self.ctx.config.setting("speed_max_tokens", 256)))
        self.temperature_spin = common.DoubleSpinBox()
        self.temperature_spin.setRange(0.0, 2.0)
        self.temperature_spin.setSingleStep(0.1)
        self.temperature_spin.setDecimals(2)
        self.temperature_spin.setValue(float(self.ctx.config.setting("speed_temperature", 0.7)))
        self.timeout_spin = common.SpinBox()
        self.timeout_spin.setRange(5, 900)
        self.timeout_spin.setSuffix(" 秒")
        self.timeout_spin.setValue(int(self.ctx.config.setting("timeout", 60)))
        self.stream_check = QCheckBox("优先使用流式输出（可测得首 Token 时间）")
        self.stream_check.setChecked(bool(self.ctx.config.setting("speed_stream", True)))
        self.both_check = QCheckBox("同时探测非流式输出")
        self.both_check.setChecked(True)
        common.form_row(form, "测试 Prompt", self.prompt_edit)
        common.form_row(form, "max_tokens", self.max_tokens_spin)
        common.form_row(form, "temperature", self.temperature_spin)
        common.form_row(form, "超时时间", self.timeout_spin)
        common.form_row(form, "输出方式", self.stream_check)
        common.form_row(form, "补充探测", self.both_check)
        params.setLayout(form)

        # ---------------------------------------------------------- 模型选择
        models_box = QGroupBox("选择模型（下拉多选）")
        models_layout = QVBoxLayout(models_box)
        models_layout.setContentsMargins(10, 6, 10, 8)
        models_layout.setSpacing(4)
        self.model_selector = ModelMultiSelector(self.ctx)
        models_layout.addWidget(self.model_selector)
        models_layout.addWidget(common.label(
            "点击「选择模型」展开下拉菜单勾选（支持全选 / 全不选）；"
            "接口未提供的模型可在菜单底部手动输入添加。", role="hint", wrap=True))

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
        self.root.addWidget(models_box)
        self.root.addWidget(buttons)

        # ---------------------------------------------------------- 结果
        self.board = StatBoard([
            ("models", "测试模型数", ""), ("success", "成功", ""), ("ttft", "平均首Token", " ms"),
            ("total", "平均响应时长", " ms"), ("tps", "平均速度", " tok/s"), ("best", "最快速度", " tok/s"),
            ("tokens", "平均输出Token", ""), ("stream", "支持流式", " 个"),
        ], columns=4)
        self.root.addWidget(self.board)

        self.chart = BarChart(min_height=200)
        self.chart.set_data([], title="各模型输出速度（tok/s）")
        self.root.addWidget(self.chart)

        self.table = common.make_table([
            "模型", "结果", "首Token(ms)", "总时长(ms)", "输出Token", "tok/s", "流式", "非流式", "错误",
        ])
        self.table.setMinimumHeight(150)
        self.table.itemSelectionChanged.connect(self._show_detail)
        self.root.addWidget(self.table, 1)

        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setFixedHeight(120)
        self.detail.setPlaceholderText("点击表格中的某一行，可查看模型返回内容与用量信息…")
        self.root.addWidget(common.label("返回内容与用量", role="cardTitle"))
        self.root.addWidget(self.detail)

        self._rows = []
        self._last = None

    def _bind(self):
        self.start_button.clicked.connect(self.start_test)
        self.cancel_button.clicked.connect(self.ctx.cancel)
        self.report_button.clicked.connect(self.export_last_report)
        self.ctx.models_changed.connect(lambda _models: self._reload_models())
        self.ctx.busy_changed.connect(self._sync_busy)

    def on_show(self):
        self._reload_models()

    # ------------------------------------------------------------ 模型列表
    def _reload_models(self):
        """把「模型列表」页面获取到的模型同步到下拉框。"""
        self.model_selector.set_models(self.ctx.model_ids())

    def checked_models(self):
        return self.model_selector.selected()

    def _sync_busy(self, busy):
        self.start_button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)

    # ------------------------------------------------------------ 测试
    def start_test(self):
        client = self.ctx.require_client()
        if client is None:
            self.warn("请先在顶部配置区填写 API 地址与 API Key，并点击「保存配置」。")
            return
        models = self.checked_models()
        if not models:
            self.warn("请至少勾选一个模型（也可以手动添加模型名）。")
            return
        prompt = self.prompt_edit.toPlainText().strip() or DEFAULT_PROMPT
        max_tokens = self.max_tokens_spin.value()
        temperature = self.temperature_spin.value()
        timeout = self.timeout_spin.value()
        stream = self.stream_check.isChecked()
        both = self.both_check.isChecked()
        self.ctx.config.update_settings(
            speed_prompt=prompt, speed_max_tokens=max_tokens,
            speed_temperature=temperature, speed_stream=stream, timeout=timeout,
        )
        self.table.setRowCount(0)
        self.board.reset()
        self.chart.set_data([], title="各模型输出速度（tok/s）")
        self.detail.clear()
        self.report_button.setEnabled(False)
        self._rows = []

        worker = Worker(speed_test_task, client, models, prompt, max_tokens=max_tokens,
                        temperature=temperature, timeout=timeout, stream=stream, test_both=both)
        self.ctx.run(worker, on_success=lambda r: self._on_done(
            r, client, {"prompt": prompt, "max_tokens": max_tokens, "temperature": temperature,
                        "timeout": timeout, "stream": stream, "test_both": both}),
            name="模型速度测试")

    def _on_done(self, result, client, config):
        rows = result.get("results") or []
        summary = result.get("summary") or {}
        self._rows = rows
        self._fill_table(rows)
        self._fill_summary(summary)
        self.chart.set_data(
            [(row["model"], row.get("tps")) for row in rows if row.get("ok")],
            unit="", title="各模型输出速度（tok/s）",
        )
        display_config = {
            "测试 Prompt": config["prompt"], "max_tokens": config["max_tokens"],
            "temperature": config["temperature"], "超时时间(秒)": config["timeout"],
            "优先流式": "是" if config["stream"] else "否",
            "同时探测非流式": "是" if config["test_both"] else "否",
        }
        self._last = report_mod.build_speed_report(client.base_url, display_config, rows, summary)
        self.report_button.setEnabled(True)
        if self.ctx.config.setting("auto_save_report", True):
            self.save_report(self._last)
        client.close()

    def _fill_summary(self, summary):
        self.board.set_values({
            "models": summary.get("model_count"), "success": summary.get("success"),
            "ttft": summary.get("avg_ttft_ms"), "total": summary.get("avg_total_ms"),
            "tps": summary.get("avg_tps"), "best": summary.get("max_tps"),
            "tokens": summary.get("avg_output_tokens"), "stream": summary.get("stream_supported"),
        })

    def _fill_table(self, rows):
        self.table.setRowCount(0)
        for row_data in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            ok = row_data.get("ok")
            error_text = row_data.get("error") or ""
            if not ok and row_data.get("error_kind"):
                error_text = "%s：%s" % (KIND_LABELS.get(row_data["error_kind"], ""), error_text)
            values = [
                row_data.get("model"), "成功" if ok else "失败",
                row_data.get("ttft_ms"), row_data.get("total_ms"), row_data.get("output_tokens"),
                row_data.get("tps"),
                "是" if row_data.get("stream_supported") else "否",
                "是" if row_data.get("non_stream_supported") else "否",
                error_text,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem("-" if value in (None, "") else str(value))
                item.setToolTip(str(value))
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()

    def _show_detail(self):
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows or not self._rows:
            return
        index = rows[0].row()
        if index >= len(self._rows):
            return
        row_data = self._rows[index]
        usage = row_data.get("usage")
        if isinstance(usage, dict):
            usage_text = json.dumps(usage, ensure_ascii=False)
        else:
            usage_text = "接口未返回用量信息（Token 数为估算值）"
        lines = [
            "模型：%s        状态：%s        完成原因：%s" % (
                row_data.get("model"), "成功" if row_data.get("ok") else "失败",
                row_data.get("finish_reason") or "-"),
            "首 Token：%s ms    完整响应：%s ms    输出 Token：%s    速度：%s tok/s" % (
                row_data.get("ttft_ms"), row_data.get("total_ms"),
                row_data.get("output_tokens"), row_data.get("tps")),
            "用量信息：%s" % usage_text,
            "返回内容：",
            (row_data.get("content") or "").strip() or "（无内容）",
        ]
        self.detail.setPlainText("\n".join(lines))

    def export_last_report(self):
        if not self._last:
            self.info("请先完成一次速度测试。")
            return
        self.export_report_dialog(self._last, "导出模型速度测试报告")
