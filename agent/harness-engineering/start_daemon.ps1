# 이 PC에서 RSI 데몬을 창 없이 백그라운드로 시작한다.
# 터미널이나 Claude 세션을 닫아도 계속 돈다. 멈추려면 stop_daemon.ps1
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$pidFile = Join-Path $here "harness\daemon.pid"
$logDir = Join-Path $here "harness\logs"
New-Item -ItemType Directory -Force $logDir | Out-Null

if (Test-Path $pidFile) {
    $old = Get-Content $pidFile
    if (Get-Process -Id $old -ErrorAction SilentlyContinue) {
        Write-Output "RSI 데몬이 이미 실행 중입니다 (pid $old)"
        exit 0
    }
}
Remove-Item (Join-Path $here "harness\STOP") -ErrorAction SilentlyContinue

$py = (Get-Command python).Source
$console = Join-Path $logDir "daemon_console.log"
$cmd = "cmd.exe /c `"`"$py`" -X utf8 `"$here\run.py`" --daemon >> `"$console`" 2>&1`""

# Win32_Process.Create 로 띄우면 현재 셸과 분리되어 셸이 끝나도 살아남는다. ShowWindow=0 은 창 숨김
$startup = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ ShowWindow = [uint16]0 }
$result = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
    CommandLine = $cmd; CurrentDirectory = $here; ProcessStartupInformation = $startup
}
if ($result.ReturnValue -ne 0) { throw "데몬 시작 실패 (코드 $($result.ReturnValue))" }

Write-Output "RSI 데몬 시작 (cmd pid $($result.ProcessId))"
Write-Output "  실행 로그 : $logDir\rsi.log"
Write-Output "  보고서    : $here\harness\RSI_REPORT.md"
Write-Output "  상태 확인 : python run.py --status"
