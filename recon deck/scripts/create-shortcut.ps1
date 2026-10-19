$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$ws = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')
$linkPath = Join-Path $desktop 'Recon Deck.lnk'
$shortcut = $ws.CreateShortcut($linkPath)

$portable = Get-ChildItem (Join-Path $root 'dist\ReconDeck-*.exe') -ErrorAction SilentlyContinue |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1

if ($portable) {
  $shortcut.TargetPath = $portable.FullName
  $shortcut.Arguments = ''
  $shortcut.WorkingDirectory = $portable.DirectoryName
} else {
  $electron = Join-Path $root 'node_modules\electron\dist\electron.exe'
  if (-not (Test-Path $electron)) {
    Write-Host 'Neither dist\ReconDeck-*.exe nor Electron runtime found.'
    exit 1
  }
  $shortcut.TargetPath = $electron
  $shortcut.Arguments = '"' + $root + '"'
  $shortcut.WorkingDirectory = $root
}

$shortcut.IconLocation = Join-Path $root 'assets\icon.ico'
$shortcut.Description = 'Recon Deck - collection console'
$shortcut.Save()

Write-Host "Shortcut created: $linkPath"
