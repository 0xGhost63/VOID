$ErrorActionPreference = "Stop"

$Repo       = "0xGhost63/VOID"
$ZipUrl     = "https://github.com/$Repo/archive/refs/heads/main.zip"
$ApiUrl     = "https://api.github.com/repos/$Repo/commits/main"
$WebUrl     = "https://0xghost-void.vercel.app"
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

    # ── stash the commit we just installed, so the launcher doesn't think ────
    # ── an update is available on its very first run ─────────────────────────
    Write-Bar 88 "recording version..."
    try {
        $InstalledCommit = Invoke-RestMethod -Uri $ApiUrl -UseBasicParsing
        if ($InstalledCommit.sha) {
            Set-Content -Path (Join-Path $InstallDir ".void-commit") -Value $InstalledCommit.sha -NoNewline
        }
    } catch {
        # offline / rate-limited — fine, first launch will just check again
    }

    Write-Bar 92 "wiring 'void' command..."
    New-Item -ItemType Directory -Force -Path $BinDir | Out-Null

    # void.cmd just forwards to the PowerShell launcher, which does the real work
    $CmdLauncher = @"
@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0void.ps1" %*
"@
    Set-Content -Path (Join-Path $BinDir "void.cmd") -Value $CmdLauncher -Encoding ASCII

    $Ps1Launcher = @"
`$ErrorActionPreference = "Stop"
`$InstallDir = Join-Path `$env:USERPROFILE ".void-cli"
`$Repo       = "$Repo"
`$ApiUrl     = "$ApiUrl"
`$ZipUrl     = "$ZipUrl"
`$WebUrl     = "$WebUrl"

`$CliArgs = `$args

# -- --web : open the landing page --------------------------------------------
if (`$CliArgs.Count -gt 0 -and `$CliArgs[0] -eq "--web") {
    Start-Process `$WebUrl
    exit 0
}

# -- --delete : wipe all app data ---------------------------------------------
if (`$CliArgs.Count -gt 0 -and `$CliArgs[0] -eq "--delete") {
    Write-Host "This will permanently delete VOID and all its data:"
    Write-Host "  `$InstallDir"
    `$confirm = Read-Host "Are you sure? [y/N]"
    if (`$confirm -match '^(y|yes)$') {
        Remove-Item -Recurse -Force `$InstallDir -ErrorAction SilentlyContinue
        Remove-Item -Force `$PSCommandPath -ErrorAction SilentlyContinue
        Remove-Item -Force (Join-Path (Split-Path `$PSCommandPath) "void.cmd") -ErrorAction SilentlyContinue
        Write-Host "VOID has been removed."
    } else {
        Write-Host "Cancelled."
    }
    exit 0
}

if (-not (Test-Path `$InstallDir)) {
    Write-Host "VOID is not installed. Re-run the installer."
    exit 1
}
Set-Location `$InstallDir

if ((-not (Test-Path ".env")) -and (Test-Path ".env.example")) {
    Copy-Item ".env.example" ".env" -Force
}

# -- check for updates against the latest commit on main ----------------------
try {
    `$Latest = Invoke-RestMethod -Uri `$ApiUrl -UseBasicParsing
    `$LatestSha = `$Latest.sha
    `$LocalSha = ""
    if (Test-Path ".void-commit") { `$LocalSha = (Get-Content ".void-commit" -Raw).Trim() }
    if (`$LatestSha -and (`$LatestSha.Trim() -ne `$LocalSha)) {
        Write-Host "Update found -- updating VOID..."
        `$TmpUpdate = Join-Path `$env:TEMP ("void-update-" + [guid]::NewGuid().ToString("N"))
        New-Item -ItemType Directory -Force -Path `$TmpUpdate | Out-Null
        `$ZipPath = Join-Path `$TmpUpdate "void.zip"
        Invoke-WebRequest -Uri `$ZipUrl -OutFile `$ZipPath -UseBasicParsing
        Expand-Archive -Path `$ZipPath -DestinationPath `$TmpUpdate -Force
        `$UpdSrc = Join-Path `$TmpUpdate "VOID-main"
        if (-not (Test-Path `$UpdSrc)) { `$UpdSrc = Join-Path `$TmpUpdate "VOID-master" }
        if (Test-Path `$UpdSrc) {
            Copy-Item -Path (Join-Path `$UpdSrc "*") -Destination `$InstallDir -Recurse -Force
            Set-Content -Path ".void-commit" -Value `$LatestSha -NoNewline
            `$Pip = Join-Path `$InstallDir "venv\Scripts\pip.exe"
            if ((Test-Path `$Pip) -and (Test-Path "requirements.txt")) {
                & `$Pip install -q --upgrade -r requirements.txt | Out-Null
            }
            Write-Host "Updated to latest version."
        }
        Remove-Item -Recurse -Force `$TmpUpdate -ErrorAction SilentlyContinue
    }
} catch {
    # offline / rate-limited -- just launch what's already installed
}

`$Py = Join-Path `$InstallDir "venv\Scripts\python.exe"
& `$Py "main.py" @CliArgs
"@
    Set-Content -Path (Join-Path $BinDir "void.ps1") -Value $Ps1Launcher -Encoding UTF8

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
    Write-Host "  launch        :  void"
    Write-Host "  open webpage  :  void --web"
    Write-Host "  wipe app data :  void --delete"
    Write-Host ""
}
finally {
    if (Test-Path $TmpDir) {
        Remove-Item -Recurse -Force $TmpDir -ErrorAction SilentlyContinue
    }
}