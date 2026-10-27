"""统计指标卡片：一行小标题 + 一行大数值。"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QGridLayout, QFrame, QLabel, QSizePolicy, QVBoxLayout, QWidget,
)


class StatCard(QFrame):
    """单个指标卡片。"""

    MIN_HEIGHT = 58

    def __init__(self, title, value="-", parent=None):
        super(StatCard, self).__init__(parent)
        self.setProperty("role", "card")
        self.setMinimumHeight(self.MIN_HEIGHT)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)
        self.title_label = QLabel(title)
        self.title_label.setProperty("role", "cardTitle")
        title_font = QFont(self.title_label.font())
        title_font.setPointSizeF(max(7.5, title_font.pointSizeF() - 1.5))
        self.title_label.setFont(title_font)
        self.value_label = QLabel(str(value))
        self.value_label.setProperty("role", "cardValue")
        value_font = QFont(self.value_label.font())
        value_font.setPointSizeF(max(10.0, value_font.pointSizeF() + 3.0))
        value_font.setBold(True)
        self.value_label.setFont(value_font)
        self.value_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)

    def set_value(self, value, role=None):
        self.value_label.setText("-" if value is None else str(value))
        self.value_label.setProperty("role", role or "cardValue")
        self._refresh_style()

    def _refresh_style(self):
        self.value_label.style().unpolish(self.value_label)
        self.value_label.style().polish(self.value_label)


class StatBoard(QWidget):
    """指标卡片网格；通过字段名批量更新。"""

    def __init__(self, fields, columns=4, parent=None):
        """fields: [(key, 标题, 单位后缀), ...]"""
        super(StatBoard, self).__init__(parent)
        self.cards = {}
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        for index, field in enumerate(fields):
            key, title = field[0], field[1]
            suffix = field[2] if len(field) > 2 else ""
            card_widget = StatCard(title)
            card_widget.unit = suffix
            self.cards[key] = card_widget
            layout.addWidget(card_widget, index // columns, index % columns)

    def set_value(self, key, value, role=None):
        card_widget = self.cards.get(key)
        if card_widget is None:
            return
        unit = getattr(card_widget, "unit", "")
        text = "-" if value is None else "%s%s" % (value, unit)
        card_widget.set_value(text, role=role)

    def set_values(self, values, roles=None):
        roles = roles or {}
        for key, value in (values or {}).items():
            self.set_value(key, value, roles.get(key))

    def reset(self):
        for card_widget in self.cards.values():
            card_widget.set_value("-")
