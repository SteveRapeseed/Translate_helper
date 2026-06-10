@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ==^> Translate Helper Windows exe build

set HTTP_PROXY=
set HTTPS_PROXY=
set ALL_PROXY=
set NO_PROXY=*

python --version >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python 3.10+ required
  exit /b 1
)

if not exist ".venv-win" (
  echo Creating .venv-win ...
  python -m venv .venv-win
)

call .venv-win\Scripts\activate.bat

set OFFLINE=
if exist "win-wheels\pyinstaller-*.whl" set OFFLINE=1

if defined OFFLINE (
  echo Using offline wheels in win-wheels\
  python -m pip install --no-index --find-links=win-wheels --force-reinstall setuptools wheel >nul
  python -m pip install --no-index --find-links=win-wheels pyinstaller pillow requests certifi charset-normalizer idna urllib3 altgraph packaging pefile pywin32-ctypes pyinstaller-hooks-contrib
) else (
  echo Installing from PyPI ...
  python -m pip install -U pip wheel pyinstaller pillow requests
  if errorlevel 1 (
    echo.
    echo ERROR: pip failed. Run in WSL first:
    echo   bash scripts/download-win-wheels.sh
    echo Then copy win-wheels\ to this folder and retry.
    exit /b 1
  )
)

python -m pip install -e . --no-build-isolation --no-deps
if errorlevel 1 exit /b 1

python -m PyInstaller --noconfirm --clean translate-helper.spec
if errorlevel 1 exit /b 1

set VERSION=0.1.0
set APP_DIR=dist\TranslateHelper-%VERSION%-win64
if exist "%APP_DIR%" rmdir /s /q "%APP_DIR%"
mkdir "%APP_DIR%"
xcopy /E /I /Y dist\TranslateHelper "%APP_DIR%\" >nul

copy /Y desktop\.env.example "%APP_DIR%\.env.example" >nul
if exist "使用说明.txt" copy /Y "使用说明.txt" "%APP_DIR%\" >nul

(
echo @echo off
echo chcp 65001 ^>nul
echo cd /d "%%~dp0"
echo if not exist ".env" ^(
echo   if exist ".env.example" copy /Y ".env.example" ".env" ^>nul
echo   echo 请编辑 .env 填写 HF_TOKEN 后重新运行
echo   pause
echo   exit /b 1
echo ^)
echo start "" "%%~dp0TranslateHelper.exe"
) > "%APP_DIR%\启动翻译助手.bat"

powershell -NoProfile -Command "Compress-Archive -Path '%CD%\%APP_DIR%\*' -DestinationPath '%CD%\dist\TranslateHelper-%VERSION%-win64.zip' -Force" 2>nul

echo.
echo DONE: %APP_DIR%
echo ZIP:  dist\TranslateHelper-%VERSION%-win64.zip
echo RUN:  %APP_DIR%\启动翻译助手.bat

if not defined BUILD_NO_PAUSE pause
