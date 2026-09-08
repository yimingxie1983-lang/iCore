@echo off
chcp 65001 >nul
title iCore
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-icore.ps1" %*
if errorlevel 1 pause
