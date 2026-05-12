# start_all.ps1 — PULSE-GPT 一键启动
# 用法: .\start_all.ps1
# 停止: .\stop_all.ps1

$ROOT   = $PSScriptRoot
$PYTHON = "C:\Users\YaRa\anaconda3\python.exe"

$env:PYTHONIOENCODING = "utf-8"
$env:HF_HOME          = "D:\huggingface_cache"
$env:OLLAMA_BASE_URL  = "http://localhost:11434/v1"
$env:OLLAMA_MODEL     = "qwen2.5:7b-instruct-q4_K_M"
$env:PULSEFORMER_API  = "http://localhost:8000"
$env:RAG_API          = "http://localhost:8001"
$env:ABLETON_API      = "http://localhost:8002"

Write-Host ""
Write-Host "  PULSE-GPT — Starting all services" -ForegroundColor Cyan
Write-Host ""

# ── 辅助函数 ──────────────────────────────────────────────────────────────────
function Open-Window($title, $cmd) {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", `
        "`$host.UI.RawUI.WindowTitle = '$title'; cd '$ROOT'; $cmd"
}

function Wait-Port($port, $label, $timeoutSec = 60) {
    $deadline = (Get-Date).AddSeconds($timeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $tcp = New-Object System.Net.Sockets.TcpClient
            $tcp.Connect("127.0.0.1", $port)
            $tcp.Close()
            Write-Host "  OK  $label  http://localhost:$port" -ForegroundColor Green
            return $true
        } catch {}
        Start-Sleep -Seconds 2
    }
    Write-Host "  !!  $label 未就绪（端口 $port 超时）" -ForegroundColor Yellow
    return $false
}

# ── 1. Ollama ─────────────────────────────────────────────────────────────────
Write-Host "  [1/5] Ollama..." -ForegroundColor DarkCyan
Open-Window "Ollama" "ollama serve"
Start-Sleep -Seconds 2

# ── 2. PulseFormer API :8000 ──────────────────────────────────────────────────
Write-Host "  [2/5] PulseFormer API..." -ForegroundColor DarkCyan
Open-Window "PulseFormer :8000" `
    "& '$PYTHON' -m uvicorn api.server:app --host 0.0.0.0 --port 8000"

Write-Host "  等待 PulseFormer 就绪..." -ForegroundColor DarkGray
if (Wait-Port 8000 "PulseFormer") {
    Write-Host "  加载模型..." -ForegroundColor DarkCyan
    try {
        Invoke-WebRequest -Uri "http://localhost:8000/model/load" `
            -Method POST -ContentType "application/json" `
            -Body '{"model_path":"checkpoints/pulsecp_v5_clean_best.pt"}' `
            -TimeoutSec 10 | Out-Null
        Write-Host "  OK  模型加载请求已发送（后台加载中）" -ForegroundColor Green
    } catch {
        Write-Host "  !!  模型加载请求失败，请手动执行" -ForegroundColor Yellow
    }
}

# ── 3. RAG 服务 :8001 ─────────────────────────────────────────────────────────
Write-Host "  [3/5] RAG 服务..." -ForegroundColor DarkCyan
Open-Window "RAG :8001" `
    "& '$PYTHON' -m uvicorn rag.server:app --host 0.0.0.0 --port 8001"

# ── 4. Ableton Bridge :8002 ───────────────────────────────────────────────────
Write-Host "  [4/5] Ableton Bridge..." -ForegroundColor DarkCyan
Open-Window "Ableton Bridge :8002" `
    "& '$PYTHON' agent\ableton_bridge.py"

# ── 5. Web Server :7860 ───────────────────────────────────────────────────────
Write-Host "  [5/5] Web Server..." -ForegroundColor DarkCyan
Open-Window "Web Server :7860" `
    "& '$PYTHON' -m uvicorn agent.web_server:app --host 0.0.0.0 --port 7860"

# ── 等待 Web Server 就绪后打开浏览器 ─────────────────────────────────────────
Write-Host ""
Write-Host "  等待 Web Server 就绪..." -ForegroundColor DarkGray
if (Wait-Port 7860 "Web Server") {
    Start-Sleep -Seconds 1
    Start-Process "http://localhost:7860/chat-ui"
}

Write-Host ""
Write-Host "  Chat UI  ->  http://localhost:7860/chat-ui" -ForegroundColor Magenta
Write-Host "  Showcase ->  http://localhost:7860/showcase" -ForegroundColor Magenta
Write-Host ""
Write-Host "  停止所有服务: .\stop_all.ps1" -ForegroundColor DarkGray
Write-Host ""
