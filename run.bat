@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
  echo 尚未安装，正在执行 install.bat ...
  call "%~dp0install.bat"
)

call .venv\Scripts\activate.bat
translate-helper
