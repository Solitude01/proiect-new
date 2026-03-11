  @echo off
  echo 查找占用 8000 端口的进程...
  for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
      echo 杀死进程 PID: %%a
      taskkill -F -PID %%a
  )
  echo 完成
  pause