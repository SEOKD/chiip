# 치입 레이더를 Windows 작업 스케줄러에 등록 (BUILD_PROMPT §21.3)
# - 5분마다 radar/run_poll.py 실행 (원천별 실제 간격은 config/alert_rules.yaml schedule이 결정)
# - 창이 뜨지 않도록 pyw(콘솔 없는 Python) 사용
# - 로그인한 동안만 실행(비밀번호 저장 없음)
# 실행: powershell -ExecutionPolicy Bypass -File scripts\install_scheduler.ps1
# 제거: Unregister-ScheduledTask -TaskName "chiip-radar" -Confirm:$false

$root = Split-Path -Parent $PSScriptRoot
$pyw = (Get-Command pyw -ErrorAction SilentlyContinue).Source
if (-not $pyw) { $pyw = (Get-Command pythonw -ErrorAction Stop).Source; $args0 = "`"$root\radar\run_poll.py`"" }
else { $args0 = "-3 `"$root\radar\run_poll.py`"" }

$action = New-ScheduledTaskAction -Execute $pyw -Argument $args0 -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName "chiip-radar" -Action $action -Trigger $trigger -Settings $settings `
    -Principal $principal -Description "치입 레이더 폴링 (모델 호출은 새 항목이 있을 때만)" -Force | Out-Null
Get-ScheduledTask -TaskName "chiip-radar" | Select-Object TaskName, State
