"""后台任务框架：把耗时操作放到 QThread 中执行，保证界面不卡顿。

用法：
    worker = Worker(latency_test_task, client, options)
    worker.progress_changed.connect(...)
    worker.succeeded.connect(...)
    worker.start()

任务函数签名统一为 fn(ctx, *args, **kwargs)，通过 ctx 上报进度与日志。
"""

from PyQt5.QtCore import QThread, pyqtSignal


class TaskCancelled(Exception):
    """任务被用户取消。"""


class TaskContext(object):
    """任务函数与界面之间唯一的通信对象（线程安全：内部只用 Qt 信号）。"""

    def __init__(self, worker):
        self._worker = worker
        self.cancelled = False

    # ------------------------------------------------------------ 输出
    def log(self, message):
        self._worker.logged.emit(str(message))

    def progress(self, percent, message=""):
        value = max(0, min(100, int(percent)))
        self._worker.progress_changed.emit(value, str(message))

    def step(self, done, total, message=""):
        percent = 0 if not total else int(round(100.0 * done / total))
        self.progress(percent, message)

    # ------------------------------------------------------------ 控制
    def cancel(self):
        self.cancelled = True

    def check(self):
        if self.cancelled:
            raise TaskCancelled()

    def sleep(self, seconds):
        """可被取消打断的等待。"""
        import time

        deadline = time.time() + float(seconds)
        while time.time() < deadline:
            if self.cancelled:
                raise TaskCancelled()
            time.sleep(min(0.05, max(0.0, deadline - time.time())))


class Worker(QThread):
    """通用后台任务线程。"""

    progress_changed = pyqtSignal(int, str)
    logged = pyqtSignal(str)
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)
    canceled = pyqtSignal()

    def __init__(self, func, *args, **kwargs):
        super(Worker, self).__init__()
        self._func = func
        self._args = args
        self._kwargs = kwargs
        self._ctx = None

    def cancel(self):
        """请求取消（任务会在下一个检查点退出）。"""
        if self._ctx is not None:
            self._ctx.cancel()

    def run(self):
        self._ctx = TaskContext(self)
        try:
            result = self._func(self._ctx, *self._args, **self._kwargs)
        except TaskCancelled:
            self.canceled.emit()
            return
        except Exception as exc:  # 兜底：任何异常都转成提示，避免线程里吞掉
            self.failed.emit("%s：%s" % (type(exc).__name__, exc))
            return
        if self._ctx.cancelled:
            self.canceled.emit()
            return
        self.succeeded.emit(result)
