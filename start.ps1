# 一键启动 InvRef 站点（API + 页面，可选每日定时采集）
# 用法:  .\start.ps1            # 启动 http://127.0.0.1:8000
#        $env:INVREF_PORT=8001; .\start.ps1     # 换端口
#        $env:INVREF_SCHEDULE=1; .\start.ps1    # 每天 19:30 自动采集
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
& "$root\.venv\Scripts\python.exe" -m invref.api.main
