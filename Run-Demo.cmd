@echo off
setlocal
chcp 65001 >nul
if not exist "%~dp0main.py" goto missing_project
if not exist "%~dp0wechat_archive\cli.py" goto missing_project
if not exist "%~dp0wechat_archive\database\init.sql" goto missing_project
pushd "%~dp0"
if errorlevel 1 goto missing_directory
set "ARCHIVE_PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%ARCHIVE_PYTHON%" set "ARCHIVE_PYTHON=python"
"%ARCHIVE_PYTHON%" "%~dp0main.py" demo
set "ARCHIVE_EXIT=%ERRORLEVEL%"
if "%ARCHIVE_EXIT%"=="0" (
    echo 演示完成：3 位虚构联系人、5 条消息。
    echo 可重复运行。增删改查示例请查看 README.md。
) else (
    echo 演示未完成，请查看上面的错误和 README.md。
)
popd
pause
exit /b %ARCHIVE_EXIT%

:missing_project
echo 项目文件不完整，无法启动演示。
echo 如果你是在 ZIP 压缩包内直接双击本文件，请先关闭此窗口。
echo 右键 ZIP 文件，选择“全部提取”，将整个项目解压到普通文件夹。
echo 再打开解压后的 wechat_archive 文件夹，双击 Run-Demo.cmd。
echo 同一文件夹内应有 main.py，以及 wechat_archive 子文件夹。
pause
exit /b 2

:missing_directory
echo 无法进入项目文件夹，请将完整项目解压到可访问的普通文件夹。
pause
exit /b 2
