$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$toolsDir = Join-Path $projectDir 'tools'
$distDir = Join-Path $projectDir 'dist'
$appName = 'media-msi'
$distExe = Join-Path $distDir ($appName + '.exe')
$releaseDir = Join-Path $projectDir 'release'
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

& $python -m pip install --upgrade pyinstaller
if (Test-Path (Join-Path $distDir 'MediaDownloader')) { Remove-Item -LiteralPath (Join-Path $distDir 'MediaDownloader') -Recurse -Force }
if (Test-Path (Join-Path $distDir 'MediaDownloader.exe')) { Remove-Item -LiteralPath (Join-Path $distDir 'MediaDownloader.exe') -Force }
if (Test-Path $distExe) { Remove-Item -LiteralPath $distExe -Force }
& $python -m PyInstaller --noconfirm --clean --onefile --noconsole --name $appName --add-binary "$yt;." --add-binary "$ff;." --add-binary "$fp;." desktop_app.py

$iscc = Get-Command 'ISCC.exe' -ErrorAction SilentlyContinue
Copy-Item $distExe (Join-Path $releaseDir ($appName + '.exe')) -Force
Compress-Archive -Path $distExe, $installGuide -DestinationPath (Join-Path $releaseDir 'Tools-Media-AV-Windows.zip') -Force
if ($iscc) {
  & $iscc.Source (Join-Path $projectDir 'Tools-Media-AV.iss')
  Write-Host 'Da tao bo cai trong release.' -ForegroundColor Green
} else {
  Write-Host 'Chua co Inno Setup; da tao Tools-Media-AV-Windows.zip trong release.' -ForegroundColor Yellow
}

# Don output trung gian sau khi da tao xong EXE va ZIP.
$specPath = Join-Path $projectDir ($appName + '.spec')
$buildPath = Join-Path $projectDir 'build'
if (Test-Path $specPath) { Remove-Item -LiteralPath $specPath -Force }
if (Test-Path $buildPath) { Remove-Item -LiteralPath $buildPath -Recurse -Force }
