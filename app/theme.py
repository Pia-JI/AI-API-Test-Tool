"""界面主题（暗黑 / 浅色）。

用一个 QSS 模板 + 调色板生成样式表，图表的取色也走同一份调色板，
保证界面与图形颜色统一。
"""

PALETTES = {
    "dark": {
        "bg": "#1b1d21",
        "panel": "#24272c",
        "panel_alt": "#2b2f35",
        "border": "#3a3f46",
        "text": "#e8eaed",
        "muted": "#9aa3ad",
        "accent": "#4c8dff",
        "accent_text": "#ffffff",
        "ok": "#3ecf8e",
        "warn": "#f5b83d",
        "error": "#f0665c",
        "grid": "#3a3f46",
        "hover": "#31363d",
        "selection": "#35507f",
        "input_bg": "#1f2226",
    },
    "light": {
        "bg": "#f4f6f9",
        "panel": "#ffffff",
        "panel_alt": "#eef1f5",
        "border": "#d3d8e0",
        "text": "#1f2329",
        "muted": "#6b7280",
        "accent": "#2563eb",
        "accent_text": "#ffffff",
        "ok": "#1a9e63",
        "warn": "#c47f00",
        "error": "#d93a30",
        "grid": "#dfe3ea",
        "hover": "#e6ebf2",
        "selection": "#cfe0fb",
        "input_bg": "#ffffff",
    },
}

# 下拉区与微调按钮的宽度：QSS 与自绘箭头（ui/widgets/common.py）共用同一份数值。
DROP_DOWN_WIDTH = 22
SPIN_BUTTON_WIDTH = 18

_QSS_TEMPLATE = """
QWidget {{
    color: {text};
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", Arial;
    font-size: 13px;
}}
QGroupBox {{
    background: {panel};
    border: 1px solid {border};
    border-radius: 8px;
    margin-top: 14px;
    padding: 10px 10px 8px 10px;
    font-weight: bold;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    color: {muted};
}}
QLabel[role="hint"] {{ color: {muted}; }}
QLabel {{
    background: transparent;
    border: none;
}}
QCheckBox, QRadioButton {{
    background: transparent;
}}
QLabel[role="pageTitle"] {{ font-size: 18px; font-weight: bold; }}
QLabel[role="ok"] {{ color: {ok}; }}
QLabel[role="warn"] {{ color: {warn}; }}
QLabel[role="error"] {{ color: {error}; }}
QFrame[role="card"] {{
    background: {panel};
    border: 1px solid {border};
    border-radius: 8px;
}}
QLabel[role="cardTitle"] {{ color: {muted}; }}
QLabel[role="cardValue"] {{ font-weight: bold; }}
QPushButton {{
    background: {panel_alt};
    color: {text};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 6px 14px;
    min-height: 18px;
}}
QPushButton:hover {{ background: {hover}; }}
QPushButton:pressed {{ background: {selection}; }}
QPushButton:disabled {{ color: {muted}; background: {panel}; }}
QPushButton[role="primary"] {{
    background: {accent};
    color: {accent_text};
    border: 1px solid {accent};
    font-weight: bold;
}}
QPushButton[role="primary"]:hover {{ background: {accent}; }}
QPushButton[role="danger"] {{ color: {error}; }}
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {input_bg};
    color: {text};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 4px 8px;
    selection-background-color: {selection};
    selection-color: {text};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QComboBox:focus {{ border: 1px solid {accent}; }}
QComboBox QAbstractItemView {{
    background: {panel};
    color: {text};
    border: 1px solid {border};
    selection-background-color: {selection};
    selection-color: {text};
}}
QComboBox::drop-down {{
    background: transparent;
    border: none;
    width: {drop_down_width}px;
}}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    background: transparent;
    border: none;
    width: {spin_button_width}px;
}}
QCheckBox, QRadioButton {{ spacing: 6px; }}
QTableWidget, QTableView, QListWidget, QTreeWidget {{
    background: {panel};
    alternate-background-color: {panel_alt};
    border: 1px solid {border};
    border-radius: 8px;
    gridline-color: {grid};
    selection-background-color: {selection};
    selection-color: {text};
}}
QHeaderView::section {{
    background: {panel_alt};
    color: {muted};
    border: none;
    border-right: 1px solid {grid};
    border-bottom: 1px solid {grid};
    padding: 6px 8px;
    font-weight: bold;
}}
QTableWidget::item {{ padding: 2px 4px; }}
QListWidget::item {{ padding: 8px 10px; border-radius: 6px; }}
QListWidget::item:selected {{ background: {selection}; color: {text}; }}
QListWidget::item:hover {{ background: {hover}; }}
QProgressBar {{
    background: {panel_alt};
    border: 1px solid {border};
    border-radius: 6px;
    text-align: center;
    height: 16px;
}}
QProgressBar::chunk {{ background: {accent}; border-radius: 5px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {border}; border-radius: 5px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: {muted}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {border}; border-radius: 5px; min-width: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QSplitter::handle {{ background: {border}; }}
QStatusBar {{ background: {panel}; border-top: 1px solid {border}; }}
QToolTip {{
    background: {panel};
    color: {text};
    border: 1px solid {border};
    padding: 4px;
}}
QMenuBar {{ background: {panel}; }}
QMenuBar::item:selected {{ background: {hover}; }}
QMenu {{ background: {panel}; border: 1px solid {border}; }}
QMenu::item:selected {{ background: {selection}; }}
"""


def palette(theme="dark"):
    """获取主题调色板。"""
    return PALETTES.get(theme) or PALETTES["dark"]


def build_qss(theme="dark"):
    """生成指定主题的样式表。"""
    values = dict(palette(theme))
    values["drop_down_width"] = DROP_DOWN_WIDTH
    values["spin_button_width"] = SPIN_BUTTON_WIDTH
    return _QSS_TEMPLATE.format(**values)


def apply_theme(app, theme="dark"):
    """把主题应用到 QApplication。"""
    from PyQt5.QtGui import QPalette, QColor

    colors = palette(theme)
    app.setStyle(app_style())
    qp = QPalette()
    qp.setColor(QPalette.Window, QColor(colors["bg"]))
    qp.setColor(QPalette.WindowText, QColor(colors["text"]))
    qp.setColor(QPalette.Base, QColor(colors["input_bg"]))
    qp.setColor(QPalette.AlternateBase, QColor(colors["panel_alt"]))
    qp.setColor(QPalette.Text, QColor(colors["text"]))
    qp.setColor(QPalette.Button, QColor(colors["panel_alt"]))
    qp.setColor(QPalette.ButtonText, QColor(colors["text"]))
    qp.setColor(QPalette.Highlight, QColor(colors["accent"]))
    qp.setColor(QPalette.HighlightedText, QColor(colors["accent_text"]))
    qp.setColor(QPalette.ToolTipBase, QColor(colors["panel"]))
    qp.setColor(QPalette.ToolTipText, QColor(colors["text"]))
    qp.setColor(QPalette.Disabled, QPalette.Text, QColor(colors["muted"]))
    app.setPalette(qp)
    app.setStyleSheet(build_qss(theme))
    app.setProperty("ait_theme", theme)
    return colors


def current(app=None):
    """获取当前主题名（供图表等自绘控件取色）。"""
    if app is None:
        from PyQt5.QtWidgets import QApplication

        app = QApplication.instance()
    name = app.property("ait_theme") if app is not None else None
    return name if name in PALETTES else "dark"


def _make_proxy_style():
    """延迟创建代理样式，避免模块导入时就依赖 QtWidgets。"""
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QColor, QPainter, QPainterPath
    from PyQt5.QtWidgets import QProxyStyle, QStyle

    class AppStyle(QProxyStyle):
        """基础样式代理：自行绘制下拉 / 微调箭头。

        样式表接管 QComboBox、QSpinBox 之后，基础样式仍会用默认（黑色）调色板
        涂抹下拉区与微调按钮，暗色主题下就是一块纯黑，箭头也跟着看不见。
        这里直接接管这两个复杂控件：不画子控件背景，只按主题文字色画箭头，
        于是暗色是浅色三角、浅色是深色三角，两种主题下都清晰可见。
        """

        ARROW_WIDTH = 9.0
        ARROW_HEIGHT = 5.0

        def __init__(self):
            super(AppStyle, self).__init__("Fusion")

        def drawPrimitive(self, element, option, painter, widget=None):
            if element in (QStyle.PE_IndicatorArrowDown, QStyle.PE_IndicatorSpinDown):
                self._draw_arrow(False, option.rect, option.state, painter)
                return
            if element in (QStyle.PE_IndicatorArrowUp, QStyle.PE_IndicatorSpinUp):
                self._draw_arrow(True, option.rect, option.state, painter)
                return
            super(AppStyle, self).drawPrimitive(element, option, painter, widget)

        def _draw_arrow(self, up, rect, state, painter):
            colors = palette(current())
            enabled = bool(state & QStyle.State_Enabled)
            width = min(self.ARROW_WIDTH, max(4.0, rect.width() - 6.0))
            height = min(self.ARROW_HEIGHT, max(3.0, rect.height() / 3.0))
            center_x = rect.center().x() + 0.5
            center_y = rect.center().y() + 0.5

            path = QPainterPath()
            if up:
                path.moveTo(center_x - width / 2.0, center_y + height / 2.0)
                path.lineTo(center_x + width / 2.0, center_y + height / 2.0)
                path.lineTo(center_x, center_y - height / 2.0)
            else:
                path.moveTo(center_x - width / 2.0, center_y - height / 2.0)
                path.lineTo(center_x + width / 2.0, center_y - height / 2.0)
                path.lineTo(center_x, center_y + height / 2.0)
            path.closeSubpath()

            painter.save()
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(colors["text"] if enabled else colors["muted"]))
            painter.drawPath(path)
            painter.restore()

    return AppStyle


_APP_STYLE = None


def app_style():
    """返回全局唯一的代理样式实例。"""
    global _APP_STYLE
    if _APP_STYLE is None:
        _APP_STYLE = _make_proxy_style()()
    return _APP_STYLE
