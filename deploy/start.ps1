#Requires -Version 5.1
<#
启动本地部署：训练网页服务（默认 8080）与板端回执接收服务（默认 8091）。
两个服务通过 deploy\launch.py 以独立进程启动，关闭终端后仍在运行；
日志和 PID 写入项目内 .run/ 目录。
#>
[CmdletBinding()]
param(
    [int]$Port = 8080,
    [int]$ReceiptPort = 8091,
    [string]$BindHost = '127.0.0.1',
    [switch]$Restart
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { $python = (Get-Command python).Source }
$launcher = Join-Path $root 'deploy\launch.py'
$state = Join-Path $root '.run'
$logs = Join-Path $state 'logs'
New-Item -ItemType Directory -Force -Path $logs | Out-Null

function Test-Alive([int]$processId) {
    if (-not $processId) { return $false }
    return [bool](Get-Process -Id $processId -ErrorAction SilentlyContinue)
}

function Stop-Tracked([string]$name) {
    $file = Join-Path $state "$name.pid"
    if (-not (Test-Path $file)) { return }
    $processId = [int](Get-Content $file -Raw).Trim()
    if (Test-Alive $processId) {
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        Write-Host "已停止 $name (PID $processId)"
    }
    Remove-Item $file -Force -ErrorAction SilentlyContinue
}

function Wait-Health([int]$port, [string]$service, [int]$seconds = 30) {
    $deadline = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:$port/healthz" -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200 -and $response.Content -match $service) { return $true }
        } catch {
            Start-Sleep -Milliseconds 250
        }
    }
    return $false
}

function Test-PortBusy([int]$port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $connecting = $client.ConnectAsync('127.0.0.1', $port)
        if (-not $connecting.Wait(800)) { return $false }
        return $client.Connected
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Start-Tracked([string]$name, [int]$port, [string]$service, [string[]]$command, [hashtable]$envs) {
    if (Test-PortBusy $port) {
        if (Wait-Health $port $service 3) {
            Write-Host "$name 已在端口 $port 运行，跳过启动"
            return '已有实例'
        }
        throw "端口 $port 已被其他程序占用，请用 -Port / -ReceiptPort 指定其他端口"
    }
    foreach ($key in $envs.Keys) { Set-Item -Path "env:$key" -Value $envs[$key] }
    $env:PYTHONUNBUFFERED = '1'
    & $python $launcher --name $name --pid-file (Join-Path $state "$name.pid") `
        --log-dir $logs --working-dir $root -- @command | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "启动 $name 失败" }
    return [int](Get-Content (Join-Path $state "$name.pid") -Raw).Trim()
}

if ($Restart) {
    Stop-Tracked 'app'
    Stop-Tracked 'receipts'
}

$appPid = Start-Tracked 'app' $Port 'xiaosheng-training' @('app.py') @{
    TRAINING_DB      = (Join-Path $root 'training.sqlite3')
    BOARD_RECEIPT_DB = (Join-Path $root 'board_receipts.sqlite3')
    HOST             = $BindHost
    PORT             = "$Port"
}
$receiptPid = Start-Tracked 'receipts' $ReceiptPort 'xiaosheng-board-receipts' @('board_receipts.py', '--port', "$ReceiptPort") @{}

if (-not (Wait-Health $Port 'xiaosheng-training')) {
    throw "训练服务未在 $Port 端口就绪，请查看 $logs\app.err.log"
}
if (-not (Wait-Health $ReceiptPort 'xiaosheng-board-receipts')) {
    throw "回执服务未在 $ReceiptPort 端口就绪，请查看 $logs\receipts.err.log"
}

Write-Host ''
Write-Host '部署已启动'
Write-Host ("  训练网页   http://127.0.0.1:{0}/" -f $Port)
Write-Host ("  回执服务   http://127.0.0.1:{0}/healthz" -f $ReceiptPort)
Write-Host '  训练库     training.sqlite3 (sessions, turns)'
Write-Host '  回执库     board_receipts.sqlite3 (receipts) — 只读复盘'
Write-Host ("  进程       app={0} receipts={1}" -f $appPid, $receiptPid)
Write-Host ("  日志       {0}" -f $logs)
Write-Host '  停止       powershell -ExecutionPolicy Bypass -File deploy\stop.ps1'
