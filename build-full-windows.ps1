$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$toolsDir = Join-Path $projectDir 'tools'
$distDir = Join-Path $projectDir 'dist'
$appName = 'mediaAV-msi'
$distAppDir = Join-Path $distDir $appName
$distExe = Join-Path $distAppDir ($appName + '.exe')
$releaseDir = Join-Path $projectDir 'release'
$releaseAppDir = Join-Path $releaseDir $appName
$portableDir = Join-Path $releaseDir 'Media-AV-Windows'
$installGuide = Join-Path $projectDir 'client-install.txt'
Set-Location $projectDir
$python = Join-Path $env:ProgramFiles 'Python313\python.exe'
if (-not (Test-Path $python)) {
  $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
  if (-not $pythonCommand) { $pythonCommand = Get-Command py -ErrorAction Stop }
  $python = $pythonCommand.Source
}
New-Item -ItemType Directory -Force -Path $toolsDir, $releaseDir | Out-Null

function Find-Tool($name) {
  $local = Join-Path $toolsDir $name
  if (Test-Path $local) { return $local }
  $cmd = Get-Command $name -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  throw "Khong tim thay $name. Dat file vao tools\ hoac them vao PATH."
}

$yt = Find-Tool 'yt-dlp.exe'
$ff = Find-Tool 'ffmpeg.exe'
$fp = Find-Tool 'ffprobe.exe'

$hasPyInstaller = $true
& $python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) { $hasPyInstaller = $false }
if (-not $hasPyInstaller) {
  Write-Host 'PyInstaller chua co; cai mot lan de build.' -ForegroundColor Yellow
  & $python -m pip install pyinstaller
}
foreach ($legacyOutput in @('MediaDownloader', 'MediaDownloader.exe', 'media-msi.exe', 'mediaAV-msi.exe')) {
  $legacyPath = Join-Path $distDir $legacyOutput
  if (Test-Path $legacyPath) {
    Remove-Item -LiteralPath $legacyPath -Recurse -Force
  }
}
if (Test-Path $distAppDir) { Remove-Item -LiteralPath $distAppDir -Recurse -Force }
foreach ($legacyRelease in @('media-msi.exe', 'mediaAV-msi.exe', 'Tools-Media-AV-Setup.exe')) {
  $legacyPath = Join-Path $releaseDir $legacyRelease
  if (Test-Path $legacyPath) {
    Remove-Item -LiteralPath $legacyPath -Force
  }
}
if (Test-Path $releaseAppDir) { Remove-Item -LiteralPath $releaseAppDir -Recurse -Force }
foreach ($legacyPackage in @('Tools-Media-AV-Windows.zip', 'Tools-Media-AV-Windows.exe', 'Media-AV-Windows.zip', 'Media-AV-Windows.exe')) {
  $legacyPath = Join-Path $releaseDir $legacyPackage
  if (Test-Path $legacyPath) { Remove-Item -LiteralPath $legacyPath -Force }
}
& $python -m PyInstaller --noconfirm --clean --onedir --noconsole --name $appName --add-binary "$yt;." --add-binary "$ff;." --add-binary "$fp;." desktop_app.py

$iscc = Get-Command 'ISCC.exe' -ErrorAction SilentlyContinue
if (-not $iscc) {
  foreach ($innoPath in @(
    (Join-Path ${env:ProgramFiles} 'Inno Setup 7\ISCC.exe'),
    (Join-Path ${env:ProgramFiles} 'Inno Setup 6\ISCC.exe'),
    (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 7\ISCC.exe'),
    (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe')
  )) {
    if (Test-Path $innoPath) { $iscc = [pscustomobject]@{ Source = $innoPath }; break }
  }
}
Copy-Item $distAppDir $releaseAppDir -Recurse -Force
if (Test-Path $portableDir) { Remove-Item -LiteralPath $portableDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $portableDir | Out-Null
Copy-Item $distAppDir (Join-Path $portableDir 'MediaAV') -Recurse -Force
Copy-Item $installGuide $portableDir -Force
Compress-Archive -Path $portableDir -DestinationPath (Join-Path $releaseDir 'Media-AV-Windows.zip') -Force
if ($iscc) {
  & $iscc.Source (Join-Path $projectDir 'Media-AV.iss')
  if ($LASTEXITCODE -ne 0) { throw "Inno Setup compiler failed with exit code $LASTEXITCODE" }
  Write-Host 'Da tao bo cai trong release.' -ForegroundColor Green
} else {
  Write-Host 'Chua co Inno Setup; da tao Media-AV-Windows.zip trong release.' -ForegroundColor Yellow
}

# Don output trung gian sau khi da tao xong EXE va ZIP.
$specPath = Join-Path $projectDir ($appName + '.spec')
$buildPath = Join-Path $projectDir 'build'
if (Test-Path $specPath) { Remove-Item -LiteralPath $specPath -Force }
if (Test-Path $buildPath) { Remove-Item -LiteralPath $buildPath -Recurse -Force }
