@echo off
echo ========================================
echo  Stopping Polymarket Trading System
echo ========================================
echo.

echo Stopping all uvicorn processes...
taskkill /f /im python.exe >nul 2>&1
taskkill /f /im uvicorn.exe >nul 2>&1

echo Closing all trading controller windows...
taskkill /f /fi "WindowTitle eq Events Controller*" >nul 2>&1
taskkill /f /fi "WindowTitle eq Markets Controller*" >nul 2>&1
taskkill /f /fi "WindowTitle eq Strategy Controller*" >nul 2>&1
taskkill /f /fi "WindowTitle eq Paper Trading Controller*" >nul 2>&1
taskkill /f /fi "WindowTitle eq Main Trading Controller*" >nul 2>&1

echo.
echo ========================================
echo  All servers have been stopped!
echo ========================================
echo.
pause