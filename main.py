"""AI API 工具箱 —— 程序入口。

直接运行：
    python main.py

打包为单文件 exe：
    pyinstaller --onefile --windowed --name "AI-API-Toolbox" main.py
"""

import os
import sys
import traceback
import warnings

# Python 3.8 上 cryptography 会提示弃用信息，屏蔽掉保持启动干净
warnings.filterwarnings("ignore", message="Python 3.8 is no longer supported.*")

from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtGui import QColor, QFont, QIcon, QPainter, QPixmap  # noqa: E402
from PyQt5.QtWidgets import QApplication, QMessageBox  # noqa: E402

from app import APP_ID, APP_NAME, __version__  # noqa: E402
from app import paths  # noqa: E402
from app.config import ConfigManager  # noqa: E402
from app.database import ReportStore  # noqa: E402


def build_app_icon():
    """用代码绘制一个简单图标，免去外部资源文件（打包更省心）。"""
    pixmap = QPixmap(128, 128)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setBrush(QColor("#4c8dff"))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(4, 4, 120, 120, 28, 28)
    painter.setPen(QColor("#ffffff"))
    font = QFont("Arial", 46, QFont.Bold)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "AI")
    painter.end()
    return QIcon(pixmap)


def setup_logging():
    """把运行日志写入 data/logs/app.log，方便打包成 exe 后排查问题。"""
    import logging
    from logging.handlers import RotatingFileHandler

    log_path = os.path.join(paths.logs_dir(), "app.log")
    logger = logging.getLogger("ai_api_toolbox")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = RotatingFileHandler(log_path, maxBytes=1024 * 512, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)s  %(message)s"))
        logger.addHandler(handler)
    return logger


def install_excepthook(logger):
    """未捕获异常写入日志并弹窗，避免打包后界面直接消失且无任何提示。"""
    def hook(exc_type, exc_value, exc_tb):
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logger.error("未捕获异常：\n%s" % text)
        try:
            QMessageBox.critical(None, "程序异常", "发生未预期的错误：\n%s\n\n详情已写入日志：\n%s" % (
                exc_value, os.path.join(paths.logs_dir(), "app.log")))
        except Exception:
            pass

    sys.excepthook = hook


def main():
    argv = list(sys.argv[1:])
    if "--self-check" in argv:
        # 无界面自检模式：便于在打包后用同一份 exe 验证接口连通性
        argv.remove("--self-check")
        if "--log-file" not in argv:
            argv += ["--log-file", os.path.join(paths.logs_dir(), "selfcheck.log")]
        from app.selfcheck import main as selfcheck_main

        return selfcheck_main(argv)

    if hasattr(Qt, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, "AA_UseHighDpiPixmaps"):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(APP_ID)
    app.setWindowIcon(build_app_icon())

    logger = setup_logging()
    install_excepthook(logger)
    logger.info("启动 %s v%s（数据目录：%s）" % (APP_NAME, __version__, paths.data_dir()))

    config = ConfigManager()
    store = ReportStore()

    from app.ui.main_window import MainWindow

    window = MainWindow(config, store)
    window.setWindowIcon(app.windowIcon())
    window.show()

    # 界面日志同时写入文件，便于事后排查
    window.ctx.log_message.connect(lambda text: logger.info(text))
    window.ctx.log("程序已启动，数据目录：%s" % paths.data_dir())

    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
