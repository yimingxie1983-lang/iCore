@echo off
setlocal
if /I "%~1"=="-Z1" (
  tar.exe -tf "%~2"
  exit /b %ERRORLEVEL%
)
if /I "%~1"=="-p" (
  tar.exe -xOf "%~2" "%~3"
  exit /b %ERRORLEVEL%
)
echo Unsupported unzip shim arguments: %* 1>&2
exit /b 2
