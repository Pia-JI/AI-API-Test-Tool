"""主窗口：顶部配置区 + 左侧导航 + 中间内容区 + 底部状态栏与日志。"""

import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAction, QCheckBox, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QSplitter, QStackedWidget, QStatusBar, QVBoxLayout,
    QWidget, QInputDialog, QFileDialog,
)

from .. import APP_NAME, __version__, paths
from ..api_client import normalize_base_url
from ..config import KEEP
from ..crypto_utils import default_vault
from ..tasks import connection_test_task
from ..workers import Worker
from .context import AppContext
from .pages.latency_page import LatencyPage
from .pages.models_page import ModelsPage
from .pages.report_page import ReportPage
from .pages.speed_page import SpeedTestPage
from .pages.stability_page import StabilityPage
from .widgets import common


class MainWindow(QMainWindow):
    """应用主窗口。"""

    def __init__(self, config, store, parent=None):
        super(MainWindow, self).__init__(parent)
        self.config = config
        self.store = store
        self.ctx = AppContext(config, store, self)
        self._key_dirty = False

        self.setWindowTitle("%s v%s" % (APP_NAME, __version__))
        self.resize(1240, 860)
        self.setMinimumSize(1040, 700)

        self._build_menu()
        self._build_ui()
        self._bind()
        self._reload_profiles()
        self._apply_saved_theme()

    # ================================================================ 菜单
    def _build_menu(self):
        menu = self.menuBar()

        file_menu = menu.addMenu("文件(&F)")
        action = QAction("打开数据目录", self)
        action.triggered.connect(self.open_data_dir)
        file_menu.addAction(action)
        action = QAction("导出全部报告…", self)
        action.triggered.connect(self.export_all_history)
        file_menu.addAction(action)
        file_menu.addSeparator()
        action = QAction("退出", self)
        action.triggered.connect(self.close)
        file_menu.addAction(action)

        view_menu = menu.addMenu("视图(&V)")
        action = QAction("切换暗黑 / 浅色主题", self)
        action.triggered.connect(self.toggle_theme)
        view_menu.addAction(action)
        action = QAction("显示 / 隐藏日志面板", self)
        action.triggered.connect(self.toggle_log)
        view_menu.addAction(action)

        help_menu = menu.addMenu("帮助(&H)")
        action = QAction("使用说明", self)
        action.triggered.connect(self.show_help)
        help_menu.addAction(action)
        action = QAction("关于", self)
        action.triggered.connect(self.show_about)
        help_menu.addAction(action)

    # ================================================================ 界面
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 8, 10, 6)
        layout.setSpacing(8)

        layout.addWidget(self._build_config_area())

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self._build_nav())
        self.splitter.addWidget(self._build_pages())
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([170, 1000])
        layout.addWidget(self.splitter, 1)

        layout.addWidget(self._build_status_bar())

    # ---------------------------------------------------------- 顶部配置区
    def _build_config_area(self):
        box = QGroupBox("API 配置")
        outer = QVBoxLayout(box)
        outer.setContentsMargins(10, 8, 10, 10)
        outer.setSpacing(8)

        first = QHBoxLayout()
        first.setSpacing(8)
        first.addWidget(QLabel("配置档案"))
        self.profile_combo = common.ComboBox()
        self.profile_combo.setMinimumWidth(180)
        self.profile_combo.setToolTip("可以为多家 AI 服务商分别保存配置，随时切换")
        self.new_profile_button = QPushButton("新建")
        self.rename_profile_button = QPushButton("重命名")
        self.delete_profile_button = QPushButton("删除")
        self.test_button = QPushButton("测试连接")
        first.addWidget(self.profile_combo)
        first.addWidget(self.new_profile_button)
        first.addWidget(self.rename_profile_button)
        first.addWidget(self.delete_profile_button)
        first.addStretch(1)
        first.addWidget(self.test_button)
        outer.addLayout(first)

        second = QHBoxLayout()
        second.setSpacing(8)
        second.addWidget(QLabel("API 地址"))
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("例如 https://api.openai.com/v1 或 https://api.deepseek.com/v1")
        second.addWidget(self.url_edit, 3)
        second.addWidget(QLabel("API Key"))
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("sk-...（本地加密保存，不会明文写入文件）")
        second.addWidget(self.key_edit, 2)
        self.show_key_check = QCheckBox("显示")
        second.addWidget(self.show_key_check)
        outer.addLayout(second)

        third = QHBoxLayout()
        third.setSpacing(8)
        third.addWidget(QLabel("代理"))
        self.proxy_edit = QLineEdit()
        self.proxy_edit.setPlaceholderText("可选，例如 http://127.0.0.1:7890")
        self.proxy_edit.setMaximumWidth(280)
        third.addWidget(self.proxy_edit)
        self.save_button = QPushButton("保存配置")
        self.save_button.setProperty("role", "primary")
        self.clear_button = QPushButton("清除配置")
        self.clear_button.setProperty("role", "danger")
        self.config_hint = common.label("配置只保存在本机 data 目录，API Key 使用与机器绑定的密钥加密。", role="hint")
        third.addWidget(self.save_button)
        third.addWidget(self.clear_button)
        third.addWidget(self.config_hint, 1)
        outer.addLayout(third)
        return box

    # ---------------------------------------------------------- 左侧导航
    def _build_nav(self):
        self.nav = QListWidget()
        self.nav.setMaximumWidth(220)
        self.nav.setMinimumWidth(150)
        for text in ("模型列表", "延迟测试", "模型速度测试", "稳定性测试", "测试报告"):
            self.nav.addItem(QListWidgetItem(text))
        self.nav.setCurrentRow(0)
        return self.nav

    # ---------------------------------------------------------- 中间内容区
    def _build_pages(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.stack = QStackedWidget()
        self.pages = [
            ModelsPage(self.ctx),
            LatencyPage(self.ctx),
            SpeedTestPage(self.ctx),
            StabilityPage(self.ctx),
            ReportPage(self.ctx),
        ]
        for page in self.pages:
            self.stack.addWidget(page)
        layout.addWidget(self.stack, 1)

        self.log_panel = QPlainTextEdit()
        self.log_panel.setReadOnly(True)
        self.log_panel.setMaximumBlockCount(3000)
        self.log_panel.setFixedHeight(118)
        font = self.log_panel.font()
        font.setFamily("Consolas")
        self.log_panel.setFont(font)
        layout.addWidget(self.log_panel)
        return container

    # ---------------------------------------------------------- 底部状态栏
    def _build_status_bar(self):
        bar = QStatusBar()
        self.setStatusBar(bar)
        self.status_label = QLabel("就绪")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedWidth(220)
        self.progress_bar.setFormat("%p%")
        self.cancel_button = QPushButton("取消任务")
        self.cancel_button.setEnabled(False)
        self.clear_log_button = QPushButton("清空日志")
        self.log_button = QPushButton("隐藏日志")
        bar.addWidget(self.status_label, 1)
        bar.addPermanentWidget(self.progress_bar)
        bar.addPermanentWidget(self.cancel_button)
        bar.addPermanentWidget(self.clear_log_button)
        bar.addPermanentWidget(self.log_button)
        return bar

    # ================================================================ 事件
    def _bind(self):
        self.nav.currentRowChanged.connect(self._on_nav_changed)
        self.profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        self.key_edit.textEdited.connect(self._mark_key_dirty)
        self.show_key_check.toggled.connect(self._toggle_key_visibility)
        self.save_button.clicked.connect(self.save_profile)
        self.clear_button.clicked.connect(self.clear_profile)
        self.test_button.clicked.connect(self.test_connection)
        self.new_profile_button.clicked.connect(self.new_profile)
        self.rename_profile_button.clicked.connect(self.rename_profile)
        self.delete_profile_button.clicked.connect(self.delete_profile)
        self.url_edit.returnPressed.connect(self.save_profile)
        self.cancel_button.clicked.connect(self.ctx.cancel)
        self.clear_log_button.clicked.connect(self.log_panel.clear)
        self.log_button.clicked.connect(self.toggle_log)
        self.ctx.status_changed.connect(self.status_label.setText)
        self.ctx.log_message.connect(self.append_log)
        self.ctx.progress_changed.connect(self._on_progress)
        self.ctx.busy_changed.connect(self._on_busy)

    def _on_nav_changed(self, index):
        self.stack.setCurrentIndex(index)
        page = self.stack.currentWidget()
        if hasattr(page, "on_show"):
            page.on_show()

    # ---------------------------------------------------------- 配置档案
    def _reload_profiles(self):
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        names = self.config.names()
        if not names:
            self.profile_combo.addItem("默认")
        else:
            self.profile_combo.addItems(names)
        active = self.config.active_name() or (names[0] if names else "默认")
        index = self.profile_combo.findText(active)
        self.profile_combo.setCurrentIndex(index if index >= 0 else 0)
        self.profile_combo.blockSignals(False)
        self._load_profile(self.profile_combo.currentText())

    def _load_profile(self, name):
        profile = self.config.get(name)
        self.url_edit.setText((profile or {}).get("base_url", ""))
        self.proxy_edit.setText((profile or {}).get("proxy", "") or self.config.setting("proxy", ""))
        key = self.config.api_key_of(name) if profile else ""
        self._key_dirty = False
        self.key_edit.setText(key)
        self.key_edit.setEchoMode(QLineEdit.Normal if self.show_key_check.isChecked() else QLineEdit.Password)
        self.ctx.profile_changed.emit(name)
        if name and profile:
            self.ctx.status("当前配置：%s" % name)

    def _on_profile_changed(self, _index):
        name = self.profile_combo.currentText()
        if name:
            self.config.set_active(name)
            self.config.save()
        self._load_profile(name)

    def _mark_key_dirty(self, _text):
        self._key_dirty = True

    def _toggle_key_visibility(self, checked):
        self.key_edit.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)

    def _key_value(self):
        """返回要保存的 API Key：None 表示保持原值。"""
        if self._key_dirty:
            return self.key_edit.text().strip()
        return None

    def save_profile(self):
        name = self.profile_combo.currentText().strip() or "默认"
        base_url = normalize_base_url(self.url_edit.text())
        if not base_url:
            self.warn("请先填写 API 地址，例如 https://api.openai.com/v1")
            return
        key = self._key_value()
        proxy = self.proxy_edit.text().strip()
        self.config.upsert(name, base_url, api_key=(key if key is not None else KEEP), proxy=proxy)
        self.url_edit.setText(base_url)
        self._key_dirty = False
        stored = self.config.api_key_of(name)
        self.key_edit.setText(stored)
        self._reload_profile_names(keep=name)
        self.ctx.log("配置已保存：%s（%s，API Key：%s）" % (
            name, base_url, default_vault().mask(stored) if stored else "未设置"))
        self.ctx.status("配置已保存：%s" % name)
        self.ctx.profile_changed.emit(name)

    def _reload_profile_names(self, keep=None):
        keep = keep or self.config.active_name()
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        self.profile_combo.addItems(self.config.names() or ["默认"])
        index = self.profile_combo.findText(keep)
        self.profile_combo.setCurrentIndex(index if index >= 0 else 0)
        self.profile_combo.blockSignals(False)

    def clear_profile(self):
        name = self.profile_combo.currentText().strip() or "默认"
        if not self.ask("确定清除配置「%s」中的 API 地址与 API Key 吗？" % name):
            return
        self.config.upsert(name, "", api_key="")
        self.url_edit.clear()
        self.key_edit.clear()
        self.proxy_edit.clear()
        self._key_dirty = False
        self.ctx.status("配置已清除")
        self.ctx.log("已清除配置：%s" % name)
        self.ctx.profile_changed.emit(name)

    def new_profile(self):
        name, ok = QInputDialog.getText(self, "新建配置", "配置名称，例如：OpenAI / DeepSeek")
        name = (name or "").strip()
        if not ok or not name:
            return
        if self.config.get(name):
            self.warn("配置「%s」已存在。" % name)
            return
        self.config.upsert(name, "", api_key="")
        self._reload_profile_names(keep=name)
        self._load_profile(name)
        self.ctx.log("已新建配置档案：%s" % name)

    def rename_profile(self):
        old = self.profile_combo.currentText().strip()
        if not old or not self.config.get(old):
            self.warn("当前没有可重命名的配置，请先保存一次配置。")
            return
        name, ok = QInputDialog.getText(self, "重命名配置", "新的配置名称", text=old)
        name = (name or "").strip()
        if not ok or not name or name == old:
            return
        if not self.config.rename(old, name):
            self.warn("重命名失败，可能已存在同名配置。")
            return
        self._reload_profile_names(keep=name)
        self.ctx.log("配置已重命名：%s → %s" % (old, name))

    def delete_profile(self):
        name = self.profile_combo.currentText().strip()
        if not self.config.get(name):
            self.warn("当前配置尚未保存，无需删除。")
            return
        if not self.ask("确定删除配置「%s」及其保存的 API Key 吗？" % name):
            return
        self.config.delete(name)
        self._reload_profiles()
        self.ctx.log("已删除配置：%s" % name)

    # ---------------------------------------------------------- 连接测试
    def test_connection(self):
        from ..api_client import ApiClient

        base_url = normalize_base_url(self.url_edit.text())
        if not base_url:
            self.warn("请先填写 API 地址。")
            return
        key = self.key_edit.text().strip()
        if self._key_dirty and key:
            api_key = key
        else:
            api_key = self.config.api_key_of(self.profile_combo.currentText())
        if not api_key:
            self.warn("请先填写 API Key。")
            return
        proxy = self.proxy_edit.text().strip() or self.config.setting("proxy", "")
        client = ApiClient(base_url, api_key, timeout=min(30, int(self.config.setting("timeout", 60))),
                           proxy=proxy)
        self.ctx.run(
            Worker(connection_test_task, client),
            on_success=lambda result: self._on_test_done(result, client),
            name="测试连接",
        )

    def _on_test_done(self, result, client):
        client.close()
        if result.get("ok"):
            QMessageBox.information(self, "测试连接", result.get("message", "连接成功"))
        else:
            self.warn(result.get("message", "连接失败"), "测试连接失败")

    # ---------------------------------------------------------- 状态与日志
    def append_log(self, message):
        self.log_panel.appendPlainText(message)

    def _on_progress(self, percent, message):
        self.progress_bar.setValue(percent)
        self.progress_bar.setFormat(("%s  %%p%%" % message) if message else "%p%")

    def _on_busy(self, busy):
        self.cancel_button.setEnabled(busy)
        self.test_button.setEnabled(not busy)

    def toggle_log(self):
        visible = not self.log_panel.isVisible()
        self.log_panel.setVisible(visible)
        self.log_button.setText("隐藏日志" if visible else "显示日志")

    # ---------------------------------------------------------- 主题
    def _apply_saved_theme(self):
        from PyQt5.QtWidgets import QApplication
        from .. import theme

        name = self.config.setting("theme", "dark")
        theme.apply_theme(QApplication.instance(), name)

    def toggle_theme(self):
        from PyQt5.QtWidgets import QApplication
        from .. import theme

        current = theme.current(QApplication.instance())
        new_theme = "light" if current == "dark" else "dark"
        theme.apply_theme(QApplication.instance(), new_theme)
        self.config.update_settings(theme=new_theme)
        for widget in self.findChildren(QWidget):
            widget.update()
        self.ctx.status("已切换到%s主题" % ("浅色" if new_theme == "light" else "暗黑"))

    # ---------------------------------------------------------- 其它菜单
    def open_data_dir(self):
        directory = paths.data_dir()
        try:
            os.startfile(directory)
        except Exception as exc:
            self.warn("无法打开目录：%s\n目录路径：%s" % (exc, directory))

    def export_all_history(self):
        from .. import report as report_mod

        reports = self.store.list(1000)
        if not reports:
            self.warn("暂无历史报告可导出。")
            return
        directory = QFileDialog.getExistingDirectory(
            self, "选择导出目录", self.config.setting("report_dir") or paths.exports_dir()
        )
        if not directory:
            return
        count = 0
        for meta in reports:
            payload = self.store.get(meta["id"])
            if not payload:
                continue
            report_mod.export_all(payload, directory, prefix="%s_%s" % (meta["id"], meta.get("kind", "report")))
            count += 1
        self.config.update_settings(report_dir=directory)
        self.ctx.status("已导出 %d 份历史报告" % count)
        QMessageBox.information(self, "导出完成", "已导出 %d 份报告到：\n%s" % (count, directory))

    def show_help(self):
        QMessageBox.information(
            self, "使用说明",
            "1. 在顶部填写 API 地址（形如 https://xxx/v1）与 API Key，点击「保存配置」；\n"
            "2. 「模型列表」页面点击「获取模型列表」拉取可用模型；\n"
            "3. 「延迟测试」测量网络延迟分位值与成功率；\n"
            "4. 「模型速度测试」测量首 Token 时间、输出速度等指标；\n"
            "5. 「稳定性测试」按并发数压测，观察限流与错误分布；\n"
            "6. 「测试报告」页面查看历史报告并导出 JSON / CSV / Markdown。\n\n"
            "提示：可切换多家服务商的配置档案；API Key 使用与机器绑定的密钥加密后保存在 data/config.json。",
        )

    def show_about(self):
        QMessageBox.about(
            self, "关于",
            "<b>%s</b> v%s<br><br>"
            "一个面向 OpenAI 兼容接口的桌面测试工具，"
            "支持模型列表、延迟、速度与稳定性测试，并可导出测试报告。<br><br>"
            "数据目录：%s" % (APP_NAME, __version__, paths.data_dir()),
        )

    # ================================================================ 收尾
    def warn(self, message, title="提示"):
        QMessageBox.warning(self, title, message)

    def ask(self, message, title="确认"):
        return QMessageBox.question(
            self, title, message, QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        ) == QMessageBox.Yes

    def closeEvent(self, event):
        if self.ctx.is_busy():
            if not self.ask("还有任务正在运行，确定退出吗？"):
                event.ignore()
                return
        self.ctx.shutdown()
        self.store.close()
        event.accept()
