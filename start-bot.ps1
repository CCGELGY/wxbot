# Run this checkout's bot. Start and log in to WeChat manually first.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Run install.ps1 first.' }
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'config.json'))) {
    throw 'Copy config.example.json to config.json and configure the group ID first.'
}
if (-not $env:DEEPSEEK_API_KEY) {
    $env:DEEPSEEK_API_KEY = [Environment]::GetEnvironmentVariable('DEEPSEEK_API_KEY', 'User')
}
if (-not $env:DEEPSEEK_API_KEY) { throw 'Run set-api-key.ps1 first.' }
$env:PYTHONUTF8 = '1'
New-Item -ItemType Directory -Path (Join-Path $PSScriptRoot 'logs') -Force | Out-Null
$taskBot = Start-Process -FilePath $taskPython -ArgumentList 'api_bridge.py' `
    -WorkingDirectory $PSScriptRoot -NoNewWindow -PassThru -Wait `
    -RedirectStandardOutput (Join-Path $PSScriptRoot 'logs\bot-stdout.log') `
    -RedirectStandardError (Join-Path $PSScriptRoot 'logs\bot-stderr.log')
exit $taskBot.ExitCode
