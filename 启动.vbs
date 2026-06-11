Set ws = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' 设置工作目录为脚本所在目录
ws.CurrentDirectory = fso.GetParentFolderName(WScript.ScriptFullName)

' 先杀旧进程，防止重复启动
ws.Run "cmd /c taskkill /f /im python.exe >nul 2>&1 & taskkill /f /im msedgewebview2.exe >nul 2>&1", 0, True

' 等待进程清理完成
WScript.Sleep 500

' 启动程序（隐藏窗口）
ws.Run "C:\Users\23625\AppData\Local\Programs\Python\Python311\python.exe src\gui.py", 0
