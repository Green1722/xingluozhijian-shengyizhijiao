#Requires -Version 5.1
<#
停止由 start.ps1 启动的两个后台服务。
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$state = Join-Path $root '.run'

foreach ($name in @('app', 'receipts')) {
    $pidFile = Join-Path $state "$name.pid"
    if (-not (Test-Path $pidFile)) {
        Write-Host "$name 未在运行（无 PID 文件）"
        continue
    }
    $processId = [int](Get-Content $pidFile -Raw).Trim()
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($process) {
        Stop-Process -Id $processId -Force
        Write-Host "已停止 $name (PID $processId)"
    } else {
        Write-Host "$name 进程已不存在，清理 PID 文件"
    }
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}
