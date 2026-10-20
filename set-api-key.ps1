# Set DeepSeek API key into the current user's environment (input hidden).
# Usage: powershell -ExecutionPolicy Bypass -File .\set-api-key.ps1

$sec = Read-Host "Paste DeepSeek API Key (hidden)" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
$key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)

if ([string]::IsNullOrWhiteSpace($key)) {
    Write-Host "Cancelled."
    exit 1
}

setx DEEPSEEK_API_KEY $key | Out-Null
Write-Host "DEEPSEEK_API_KEY saved."
Write-Host "Close and reopen the terminal, then run:"
Write-Host "  .\.venv\Scripts\python.exe doctor.py --api"
