"""功能页面：模型列表。"""

import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QHeaderView, QLineEdit, QPushButton,
    QTableWidgetItem, QWidget,
)

from ... import paths
from ... import report as report_mod
from ..widgets import common
from .base import BasePage


class ModelsPage(BasePage):
    title = "模型列表"
    description = "调用 /models 接口获取该 API 下所有可用模型，可导出为 JSON / CSV。"

    def _build(self):
        super(ModelsPage, self)._build()
        self.root.addWidget(common.page_header(self.title, self.description))

        # ---------------------------------------------------------- 工具栏
        toolbar = QWidget()
        bar = QHBoxLayout(toolbar)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(8)
        self.fetch_button = QPushButton("获取模型列表")
        self.fetch_button.setProperty("role", "primary")
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("按模型 ID / 所属者过滤…")
        self.search_edit.setClearButtonEnabled(True)
        self.copy_button = QPushButton("复制选中 ID")
        self.export_json_button = QPushButton("导出 JSON")
        self.export_csv_button = QPushButton("导出 CSV")
        bar.addWidget(self.fetch_button)
        bar.addWidget(self.search_edit, 1)
        bar.addWidget(self.copy_button)
        bar.addWidget(self.export_json_button)
        bar.addWidget(self.export_csv_button)
        self.root.addWidget(toolbar)

        self.count_label = common.label("尚未获取模型列表", role="hint")
        self.root.addWidget(self.count_label)

        # ---------------------------------------------------------- 表格
        self.table = common.make_table(["模型 ID", "所属者", "创建时间", "接口返回的额外字段"], stretch_column=0)
        self.table.setMinimumHeight(280)
        self.root.addWidget(self.table, 1)

        self._models = []

    def _bind(self):
        self.fetch_button.clicked.connect(self.fetch_models)
        self.search_edit.textChanged.connect(self.apply_filter)
        self.copy_button.clicked.connect(self.copy_selected)
        self.export_json_button.clicked.connect(lambda: self.export("json"))
        self.export_csv_button.clicked.connect(lambda: self.export("csv"))
        self.ctx.models_changed.connect(self._on_models_changed)
        self.ctx.busy_changed.connect(lambda busy: self.fetch_button.setEnabled(not busy))

    # ------------------------------------------------------------ 事件
    def on_show(self):
        self._on_models_changed(self.ctx.models)

    def _on_models_changed(self, models):
        self._models = list(models or [])
        self.apply_filter()

    def fetch_models(self):
        self.ctx.fetch_models(on_success=self._on_fetched, on_error=self._on_fetch_failed)

    def _on_fetched(self, models):
        self.ctx.status("模型列表已更新：共 %d 个模型" % len(models))
        if self.ctx.config.setting("auto_save_report", True):
            self.save_report(report_mod.build_models_report(self.ctx.api_url(), models), auto=False)

    def _on_fetch_failed(self, message):
        self.warn(
            common.models_fetch_error_text(message),
            "获取模型列表失败",
        )

    def apply_filter(self):
        keyword = self.search_edit.text().strip().lower()
        rows = []
        for model in self._models:
            haystack = "%s %s" % (model.get("id", ""), model.get("owned_by", ""))
            if keyword and keyword not in haystack.lower():
                continue
            rows.append(model)
        self._fill_table(rows)
        total = len(self._models)
        self.count_label.setText(
            "共 %d 个模型" % total if not keyword else "匹配 %d / %d 个模型" % (len(rows), total)
        )

    def _fill_table(self, models):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for model in models:
            row = self.table.rowCount()
            self.table.insertRow(row)
            extra = model.get("raw") or {}
            extra_text = ", ".join(
                "%s=%s" % (k, v) for k, v in extra.items() if k not in ("id", "owned_by", "created")
            )
            values = [model.get("id", ""), model.get("owned_by", ""), model.get("created_text", ""), extra_text]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                if column == 0:
                    item.setData(Qt.UserRole, model.get("id", ""))
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)

    def copy_selected(self):
        ids = self.selected_ids()
        if not ids:
            self.info("请先在表格中选择要复制的模型。")
            return
        QApplication.clipboard().setText("\n".join(ids))
        self.ctx.status("已复制 %d 个模型 ID" % len(ids))

    def selected_ids(self):
        ids = []
        for index in self.table.selectionModel().selectedRows() if self.table.selectionModel() else []:
            item = self.table.item(index.row(), 0)
            if item:
                ids.append(item.text())
        return ids

    def export(self, fmt):
        if not self._models:
            self.info("还没有模型列表可导出，请先点击「获取模型列表」。")
            return
        report = report_mod.build_models_report(self.ctx.api_url(), self._models)
        default_name = report_mod.default_filename(report, fmt)
        export_dir = self.ctx.config.setting("report_dir") or paths.exports_dir()
        start_path = os.path.join(export_dir, default_name)
        filters = {"json": "JSON 文件 (*.json)", "csv": "CSV 文件 (*.csv)", "md": "Markdown 文件 (*.md)"}
        path, _ = QFileDialog.getSaveFileName(self, "导出模型列表", start_path, filters[fmt])
        if not path:
            return
        try:
            report_mod.export_report(report, path, fmt)
        except Exception as exc:
            self.error("导出失败：%s" % exc)
            return
        self.ctx.config.update_settings(report_dir=os.path.dirname(path))
        self.ctx.status("已导出：%s" % path)
        self.info("导出成功：\n%s" % path)
