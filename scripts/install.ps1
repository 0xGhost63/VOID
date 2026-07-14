$ErrorActionPreference = "Stop"

$RepoUrl = "https://github.com/0xGhost63/VOID.git"
$InstallDir = "$env:USERPROFILE\.void-cli"
$BinDir = "$env:USERPROFILE\.void-bin"

Write-Host "Installing VOID..."

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "git is required. Install it and re-run this script."
    exit 1
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "Python is required. Install it and re-run this script."
    exit 1
}

if (Test-Path $InstallDir) {
    Write-Host "Existing install found, updating..."
    git -C $InstallDir pull --quiet
} else {
    git clone --quiet $RepoUrl $InstallDir
}

Set-Location $InstallDir
python -m venv venv
& "$InstallDir\venv\Scripts\pip.exe" install --quiet --upgrade pip
& "$InstallDir\venv\Scripts\pip.exe" install --quiet -r requirements.txt

New-Item -ItemType Directory -Force -Path $BinDir | Out-Null

@"
@echo off
cd /d "$InstallDir"
git pull --quiet
"$InstallDir\venv\Scripts\python.exe" main.py %*
"@ | Set-Content -Path "$BinDir\void.cmd" -Encoding ASCII

$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($UserPath -notlike "*$BinDir*") {
    [Environment]::SetEnvironmentVariable("Path", "$UserPath;$BinDir", "User")
    Write-Host "Added $BinDir to PATH. Restart your terminal for it to take effect."
}

Write-Host ""
Write-Host "VOID installed."
Write-Host "Run it with: void"