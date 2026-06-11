Set ws = CreateObject("WScript.Shell")

ws.Run "cmd /c taskkill /f /im python.exe >nul 2>&1 & taskkill /f /im msedgewebview2.exe >nul 2>&1 & rd /s /q %LOCALAPPDATA%\pywebview >nul 2>&1", 0, True

ws.Run "C:\Users\23625\AppData\Local\Programs\Python\Python311\python.exe src\gui.py", 0
