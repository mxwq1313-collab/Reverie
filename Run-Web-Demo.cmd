@echo off
setlocal
chcp 65001 >nul
if not exist "%~dp0Run-Web.cmd" goto missing_project
call "%~dp0Run-Web.cmd" demo
exit /b %ERRORLEVEL%

:missing_project
echo 项目文件不完整，无法打开聊天浏览器。
echo 请先右键 ZIP 压缩包，选择“全部提取”，完整解压整个项目。
echo 打开解压后的 wechat_archive 文件夹，再双击 Run-Web-Demo.cmd。
pause
exit /b 2
