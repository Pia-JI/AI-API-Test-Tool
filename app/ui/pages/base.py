"""页面基类。"""

import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFileDialog, QFrame, QMessageBox, QScrollArea, QVBoxLayout, QWidget,
)

from ... import paths, report as report_mod


class BasePage(QWidget):
    """所有功能页面的父类：统一布局边距，提供提示框与结果导出辅助。"""

    title = "页面"
    description = ""

    def __init__(self, ctx, parent=None):
        super(BasePage, self).__init__(parent)
        self.ctx = ctx
        self._build()
        self._bind()

    # ------------------------------------------------------------ 生命周期
    def _build(self):
        """子类在这里创建控件，通常调用 super() 生成外层布局。

        页面内容整体放在滚动区域内：窗口较矮时自动出现滚动条，
        避免指标卡片、图表等控件被压缩变形。
        """
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        content = QWidget()
        self.root = QVBoxLayout(content)
        self.root.setContentsMargins(14, 12, 14, 12)
        self.root.setSpacing(10)
        self.scroll_area.setWidget(content)
        outer.addWidget(self.scroll_area)

    def _bind(self):
        """子类在这里连接信号。"""

    def on_show(self):
        """切换到该页面时调用。"""

    # ------------------------------------------------------------ 工具方法
    def info(self, message, title="提示"):
        QMessageBox.information(self, title, message)

    def warn(self, message, title="提示"):
        QMessageBox.warning(self, title, message)

    def error(self, message, title="出错了"):
        QMessageBox.critical(self, title, message)

    def ask(self, message, title="确认"):
        return QMessageBox.question(
            self, title, message, QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        ) == QMessageBox.Yes

    def save_report(self, report, auto=True):
        """把报告写入数据库，并按需提示。"""
        try:
            report_id = self.ctx.store.save(report)
            self.ctx.log("报告已保存到本地数据库（编号 %s）" % report_id)
        except Exception as exc:
            self.ctx.log("报告保存失败：%s" % exc)
            return None
        if auto:
            self.ctx.status("已生成测试报告，可在「测试报告」页面查看或导出")
        self.ctx.report_saved.emit()
        return report_id

    def export_report_dialog(self, report, caption="导出测试报告"):
        """弹出保存对话框并导出报告（按扩展名自动选择格式）。"""
        export_dir = self.ctx.config.setting("report_dir") or paths.exports_dir()
        default_name = report_mod.default_filename(report, "json")
        path, selected_filter = QFileDialog.getSaveFileName(
            self, caption, os.path.join(export_dir, default_name),
            "JSON 文件 (*.json);;CSV 文件 (*.csv);;Markdown 文件 (*.md);;全部文件 (*)",
        )
        if not path:
            return None
        ext = os.path.splitext(path)[1].lstrip(".").lower()
        if not ext:
            ext = "csv" if "CSV" in (selected_filter or "") else ("md" if "Markdown" in (selected_filter or "") else "json")
            path = "%s.%s" % (path, ext)
        try:
            report_mod.export_report(report, path, ext)
        except Exception as exc:
            self.error("导出失败：%s" % exc)
            return None
        self.ctx.config.update_settings(report_dir=os.path.dirname(path))
        self.ctx.status("报告已导出：%s" % path)
        self.info("导出成功：\n%s" % path)
        return path
