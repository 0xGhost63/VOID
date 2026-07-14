$ErrorActionPreference = "Stop"

$ZipUrl     = "https://github.com/0xGhost63/VOID/archive/refs/heads/main.zip"
$InstallDir = Join-Path $env:USERPROFILE ".void-cli"
$BinDir     = Join-Path $env:USERPROFILE ".void-bin"
$TmpDir     = Join-Path $env:TEMP ("void-install-" + [guid]::NewGuid().ToString("N"))

function Write-Bar {
    param(
        [int]$Percent,
        [string]$Label
    )
    $width  = 28
    $filled = [int]($Percent * $width / 100)
    $empty  = $width - $filled
    $bar    = ("#" * $filled) + ("-" * $empty)
    $line   = ("  [{0}] {1,3}%  {2,-40}" -f $bar, $Percent, $Label)
    Write-Host "`r$line" -NoNewline
    if ($Percent -ge 100) { Write-Host "" }
}

function Die {
    param([string]$Msg)
    Write-Host ""
    Write-Host "!! $Msg"
    exit 1
}

try {
    New-Item -ItemType Directory -Force -Path $TmpDir | Out-Null

    Write-Host ""
    Write-Host "  VOID  —  terminal install"
    Write-Host "  --------------------------------"
    Write-Host "  target : $InstallDir"
    Write-Host "  no git : zip pull from GitHub"
    Write-Host ""

    Write-Bar 5 "checking python..."
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        Die "Python 3.10+ missing — https://www.python.org/downloads/ (tick Add to PATH)"
    }

    Write-Bar 12 "downloading VOID (main)..."
    $ZipPath = Join-Path $TmpDir "void.zip"
    try {
        # Prefer curl.exe if present (shows transfer progress better on Win10+)
        if (Get-Command curl.exe -ErrorAction SilentlyContinue) {
            & curl.exe -fsSL $ZipUrl -o $ZipPath
            if ($LASTEXITCODE -ne 0) { throw "curl failed" }
        } else {
            Invoke-WebRequest -Uri $ZipUrl -OutFile $ZipPath -UseBasicParsing
        }
    } catch {
        Die "download failed — check your network"
    }
    if (-not (Test-Path $ZipPath) -or ((Get-Item $ZipPath).Length -lt 100)) {
        Die "downloaded archive is empty"
    }

    Write-Bar 35 "unpacking archive..."
    Expand-Archive -Path $ZipPath -DestinationPath $TmpDir -Force
    $Src = Join-Path $TmpDir "VOID-main"
    if (-not (Test-Path $Src)) {
        $Src = Join-Path $TmpDir "VOID-master"
    }
    if (-not (Test-Path $Src)) {
        Die "unexpected archive layout from GitHub"
    }

    Write-Bar 48 "staging files..."
    $KeepEnv = $null
    $ExistingEnv = Join-Path $InstallDir ".env"
    if (Test-Path $ExistingEnv) {
        $KeepEnv = Join-Path $TmpDir "saved.env"
        Copy-Item $ExistingEnv $KeepEnv -Force
    }

    if (Test-Path $InstallDir) {
        Remove-Item -Recurse -Force $InstallDir
    }
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    Copy-Item -Path (Join-Path $Src "*") -Destination $InstallDir -Recurse -Force

    $NestedVenv = Join-Path $InstallDir "venv"
    if (Test-Path $NestedVenv) { Remove-Item -Recurse -Force $NestedVenv }
    $NestedGit = Join-Path $InstallDir ".git"
    if (Test-Path $NestedGit) { Remove-Item -Recurse -Force $NestedGit }

    if ($KeepEnv) {
        Copy-Item $KeepEnv (Join-Path $InstallDir ".env") -Force
    } elseif (Test-Path (Join-Path $InstallDir ".env.example")) {
        Copy-Item (Join-Path $InstallDir ".env.example") (Join-Path $InstallDir ".env") -Force
    }

    Set-Location $InstallDir
    if (-not (Test-Path "main.py")) {
        Die "main.py missing after extract — bad archive?"
    }

    Write-Bar 55 "config ready"

    Write-Bar 60 "building virtualenv..."
    python -m venv venv
    $Pip = Join-Path $InstallDir "venv\Scripts\pip.exe"
    $Py  = Join-Path $InstallDir "venv\Scripts\python.exe"
    if (-not (Test-Path $Pip)) { Die "venv creation failed" }

    Write-Bar 72 "upgrading pip..."
    & $Pip install --upgrade pip | Out-Null

    Write-Bar 80 "installing packages (this takes a bit)..."
    & $Pip install -r requirements.txt | Out-Null

    Write-Bar 92 "wiring 'void' command..."
    New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
    $Launcher = @"
@echo off
cd /d "$InstallDir"
if not exist ".env" if exist ".env.example" copy /Y ".env.example" ".env" >nul
"$Py" main.py %*
"@
    Set-Content -Path (Join-Path $BinDir "void.cmd") -Value $Launcher -Encoding ASCII

    $UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($null -eq $UserPath) { $UserPath = "" }
    if ($UserPath -notlike "*$BinDir*") {
        [Environment]::SetEnvironmentVariable("Path", "$UserPath;$BinDir", "User")
        Write-Host ""
        Write-Host "  PATH updated. Open a new terminal so 'void' is picked up."
    }

    Write-Bar 100 "done"
    Write-Host ""
    Write-Host "  installed -> $InstallDir"
    Write-Host "  launcher  -> $(Join-Path $BinDir 'void.cmd')"
    Write-Host ""
    Write-Host "  launch :  void"
    Write-Host "  update :  re-run this installer (your .env is kept)"
    Write-Host "  remove :"
    Write-Host "      Remove-Item -Recurse -Force `$env:USERPROFILE\.void-cli"
    Write-Host "      Remove-Item -Force `$env:USERPROFILE\.void-bin\void.cmd"
    Write-Host ""
}
finally {
    if (Test-Path $TmpDir) {
        Remove-Item -Recurse -Force $TmpDir -ErrorAction SilentlyContinue
    }
}
