@echo off
setlocal
chcp 65001 >nul
if not exist "%~dp0Import-Data.py" goto missing_project
if not exist "%~dp0wechat_archive\ui\import_window.py" goto missing_project
if not exist "%~dp0wechat_archive\database\init.sql" goto missing_project
pushd "%~dp0"
if errorlevel 1 goto missing_project
set "ARCHIVE_PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%ARCHIVE_PYTHON%" set "ARCHIVE_PYTHON=python"
"%ARCHIVE_PYTHON%" "%~dp0Import-Data.py"
set "ARCHIVE_EXIT=%ERRORLEVEL%"
popd
if not "%ARCHIVE_EXIT%"=="0" (
    echo 导入窗口未能启动，请查看上面的错误和 README.md。
    pause
)
exit /b %ARCHIVE_EXIT%

:missing_project
echo 项目文件不完整，无法打开导入窗口。
echo 请右键 ZIP 压缩包选择“全部提取”，完整解压后再双击“导入数据.cmd”。
pause
exit /b 2
