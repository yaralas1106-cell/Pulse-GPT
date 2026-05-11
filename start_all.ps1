# start_all.ps1  —  TOMI Music Agent 一键启动
# 用法: .\start_all.ps1
# 停止: .\stop_all.ps1

$ROOT   = $PSScriptRoot
$PYTHON = "C:\Users\YaRa\anaconda3\python.exe"

# ── 环境变量 ─────────────────────────────────────────────────────────────────
$env:HF_HOME                         = "D:\huggingface_cache"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
$env:PYTHONIOENCODING                = "utf-8"
$env:OLLAMA_BASE_URL                 = "http://localhost:11434/v1"
$env:OLLAMA_MODEL                    = "qwen2.5:7b-instruct-q4_K_M"
$env:PULSEFORMER_API                 = "http://localhost:8000"
$env:RAG_API                         = "http://localhost:8001"
$env:ABLETON_API                     = "http://localhost:8002"

# ── 日志目录 ─────────────────────────────────────────────────────────────────
$LOGS = "$ROOT\logs"
New-Item -ItemType Directory -Force -Path $LOGS | Out-Null

Write-Host ""
Write-Host "  TOMI Music Agent - Starting all services" -ForegroundColor Cyan
Write-Host ""

# ── 启动函数 ─────────────────────────────────────────────────────────────────
function Start-Service {
    param(
        [string]$Title,
        [string]$Exe,
        [string[]]$CmdArgs,
        [string]$WorkDir,
        [string]$LogFile
    )
    Write-Host "  Starting $Title ..." -ForegroundColor DarkCyan
    $proc = Start-Process `
        -FilePath $Exe `
        -ArgumentList $CmdArgs `
        -WorkingDirectory $WorkDir `
        -RedirectStandardOutput $LogFile `
        -RedirectStandardError  "$LogFile.err" `
        -WindowStyle Minimized `
        -PassThru
    return $proc
}

# ── PulseFormer API  :8000 ────────────────────────────────────────────────────
$p1 = Start-Service `
    -Title    "PulseFormer :8000" `
    -Exe      $PYTHON `
    -CmdArgs  @("api\server.py") `
    -WorkDir  $ROOT `
    -LogFile  "$LOGS\pulseformer.log"

Start-Sleep -Milliseconds 500

# ── RAG Server  :8001 ─────────────────────────────────────────────────────────
$p2 = Start-Service `
    -Title    "RAG :8001" `
    -Exe      $PYTHON `
    -CmdArgs  @("-m", "uvicorn", "rag.server:app", "--host", "0.0.0.0", "--port", "8001") `
    -WorkDir  $ROOT `
    -LogFile  "$LOGS\rag.log"

Start-Sleep -Milliseconds 500

# ── Ableton Bridge  :8002 ─────────────────────────────────────────────────────
$p3 = Start-Service `
    -Title    "Ableton Bridge :8002" `
    -Exe      $PYTHON `
    -CmdArgs  @("-m", "uvicorn", "agent.ableton_bridge:app", "--host", "0.0.0.0", "--port", "8002") `
    -WorkDir  $ROOT `
    -LogFile  "$LOGS\ableton_bridge.log"

Start-Sleep -Milliseconds 500

# ── Agent / Web Server  :7860 ─────────────────────────────────────────────────
$p4 = Start-Service `
    -Title    "Agent :7860" `
    -Exe      $PYTHON `
    -CmdArgs  @("agent\web_server.py") `
    -WorkDir  $ROOT `
    -LogFile  "$LOGS\agent.log"

Start-Sleep -Milliseconds 500

# ── Next.js Frontend  :3000 ───────────────────────────────────────────────────
Write-Host "  Starting Frontend :3000 ..." -ForegroundColor DarkCyan
$p5 = Start-Process `
    -FilePath "cmd.exe" `
    -ArgumentList "/c npm run dev" `
    -WorkingDirectory "$ROOT\frontend" `
    -WindowStyle Minimized `
    -PassThru

# 保存所有 PID，供 stop_all.ps1 使用
$pids = @($p1.Id, $p2.Id, $p3.Id, $p4.Id, $p5.Id)
$pids | Out-File -FilePath "$ROOT\logs\.pids" -Encoding utf8

# ── 等待端口就绪 ──────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  Waiting for services..." -ForegroundColor DarkGray

$checks = @(
    @{ Port = 8000; Label = "PulseFormer" },
    @{ Port = 8001; Label = "RAG" },
    @{ Port = 8002; Label = "Ableton Bridge" },
    @{ Port = 7860; Label = "Agent" },
    @{ Port = 3000; Label = "Frontend" }
)

$deadline = (Get-Date).AddSeconds(90)
$done = @{}

while ((Get-Date) -lt $deadline -and $done.Count -lt $checks.Count) {
    foreach ($c in $checks) {
        if ($done[$c.Port]) { continue }
        try {
            $tcp = New-Object System.Net.Sockets.TcpClient
            $tcp.Connect("127.0.0.1", $c.Port)
            $tcp.Close()
            $done[$c.Port] = $true
            Write-Host ("  OK  {0,-18} http://localhost:{1}" -f $c.Label, $c.Port) -ForegroundColor Green
        } catch { }
    }
    Start-Sleep -Seconds 2
}

# 超时未就绪的服务
foreach ($c in $checks) {
    if (-not $done[$c.Port]) {
        Write-Host ("  --  {0,-18} port {1} not ready — check logs\{2}.log" -f `
            $c.Label, $c.Port, $c.Label.ToLower().Replace(" ","_")) -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "  Frontend  ->  http://localhost:3000" -ForegroundColor Magenta
Write-Host "  API Docs  ->  http://localhost:7860/docs" -ForegroundColor Magenta
Write-Host "  Logs      ->  $LOGS\" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Run .\stop_all.ps1 to stop all services." -ForegroundColor DarkGray
Write-Host ""
