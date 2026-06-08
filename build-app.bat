@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ==^> Translate Helper Windows exe build

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
python -m pip install -U pip wheel pyinstaller
python -m pip install -e .
python -m PyInstaller --noconfirm --clean translate-helper.spec
if errorlevel 1 exit /b 1

set VERSION=0.1.0
set APP_DIR=dist\TranslateHelper-%VERSION%-win64
if exist "%APP_DIR%" rmdir /s /q "%APP_DIR%"
mkdir "%APP_DIR%"
xcopy /E /I /Y dist\TranslateHelper\* "%APP_DIR%\" >nul

copy /Y desktop\.env.example "%APP_DIR%\.env.example" >nul
if exist ".env" copy /Y ".env" "%APP_DIR%\.env" >nul

(
echo @echo off
echo cd /d "%%~dp0"
echo if not exist ".env" ^(
echo   copy /Y ".env.example" ".env" ^>nul
echo   echo Edit .env and set HF_TOKEN, then run again
echo   pause
echo   exit /b 1
echo ^)
echo start "" "%%~dp0TranslateHelper.exe"
) > "%APP_DIR%\启动翻译助手.bat"

copy /Y "使用说明.txt" "%APP_DIR%\" >nul 2>nul

powershell -NoProfile -Command "Compress-Archive -Path '%APP_DIR%\*' -DestinationPath 'dist\TranslateHelper-%VERSION%-win64.zip' -Force"

echo.
echo DONE: %APP_DIR%
echo ZIP:  dist\TranslateHelper-%VERSION%-win64.zip
echo RUN:  %APP_DIR%\启动翻译助手.bat
pause
