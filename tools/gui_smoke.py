"""界面冒烟测试（开发环境使用，离屏运行，不需要真实接口）。

用法：
    python tools/gui_smoke.py

覆盖：页面结构、主题切换、模型下拉的填充与自绘箭头、报告页刷新等。
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import io

OUT = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stdout = OUT

from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QImage
from PyQt5.QtWidgets import (
    QApplication, QComboBox, QDoubleSpinBox, QProxyStyle, QSpinBox, QVBoxLayout, QWidget,
)

from app import report as report_mod
from app import theme
from app.config import ConfigManager
from app.database import ReportStore
from app.ui.main_window import MainWindow
from app.ui.widgets import common

PASS = []
FAIL = []


def log(message):
    print(message)
    OUT.flush()


def check(label, ok, extra=""):
    (PASS if ok else FAIL).append(label)
    log("%s | %s %s" % ("PASS" if ok else "FAIL", label, extra))


app = QApplication(sys.argv)
window = MainWindow(ConfigManager(), ReportStore())
window.resize(1360, 900)
window.show()
app.processEvents()


def arrow_pixels(widget, theme_name):
    image = widget.grab().toImage().convertToFormat(QImage.Format_RGB32)
    raw = theme.palette(theme_name)["input_bg"].lstrip("#")
    br, bg, bb = int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
    hits = 0
    w, h = image.width(), image.height()
    for x in range(max(0, w - 26), w):
        for y in range(h):
            px = image.pixel(x, y)
            r, g, b = (px >> 16) & 0xFF, (px >> 8) & 0xFF, px & 0xFF
            if abs(r - br) + abs(g - bg) + abs(b - bb) > 120:
                hits += 1
    return hits


def run():
    check("窗口包含 5 个页面", len(window.pages) == 5)
    check("左侧导航 5 项", window.nav.count() == 5)
    check("代理样式可用", isinstance(theme.app_style(), QProxyStyle))

    holder = QWidget()
    layout = QVBoxLayout(holder)
    combo = common.ComboBox()
    combo.setEditable(True)
    combo.addItems(["mock-chat-pro", "mock-fast-1"])
    spin = common.SpinBox()
    spin.setValue(7)
    layout.addWidget(combo)
    layout.addWidget(spin)
    holder.resize(240, 90)
    holder.show()
    app.processEvents()

    for name in ("dark", "light"):
        theme.apply_theme(app, name)
        app.processEvents()
        c_hits = arrow_pixels(combo, name)
        s_hits = arrow_pixels(spin, name)
        check("下拉箭头可见（%s）" % name, c_hits > 20, "pixels=%d" % c_hits)
        check("微调箭头可见（%s）" % name, s_hits > 20, "pixels=%d" % s_hits)
        check("主题标记写入（%s）" % name, app.property("ait_theme") == name)

    theme.apply_theme(app, "dark")
    app.processEvents()

    plain = []
    for page in window.pages:
        for widget in page.findChildren((QComboBox, QSpinBox, QDoubleSpinBox)):
            if not isinstance(widget, (common.ComboBox, common.SpinBox, common.DoubleSpinBox)):
                plain.append(widget.__class__.__name__)
    check("页面无遗漏的原生下拉/微调控件", plain == [], str(plain))

    window.url_edit.setText("http://127.0.0.1:8899/v1")
    window.key_edit.setText("test-key")
    window._key_dirty = True
    window.save_profile()
    app.processEvents()
    check("配置档案可保存", window.profile_combo.count() >= 1)

    window.ctx.set_models([
        {"id": "mock-chat-pro"},
        {"id": "mock-fast-1"},
        {"id": "mock-slow-1", "owned_by": "mock-lab"},
    ])
    app.processEvents()
    check("模型列表已广播", len(window.ctx.models) == 3)

    models_page, latency_page, speed_page, stability_page, report_page = window.pages
    check("模型页表格已填充", models_page.table.rowCount() == 3, "rows=%d" % models_page.table.rowCount())
    check("延迟页下拉已填充", latency_page.model_selector.combo.count() == 3)
    check("稳定性页下拉已填充", stability_page.model_selector.combo.count() == 3)
    check("延迟页请求目标可选", latency_page.target_combo.count() >= 2, latency_page.target_combo.currentText())
    check("速度页多选可选项已同步", len(speed_page.model_selector.options()) == 3,
          speed_page.model_selector.button.text())

    latency_page.model_selector.set_current("mock-fast-1")
    app.processEvents()
    check("下拉可指定模型", latency_page.model_selector.current() == "mock-fast-1")

    latency_page.target_combo.setCurrentIndex(1)
    app.processEvents()
    check("请求目标可切换", latency_page.target_combo.currentText() != "")

    check("多选默认不勾选", speed_page.model_selector.selected() == [])
    speed_page.model_selector.set_all(True)
    app.processEvents()
    check("多选全选可用", len(speed_page.model_selector.selected()) == 3)
    speed_page.model_selector.add_manual("custom-model-x")
    app.processEvents()
    check("多选可手动添加", "custom-model-x" in speed_page.model_selector.options())

    window.toggle_theme()
    app.processEvents()
    check("主题可切换", app.property("ait_theme") in ("dark", "light"))
    window.toggle_theme()
    app.processEvents()

    models_page.save_report(
        report_mod.build_models_report(window.ctx.api_url(), window.ctx.models), auto=False)
    app.processEvents()
    report_page.reload()
    app.processEvents()
    check("报告页可刷新", report_page.list_widget.count() >= 1,
          "items=%d" % report_page.list_widget.count())
    report_page.list_widget.setCurrentRow(0)
    report_page.show_selected()
    app.processEvents()
    check("报告预览可渲染", bool(report_page.preview.toPlainText().strip()))

    for index in range(5):
        window.nav.setCurrentRow(index)
        app.processEvents()
    check("全部页面可切换", window.stack.currentIndex() == 4)

    log("SUMMARY pass=%d fail=%d" % (len(PASS), len(FAIL)))
    if FAIL:
        log("FAILED: " + ", ".join(FAIL))
    window.close()
    app.quit()


QTimer.singleShot(800, run)

if __name__ == "__main__":
    sys.exit(app.exec_())
