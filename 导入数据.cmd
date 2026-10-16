@echo off
setlocal
chcp 65001 >nul
if not exist "%~dp0Import-Data.cmd" goto missing_project
call "%~dp0Import-Data.cmd"
exit /b %ERRORLEVEL%

:missing_project
echo 项目文件不完整，请先完整解压 ZIP，再打开“导入数据.cmd”。
pause
exit /b 2
