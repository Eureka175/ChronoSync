# Build a self-contained Windows release package and (optionally) publish it.
#
#   pwsh -File packaging/build_release.ps1                 # build only
#   pwsh -File packaging/build_release.ps1 -Publish        # build + GitHub prerelease
#
# Outputs:
#   dist/                                  sdist + wheel
#   release/wheelhouse/                    offline dependency wheels (cp311 win_amd64)
#   release/ChronoSync-<release>-win64-selfcontained/    assembled package
#   release/ChronoSync-<release>-win64-selfcontained.zip
#   release/SHA256SUMS.txt

param(
    [string]$Python = "C:\Users\吴汶睿\AppData\Local\Programs\Python\Python311\python.exe",
    [string]$Release = "v0.1.0-beta.2",
    [string]$PepVersion = "0.1.0b0",
    [string]$PyTarget = "3.11",
    [string]$Platform = "win_amd64",
    [switch]$SkipExe,
    [switch]$Publish,
    [switch]$Prerelease
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
Write-Host "repo: $repo"

if (-not (Test-Path $Python)) { throw "python not found: $Python" }

# ---------------------------------------------------------------- 1) sdist + wheel
Write-Host "`n[1/6] building sdist + wheel ..."
Remove-Item -Recurse -Force dist -ErrorAction SilentlyContinue
& $Python -m build --no-isolation --outdir dist
if ($LASTEXITCODE -ne 0) { throw "build failed" }

# ---------------------------------------------------------------- 2) wheelhouse
Write-Host "`n[2/6] downloading offline dependency wheels ..."
$wheelhouse = "release/wheelhouse"
Remove-Item -Recurse -Force $wheelhouse -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $wheelhouse | Out-Null
& $Python -m pip download --quiet --only-binary=:all: `
    --python-version $PyTarget --implementation cp --platform $Platform `
    --dest $wheelhouse numpy scipy soundfile soxr psutil
if ($LASTEXITCODE -ne 0) { throw "pip download failed" }
Copy-Item "dist/chronosync-$PepVersion-py3-none-any.whl" $wheelhouse

# ---------------------------------------------------------------- 3) executable
$stage = "release/ChronoSync-$Release-win64-selfcontained"
Remove-Item -Recurse -Force $stage -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force "$stage/bin" | Out-Null
if (-not $SkipExe) {
    Write-Host "`n[3/6] building self-contained chronosync.exe (PyInstaller) ..."
    & $Python -m PyInstaller --noconfirm --clean --onefile --name chronosync `
        --paths src `
        --collect-all soundfile --collect-all soxr `
        --collect-submodules chronosync `
        --exclude-module pytest --exclude-module matplotlib `
        --distpath "$stage/bin" --workpath build/pyinstaller --specpath build/pyinstaller `
        packaging/entry_chronosync.py
    if ($LASTEXITCODE -ne 0) { throw "pyinstaller failed" }
} else {
    Write-Host "`n[3/6] skipped executable build (-SkipExe)"
}

# ---------------------------------------------------------------- 4) assemble
Write-Host "`n[4/6] assembling package ..."
Copy-Item packaging/README-FIRST.txt "$stage/README-FIRST.txt"
Copy-Item LICENSE, README.md, README.zh-CN.md, CHANGELOG.md $stage
Copy-Item -Recurse $wheelhouse "$stage/wheelhouse"
Copy-Item dist/chronosync-$PepVersion.tar.gz, dist/chronosync-$PepVersion-py3-none-any.whl $stage
New-Item -ItemType Directory -Force "$stage/docs" | Out-Null
Copy-Item docs/*.md "$stage/docs"
Copy-Item -Recurse docs/adr "$stage/docs/adr"
New-Item -ItemType Directory -Force "$stage/handoff" | Out-Null
Copy-Item -Recurse handoff/mp4_channel_sync "$stage/handoff/mp4_channel_sync"

@"
ChronoSync $Release
PEP 440 version : $PepVersion
Built (UTC)     : $((Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ"))
Built with      : $((& $Python --version) 2>&1) on $Platform
Contents        : bin/chronosync.exe (self-contained), wheelhouse/ (offline wheels),
                  chronosync sdist + wheel, docs/, handoff/, README-FIRST.txt
"@ | Set-Content -Encoding UTF8 "$stage/VERSION.txt"

@"
@echo off
rem Offline install from the bundled wheelhouse (no network required).
setlocal
set PY=python
if not "%~1"=="" set PY=%~1
%PY% -m pip install --no-index --find-links "%~dp0wheelhouse" "chronosync[io,dev]"
if errorlevel 1 (
  echo.
  echo Install failed. Pass a Python 3.11+ interpreter path as the first argument,
  echo e.g.  install-offline.bat C:\Python311\python.exe
) else (
  echo.
  echo Installed. Try:  chronosync --version
)
endlocal
"@ | Set-Content -Encoding ASCII "$stage/install-offline.bat"

# examples: reuse the demo generator output if present, otherwise skip
if (Test-Path "demo/align_ref.wav") {
    New-Item -ItemType Directory -Force "$stage/examples" | Out-Null
    Copy-Item demo/align_ref.wav, demo/align_tgt.wav "$stage/examples"
}

# ---------------------------------------------------------------- 5) checksums
Write-Host "`n[5/6] computing checksums ..."
$sums = Get-ChildItem -Recurse -File $stage | Where-Object { $_.Name -ne "SHA256SUMS.txt" } |
    ForEach-Object {
        $rel = $_.FullName.Substring((Resolve-Path $stage).Path.Length + 1)
        $h = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower()
        "$h  $rel"
    }
$sums | Set-Content -Encoding ASCII "$stage/SHA256SUMS.txt"
$sums | Set-Content -Encoding ASCII release/SHA256SUMS.txt

# ---------------------------------------------------------------- 6) zip
Write-Host "`n[6/6] zipping ..."
$zip = "release/ChronoSync-$Release-win64-selfcontained.zip"
Remove-Item -Force $zip -ErrorAction SilentlyContinue
Compress-Archive -Path $stage -DestinationPath $zip -CompressionLevel Optimal
$zipHash = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
Add-Content -Encoding ASCII release/SHA256SUMS.txt "$zipHash  $(Split-Path -Leaf $zip)"

Write-Host "`nartifact: $zip"
"{0:N1} MB" -f ((Get-Item $zip).Length / 1MB)
Write-Host "sha256: $zipHash"

if ($Publish) {
    $flag = if ($Prerelease) { "--prerelease" } else { "--prerelease" }
    Write-Host "`npublishing GitHub release $Release ($flag) ..."
    $notes = if (Test-Path ".git/RELEASE_NOTES_B2.md") { ".git/RELEASE_NOTES_B2.md" } else { ".git/RELEASE_NOTES_B1.md" }
    gh release create $Release --title "ChronoSync $Release — self-contained Windows package" `
        --notes-file $notes $flag `
        "dist/chronosync-$PepVersion-py3-none-any.whl" `
        "dist/chronosync-$PepVersion.tar.gz" `
        $zip "release/SHA256SUMS.txt"
}
Write-Host "`ndone."
