# RSI 데몬을 멈춘다.
#   기본: harness\STOP 파일을 만들어 지금 하는 LLM 작업을 마친 뒤 깔끔하게 종료 (최대 수십 분)
#   -Now: 즉시 강제 종료 (진행 중인 LLM 호출 하나는 버려지고, 다음 실행 때 이어서 진행)
param([switch]$Now)
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$pidFile = Join-Path $here "harness\daemon.pid"

if (-not (Test-Path $pidFile)) { Write-Output "실행 중인 RSI 데몬이 없습니다"; exit 0 }
$daemonPid = [int](Get-Content $pidFile)

if ($Now) {
    # 데몬과 그 하위 프로세스(claude CLI, node, LibreOffice)를 함께 정리
    & taskkill.exe /PID $daemonPid /T /F | Out-Null
    Remove-Item $pidFile -ErrorAction SilentlyContinue
    Write-Output "RSI 데몬 강제 종료 (pid $daemonPid)"
} else {
    New-Item -ItemType File -Force (Join-Path $here "harness\STOP") | Out-Null
    Write-Output "STOP 파일 생성 — 현재 작업을 마치면 데몬이 종료됩니다 (pid $daemonPid)"
}
