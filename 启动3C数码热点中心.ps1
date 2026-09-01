$root = "C:\Users\guochengxia.1\Documents\新品热点中心"
$port = 8788
$listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if (-not $listener) { Start-Process -FilePath "python" -ArgumentList "server.py" -WorkingDirectory $root -WindowStyle Hidden; Start-Sleep -Seconds 1 }
Start-Process "http://localhost:$port"

