#Requires -Version 5.1
<#
录一轮板端对话并上传，最后直接打印回执编号。

用法：
    powershell -ExecutionPolicy Bypass -File deploy\record.ps1 -Seconds 120

录制期间对着板子正常说话即可。脚本会自动：
    串口日志 -> samples\board-capture.json -> 上传到 8091 -> 打印回执编号

参数：
    -Seconds   录制时长（默认 120 秒）
    -PortName  串口（默认 COM5）
    -Case      病例名，写进回执
    -Ask       可选，录制开始时用文本提问（中文自动转 base64）
    -Out       可选，capture JSON 输出路径
    -SkipUpload 只采集不 上传
#>
[CmdletBinding()]
param(
    [int]$Seconds = 120,
    [string]$PortName = 'COM5',
    [int]$Baud = 115200,
    [string]$Case = '小儿静脉输液（实机）',
    [string[]]$Ask = @(),
    [string]$Out = '',
    [switch]$SkipUpload
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { $python = (Get-Command python).Source }
$log = Join-Path $root '.run\serial.log'
if (-not $Out) { $Out = Join-Path $root 'samples\board-capture.json' }
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $log) | Out-Null

# 让 Python 子进程的中文输出在这个控制台里显示正常
$env:PYTHONIOENCODING = 'utf-8'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

if (-not ([System.IO.Ports.SerialPort]::GetPortNames() -contains $PortName)) {
    throw "找不到串口 $PortName，请确认板子已连接（当前可用：$([System.IO.Ports.SerialPort]::GetPortNames() -join ', ')）"
}

$sp = New-Object System.IO.Ports.SerialPort -ArgumentList $PortName, $Baud, 'None', 8, 'One'
$sp.ReadTimeout = 300
$sp.Encoding = [System.Text.Encoding]::UTF8
$sp.Open()
$sp.DtrEnable = $false      # 不要拉 DTR/RTS，避免把板子拉进下载模式
$sp.RtsEnable = $false
Start-Sleep -Milliseconds 500
$sp.DiscardInBuffer()

$anchor = (Get-Date).ToString('yyyy-MM-ddTHH:mm:sszzz')
[IO.File]::WriteAllText($log, "#T $anchor`r`n", [System.Text.Encoding]::UTF8)

Write-Host ("已连接 {0}，开始录制 {1} 秒" -f $PortName, $Seconds)
Write-Host '现在对着板子说话：身份核对、报告操作进度、询问感受、健康宣教各说一两句。'
Write-Host ''

# 有 -Ask 时按间隔依次注入，形成一轮干净的多轮对话（不依赖麦克风）
$askIndex = 0
$askInterval = if ($Ask.Count -gt 0) { [Math]::Max([int](($Seconds - 12) / $Ask.Count), 6) } else { 0 }
$nextAskAt = (Get-Date).AddSeconds(3)

$deadline = (Get-Date).AddSeconds($Seconds)
$lastReport = [DateTime]::MinValue
try {
    while ((Get-Date) -lt $deadline) {
        try {
            $chunk = $sp.ReadExisting()
            if ($chunk) { [IO.File]::AppendAllText($log, $chunk, [System.Text.Encoding]::UTF8) }
        } catch {
            # 单次读取超时不打断录制
        }
        if ($askIndex -lt $Ask.Count -and (Get-Date) -ge $nextAskAt) {
            $question = $Ask[$askIndex]
            $b64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($question))
            [IO.File]::AppendAllText($log, "#Q " + $question + "`r`n", [System.Text.Encoding]::UTF8)
            $sp.Write("ask64 $b64`r`n")
            Write-Host ("  注入提问：{0}" -f $question)
            $askIndex++
            $nextAskAt = (Get-Date).AddSeconds($askInterval)
        }
        if (((Get-Date) - $lastReport).TotalSeconds -ge 10) {
            $left = [int]($deadline - (Get-Date)).TotalSeconds
            Write-Host ("  录制中…剩余 {0} 秒" -f [Math]::Max($left, 0))
            $lastReport = Get-Date
        }
        Start-Sleep -Milliseconds 80
    }
} finally {
    $sp.Close()
}

$text = [IO.File]::ReadAllText($log, [System.Text.Encoding]::UTF8)
$turns = ($text -split "`r?`n" | Where-Object { $_ -match 'Application: (>>|<<)' }).Count
Write-Host ''
Write-Host ("录制结束：日志 {0} 字节，识别到 {1} 条对话行" -f (Get-Item $log).Length, $turns)
if ($turns -eq 0) {
    Write-Host ''
    Write-Host '这段时间板子没有进入对话。最近的串口输出：'
    ($text -split "`r?`n" | Where-Object { $_.Trim() } | Select-Object -Last 8) | ForEach-Object { Write-Host ("  " + $_) }
    Write-Host ''
    Write-Host '常见原因与处理：'
    Write-Host '  1. 没有先叫唤醒词。先喊「小圣老师」，等板子有回应（屏幕亮/喇叭出声）再说。'
    Write-Host '  2. 板子上可能还有按键，按一下再说话。'
    Write-Host '  3. 想跳过麦克风：用文本提问，加  -Ask "请问您的住院号是多少"'
    Write-Host '  4. 日志里若有 MQTT 报错，说明板子连不上云端，回复不会生成。'
    throw '本轮没有录到对话，请按上面提示重试'
}

& $python (Join-Path $root 'deploy\build_capture.py') --log $log --case $Case --out $Out
if ($LASTEXITCODE -ne 0) { throw '生成 capture JSON 失败' }

if ($SkipUpload) {
    Write-Host "已跳过上传，文件在 $Out"
    return
}

try {
    Invoke-WebRequest 'http://127.0.0.1:8091/healthz' -UseBasicParsing -TimeoutSec 2 | Out-Null
} catch {
    throw '接收服务没启动。请先在另一个窗口运行 deploy\serve.cmd'
}

Write-Host ''
Write-Host '上传中…'
$result = (& $python (Join-Path $root 'board_receipts.py') --port 8091 --verify-upload $Out) -join ''
Write-Host $result

$match = [regex]::Match($result, '"receipt":\s*"([0-9a-f]{64})"')
if (-not $match.Success) { throw '上传返回里没有回执编号' }
$receipt = $match.Groups[1].Value

Write-Host ''
Write-Host '=========================================='
Write-Host ("回执编号：{0}" -f $receipt)
Write-Host '=========================================='
Write-Host '打开 http://127.0.0.1:8080/ ，在「实机训练复盘」里粘贴上面这串号码查询。'
