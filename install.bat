@echo off
setlocal
cd /d "%~dp0"

echo ==^> Translate Helper 安装 (Windows)
python --version >nul 2>&1
if errorlevel 1 (
  echo 错误: 未找到 python，请先安装 Python 3.10+
  exit /b 1
)

if not exist ".venv" (
  echo ==^> 创建虚拟环境
  python -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install -U pip wheel
python -m pip install -e .

if not exist "%USERPROFILE%\.config\translate-helper" mkdir "%USERPROFILE%\.config\translate-helper"
if not exist "%USERPROFILE%\.config\translate-helper\.env" (
  if exist ".env" (
    copy /Y ".env" "%USERPROFILE%\.config\translate-helper\.env"
  ) else (
    copy /Y "desktop\.env.example" "%USERPROFILE%\.config\translate-helper\.env"
    echo 请编辑 %%USERPROFILE%%\.config\translate-helper\.env 填写 HF_TOKEN
  )
)

echo.
echo 安装完成。运行: run.bat
exit /b 0
