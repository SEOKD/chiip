# 치입 로컬 서버 시작 (크롬 확장용). 창을 닫으면 서버도 멈춘다.
# 로그인할 때 자동 시작하려면: 이 파일의 바로가기를 shell:startup 폴더에 넣는다(마스터 선택).
$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
Set-Location (Split-Path $PSScriptRoot -Parent)
py scripts/chiip_server.py
