#Requires -Version 5.1
<#
运行仓库自带的验收脚本，并检查服务是否在线。
示例：powershell -ExecutionPolicy Bypass -File deploy\verify.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { $python = (Get-Command python).Source }
$state = Join-Path $root '.run'
New-Item -ItemType Directory -Force -Path $state | Out-Null

# 受限沙箱会把 tempfile 的 0o700 临时目录变成不可写 ACL。
# 用 deploy\sandbox 兼容层 + 项目内临时目录，让验收脚本在沙箱内也能运行。
$env:PYTHONPATH = Join-Path $root 'deploy\sandbox'
$env:TEMP = Join-Path $state 'tmp'
$env:TMP = $env:TEMP
$env:PYTHONIOENCODING = 'utf-8'
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null

$failures = 0
function Invoke-Check([string]$label, [string[]]$arguments) {
    Write-Host "=== $label ==="
    Push-Location $root
    try {
        & $python @arguments
        $code = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    if ($code -ne 0) {
        Write-Host "$label 失败 (exit $code)" -ForegroundColor Red
        $script:failures++
    }
}

Invoke-Check '规则边界 verify_training.py' @('verify_training.py')
Invoke-Check '回执复盘 verify_board_review.py' @('verify_board_review.py')
Invoke-Check 'HTTP 验收 verify_http.py' @('verify_http.py')
Invoke-Check '改写用例 verify_paraphrases.py' @('verify_paraphrases.py', (Join-Path $state 'paraphrases.csv'))

Write-Host ''
foreach ($probe in @(@{ Port = 8080; Service = 'xiaosheng-training'; Label = '训练网页' },
                     @{ Port = 8091; Service = 'xiaosheng-board-receipts'; Label = '回执服务' })) {
    try {
        $response = Invoke-WebRequest -Uri ("http://127.0.0.1:{0}/healthz" -f $probe.Port) -UseBasicParsing -TimeoutSec 2
        $online = $response.Content -match $probe.Service
    } catch {
        $online = $false
    }
    if ($online) {
        Write-Host ("{0} 在线 http://127.0.0.1:{1}/" -f $probe.Label, $probe.Port)
    } else {
        Write-Host ("{0} 未在线（可用 deploy\start.ps1 启动）" -f $probe.Label) -ForegroundColor Yellow
    }
}

Write-Host ''
if ($failures) {
    Write-Host "$failures 项验收未通过" -ForegroundColor Red
    exit 1
}
Write-Host '全部验收通过'
