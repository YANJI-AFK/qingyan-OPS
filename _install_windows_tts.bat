@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ================================================
echo   Install Windows TTS Voices (Run as Administrator)
echo ================================================
echo.
echo   This script installs Windows Chinese speech
echo   packages (Xiaoxiao / Xiaoyi neural voices).
echo   Please run it AS ADMINISTRATOR.
echo.

echo   [1/2] Installing zh-CN speech capability ...
powershell -NoProfile -Command "Add-WindowsCapability -Online -Name 'Language.Speech~~~~zh-CN~0.0.1.0'"
if errorlevel 1 (
    echo   [ERROR] Failed to install speech capability.
    echo           Fallback: Settings - Time & Language - Language
    echo                    - Chinese - Speech - Add voices
) else (
    echo   [OK] zh-CN speech capability installed.
)

echo.
echo   [2/2] Opening voice settings for manual download ...
echo          Download Xiaoxiao / Xiaoyi voices there.
start ms-settings:speech

echo.
echo   Done! Restart the backend to see new voices.
echo.
pause
