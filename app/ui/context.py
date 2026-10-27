"""界面层的共享上下文：配置、数据库、模型缓存、后台任务调度。

各功能页面通过 AppContext 拿到 ApiClient、共享模型列表、状态栏 / 日志输出入口，
避免页面之间直接互相引用。
"""

from PyQt5.QtCore import QObject, pyqtSignal

from ..api_client import ApiClient


class AppContext(QObject):
    """贯穿整个应用的状态容器。"""

    status_changed = pyqtSignal(str)          # 底部状态栏文本
    log_message = pyqtSignal(str)             # 日志输出
    progress_changed = pyqtSignal(int, str)   # 进度百分比 + 说明
    busy_changed = pyqtSignal(bool)           # 是否有任务在跑
    models_changed = pyqtSignal(list)         # 模型列表更新
    profile_changed = pyqtSignal(str)         # 当前配置档案变化
    report_saved = pyqtSignal()               # 有新报告写入数据库

    def __init__(self, config, store, parent=None):
        super(AppContext, self).__init__(parent)
        self.config = config
        self.store = store
        self.models = []               # [{"id":..., "owned_by":..., ...}]
        self._worker = None

    # ------------------------------------------------------------ 基础输出
    def log(self, message):
        self.log_message.emit(str(message))

    def status(self, message):
        self.status_changed.emit(str(message))

    def progress(self, percent, message=""):
        self.progress_changed.emit(int(percent), str(message))

    # ------------------------------------------------------------ 客户端
    def profile_name(self):
        return self.config.active_name()

    def api_url(self):
        profile = self.config.active_profile()
        return (profile or {}).get("base_url", "")

    def client(self):
        """按当前配置构造 ApiClient；未配置完整时返回 None。"""
        base_url, api_key, proxy, timeout = self.config.client_config()
        if not base_url:
            return None
        return ApiClient(base_url, api_key, timeout=timeout, proxy=proxy)

    def require_client(self, need_key=True):
        """获取客户端，并在配置缺失时给出友好提示。"""
        base_url, api_key, _, _ = self.config.client_config()
        if not base_url:
            self.status("请先在顶部填写 API 地址并保存配置")
            return None
        if need_key and not api_key:
            self.status("请先在顶部填写 API Key 并保存配置")
            return None
        return self.client()

    # ------------------------------------------------------------ 模型缓存
    def set_models(self, models):
        self.models = list(models or [])
        self.models_changed.emit(self.models)

    def model_ids(self):
        return [m.get("id") for m in self.models if m.get("id")]

    def fetch_models(self, on_success=None, on_error=None, name="获取模型列表"):
        """拉取模型列表并写入缓存，供各页面的模型下拉框共用。

        on_success 收到模型列表（[{"id":..., ...}, ...]），on_error 收到错误文案。
        """
        from ..tasks import fetch_models_task
        from ..workers import Worker

        client = self.require_client()
        if client is None:
            if on_error:
                on_error("请先在顶部配置区填写 API 地址与 API Key，并点击「保存配置」。")
            return False

        def success(result):
            models = result.get("models") or []
            self.set_models(models)
            client.close()
            if not models:
                message = "接口返回成功，但没有解析到模型，请确认该服务商是否遵循 OpenAI 的 /models 规范。"
                self.log(message)
                if on_error:
                    on_error(message)
                return
            if on_success:
                on_success(models)

        def failure(message):
            client.close()
            if on_error:
                on_error(message)

        return self.run(Worker(fetch_models_task, client), on_success=success,
                        on_error=failure, name=name)

    # ------------------------------------------------------------ 任务调度
    def is_busy(self):
        return self._worker is not None and self._worker.isRunning()

    def run(self, worker, on_success=None, on_error=None, on_cancel=None, name="任务"):
        """启动后台任务；同一时间只允许一个任务运行。"""
        from ..workers import Worker

        if not isinstance(worker, Worker):
            raise TypeError("worker 必须是 app.workers.Worker 实例")
        if self.is_busy():
            self.log("已有任务正在运行（%s），请等待完成或先点击取消。" % name)
            self.status("已有任务正在运行")
            return False

        self._worker = worker
        self.busy_changed.emit(True)
        self.progress(0, "%s 开始" % name)
        self.log("===== 开始：%s =====" % name)

        def finish():
            self._worker = None
            self.busy_changed.emit(False)

        def handle_success(result):
            finish()
            self.progress(100, "%s 完成" % name)
            self.log("===== 完成：%s =====" % name)
            if on_success:
                on_success(result)

        def handle_error(message):
            finish()
            self.progress(0, "%s 失败" % name)
            self.log("任务失败：%s" % message)
            self.status("任务失败：%s" % message)
            if on_error:
                on_error(message)

        def handle_cancel():
            finish()
            self.progress(0, "已取消")
            self.log("任务已取消：%s" % name)
            self.status("已取消")
            if on_cancel:
                on_cancel()

        worker.progress_changed.connect(self.progress)
        worker.logged.connect(self.log)
        worker.succeeded.connect(handle_success)
        worker.failed.connect(handle_error)
        worker.canceled.connect(handle_cancel)
        worker.finished.connect(worker.deleteLater)
        worker.start()
        return True

    def cancel(self):
        """请求取消当前任务。"""
        if self.is_busy():
            self.status("正在取消当前任务...")
            self._worker.cancel()
            return True
        self.log("当前没有正在运行的任务")
        return False

    def shutdown(self):
        """退出前结束后台线程。"""
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(3000)
