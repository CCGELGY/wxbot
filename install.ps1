$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    py -3.10 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.10 x64 with the Python launcher first.' }
}
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
& $taskPython -c "import sys; assert sys.version_info[:2] == (3,10) and sys.maxsize > 2**32, 'Python 3.10 x64 required for the tested setup'"
if ($LASTEXITCODE -ne 0) { throw 'Unexpected Python version or architecture.' }
& $taskPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
Write-Host 'Installed. Copy config.example.json to config.json, then follow README.md.'
