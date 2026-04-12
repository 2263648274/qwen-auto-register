param(
    [switch]$SkipInstall,
    [ValidateSet("web", "gui")]
    [string]$Mode = "web",
    [int]$Port = 18080
)

$ErrorActionPreference = "Stop"

function Write-Step { param([string]$Msg) Write-Host "`n==> $Msg" -ForegroundColor Cyan }
function Write-Ok { param([string]$Msg) Write-Host "OK: $Msg" -ForegroundColor Green }
function Write-Warn { param([string]$Msg) Write-Host "WARN: $Msg" -ForegroundColor Yellow }
function Write-Err { param([string]$Msg) Write-Host "ERROR: $Msg" -ForegroundColor Red }

# 1) Resolve project root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

Write-Step "Switch to project root"
Set-Location $ProjectRoot
Write-Ok "ProjectRoot = $ProjectRoot"

# 2) Find Python launcher
Write-Step "Check Python"
$pythonCmd = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonCmd = "py"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCmd = "python"
}

if (-not $pythonCmd) {
    Write-Err "Python not found. Install Python 3.10+ first. Example: winget install -e --id Python.Python.3.12"
    exit 1
}

try {
    $ver = & $pythonCmd -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"
    Write-Ok "Python $ver"
} catch {
    Write-Err "Cannot execute Python: $($_.Exception.Message)"
    exit 1
}

# 3) Create virtualenv if missing
$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Step "Create virtual environment (.venv)"
    & $pythonCmd -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Failed to create virtual environment"
        exit 1
    }
    Write-Ok "Virtual environment created"
} else {
    Write-Ok "Virtual environment already exists"
}

if (-not (Test-Path $venvPython)) {
    Write-Err "Virtual environment Python not found: $venvPython"
    exit 1
}

# 4) Install deps unless skipped
if (-not $SkipInstall) {
    Write-Step "Install or update dependencies"
    & $venvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Failed to upgrade pip"
        exit 1
    }

    & $venvPython -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Failed to install requirements"
        exit 1
    }

    & $venvPython -m playwright install chromium
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Failed to install Playwright Chromium"
        exit 1
    }

    & $venvPython -m pip install -e .
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Failed to install project in editable mode"
        exit 1
    }
    Write-Ok "Dependencies ready"
} else {
    Write-Warn "Skipped dependency installation (-SkipInstall)"

    $oldEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $venvPython -c "import customtkinter, playwright, httpx, fastapi, uvicorn" *> $null
    $depExit = $LASTEXITCODE
    $ErrorActionPreference = $oldEap

    if ($depExit -ne 0) {
        Write-Err "Dependencies are missing in .venv. Run .\\scripts\\start.ps1 once without -SkipInstall."
        exit 1
    }
}

# 5) Build launch args
$launchArgs = @("-m", "auto_register", "--mode", $Mode)

if ($Mode -eq "web") {
    $launchArgs += @("--host", "0.0.0.0", "--port", "$Port")
}

# Ensure module is importable even when editable install is skipped.
$env:PYTHONPATH = Join-Path $ProjectRoot "src"

# 6) Launch app
Write-Step "Launch AutoRegister"
Write-Host "$venvPython $($launchArgs -join ' ')" -ForegroundColor DarkGray
if ($Mode -eq "web") {
    Write-Ok "Web UI: http://127.0.0.1:$Port"
}
& $venvPython @launchArgs
exit $LASTEXITCODE
