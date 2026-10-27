"""运行时目录解析。

源码运行与 PyInstaller 打包后的单文件 exe 运行，两种情况下
「程序目录 / 数据目录」的取值不同，这里统一封装，避免各模块重复判断。

数据目录优先级：
    1. 环境变量 AIT_DATA_DIR（便于便携部署与测试）
    2. 打包运行：exe 所在目录下的 data/
    3. 源码运行：项目根目录下的 data/
"""

import os
import sys


def is_frozen():
    """是否运行在 PyInstaller 打包出的 exe 中。"""
    return bool(getattr(sys, "frozen", False))


def app_dir():
    """程序所在目录（exe 目录或项目根目录）。"""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_dir():
    """数据目录，不存在时自动创建。"""
    env = os.environ.get("AIT_DATA_DIR")
    path = os.path.abspath(env) if env else os.path.join(app_dir(), "data")
    os.makedirs(path, exist_ok=True)
    return path


def logs_dir():
    """日志目录，不存在时自动创建。"""
    path = os.path.join(data_dir(), "logs")
    os.makedirs(path, exist_ok=True)
    return path


def exports_dir():
    """报告导出默认目录，不存在时自动创建。"""
    path = os.path.join(data_dir(), "exports")
    os.makedirs(path, exist_ok=True)
    return path


def path_in_data(*names):
    """拼接数据目录下的文件路径。"""
    return os.path.join(data_dir(), *names)
