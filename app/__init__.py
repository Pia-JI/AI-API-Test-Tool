"""AI API 工具箱（AI API Toolbox）核心包。

模块划分：
    paths         运行时目录解析（源码运行 / exe 打包运行统一入口）
    crypto_utils  API Key 本地加密存储
    config        多组 API 配置的读写与管理
    api_client    OpenAI 兼容接口的网络请求封装（模型列表 / 延迟 / 对话）
    stats         延迟、速度、稳定性指标的统计计算
    tasks         后台任务的具体实现（在子线程中执行）
    workers       QThread 异步任务框架（不阻塞 UI）
    database      SQLite 报告存储
    report        测试报告的结构化生成与 JSON / CSV / Markdown 导出
    theme         暗黑 / 浅色主题
    ui            界面层（主窗口、功能页面、通用控件）
"""

__version__ = "1.0.0"
APP_NAME = "AI API 工具箱"
APP_ID = "AI-API-Toolbox"
