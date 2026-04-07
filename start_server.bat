@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

echo.
echo ============================================================
echo   WorkBuddy 会话查看器 - 正在启动，请稍候...
echo ============================================================
echo.

:: ============================================================
:: 第一步：检查电脑是否安装了 Python
:: ============================================================
echo 【第 1 步 / 共 4 步】检测运行环境...

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo ╔══════════════════════════════════════════════════════╗
    echo ║  提示：您的电脑尚未安装 Python，无法启动本程序。     ║
    echo ║                                                      ║
    echo ║  请按以下步骤操作：                                  ║
    echo ║  1. 打开浏览器，访问 https://www.python.org/downloads ║
    echo ║  2. 点击黄色大按钮下载安装包                         ║
    echo ║  3. 运行安装包时，务必勾选底部的                     ║
    echo ║     "Add Python to PATH" 选项                        ║
    echo ║  4. 安装完成后，重新双击本文件启动                   ║
    echo ╚══════════════════════════════════════════════════════╝
    echo.
    pause
    exit /b 1
)

:: 获取版本号
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set VER_FULL=%%v
for /f "tokens=1,2 delims=." %%a in ("!VER_FULL!") do (
    set VER_MAJOR=%%a
    set VER_MINOR=%%b
)

:: 检查版本 >= 3.9
set VER_OK=1
if !VER_MAJOR! LSS 3 set VER_OK=0
if !VER_MAJOR! EQU 3 if !VER_MINOR! LSS 9 set VER_OK=0

if !VER_OK! EQU 0 (
    echo.
    echo ╔══════════════════════════════════════════════════════╗
    echo ║  提示：您的 Python 版本（!VER_FULL!）过旧，          ║
    echo ║  本程序需要 Python 3.9 或更新版本。                  ║
    echo ║                                                      ║
    echo ║  请访问 https://www.python.org/downloads             ║
    echo ║  下载最新版本并重新安装，安装时勾选                  ║
    echo ║  "Add Python to PATH"，完成后重新启动本文件。        ║
    echo ╚══════════════════════════════════════════════════════╝
    echo.
    pause
    exit /b 1
)

echo   √ 运行环境正常（Python !VER_FULL!）

:: ============================================================
:: 第二步：检查 Git 并拉取最新程序
:: ============================================================
echo.
echo 【第 2 步 / 共 4 步】检查并更新程序到最新版本...

:: 先切到项目根目录（bat 所在目录）
cd /d "%~dp0"

:: 检查是否安装了 Git
git --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo ╔══════════════════════════════════════════════════════════╗
    echo ║  提示：未检测到 Git 工具，无法自动更新程序。            ║
    echo ║                                                          ║
    echo ║  Git 是用于自动下载程序更新的工具，不影响程序正常运行。 ║
    echo ║                                                          ║
    echo ║  您可以：                                                ║
    echo ║  · 安装 Git 后重新启动（推荐，以后可自动更新）          ║
    echo ║    下载地址：https://git-scm.com/download/win           ║
    echo ║  · 或直接跳过更新，使用当前已有版本继续启动             ║
    echo ╚══════════════════════════════════════════════════════════╝
    echo.
    set /p GIT_CHOICE=  请输入您的选择：直接按回车跳过更新，或输入 Q 后回车退出安装 Git ^> 
    if /i "!GIT_CHOICE!"=="Q" (
        echo.
        echo   已退出。安装 Git 后重新双击本文件即可自动更新。
        echo.
        pause
        exit /b 0
    )
    echo   → 已跳过更新，使用当前版本继续启动...
    goto :SKIP_GIT_PULL
)

:: 检查当前目录是否是 Git 仓库
if not exist ".git" (
    echo.
    echo ╔══════════════════════════════════════════════════════════╗
    echo ║  提示：当前程序目录不是通过 Git 下载的，无法自动更新。  ║
    echo ║                                                          ║
    echo ║  · 若您是手动下载解压的，可跳过此步骤正常使用           ║
    echo ║  · 若需要自动更新功能，请从以下地址重新下载程序：       ║
    echo ║    https://github.com/yincangshiwei/                     ║
    echo ║            workbuddy-session-viewer.git                  ║
    echo ╚══════════════════════════════════════════════════════════╝
    echo.
    set /p GIT_CHOICE=  请输入您的选择：直接按回车跳过更新，或输入 Q 后回车退出 ^> 
    if /i "!GIT_CHOICE!"=="Q" (
        echo.
        echo   已退出。
        echo.
        pause
        exit /b 0
    )
    echo   → 已跳过更新，使用当前版本继续启动...
    goto :SKIP_GIT_PULL
)

:: 执行 git pull
echo   正在连接服务器拉取最新版本，请稍候...
git pull origin master 2>&1
set GIT_RESULT=%errorlevel%

if !GIT_RESULT! neq 0 (
    echo.
    echo ╔══════════════════════════════════════════════════════════╗
    echo ║  提示：自动更新失败，可能是网络不通或服务器繁忙。       ║
    echo ║                                                          ║
    echo ║  这不影响程序正常运行，您可以：                         ║
    echo ║  · 跳过更新，使用当前已有版本继续启动（推荐）           ║
    echo ║  · 或退出后检查网络连接，稍后重试                       ║
    echo ╚══════════════════════════════════════════════════════════╝
    echo.
    set /p PULL_CHOICE=  请输入您的选择：直接按回车跳过更新继续启动，或输入 Q 后回车退出 ^> 
    if /i "!PULL_CHOICE!"=="Q" (
        echo.
        echo   已退出。请检查网络连接后重新启动。
        echo.
        pause
        exit /b 0
    )
    echo   → 已跳过更新，使用当前版本继续启动...
) else (
    echo   √ 程序已是最新版本
)

:SKIP_GIT_PULL

:: ============================================================
:: 第三步：自动安装所需组件
:: ============================================================
echo.
echo 【第 3 步 / 共 4 步】检查并安装所需组件...
echo   （首次运行需要联网下载，大约需要 1-3 分钟，请耐心等待）

python -m pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   正在初始化包管理工具...
    python -m ensurepip --upgrade >nul 2>&1
    if %errorlevel% neq 0 (
        echo.
        echo ╔══════════════════════════════════════════════════════╗
        echo ║  提示：组件管理工具初始化失败。                      ║
        echo ║  请尝试重新安装 Python，或联系技术支持。             ║
        echo ╚══════════════════════════════════════════════════════╝
        echo.
        pause
        exit /b 1
    )
)

cd /d "%~dp0servers"

if not exist "requirements.txt" (
    echo.
    echo ╔══════════════════════════════════════════════════════╗
    echo ║  提示：程序文件不完整，缺少依赖配置文件。            ║
    echo ║  请重新下载完整的程序包后再试。                      ║
    echo ╚══════════════════════════════════════════════════════╝
    echo.
    pause
    exit /b 1
)

python -m pip install -r requirements.txt --quiet 2>&1
if %errorlevel% neq 0 (
    echo.
    echo ╔══════════════════════════════════════════════════════╗
    echo ║  提示：组件安装失败，可能是网络问题。                ║
    echo ║                                                      ║
    echo ║  请检查：                                            ║
    echo ║  · 电脑是否已连接网络                                ║
    echo ║  · 是否需要关闭代理或 VPN 后重试                    ║
    echo ║  · 如问题持续，请联系技术支持                        ║
    echo ╚══════════════════════════════════════════════════════╝
    echo.
    pause
    exit /b 1
)

echo   √ 所需组件已就绪

:: ============================================================
:: 第四步：启动服务并自动打开浏览器
:: ============================================================
echo.
echo 【第 4 步 / 共 4 步】启动服务，即将自动打开浏览器...
echo.

:: 等待服务启动后再打开浏览器（后台延迟打开）
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://localhost:9877"

echo ============================================================
echo.
echo   程序已成功启动！
echo.
echo   浏览器将在 3 秒后自动打开。
echo   如果浏览器没有自动打开，请手动访问：
echo.
echo       http://localhost:9877
echo.
echo   ※ 请保持此窗口开启，关闭此窗口将停止程序运行。
echo.
echo ============================================================
echo.

python -m uvicorn app.main:app --host 0.0.0.0 --port 9877

:: 服务退出后的提示
echo.
echo ============================================================
echo   程序已停止运行。
echo.
if %errorlevel% neq 0 (
    echo   启动过程中出现错误，请将上方文字截图发给技术支持。
    echo.
)
echo   您可以直接关闭此窗口。
echo ============================================================
echo.
pause

endlocal
