$ErrorActionPreference = "Stop"

$RepoUrl = "https://github.com/0xGhost63/VOID.git"
$InstallDir = Join-Path $env:USERPROFILE ".void-cli"
$BinDir = Join-Path $env:USERPROFILE ".void-bin"

Write-Host "Installing VOID..."

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "git is required. Install it from https://git-scm.com/downloads and re-run."
    exit 1
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "Python 3.10+ is required. Install it from https://www.python.org/downloads/ and re-run."
    Write-Host "(Make sure 'Add python.exe to PATH' is checked during setup.)"
    exit 1
}

if (Test-Path (Join-Path $InstallDir ".git")) {
    Write-Host "Existing install found, updating..."
    git -C $InstallDir pull --ff-only
    if ($LASTEXITCODE -ne 0) { git -C $InstallDir pull }
} else {
    if (Test-Path $InstallDir) {
        Write-Host "Removing incomplete install at $InstallDir ..."
        Remove-Item -Recurse -Force $InstallDir
    }
    git clone --quiet $RepoUrl $InstallDir
}

Set-Location $InstallDir

# Public app config only — AI calls use the VOID web backend.
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "Created .env from .env.example"
    } else {
        Write-Host "Warning: no .env or .env.example found — login may fail until you add one."
    }
}

python -m venv venv
& "$InstallDir\venv\Scripts\pip.exe" install --quiet --upgrade pip
& "$InstallDir\venv\Scripts\pip.exe" install --quiet -r requirements.txt

New-Item -ItemType Directory -Force -Path $BinDir | Out-Null

$launcher = @"
@echo off
cd /d "$InstallDir"
git pull --ff-only >nul 2>&1
if errorlevel 1 git pull >nul 2>&1
if not exist ".env" if exist ".env.example" copy /Y ".env.example" ".env" >nul
"$InstallDir\venv\Scripts\pip.exe" install --quiet -r requirements.txt >nul 2>&1
"$InstallDir\venv\Scripts\python.exe" main.py %*
"@
Set-Content -Path (Join-Path $BinDir "void.cmd") -Value $launcher -Encoding ASCII

$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($UserPath -notlike "*$BinDir*") {
    [Environment]::SetEnvironmentVariable("Path", "$UserPath;$BinDir", "User")
    Write-Host "Added $BinDir to PATH. Restart your terminal for it to take effect."
}

Write-Host ""
Write-Host "VOID installed to $InstallDir"
Write-Host "Run it with:  void"
