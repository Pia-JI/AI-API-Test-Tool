"""模型选择控件：下拉单选 / 下拉多选。

特点：
    1. 自动跟随「模型列表」页面获取到的模型（AppContext.models_changed）；
    2. 下拉框可手动输入接口未列出的模型名；
    3. 内置「获取模型」按钮，无需切回模型列表页也能拉取。
"""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox, QHBoxLayout, QLineEdit, QMenu, QMessageBox, QPushButton,
    QWidget, QWidgetAction,
)

from . import common

PLACEHOLDER = "请先获取模型列表，或直接输入模型名"


class _FetchMixin(object):
    """给选择器加上「获取模型」能力。"""

    def _init_fetch(self, ctx):
        self.ctx = ctx

    def fetch_models(self):
        """从「模型列表」接口拉取模型并填充下拉框。"""
        if self.ctx is None:
            return
        self.ctx.fetch_models(on_error=self._on_fetch_error)

    def _on_fetch_error(self, message):
        QMessageBox.warning(self, "获取模型列表失败", common.models_fetch_error_text(message))


class ModelSelector(QWidget, _FetchMixin):
    """下拉单选：用于只需要一个模型的测试。"""

    changed = pyqtSignal(str)

    def __init__(self, ctx=None, parent=None, minimum_width=240):
        super(ModelSelector, self).__init__(parent)
        self._init_fetch(ctx)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.combo = common.ComboBox()
        self.combo.setEditable(True)
        self.combo.setInsertPolicy(QComboBox.NoInsert)
        self.combo.setMinimumWidth(minimum_width)
        self.combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo.setToolTip("下拉选择模型；也可以直接输入模型名")
        if self.combo.lineEdit() is not None:
            self.combo.lineEdit().setPlaceholderText(PLACEHOLDER)
        self.fetch_button = QPushButton("获取模型")
        self.fetch_button.setToolTip("调用 /models 接口刷新模型列表")
        layout.addWidget(self.combo, 1)
        layout.addWidget(self.fetch_button)
        self.combo.currentTextChanged.connect(self.changed.emit)
        self.fetch_button.clicked.connect(self.fetch_models)

    # ------------------------------------------------------------ 数据
    def set_models(self, model_ids):
        """填充下拉项，尽量保留用户当前已填写的模型名。"""
        current = self.combo.currentText().strip()
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItems([str(m) for m in (model_ids or [])])
        if current:
            self.combo.setCurrentText(current)
        self.combo.blockSignals(False)
        if self.combo.count() and not current:
            self.changed.emit(self.combo.currentText())

    def current(self):
        return self.combo.currentText().strip()

    def set_current(self, text):
        if text:
            self.combo.setCurrentText(str(text))

    def setEnabled(self, enabled):
        super(ModelSelector, self).setEnabled(enabled)
        self.combo.setEnabled(enabled)
        self.fetch_button.setEnabled(enabled)


class ModelMultiSelector(QWidget, _FetchMixin):
    """下拉多选：用于需要对多个模型批量测试的场景。"""

    changed = pyqtSignal(list)

    def __init__(self, ctx=None, parent=None, max_summary=72):
        super(ModelMultiSelector, self).__init__(parent)
        self._init_fetch(ctx)
        self._max_summary = max_summary
        self._models = []      # 接口返回的模型
        self._custom = []      # 手动添加的模型
        self._selected = []    # 已勾选模型（按选择顺序）

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.button = QPushButton("选择模型")
        self.button.setMinimumWidth(170)
        self.fetch_button = QPushButton("获取模型")
        self.fetch_button.setToolTip("调用 /models 接口刷新模型列表")
        self.summary_label = common.label("未选择模型", role="hint")
        self.summary_label.setWordWrap(False)
        layout.addWidget(self.button)
        layout.addWidget(self.fetch_button)
        layout.addWidget(self.summary_label, 1)

        self.menu = QMenu(self)
        self.menu.aboutToShow.connect(self._rebuild_menu)
        self.button.setMenu(self.menu)
        self.fetch_button.clicked.connect(self.fetch_models)

    # ------------------------------------------------------------ 数据
    def set_models(self, model_ids):
        """更新可选项：保留手动添加项与已有勾选状态。"""
        self._models = [str(m) for m in (model_ids or [])]
        for name in self._custom:
            if name in self._models:
                self._custom.remove(name)
        self._refresh_summary()

    def options(self):
        return self._models + self._custom

    def selected(self):
        return list(self._selected)

    def set_all(self, checked):
        self._selected = list(self.options()) if checked else []
        self._after_change()

    def set_selected(self, names):
        names = [str(n) for n in (names or [])]
        for name in names:
            if name not in self.options():
                self._custom.append(name)
        self._selected = names
        self._after_change()

    def add_manual(self, name):
        name = (name or "").strip()
        if not name:
            return
        if name not in self.options():
            self._custom.append(name)
        if name not in self._selected:
            self._selected.append(name)
        self._after_change()

    def toggle(self, name, checked):
        if checked and name not in self._selected:
            self._selected.append(name)
        elif not checked and name in self._selected:
            self._selected.remove(name)
        self._after_change()

    def _after_change(self):
        self._refresh_summary()
        self.changed.emit(self.selected())

    def _refresh_summary(self):
        count = len(self._selected)
        self.button.setText("选择模型（已选 %d）" % count if count else "选择模型")
        if not count:
            text = "未选择模型，点击左侧按钮勾选（可多选）"
        else:
            text = "已选：%s" % "、".join(self._selected)
            if len(text) > self._max_summary:
                text = text[: self._max_summary - 1] + "…"
        self.summary_label.setText(text)
        self.summary_label.setToolTip("\n".join(self._selected) if self._selected else "")

    # ------------------------------------------------------------ 菜单
    def _rebuild_menu(self):
        self.menu.clear()
        options = self.options()
        if not options:
            action = self.menu.addAction("（暂无模型，请点击「获取模型」或手动添加）")
            action.setEnabled(False)
        for name in options:
            action = self.menu.addAction(name)
            action.setCheckable(True)
            action.setChecked(name in self._selected)
            action.toggled.connect(lambda checked, value=name: self.toggle(value, checked))
        self.menu.addSeparator()
        self.menu.addAction("全选", lambda: self.set_all(True))
        self.menu.addAction("全不选", lambda: self.set_all(False))
        self.menu.addSeparator()

        holder = QWidget(self.menu)
        holder_layout = QHBoxLayout(holder)
        holder_layout.setContentsMargins(8, 4, 8, 4)
        holder_layout.setSpacing(6)
        edit = QLineEdit(holder)
        edit.setPlaceholderText("手动输入模型名后回车添加")
        edit.setMinimumWidth(180)
        add_button = QPushButton("添加", holder)
        holder_layout.addWidget(edit)
        holder_layout.addWidget(add_button)
        action = QWidgetAction(self.menu)
        action.setDefaultWidget(holder)
        self.menu.addAction(action)

        def handle_add():
            self.add_manual(edit.text())
            edit.clear()

        add_button.clicked.connect(handle_add)
        edit.returnPressed.connect(handle_add)
        edit.setFocus(Qt.OtherFocusReason)

    def setEnabled(self, enabled):
        super(ModelMultiSelector, self).setEnabled(enabled)
        self.button.setEnabled(enabled)
        self.fetch_button.setEnabled(enabled)
