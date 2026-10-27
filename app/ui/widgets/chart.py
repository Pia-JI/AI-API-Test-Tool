"""轻量自绘图表（柱状图），不依赖 matplotlib 等第三方绘图库。

用于展示：延迟分布、各模型速度对比、错误类型分布等。
"""

from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PyQt5.QtWidgets import QWidget

from ... import theme as theme_mod


class BarChart(QWidget):
    """横向排列的柱状图，柱顶显示数值，底部显示标签。"""

    def __init__(self, parent=None, min_height=180):
        super(BarChart, self).__init__(parent)
        self._data = []          # [(label, value), ...]
        self._unit = ""
        self._title = ""
        self._color_key = "accent"
        self.setMinimumHeight(min_height)

    # ------------------------------------------------------------ 数据
    def set_data(self, data, unit="", title="", color_key="accent"):
        self._data = [(str(k), v) for k, v in (data or [])]
        self._unit = unit
        self._title = title
        self._color_key = color_key
        self.update()

    def clear(self):
        self.set_data([])

    # ------------------------------------------------------------ 绘制
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        colors = theme_mod.palette(theme_mod.current())
        rect = self.rect().adjusted(8, 8, -8, -8)

        title_font = QFont(self.font())
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QPen(QColor(colors["muted"])))
        if self._title:
            painter.drawText(QRectF(rect.left(), rect.top(), rect.width(), 18),
                             Qt.AlignLeft | Qt.AlignVCenter, self._title)
            rect.setTop(rect.top() + 22)

        if not self._data:
            painter.setPen(QPen(QColor(colors["muted"])))
            painter.setFont(self.font())
            painter.drawText(rect, Qt.AlignCenter, "暂无可展示的数据")
            painter.end()
            return

        values = [v for _, v in self._data if isinstance(v, (int, float))]
        max_value = max(values) if values else 1.0
        max_value = max(max_value, 1e-9)

        title_height = 22.0
        value_height = 18.0   # 柱顶数值
        label_height = 40.0   # 底部标签
        plot = QRectF(
            rect.left(),
            rect.top() + title_height + value_height,
            rect.width(),
            max(10.0, rect.height() - title_height - value_height - label_height),
        )
        count = len(self._data)
        slot = plot.width() / float(count)
        bar_width = min(56.0, slot * 0.6)
        # 柱子密集时抽稀标签，避免文字互相重叠
        label_step = 1
        if slot < 34:
            label_step = 3
        elif slot < 54:
            label_step = 2
        show_values = slot >= 40
        base_color = QColor(colors.get(self._color_key, colors["accent"]))

        # 基线
        painter.setPen(QPen(QColor(colors["grid"]), 1))
        painter.drawLine(int(plot.left()), int(plot.bottom()), int(plot.right()), int(plot.bottom()))

        value_font = QFont(self.font())
        value_font.setPointSize(max(8, self.font().pointSize() - 1))
        painter.setFont(value_font)
        value_metrics = QFontMetrics(value_font)
        label_metrics = QFontMetrics(self.font())
        for index, (name, value) in enumerate(self._data):
            center = plot.left() + slot * (index + 0.5)
            span = slot * label_step   # 抽稀后每个标签可用的横向空间
            ratio = 0.0 if not isinstance(value, (int, float)) else max(0.0, min(1.0, float(value) / max_value))
            height = max(2.0, plot.height() * ratio)
            bar = QRectF(center - bar_width / 2.0, plot.bottom() - height, bar_width, height)
            painter.setPen(Qt.NoPen)
            painter.setBrush(base_color)
            painter.drawRoundedRect(bar, 3, 3)

            if show_values and index % label_step == 0:
                text = "-" if value is None else self._format(value)
                text = value_metrics.elidedText(text, Qt.ElideRight, int(span) - 4)
                painter.setPen(QPen(QColor(colors["text"])))
                painter.drawText(QRectF(center - span / 2.0, bar.top() - value_height, span, value_height - 2),
                                 Qt.AlignCenter, text)

            if index % label_step == 0:
                text = label_metrics.elidedText(name, Qt.ElideRight, int(span) - 6)
                painter.setPen(QPen(QColor(colors["muted"])))
                painter.drawText(QRectF(center - span / 2.0, plot.bottom() + 4, span, label_height - 6),
                                 Qt.AlignHCenter | Qt.AlignTop, text)
        painter.end()

    def _format(self, value):
        if isinstance(value, float):
            text = ("%.2f" % value) if abs(value) < 100 else ("%.1f" % value)
        else:
            text = str(value)
        return "%s%s" % (text, self._unit)
