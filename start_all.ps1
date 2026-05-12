# start_all.ps1 - PULSE-GPT one-click startup
# Usage : .\start_all.ps1
# Stop  : .\stop_all.ps1

$ROOT   = $PSScriptRoot
$PYTHON = "C:\Users\YaRa\anaconda3\python.exe"

$env:PYTHONIOENCODING = "utf-8"
$env:OLLAMA_BASE_URL  = "http://localhost:11434/v1"
$env:OLLAMA_MODEL     = "qwen2.5:7b-instruct-q4_K_M"
$env:PULSEFORMER_API  = "http://localhost:8000"
$env:RAG_API          = "http://localhost:8001"
$env:ABLETON_API      = "http://localhost:8002"

function Open-Cmd($title, $cmd) {
    Start-Process cmd -ArgumentList "/k", "title $title && $cmd"
}

function Wait-Port($port, $label, $timeoutSec = 60) {
    $deadline = (Get-Date).AddSeconds($timeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $tcp = New-Object System.Net.Sockets.TcpClient
            $tcp.Connect("127.0.0.1", $port)
            $tcp.Close()
            Write-Host "  OK  $label  ->  http://localhost:$port" -ForegroundColor Green
            return $true
        } catch {}
        Start-Sleep -Seconds 2
    }
    Write-Host "  WARN  $label port $port not ready (timeout)" -ForegroundColor Yellow
    return $false
}

Write-Host ""
Write-Host "  PULSE-GPT - Starting all services" -ForegroundColor Cyan
Write-Host ""

# [1] Ollama
Write-Host "  [1/5] Ollama..." -ForegroundColor DarkCyan
Open-Cmd "Ollama" "ollama serve"
Start-Sleep -Seconds 2

# [2] PulseFormer API :8000
Write-Host "  [2/5] PulseFormer API..." -ForegroundColor DarkCyan
Open-Cmd "PulseFormer :8000" "cd /d `"$ROOT`" && `"$PYTHON`" -m uvicorn api.server:app --host 0.0.0.0 --port 8000"

Write-Host "  Waiting for PulseFormer to be ready..." -ForegroundColor DarkGray
if (Wait-Port 8000 "PulseFormer") {
    Write-Host "  Loading model..." -ForegroundColor DarkCyan
    try {
        Invoke-WebRequest -Uri "http://localhost:8000/model/load" `
            -Method POST -ContentType "application/json" `
            -Body '{"model_path":"checkpoints/pulsecp_v5_clean_best.pt"}' `
            -TimeoutSec 10 | Out-Null
        Write-Host "  OK  Model load request sent (loading in background)" -ForegroundColor Green
    } catch {
        Write-Host "  WARN  Model load request failed - run manually if needed" -ForegroundColor Yellow
    }
}

# [3] RAG :8001
Write-Host "  [3/5] RAG service..." -ForegroundColor DarkCyan
Open-Cmd "RAG :8001" "cd /d `"$ROOT`" && `"$PYTHON`" -m uvicorn rag.server:app --host 0.0.0.0 --port 8001"

# [4] Ableton Bridge :8002
Write-Host "  [4/5] Ableton Bridge..." -ForegroundColor DarkCyan
Open-Cmd "Ableton Bridge :8002" "cd /d `"$ROOT`" && `"$PYTHON`" agent\ableton_bridge.py"

# [5] Web Server :7860
Write-Host "  [5/5] Web Server..." -ForegroundColor DarkCyan
Open-Cmd "Web Server :7860" "cd /d `"$ROOT`" && `"$PYTHON`" -m uvicorn agent.web_server:app --host 0.0.0.0 --port 7860"

Write-Host ""
Write-Host "  Waiting for Web Server..." -ForegroundColor DarkGray
if (Wait-Port 7860 "Web Server") {
    Start-Sleep -Seconds 1
    Start-Process "http://localhost:7860/chat-ui"
}

Write-Host ""
Write-Host "  Chat UI  ->  http://localhost:7860/chat-ui" -ForegroundColor Magenta
Write-Host "  Showcase ->  http://localhost:7860/showcase" -ForegroundColor Magenta
Write-Host ""
Write-Host "  To stop all services run: .\stop_all.ps1" -ForegroundColor DarkGray
Write-Host ""
