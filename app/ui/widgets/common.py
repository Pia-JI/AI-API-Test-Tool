"""界面通用小工具：卡片、表单行、表格等。"""

from PyQt5.QtCore import QPointF, QRect, Qt
from PyQt5.QtGui import QColor, QPainter, QPainterPath
from PyQt5.QtWidgets import (
    QAbstractItemView, QComboBox, QDoubleSpinBox, QFormLayout, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QSizePolicy, QSpinBox, QTableWidget, QVBoxLayout, QWidget,
)

from ...theme import DROP_DOWN_WIDTH, SPIN_BUTTON_WIDTH, current, palette


def label(text, role=None, wrap=False, parent=None):
    """创建带角色样式的标签（role: hint / pageTitle / ok / warn / error）。"""
    item = QLabel(text, parent)
    if role:
        item.setProperty("role", role)
    item.setWordWrap(wrap)
    return item


def page_header(title, description=""):
    """页面标题 + 说明文字。"""
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 6)
    layout.setSpacing(2)
    layout.addWidget(label(title, role="pageTitle"))
    if description:
        layout.addWidget(label(description, role="hint", wrap=True))
    return box


def form_row(form, caption, widget, hint=None):
    """向 QFormLayout 添加一行，支持在右侧追加提示文字。"""
    if hint:
        holder = QWidget()
        layout = QHBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(widget)
        layout.addWidget(label(hint, role="hint"))
        layout.addStretch(1)
        form.addRow(caption, holder)
    else:
        form.addRow(caption, widget)
    return widget


def new_form(margins=(0, 0, 0, 0), spacing=8):
    form = QFormLayout()
    form.setContentsMargins(*margins)
    form.setSpacing(spacing)
    form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
    form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    return form


def make_table(headers, stretch_column=0, select_rows=True):
    """创建统一风格的表格。"""
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().setVisible(False)
    table.setAlternatingRowColors(True)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setWordWrap(False)
    if select_rows:
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.ExtendedSelection)
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeToContents)
    if 0 <= stretch_column < len(headers):
        header.setSectionResizeMode(stretch_column, QHeaderView.Stretch)
    table.setSortingEnabled(False)
    return table


def card(title, parent=None):
    """带标题的分组卡片。"""
    frame = QFrame(parent)
    frame.setProperty("role", "card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(12, 10, 12, 12)
    layout.setSpacing(8)
    layout.addWidget(label(title, role="cardTitle"))
    return frame, layout


def hline():
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    return line


def stretch_label():
    """占位控件，用于把后续控件推到右侧。"""
    widget = QWidget()
    widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    return widget


def models_fetch_error_text(message):
    """获取模型列表失败时的友好提示文案（页面与下拉框共用）。"""
    return (
        "%s\n\n可尝试的做法：\n"
        "1. 检查 API 地址是否为 https://xxx/v1 形式；\n"
        "2. 检查 API Key 是否有效；\n"
        "3. 若该服务商不提供 /models 接口，可在下拉框中直接手动输入模型名。" % message
    )


def draw_arrow(painter, rect, up, color, width=9.0, height=5.0):
    """在 rect 中央画一个三角箭头（用于下拉框与微调按钮）。"""
    center_x = rect.center().x() + 0.5
    center_y = rect.center().y() + 0.5
    half_width = width / 2.0
    half_height = height / 2.0
    if up:
        points = (
            QPointF(center_x - half_width, center_y + half_height),
            QPointF(center_x + half_width, center_y + half_height),
            QPointF(center_x, center_y - half_height),
        )
    else:
        points = (
            QPointF(center_x - half_width, center_y - half_height),
            QPointF(center_x + half_width, center_y - half_height),
            QPointF(center_x, center_y + half_height),
        )
    path = QPainterPath(points[0])
    path.lineTo(points[1])
    path.lineTo(points[2])
    path.closeSubpath()

    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(color))
    painter.drawPath(path)
    painter.restore()


def _arrow_color(widget):
    """箭头取主题文字色，禁用时用弱化色。"""
    colors = palette(current())
    return colors["text"] if widget.isEnabled() else colors["muted"]


class ComboBox(QComboBox):
    """下拉框：样式表接管子控件绘制后箭头不可靠，这里自己补画一个。"""

    def paintEvent(self, event):
        super(ComboBox, self).paintEvent(event)
        rect = QRect(self.width() - DROP_DOWN_WIDTH, 0, DROP_DOWN_WIDTH, self.height())
        draw_arrow(QPainter(self), rect, False, _arrow_color(self))


def _paint_spin_arrows(widget):
    """在数值输入框右侧画上 / 下两个箭头。"""
    top = widget.height() // 2
    color = _arrow_color(widget)
    painter = QPainter(widget)
    draw_arrow(painter, QRect(widget.width() - SPIN_BUTTON_WIDTH, 0, SPIN_BUTTON_WIDTH, top),
               True, color, width=8.0, height=4.5)
    draw_arrow(painter, QRect(widget.width() - SPIN_BUTTON_WIDTH, top, SPIN_BUTTON_WIDTH,
                              widget.height() - top), False, color, width=8.0, height=4.5)


class SpinBox(QSpinBox):
    """整数输入框：自绘上下箭头。"""

    def paintEvent(self, event):
        super(SpinBox, self).paintEvent(event)
        _paint_spin_arrows(self)


class DoubleSpinBox(QDoubleSpinBox):
    """浮点数输入框：自绘上下箭头。"""

    def paintEvent(self, event):
        super(DoubleSpinBox, self).paintEvent(event)
        _paint_spin_arrows(self)

