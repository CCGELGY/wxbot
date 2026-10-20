' 隐藏窗口启动 api_bridge.py（使用本目录的 .venv），适合任务计划程序。
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = dir
If Not fso.FolderExists(dir & "\logs") Then fso.CreateFolder(dir & "\logs")
sh.Run "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File """ & dir & "\start-bot.ps1""", 0, False
