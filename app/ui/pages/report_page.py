"""功能页面：测试报告（历史记录、预览与导出）。"""

import os
import subprocess

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFontMetrics
from PyQt5.QtWidgets import (
    QHBoxLayout, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton,
    QSplitter, QVBoxLayout, QWidget,
)

from ... import paths
from ... import report as report_mod
from ..widgets import common
from .base import BasePage

KIND_TITLES = report_mod.KIND_TITLES


class ReportPage(BasePage):
    title = "测试报告"
    description = "每次测试完成后会自动保存报告，这里可以查看历史报告，并导出为 JSON / CSV / Markdown。"

    def _build(self):
        super(ReportPage, self)._build()
        self.root.addWidget(common.page_header(self.title, self.description))

        splitter = QSplitter(Qt.Horizontal)

        # ---------------------------------------------------------- 左侧列表
        left = QWidget()
        left.setMinimumWidth(250)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)
        self.list_widget = QListWidget()
        self.list_widget.setTextElideMode(Qt.ElideRight)
        self.list_widget.itemSelectionChanged.connect(self.show_selected)

        buttons = QWidget()
        row = QHBoxLayout(buttons)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.refresh_button = QPushButton("刷新")
        self.delete_button = QPushButton("删除")
        self.clear_button = QPushButton("清空")
        self.clear_button.setProperty("role", "danger")
        self.open_dir_button = QPushButton("打开数据目录")
        row.addWidget(self.refresh_button)
        row.addWidget(self.delete_button)
        row.addWidget(self.clear_button)
        row.addStretch(1)
        left_layout.addWidget(self.list_widget, 1)
        left_layout.addWidget(buttons)
        left_layout.addWidget(self.open_dir_button)

        # ---------------------------------------------------------- 右侧预览
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)
        toolbar = QWidget()
        toolbar_row = QHBoxLayout(toolbar)
        toolbar_row.setContentsMargins(0, 0, 0, 0)
        toolbar_row.setSpacing(6)
        self.format_combo = common.ComboBox()
        self.format_combo.addItems(["Markdown 预览", "JSON 预览"])
        self.export_json_button = QPushButton("导出 JSON")
        self.export_csv_button = QPushButton("导出 CSV")
        self.export_md_button = QPushButton("导出 Markdown")
        self.export_all_button = QPushButton("全部导出")
        self.export_all_button.setProperty("role", "primary")
        toolbar_row.addWidget(self.format_combo)
        toolbar_row.addStretch(1)
        toolbar_row.addWidget(self.export_json_button)
        toolbar_row.addWidget(self.export_csv_button)
        toolbar_row.addWidget(self.export_md_button)
        toolbar_row.addWidget(self.export_all_button)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("在左侧选择一份报告查看详情…")
        font = self.preview.font()
        font.setFamily("Consolas")
        self.preview.setFont(font)
        right_layout.addWidget(toolbar)
        right_layout.addWidget(self.preview, 1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([330, 900])
        self.root.addWidget(splitter, 1)

        self._current = None

    def _bind(self):
        self.refresh_button.clicked.connect(self.reload)
        self.delete_button.clicked.connect(self.delete_selected)
        self.clear_button.clicked.connect(self.clear_all)
        self.open_dir_button.clicked.connect(self.open_data_dir)
        self.format_combo.currentIndexChanged.connect(self._render)
        self.export_json_button.clicked.connect(lambda: self.export_current("json"))
        self.export_csv_button.clicked.connect(lambda: self.export_current("csv"))
        self.export_md_button.clicked.connect(lambda: self.export_current("md"))
        self.export_all_button.clicked.connect(self.export_all)
        self.ctx.report_saved.connect(self.reload)

    def on_show(self):
        self.reload()

    # ------------------------------------------------------------ 列表
    def reload(self):
        selected_id = self.current_id()
        self.list_widget.clear()
        reports = self.ctx.store.list(300)
        for item in reports:
            kind = KIND_TITLES.get(item.get("kind"), item.get("kind"))
            summary = (item.get("summary") or "").strip()
            second = item.get("created_at", "")
            if item.get("models"):
                second += "｜%s" % item["models"]
            label = "#%s  %s\n%s" % (item.get("id"), kind, self._elide(second))
            if summary:
                label += "\n%s" % self._elide(summary)
            entry = QListWidgetItem(label)
            entry.setData(Qt.UserRole, item.get("id"))
            tooltip = "%s\n%s" % (item.get("api_url", ""), summary)
            entry.setToolTip(tooltip)
            self.list_widget.addItem(entry)
            if selected_id and item.get("id") == selected_id:
                self.list_widget.setCurrentItem(entry)
        if not reports:
            self.preview.setPlainText("暂无历史报告。完成任意一次测试后，报告会自动出现在这里。")

    def current_id(self):
        item = self.list_widget.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _elide(self, text):
        """按列表宽度截断文本，避免内容被硬切。"""
        metrics = QFontMetrics(self.list_widget.font())
        budget = max(160, self.list_widget.width() - 36)
        return metrics.elidedText(text, Qt.ElideRight, budget)

    def show_selected(self):
        report_id = self.current_id()
        if not report_id:
            self._current = None
            return
        self._current = self.ctx.store.get(report_id)
        self._render()

    def _render(self):
        if not self._current:
            return
        if self.format_combo.currentIndex() == 1:
            self.preview.setPlainText(report_mod.to_json(self._current))
        else:
            self.preview.setPlainText(report_mod.to_markdown(self._current))

    # ------------------------------------------------------------ 操作
    def delete_selected(self):
        report_id = self.current_id()
        if not report_id:
            self.info("请先选择一份报告。")
            return
        if not self.ask("确定删除报告 #%s 吗？" % report_id):
            return
        self.ctx.store.delete(report_id)
        self._current = None
        self.preview.clear()
        self.reload()
        self.ctx.status("报告已删除")

    def clear_all(self):
        if not self.ask("确定清空全部历史报告吗？该操作不可恢复。"):
            return
        self.ctx.store.clear()
        self._current = None
        self.preview.clear()
        self.reload()
        self.ctx.status("历史报告已清空")

    def export_current(self, fmt):
        if not self._current:
            self.info("请先在左侧选择一份报告。")
            return
        export_dir = self.ctx.config.setting("report_dir") or paths.exports_dir()
        default_name = report_mod.default_filename(self._current, fmt)
        path = os.path.join(export_dir, default_name)
        try:
            report_mod.export_report(self._current, path, fmt)
        except Exception as exc:
            self.error("导出失败：%s" % exc)
            return
        self.ctx.status("已导出：%s" % path)
        self.info("导出成功：\n%s" % path)

    def export_all(self):
        if not self._current:
            self.info("请先在左侧选择一份报告。")
            return
        export_dir = self.ctx.config.setting("report_dir") or paths.exports_dir()
        try:
            generated = report_mod.export_all(self._current, export_dir)
        except Exception as exc:
            self.error("导出失败：%s" % exc)
            return
        self.ctx.config.update_settings(report_dir=export_dir)
        self.ctx.status("已同时导出 3 种格式")
        self.info("已导出到：\n%s\n\n%s" % (export_dir, "\n".join(os.path.basename(p) for p in generated)))

    def open_data_dir(self):
        directory = paths.data_dir()
        try:
            if os.name == "nt":
                os.startfile(directory)  # noqa: S606 - Windows 资源管理器
            else:
                subprocess.Popen(["xdg-open", directory])
        except Exception as exc:
            self.info("无法打开目录：%s\n目录路径：%s" % (exc, directory))
