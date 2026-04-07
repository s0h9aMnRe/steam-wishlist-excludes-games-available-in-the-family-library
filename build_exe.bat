@echo off
setlocal
chcp 65001 >nul

set "ROOT=%~dp0"
cd /d "%ROOT%"

if not exist ".venv\Scripts\python.exe" (
    echo [1/4] 创建本地虚拟环境...
    python -m venv .venv
    if errorlevel 1 (
        echo 创建虚拟环境失败，请确认已安装 Python 3.12+。
        pause
        exit /b 1
    )
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 (
    echo 激活虚拟环境失败。
    pause
    exit /b 1
)

echo [2/4] 升级 pip...
python -m pip install --upgrade pip
if errorlevel 1 (
    echo pip 升级失败。
    pause
    exit /b 1
)

echo [3/4] 安装轻量依赖...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo 依赖安装失败。
    pause
    exit /b 1
)

echo [4/4] 开始打包...
python -m PyInstaller --noconfirm --clean SteamWishlistChecker.spec
if errorlevel 1 (
    echo 打包失败。
    pause
    exit /b 1
)

echo.
echo 打包完成：dist\SteamWishlistChecker.exe
if exist "dist\SteamWishlistChecker.exe" (
    for %%I in ("dist\SteamWishlistChecker.exe") do echo EXE 大小：%%~zI 字节
)
echo.
pause
