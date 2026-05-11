# ============================================================
# TOMI-GPT  一键公网 Demo 启动脚本
# 运行方式：powershell -ExecutionPolicy Bypass -File start_demo.ps1
# ============================================================

$ROOT   = "d:\BigData\PycharmProject\TOMI-GPT"
$PYTHON = "C:\Users\YaRa\anaconda3\python.exe"
$FRONT  = "$ROOT\frontend"
$CF     = "$ROOT\cloudflared.exe"

function Kill-Port($port) {
    $pids = netstat -ano | Select-String ":$port " | ForEach-Object {
        ($_ -split '\s+')[-1]
    } | Sort-Object -Unique
    foreach ($p in $pids) {
        if ($p -match '^\d+$' -and $p -ne '0') {
            Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
        }
    }
}

Write-Host ""
Write-Host "=============================="
Write-Host "  TOMI-GPT  Demo  Launcher"
Write-Host "=============================="
Write-Host ""

# ── 清理旧进程 ─────────────────────────────────────────────
Write-Host "[1/5] 清理旧进程..."
Kill-Port 7860
Kill-Port 8002
Start-Sleep -Seconds 1

# ── 启动 Web Server (:7860) ────────────────────────────────
Write-Host "[2/5] 启动 Web Server (port 7860)..."
Start-Process -FilePath $PYTHON `
    -ArgumentList "-X", "utf8", "-m", "uvicorn", "agent.web_server:app",
                  "--host", "0.0.0.0", "--port", "7860" `
    -WorkingDirectory $ROOT -WindowStyle Minimized
Start-Sleep -Seconds 3

# ── 启动 Ableton Bridge (:8002) ────────────────────────────
Write-Host "[3/5] 启动 Ableton Bridge (port 8002)..."
Start-Process -FilePath $PYTHON `
    -ArgumentList "-X", "utf8", "-m", "uvicorn", "agent.ableton_bridge:app",
                  "--host", "0.0.0.0", "--port", "8002" `
    -WorkingDirectory $ROOT -WindowStyle Minimized
Start-Sleep -Seconds 3

# ── 启动 / 重启前端 (:3000) ───────────────────────────────
Write-Host "[4/5] 启动前端 Next.js dev (port 3000)..."
Kill-Port 3000
Start-Sleep -Seconds 1

Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/c", "cd /d $FRONT && npm run dev" `
    -WindowStyle Minimized
Start-Sleep -Seconds 8

# ── 验证服务 ───────────────────────────────────────────────
Write-Host ""
Write-Host "检查各服务..."
$ok = $true
@(7860, 8002, 3000) | ForEach-Object {
    $port = $_
    $conn = netstat -ano | Select-String ":$port " | Select-String "LISTENING"
    if ($conn) {
        Write-Host "  [OK] :$port"
    } else {
        Write-Host "  [WARN] :$port 未就绪（服务可能还在启动）"
        $ok = $false
    }
}

# ── 启动 Cloudflare Tunnel ─────────────────────────────────
Write-Host ""
Write-Host "[5/5] 启动 Cloudflare Tunnel..."

if (-not (Test-Path $CF)) {
    Write-Host "  [ERROR] 找不到 cloudflared.exe，请先下载："
    Write-Host "  Invoke-WebRequest -Uri https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe -OutFile $CF"
    Write-Host ""
    Write-Host "  临时方案：直接访问 http://localhost:3000"
    exit 1
}

Write-Host ""
Write-Host "=============================="
Write-Host "  公网 URL 即将出现在下方"
Write-Host "  按 Ctrl+C 停止隧道"
Write-Host "=============================="
Write-Host ""

# 启动隧道（前台运行，URL会打印在控制台）
& $CF tunnel --url http://localhost:3000
