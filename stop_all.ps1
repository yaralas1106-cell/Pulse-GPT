# stop_all.ps1  —  停止所有 TOMI 服务

$ROOT  = $PSScriptRoot
$PIDS_FILE = "$ROOT\logs\.pids"

Write-Host ""
Write-Host "  Stopping PULSE-GPT services..." -ForegroundColor Cyan

# 方式1: 用保存的 PID 文件
if (Test-Path $PIDS_FILE) {
    $savedPids = Get-Content $PIDS_FILE
    foreach ($pid in $savedPids) {
        $pid = $pid.Trim()
        if ($pid -match '^\d+$') {
            try {
                Stop-Process -Id $pid -Force -ErrorAction Stop
                Write-Host "  Killed PID $pid" -ForegroundColor Green
            } catch { }
        }
    }
    Remove-Item $PIDS_FILE -Force
}

# 方式2: 按端口兜底 kill
$ports = @(8000, 8001, 8002, 7860, 3000)
foreach ($port in $ports) {
    $lines = netstat -ano | Select-String "\s+0\.0\.0\.0:$port\s"
    if (-not $lines) {
        $lines = netstat -ano | Select-String "\s+127\.0\.0\.1:$port\s"
    }
    foreach ($line in $lines) {
        if ($line -match '\s(\d+)\s*$') {
            $pid = $Matches[1]
            try {
                Stop-Process -Id $pid -Force -ErrorAction Stop
                Write-Host "  Killed PID $pid (port $port)" -ForegroundColor Green
            } catch { }
        }
    }
}

Write-Host ""
Write-Host "  All PULSE-GPT services stopped." -ForegroundColor Cyan
Write-Host ""
