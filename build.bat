@echo off
chcp 65001 > nul
setlocal

rem ============================================================
rem  AI API 工具箱 - Windows 单文件 exe 打包脚本
rem  用法：双击运行，或在命令行执行 build.bat
rem  产物：dist\AI-API-Toolbox.exe（无需安装 Python 即可运行）
rem ============================================================

cd /d "%~dp0"

echo [1/4] 检查 Python 环境...
python --version > nul 2>&1
if errorlevel 1 (
    echo 未找到 python 命令，请先安装 Python 3.8 及以上版本并加入 PATH。
    pause
    exit /b 1
)

echo [2/4] 安装 / 更新依赖...
python -m pip install --upgrade pip > nul
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo 依赖安装失败，请检查网络后重试。
    pause
    exit /b 1
)

echo [3/4] 使用 PyInstaller 打包...
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name "AI-API-Toolbox" ^
    --exclude-module tkinter ^
    --exclude-module matplotlib ^
    --exclude-module PyQt5.QtWebEngineWidgets ^
    main.py
if errorlevel 1 (
    echo 打包失败。
    pause
    exit /b 1
)

echo [4/4] 完成！
echo 可执行文件：%cd%\dist\AI-API-Toolbox.exe
echo.
echo 提示：exe 首次运行时会在同目录下创建 data 文件夹，用于保存配置与测试报告。
pause
