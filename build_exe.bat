@echo off
chcp 65001
echo 正在设置控制台编码为UTF-8...
echo.

echo 检查Python环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到Python，请先安装Python 3.7或更高版本
    pause
    exit /b 1
)

echo 检查PyInstaller...
pip list | findstr "pyinstaller" >nul 2>&1
if errorlevel 1 (
    echo 安装PyInstaller...
    pip install pyinstaller
    if errorlevel 1 (
        echo 错误: PyInstaller安装失败
        pause
        exit /b 1
    )
)

echo 检查easyocr...
pip list | findstr "easyocr" >nul 2>&1
if errorlevel 1 (
    echo 安装easyocr...
    pip install easyocr
    if errorlevel 1 (
        echo 错误: easyocr安装失败
        pause
        exit /b 1
    )
)

echo 开始打包Steam愿望单检查工具...
echo.

set SCRIPT_PATH=steamwishlist_v1.00.py
set ICON_PATH=icon.ico
set OUTPUT_NAME=SteamWishlistChecker

if not exist "%SCRIPT_PATH%" (
    echo 错误: 找不到源代码文件 %SCRIPT_PATH%
    pause
    exit /b 1
)

if not exist "%ICON_PATH%" (
    echo 警告: 找不到图标文件 %ICON_PATH%，将使用默认图标
    set ICON_OPTION=
) else (
    set ICON_OPTION=--icon="%ICON_PATH%"
)

echo 创建PyInstaller spec文件...
pyi-makespec --onefile --windowed %ICON_OPTION% --name="%OUTPUT_NAME%" "%SCRIPT_PATH%"

if errorlevel 1 (
    echo 错误: 创建spec文件失败
    pause
    exit /b 1
)

echo 修改spec文件以包含easyocr模型...
powershell -Command "
$specContent = Get-Content -Path '%OUTPUT_NAME%.spec' -Raw
$newContent = $specContent -replace 'datas=\[\]', 'datas=[(r''C:\Users\DESKTOP-43TDRJE\Desktop\steamwishlist\easyocr'', ''easyocr'')]'
$newContent | Set-Content -Path '%OUTPUT_NAME%.spec'
"

echo 使用修改后的spec文件打包...
pyinstaller "%OUTPUT_NAME%.spec"

if errorlevel 1 (
    echo 错误: 打包失败
    pause
    exit /b 1
)

echo.
echo 打包完成！
echo 可执行文件位置: dist\%OUTPUT_NAME%.exe
echo.
echo 清理临时文件...
if exist build rmdir /s /q build
if exist "%OUTPUT_NAME%.spec" del "%OUTPUT_NAME%.spec"

echo.
echo 生成运行批处理文件...
echo @echo off > "运行Steam愿望单检查工具.bat"
echo chcp 65001 >> "运行Steam愿望单检查工具.bat"
echo title Steam愿望单检查工具 >> "运行Steam愿望单检查工具.bat"
echo echo 正在启动Steam愿望单检查工具... >> "运行Steam愿望单检查工具.bat"
echo echo. >> "运行Steam愿望单检查工具.bat"
echo dist\%OUTPUT_NAME%.exe >> "运行Steam愿望单检查工具.bat"
echo pause >> "运行Steam愿望单检查工具.bat"

echo 完成！您现在可以:
echo 1. 直接运行 dist\%OUTPUT_NAME%.exe
echo 2. 或运行 "运行Steam愿望单检查工具.bat"
echo.
pause
