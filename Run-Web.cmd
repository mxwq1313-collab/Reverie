@echo off
setlocal
chcp 65001 >nul
if not exist "%~dp0main.py" goto missing_project
if not exist "%~dp0wechat_archive\database\init.sql" goto missing_project
if not exist "%~dp0wechat_archive\web\server.py" goto missing_project
if not exist "%~dp0wechat_archive\web\static\index.html" goto missing_project
if not exist "%~dp0wechat_archive\web\static\app.css" goto missing_project
if not exist "%~dp0wechat_archive\web\static\app.js" goto missing_project
pushd "%~dp0"
if errorlevel 1 goto missing_project
set "ARCHIVE_PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%ARCHIVE_PYTHON%" set "ARCHIVE_PYTHON=python"
set "ARCHIVE_DEMO="
if "%~1"=="demo" set "ARCHIVE_DEMO=--demo"
"%ARCHIVE_PYTHON%" "%~dp0main.py" serve %ARCHIVE_DEMO% --open --port 0
set "ARCHIVE_EXIT=%ERRORLEVEL%"
popd
if not "%ARCHIVE_EXIT%"=="0" echo 启动未完成，请查看上面的错误和 README.md。
pause
exit /b %ARCHIVE_EXIT%

:missing_project
echo 项目文件不完整，无法打开聊天浏览器。
echo 请先右键 ZIP 压缩包，选择“全部提取”，完整解压整个项目。
echo 打开解压后的 wechat_archive 文件夹，再双击启动文件。
pause
exit /b 2
