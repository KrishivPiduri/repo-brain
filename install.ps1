# repo-brain installer — Windows (PowerShell)
# Usage: irm <url-to-this-file> | iex
#
# If you get an execution policy error, run this first:
#   Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
$ErrorActionPreference = "Stop"

$GithubRepo = "https://github.com/KrishivPiduri/repo-brain"
$InstallDir = "$env:USERPROFILE\.repo-brain"
$BinDir     = "$env:USERPROFILE\.local\bin"
$ZipPath    = "$InstallDir\repo-brain.zip"

function Write-Green($msg) { Write-Host $msg -ForegroundColor Green }
function Write-Red($msg)   { Write-Host $msg -ForegroundColor Red }
function Write-Bold($msg)  { Write-Host $msg -ForegroundColor White }

# ---- Python check ----------------------------------------------------------
$Python = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd -c "import sys; print(sys.version_info >= (3,10))" 2>$null
        if ($ver -eq "True") { $Python = $cmd; break }
    } catch {}
}
if (-not $Python) {
    Write-Red "error: Python 3.10+ is required."
    Write-Host "  Download from https://python.org  (check 'Add to PATH' during install)"
    exit 1
}

Write-Bold "Installing repo-brain..."
$pyVer = & $Python --version
Write-Host "  Python: $pyVer"

# ---- download latest release -----------------------------------------------
$LatestUrl = "$GithubRepo/releases/latest/download/repo-brain.zip"
Write-Host "  Downloading $LatestUrl"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Invoke-WebRequest -Uri $LatestUrl -OutFile $ZipPath -UseBasicParsing

# ---- unzip -----------------------------------------------------------------
Write-Host "  Extracting..."
Expand-Archive -Path $ZipPath -DestinationPath $InstallDir -Force
Remove-Item $ZipPath

# ---- virtual environment ---------------------------------------------------
Write-Host "  Creating virtual environment..."
& $Python -m venv "$InstallDir\.venv"
& "$InstallDir\.venv\Scripts\pip.exe" install -q --upgrade pip
& "$InstallDir\.venv\Scripts\pip.exe" install -q -r "$InstallDir\requirements.txt"

# ---- launcher script (.cmd) ------------------------------------------------
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
$launcher = "@echo off`r`n`"$InstallDir\.venv\Scripts\python.exe`" `"$InstallDir\main.py`" %*`r`n"
Set-Content -Path "$BinDir\repo-brain.cmd" -Value $launcher -Encoding ASCII

# ---- PATH update -----------------------------------------------------------
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$BinDir*") {
    [Environment]::SetEnvironmentVariable("Path", "$BinDir;$userPath", "User")
    Write-Host "  Added $BinDir to your PATH (restart your terminal to apply)"
}

Write-Green "`nDone! repo-brain installed."
Write-Host ""
Write-Host "  Set your API key (PowerShell):"
Write-Host "    `$env:OPENAI_API_KEY = 'sk-...'"
Write-Host "    # or ANTHROPIC_API_KEY, DEEPSEEK_API_KEY, GEMINI_API_KEY, etc."
Write-Host ""
Write-Host "  Or set it permanently:"
Write-Host "    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', 'sk-...', 'User')"
Write-Host ""
Write-Host "  Run on any repo (restart terminal first if PATH was just updated):"
Write-Host "    repo-brain C:\path\to\your\repo"
Write-Host "    repo-brain C:\path\to\your\repo --model claude-3-5-haiku-20241022"
Write-Host "    repo-brain C:\path\to\your\repo --no-llm"
Write-Host ""
Read-Host "Press Enter to exit"
