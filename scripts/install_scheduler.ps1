# 치입 수집 작업을 Windows 작업 스케줄러에 등록 (BUILD_PROMPT §21.3)
# - chiip-radar  : 5분마다 radar/run_poll.py  (원천별 실제 간격은 config/alert_rules.yaml schedule)
# - chiip-hourly : 30분마다 radar/run_hourly.py (관보·EDGAR 전문 검색·DART 타사·대만 월매출)
# - 창이 뜨지 않도록 pyw(콘솔 없는 Python), 로그인한 동안만 실행(비밀번호 저장 없음)
# 실행: powershell -ExecutionPolicy Bypass -File scripts\install_scheduler.ps1
# 제거: Unregister-ScheduledTask -TaskName "chiip-radar","chiip-hourly" -Confirm:$false

$root = Split-Path -Parent $PSScriptRoot
$pyw = (Get-Command pyw -ErrorAction Stop).Source
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

function Register-Chiip($name, $script, $minutes, $desc) {
    $action = New-ScheduledTaskAction -Execute $pyw -Argument "-3 `"$root\radar\$script`"" -WorkingDirectory $root
    $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes $minutes)
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings `
        -Principal $principal -Description $desc -Force | Out-Null
}

Register-Chiip "chiip-radar" "run_poll.py" 5 "치입 레이더 폴링 (모델 호출은 새 항목이 있을 때만)"
Register-Chiip "chiip-hourly" "run_hourly.py" 30 "치입 저빈도 수집: 관보·EDGAR·DART 타사·대만 월매출"
Get-ScheduledTask -TaskName "chiip-*" | Select-Object TaskName, State