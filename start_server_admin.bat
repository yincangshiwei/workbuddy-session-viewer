@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

echo.
echo ============================================================
echo   WorkBuddy 会话查看器 - 管理员模式启动，请稍候...
echo ============================================================
echo.
echo   ⚠ 注意：此为管理员模式，启动后访问页面时请在 URL 末尾
echo     添加 ?admin=true 以进入管理配置界面。
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

cd /d "%~dp0"

git --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   → 未检测到 Git，跳过自动更新...
    goto :SKIP_GIT_PULL
)

if not exist ".git" (
    echo   → 当前目录不是 Git 仓库，跳过自动更新...
    goto :SKIP_GIT_PULL
)

echo   正在连接服务器拉取最新版本，请稍候...
git pull origin master 2>&1
set GIT_RESULT=%errorlevel%

if !GIT_RESULT! neq 0 (
    echo   → 更新失败，使用当前版本继续启动...
) else (
    echo   √ 程序已是最新版本
)

:SKIP_GIT_PULL

:: ============================================================
:: 第三步：自动安装所需组件
:: ============================================================
echo.
echo 【第 3 步 / 共 4 步】检查并安装所需组件...

python -m pip --version >nul 2>&1
if %errorlevel% neq 0 (
    python -m ensurepip --upgrade >nul 2>&1
)

cd /d "%~dp0servers"

if not exist "requirements.txt" (
    echo.
    echo ╔══════════════════════════════════════════════════════╗
    echo ║  提示：程序文件不完整，缺少依赖配置文件。            ║
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
    echo ╚══════════════════════════════════════════════════════╝
    echo.
    pause
    exit /b 1
)

echo   √ 所需组件已就绪

:: ============================================================
:: 第四步：以管理员模式启动服务并自动打开浏览器
:: ============================================================
echo.
echo 【第 4 步 / 共 4 步】以管理员模式启动服务...
echo.

:: 延迟打开浏览器，URL 包含 admin=true 参数
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://localhost:9877?admin=true"

echo ============================================================
echo.
echo   程序已以【管理员模式】成功启动！
echo.
echo   浏览器将在 3 秒后自动打开（管理员界面）。
echo   如果浏览器没有自动打开，请手动访问：
echo.
echo       http://localhost:9877?admin=true
echo.
echo   ※ 请保持此窗口开启，关闭此窗口将停止程序运行。
echo.
echo ============================================================
echo.

:: 设置管理员模式环境变量
set WORKBUDDY_ADMIN=1

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
