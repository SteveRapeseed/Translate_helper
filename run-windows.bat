@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ==^> Translate Helper Windows 原生版（可浮在浏览器之上）
echo.

python --version >nul 2>&1
if errorlevel 1 (
  echo 错误: 未找到 Python。请从 https://python.org 安装 Python 3.10+，并勾选 tcl/tk
  pause
  exit /b 1
)

if not exist ".venv-win" (
  echo 创建 Windows 虚拟环境...
  python -m venv .venv-win
)

call .venv-win\Scripts\activate.bat
python -m pip install -U pip wheel
python -m pip install -e .

if not exist "%USERPROFILE%\.config\translate-helper\.env" (
  if not exist "%USERPROFILE%\.config\translate-helper" mkdir "%USERPROFILE%\.config\translate-helper"
  if exist ".env" (
    copy /Y ".env" "%USERPROFILE%\.config\translate-helper\.env" >nul
  ) else (
    copy /Y "desktop\.env.example" "%USERPROFILE%\.config\translate-helper\.env" >nul
    echo 请编辑 %USERPROFILE%\.config\translate-helper\.env 填写 HF_TOKEN
  )
)

echo.
echo 启动中（Windows 原生窗口，可置顶于浏览器）...
translate-helper
