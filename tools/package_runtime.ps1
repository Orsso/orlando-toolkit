Param(
    [string]$OutputDir = "release"
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

# --- Settings ---
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$BuildRoot = Join-Path $RepoRoot 'build'
$StageRoot = Join-Path $BuildRoot 'stage'
$ToolsDir  = Join-Path $BuildRoot 'tools'
$OutDir    = Join-Path $RepoRoot $OutputDir

$ZipBaseName = 'OrlandoToolkit-AppRuntime-win64'
$WinPythonRelease = '5.0.20221030final'
$WinPythonFile    = 'Winpython64-3.10.8.0dot.exe'
$WinPythonUrl     = "https://github.com/winpython/winpython/releases/download/$WinPythonRelease/$WinPythonFile"

# --- Prepare directories ---
New-Item -ItemType Directory -Force -Path $BuildRoot | Out-Null
New-Item -ItemType Directory -Force -Path $StageRoot | Out-Null
New-Item -ItemType Directory -Force -Path $ToolsDir | Out-Null
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

# --- Version from tag ---
if (-not $env:GITHUB_REF) {
    # Local fallback: derive from latest tag or allow manual override
    $tag = (git describe --tags --abbrev=0) 2>$null
    if (-not $tag) { throw "No tag found. Run under CI with GITHUB_REF or create a tag (vX.Y.Z)." }
} else {
    $tag = $env:GITHUB_REF -replace '^refs/tags/', ''
}
if ($tag -notmatch '^v\d+\.\d+\.\d+$') { throw "Tag must be like vX.Y.Z (got '$tag')." }
$Version = $tag.TrimStart('v')

# --- Download WinPython SFX if needed ---
$WinPySfx = Join-Path $ToolsDir $WinPythonFile
if (-not (Test-Path $WinPySfx) -or ((Get-Item $WinPySfx).Length -lt 20000000)) {
    Write-Host "Downloading WinPython..." -ForegroundColor Cyan
    Invoke-WebRequest -UseBasicParsing -Uri $WinPythonUrl -OutFile $WinPySfx
}

# --- Extract WinPython into stage ---
$ExtractDir = Join-Path $StageRoot 'winpython'
if (Test-Path $ExtractDir) { Remove-Item -Recurse -Force $ExtractDir }
New-Item -ItemType Directory -Force -Path $ExtractDir | Out-Null

& $WinPySfx -y -o"$ExtractDir" | Out-Null

# Find python runtime directory (python-*) that contains pythonw.exe
$PythonDir = Get-ChildItem -Path $ExtractDir -Directory -Recurse -ErrorAction SilentlyContinue |
    Where-Object { Test-Path (Join-Path $_.FullName 'pythonw.exe') } |
    Select-Object -First 1
if (-not $PythonDir) { throw "pythonw.exe not found after extracting WinPython." }

# --- Prepare bundle staging layout ---
$BundleRootName = "$ZipBaseName-v$Version"
$BundleRoot = Join-Path $StageRoot $BundleRootName
$BundleRuntime = Join-Path $BundleRoot 'runtime'
$BundleApp     = Join-Path $BundleRoot 'app'

if (Test-Path $BundleRoot) { Remove-Item -Recurse -Force $BundleRoot }
New-Item -ItemType Directory -Force -Path $BundleRuntime | Out-Null
New-Item -ItemType Directory -Force -Path $BundleApp | Out-Null

# Copy runtime (only the python-* directory contents to keep size sane)
Write-Host "Copying Python runtime..." -ForegroundColor Cyan
robocopy "$($PythonDir.FullName)" "$BundleRuntime" /E /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "Failed to copy Python runtime (robocopy exit $LASTEXITCODE)." }

# Ensure pip and install dependencies into runtime
$PythonExe = Join-Path $BundleRuntime 'python.exe'
if (-not (Test-Path $PythonExe)) { throw "python.exe missing in runtime." }

Write-Host "Bootstrapping pip..." -ForegroundColor Cyan
& $PythonExe -m ensurepip --default-pip | Out-Null

$Req = Join-Path $RepoRoot 'requirements.txt'
if (Test-Path $Req) {
    Write-Host "Installing requirements..." -ForegroundColor Cyan
    & $PythonExe -m pip install --quiet --no-cache-dir --disable-pip-version-check -r "$Req" | Out-Null
}

# Copy app code
Write-Host "Staging app files..." -ForegroundColor Cyan
$AppFiles = @('run.py', 'orlando_toolkit', 'assets')
foreach ($f in $AppFiles) {
    $src = Join-Path $RepoRoot $f
    if (Test-Path $src) {
        if ((Get-Item $src).PSIsContainer) {
            robocopy "$src" "$BundleApp\$f" /E /NFL /NDL /NJH /NJS /NP | Out-Null
            if ($LASTEXITCODE -ge 8) { throw "Failed to copy folder $f (robocopy exit $LASTEXITCODE)." }
        } else {
            Copy-Item -LiteralPath $src -Destination (Join-Path $BundleApp (Split-Path $src -Leaf)) -Force
        }
    }
}

# Write version.txt
"$Version" | Out-File -Encoding ASCII -NoNewline -FilePath (Join-Path $BundleApp 'version.txt')

# Create launch.cmd
$LaunchCmd = @"
@echo off
setlocal
set "RUNTIME=%~dp0runtime"
set "APPDIR=%~dp0app"
"%RUNTIME%\pythonw.exe" "%APPDIR%\run.py"
exit /b %errorlevel%
"@
$LaunchPath = Join-Path $BundleRoot 'launch.cmd'
$LaunchCmd | Out-File -Encoding ASCII -NoNewline -FilePath $LaunchPath

# --- Create ZIPs ---
$ZipVersioned = Join-Path $OutDir "$ZipBaseName-v$Version.zip"

if (Test-Path $ZipVersioned) { Remove-Item -Force $ZipVersioned }

Write-Host "Creating ZIP (versioned)..." -ForegroundColor Cyan
Compress-Archive -LiteralPath $BundleRoot -DestinationPath $ZipVersioned -Force


# --- SHA256 files ---
Write-Host "Computing SHA256..." -ForegroundColor Cyan
$HashV = (Get-FileHash -Algorithm SHA256 -LiteralPath $ZipVersioned).Hash

"$HashV *$($ZipVersioned | Split-Path -Leaf)" | Out-File -Encoding ASCII -NoNewline -FilePath (Join-Path $OutDir "$(Split-Path $ZipVersioned -Leaf).sha256")

Write-Host "Done. Output in: $OutDir" -ForegroundColor Green
