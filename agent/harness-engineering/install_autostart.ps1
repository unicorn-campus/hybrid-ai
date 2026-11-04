# (선택) Windows 로그인 때 RSI 데몬이 자동으로 시작되도록 작업 스케줄러에 등록한다. 이 PC의 현재 사용자 전용.
#   등록:   .\install_autostart.ps1
#   해제:   .\install_autostart.ps1 -Remove
param([switch]$Remove)
$name = "CoursewareAgent-RSI-Daemon"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

if ($Remove) {
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
    Write-Output "자동 시작 해제: $name"
    exit 0
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$here\start_daemon.ps1`"" `
    -WorkingDirectory $here
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings `
    -Description "교재 제작 에이전트 RSI 데몬 (이 PC 전용)" -Force | Out-Null
Write-Output "자동 시작 등록: $name (로그인할 때 start_daemon.ps1 실행)"
