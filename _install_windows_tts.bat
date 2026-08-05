@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ================================================
echo   Install Windows Neural TTS Voices
echo   Run as Administrator for full installation
echo ================================================
echo.
echo   This script installs Chinese neural speech
echo   capabilities (Xiaoxiao / Xiaoyi / Yunxi etc.)
echo   for fully offline, high-quality TTS.
echo.

echo   [1/4] Installing zh-CN speech capability ...
powershell -NoProfile -Command "$c = Get-WindowsCapability -Online | Where-Object { $_.Name -like '*Speech*zh-CN*' -and $_.State -ne 'Installed' }; if ($c) { Write-Host 'Found:' $c[0].Name; Add-WindowsCapability -Online -Name $c[0].Name } else { Write-Host 'Already installed or not available.' }"
echo.

echo   [2/4] Exposing OneCore voices to SAPI5 ...
powershell -NoProfile -Command "& '%~dp0_setup_tts_voices.ps1'"
echo.

echo   [3/4] Listing available neural voices ...
powershell -NoProfile -Command "Get-WindowsCapability -Online | Where-Object { $_.Name -like '*Speech*zh-CN*' } | Select-Object Name,State | Format-Table -AutoSize"
echo.

echo   [4/4] Opening Windows Speech settings ...
echo          To download Xiaoxiao / Xiaoyi neural voices:
echo          Settings ^> Time ^& Language ^> Speech ^> Manage voices
echo          ^> Add voices ^> Chinese (Simplified) ^> Xiaoxiao
echo.
start ms-settings:speech

echo.
echo   ================================================
echo   After installing neural voices:
echo     1. Restart your computer (recommended)
echo     2. Restart QingyanOPS backend
echo     3. The new voices will appear in TTS settings
echo        and be automatically selected as best voice
echo   ================================================
echo.
pause
