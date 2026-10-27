# AI API 工具箱（AI-API-Toolbox）

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)
![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-lightgrey.svg)

一个面向 **OpenAI 兼容接口** 的 Windows 桌面测试工具：填入 API 地址与 API Key 后，
可以自动获取模型列表、测量网络延迟与稳定性、测试每个模型的首 Token 时间与生成速度，
并生成可导出的测试报告。基于 Python + PyQt5 开发，使用 PyInstaller 打包为**单个 exe**，
双击即可运行，无需安装。

---

## 一、项目目录结构

```
AI-API测试工具/
├── main.py                       # 程序入口（含 --self-check 无界面自检模式）
├── requirements.txt              # 依赖清单
├── build.bat                     # 一键打包脚本（PyInstaller）
├── AI-API-Toolbox.spec           # PyInstaller 生成的配置（可重复执行打包）
├── README.md                     # 使用说明（本文件）
├── app/                          # 核心代码
│   ├── __init__.py               # 应用名、版本号
│   ├── paths.py                  # 运行时目录解析（源码 / exe 统一）
│   ├── crypto_utils.py           # API Key 加密存储（Fernet + 机器绑定密钥）
│   ├── config.py                 # 多组 API 配置读写（data/config.json）
│   ├── api_client.py             # 网络请求封装：/models、/chat/completions、延迟探测
│   ├── stats.py                  # 延迟 / 速度 / 稳定性统计（百分位、错误分布）
│   ├── tasks.py                  # 后台任务实现（获取模型、延迟、速度、稳定性）
│   ├── workers.py                # QThread 异步任务框架（不阻塞 UI）
│   ├── database.py               # SQLite 报告存储（data/ai_api_toolbox.db）
│   ├── report.py                 # 报告生成与 JSON / CSV / Markdown 导出
│   ├── selfcheck.py              # 无界面自检流程（命令行与 exe 均可调用）
│   ├── theme.py                  # 暗黑 / 浅色主题
│   └── ui/                       # 界面层
│       ├── main_window.py        # 主窗口：顶部配置 + 左侧导航 + 内容区 + 底部状态栏
│       ├── context.py            # 共享上下文（配置、数据库、模型缓存、任务调度）
│       ├── widgets/              # 通用控件
│       │   ├── common.py         # 统一风格的标签 / 表单 / 表格
│       │   ├── stat_card.py      # 指标卡片（平均延迟、成功率…）
│       │   ├── chart.py          # 自绘柱状图（无第三方绘图依赖）
│       │   └── model_selector.py # 模型下拉单选 / 下拉多选控件
│       └── pages/                # 功能页面（一个功能一个文件）
│           ├── base.py           # 页面基类
│           ├── models_page.py    # 模型列表
│           ├── latency_page.py   # 延迟测试
│           ├── speed_page.py     # 模型速度测试
│           ├── stability_page.py # 稳定性测试
│           └── report_page.py    # 测试报告
└── tools/
    ├── self_check.py             # 命令行自检脚本
    ├── gui_smoke.py              # 界面冒烟测试（离屏运行，不需要真实接口）
    └── mock_api_server.py        # 本地模拟 OpenAI 接口（无需真实 Key 也能试跑）
examples/                         # 脱敏示例（配置结构与报告格式样例）
├── config.example.json
└── report.example.json
.gitignore                        # 排除 data/ dist/ build/ 等运行时数据
LICENSE                           # MIT 许可证
```

> 打包过程中还会生成 `build/`（中间文件）与 `dist/AI-API-Toolbox.exe`（最终产物）。

运行后自动生成的数据目录（源码运行在项目根目录，exe 运行在 exe 同目录）：

```
data/
├── config.json            # 多组 API 配置（API Key 为密文）
├── vault.salt             # 加密用随机盐（删除后已保存的 Key 需重新填写）
├── ai_api_toolbox.db      # 历史测试报告（SQLite）
├── exports/               # 报告默认导出目录
└── logs/app.log           # 运行日志
```

---

## 二、环境要求

- Windows 10 / 11（64 位）
- Python 3.8 及以上（仅源码运行或自行打包时需要）
- 依赖：PyQt5、requests、cryptography、pyinstaller

```bat
pip install -r requirements.txt
```

---

## 三、运行方式

### 1. 源码运行

```bat
python main.py
```

### 2. 直接运行 exe

双击 `dist\AI-API-Toolbox.exe`（无需安装 Python）。

### 3. 命令行自检（可选）

```bat
python tools\self_check.py --base-url https://api.openai.com/v1 --api-key sk-xxx --count 5
```

打包后的 exe 同样支持自检（无控制台，结果写入 `data\logs\selfcheck.log`）：

```bat
AI-API-Toolbox.exe --self-check --base-url https://api.deepseek.com/v1 --api-key sk-xxx --count 5
```

---

## 四、功能说明

### 1. API 配置

- 顶部配置区填写 **Base URL**（如 `https://api.openai.com/v1`）与 **API Key**，点击「保存配置」。
  Base URL 会自动规整：自动去掉末尾 `/`，误填 `/chat/completions`、`/models` 也能识别。
- **多组配置档案**：可为 OpenAI、DeepSeek、通义、本地 Ollama 等服务商各保存一组配置，随时切换。
- **本地加密存储**：API Key 使用 Fernet 对称加密，密钥由「机器唯一标识 + 当前用户名 + 随机盐」
  经 PBKDF2-HMAC-SHA256（20 万次迭代）派生，`config.json` 中不会出现明文；
  把配置复制到其它电脑也无法解密，需要重新填写。
- **测试连接**：一键验证地址与 Key 是否可用，兼容不提供 `/models` 的服务商。
- **代理**：如需通过代理访问，在「代理」输入框填写，例如 `http://127.0.0.1:7890`。

### 2. 模型列表

- 调用 `GET {Base URL}/models`，解析模型 ID、所属者、创建时间等字段并以表格展示。
- 支持关键字过滤、复制选中模型 ID、导出 JSON / CSV。
- 若服务商不支持 `/models`（返回 404/405），会给出友好提示，并引导手动填写模型名。
- **获取到的模型会自动填充到后续各测试页面的「模型」下拉框中**，无需重复输入。

### 3. 延迟测试

- 可设置测试次数（默认 10 次）、并发数、超时时间，请求目标可选：
  **轻量请求 `/models`**（几乎不消耗额度）或 **对话接口 `/chat/completions`**。
- 选择「对话接口」时，模型通过**下拉框**选择（已自动填入已获取的模型，也可手动输入，
  并可点击「获取模型」直接刷新列表）。
- 输出指标：平均 / 最小 / 最大延迟、**P50 / P90 / P95 / P99**、标准差、成功率、失败次数、超时次数。
- 同时生成每次请求耗时的柱状图与明细表（含 HTTP 状态与错误原因）。

### 4. 模型速度测试

- 模型使用**下拉多选**：点击「选择模型」展开菜单勾选（支持「全选 / 全不选」），
  菜单底部可手动输入接口未提供的模型名；「获取模型」按钮可直接刷新模型列表。
- 使用固定 Prompt（默认「请用一句话介绍人工智能。」），
  可自定义 Prompt、`max_tokens`、`temperature`、超时时间。
- 记录指标：**首 Token 时间（TTFT）**、完整响应时间、输出 Token 数、**每秒输出 Token 数**、
  是否成功、错误信息、**是否支持流式** / **是否支持非流式**、接口返回的用量（usage）信息。
- 流式请求逐块读取 SSE，首 Token 时间真实可信；若接口未返回 usage，会按中英文规则估算 Token 数并标注。
- 点击结果行可查看该模型的返回内容与用量详情；图表对比各模型的 tok/s。

### 5. 稳定性测试

- 测试模型同样通过**下拉框**选择（可手动输入，可一键获取模型列表）。
- 可设置测试次数（5 / 10 / 20 / 50，也可自定义）、并发数、超时时间、Prompt 与 `max_tokens`。
- 统计：成功率、失败率、平均延迟、P50 / P95 / P99、**错误类型分布**（超时、鉴权失败、404、
  429 限流、5xx 服务端错误、网络异常等）、**是否触发限流**、**是否触发内容审核**。

### 6. 测试报告

- 每次测试完成后自动写入本地 SQLite 数据库，随时回看。
- 报告内容：测试时间、API 地址、模型名称、延迟统计、速度统计、稳定性统计、错误详情。
- 支持导出 **JSON / CSV / Markdown**，也可在「文件 → 导出全部报告」中批量导出历史记录。

### 7. 界面与交互

- 布局：顶部 API 配置区、左侧功能导航、中间内容区、底部状态栏（状态文字 + 进度条 + 日志面板 + 取消任务）。
- 支持 **暗黑 / 浅色主题**切换（视图菜单），偏好会被记住。
- 模型下拉框（模型列表 / 延迟 / 速度 / 稳定性各页）在获取模型后自动填充，也可直接输入；
  下拉箭头与微调按钮箭头由程序自绘（`app/ui/widgets/common.py`），两种主题下都清晰可见。
- 所有网络请求都在后台线程执行（QThread / 线程池），界面不卡顿；任务可随时取消。

---

## 五、打包为单个 exe

执行打包脚本（推荐）：

```bat
build.bat
```

或手动执行 PyInstaller 命令：

```bat
pyinstaller --onefile --windowed --name "AI-API-Toolbox" main.py
```

产物位于 `dist\AI-API-Toolbox.exe`，可在**没有 Python 环境**的 Windows 电脑上直接双击运行。

打包说明：

- `--onefile` 打成单文件，`--windowed` 不显示黑色控制台窗口。
- 不需要额外的资源文件：程序图标由代码绘制，data 目录在首次运行时自动创建。
- 若需自定义图标，把 `app.ico` 放到项目根目录，并给命令加上 `--icon app.ico`。

---

## 六、常见问题

| 现象 | 原因与解决办法 |
| --- | --- |
| 提示「鉴权失败」 | API Key 不正确或已失效；注意部分服务商 Key 需要加上 `Bearer` 之外的额外参数 |
| 提示「接口/模型不存在」 | Base URL 或模型名不对；Base URL 应为 `https://xxx/v1` 形式 |
| 提示「该接口不支持 /models」 | 部分服务商（或本地部署）未实现该接口，可在各测试页面的模型下拉框中手动输入模型名 |
| 提示「触发限流」(429) | 并发过高或额度受限，降低并发数与测试次数后重试 |
| 提示「请求超时」 | 网络较慢或模型较慢，适当增大超时时间（本地大模型常需 120 秒以上） |
| 首 Token 时间显示为 `-` | 该模型不支持流式输出，工具会自动改用非流式指标 |
| 换电脑后 Key 无法解密 | 加密密钥与本机绑定，属于设计行为，重新填写一次即可 |
| exe 启动后界面没反应 | 查看 `data\logs\app.log` 中的错误信息 |

---

## 七、开发者提示

- 想在无真实 API Key 的情况下试跑：先启动本地模拟接口，再在软件里把地址填成
  `http://127.0.0.1:8899/v1`、Key 随意填写。

  ```bat
  python tools\mock_api_server.py --port 8899 --latency 0.1 --fail-rate 0.15
  ```

- 各模块职责单一、彼此解耦：新增测试项只需在 `app/tasks.py` 增加任务函数、
  在 `app/ui/pages/` 增加页面，并在 `app/ui/main_window.py` 注册导航项即可。
- 改动界面后可跑一遍界面冒烟测试（26 项断言，含下拉箭头像素校验）：

  ```bat
  python tools\gui_smoke.py
  ```

---

## 八、数据与隐私

本仓库**不包含任何真实的 API Key、接口地址与测试记录**。

`data/`、`dist/`、`build/` 以及所有 `*.db` / `*.salt` / `*.log` 文件均已写入 `.gitignore`，
它们只存在于本地。其中：

| 文件 | 为什么不能提交 |
| --- | --- |
| `data/config.json` | 含配置档案与 API Key 密文 |
| `data/vault.salt` | 加密用随机盐，与密文同时泄露则等同明文 |
| `data/ai_api_toolbox.db` | 历史测试报告，含被测接口地址与调用记录 |
| `data/logs/app.log` | 运行日志，含脱敏 Key 片段与本地绝对路径 |

想在本地复现界面效果，可把 `examples/` 下的示例文件复制到 `data/` 使用：

```bat
copy examples\config.example.json data\config.json
```

- `examples/config.example.json`：配置结构示例，地址均为占位域名，Key 为空字符串。
- `examples/report.example.json`：一份延迟测试报告的结构示例，用于对照导出格式。

> 若曾把含真实数据的版本提交过，仅靠删除文件是不够的，历史提交里仍留有副本，
> 需要改写提交历史（如 `git filter-repo`）并**立即在服务商处轮换该 Key**。

---

## 九、许可证

本项目基于 [MIT License](LICENSE) 开源，Copyright (c) 2026 Pia-JI。

简单来说，你可以自由地使用、修改、分发甚至商用本项目，**唯一的要求是保留原始版权声明
与许可证声明**。软件按「现状」提供，作者不承担任何担保责任——例如因测试行为产生的
API 调用费用，需由使用者自行承担。
