@echo off
chcp 65001 >nul
cd /d "D:\全场基金监测"

echo 清理旧进程...
taskkill /f /im python.exe >nul 2>&1
taskkill /f /im msedgewebview2.exe >nul 2>&1

echo 清除 WebView2 缓存...
if exist "%LOCALAPPDATA%\pywebview" rd /s /q "%LOCALAPPDATA%\pywebview" >nul 2>&1

echo 启动基金监测...
start "" "C:\Users\23625\AppData\Local\Programs\Python\Python311\python.exe" "src\gui.py"
