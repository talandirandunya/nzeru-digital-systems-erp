# Open the dashboard demo in the default browser
$path = Join-Path $PSScriptRoot 'Erpis.html'
if (Test-Path $path) {
  Start-Process $path
} else {
  Write-Error "Erpis.html not found at $path"
}