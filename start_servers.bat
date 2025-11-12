@echo off
echo ========================================
echo  Starting Polymarket Trading System
echo ========================================
echo.

echo Would you like to start in debug mode for detailed logging?
set /p DEBUG_MODE="Debug mode? (y/n): "
if /i "%DEBUG_MODE%"=="y" (
    set DEBUG_FLAGS=--log-level debug --access-log
    set PYTHON_LOG_LEVEL=DEBUG
    echo Debug mode ENABLED - Detailed logging active
) else (
    set DEBUG_FLAGS=
    set PYTHON_LOG_LEVEL=INFO
    echo Normal mode - Standard logging
)
echo.

echo Checking for virtual environment...
if exist "venv\Scripts\activate.bat" (
    echo Found venv at venv\Scripts\activate.bat
    set VENV_PATH=venv\Scripts\activate.bat
) else if exist ".venv\Scripts\activate.bat" (
    echo Found venv at .venv\Scripts\activate.bat
    set VENV_PATH=.venv\Scripts\activate.bat
) else if exist "env\Scripts\activate.bat" (
    echo Found venv at env\Scripts\activate.bat
    set VENV_PATH=env\Scripts\activate.bat
) else (
    echo ERROR: No virtual environment found!
    echo Please create a virtual environment first:
    echo   python -m venv venv
    echo   venv\Scripts\activate
    echo   pip install -r requirements.txt
    pause
    exit /b 1
)
echo.

echo Creating data directories...
if not exist "data\events" mkdir "data\events"
if not exist "data\markets" mkdir "data\markets" 
if not exist "data\trades" mkdir "data\trades"
if not exist "data\history" mkdir "data\history"
echo Data directories created.
echo.

echo Starting all trading controllers...
echo.

echo [1/5] Starting Events Controller (Port 8000)...
start "Events Controller" cmd /k "%VENV_PATH% && uvicorn src.events_controller:app --reload --port 8000 %DEBUG_FLAGS%"
timeout /t 2 /nobreak > nul

echo [2/5] Starting Markets Controller (Port 8001)...
start "Markets Controller" cmd /k "%VENV_PATH% && uvicorn src.market_controller:app --reload --port 8001 %DEBUG_FLAGS%"
timeout /t 2 /nobreak > nul

echo [3/5] Starting Momentum Strategy Controller (Port 8002)...
start "Momentum Strategy" cmd /k "%VENV_PATH% && uvicorn src.strategies.momentum_strategy_controller:app --reload --port 8002 %DEBUG_FLAGS%"
timeout /t 2 /nobreak > nul

echo [4/5] Starting Paper Trading Controller (Port 8003)...
start "Paper Trading Controller" cmd /k "%VENV_PATH% && uvicorn src.paper_trading_controller:app --reload --port 8003 %DEBUG_FLAGS%"
timeout /t 2 /nobreak > nul

echo [5/5] Starting Portfolio Orchestrator (Port 8004)...
start "Portfolio Orchestrator" cmd /k "%VENV_PATH% && uvicorn src.portfolio_orchestrator:app --reload --port 8004 %DEBUG_FLAGS%"
timeout /t 2 /nobreak > nul

echo.
echo ========================================
echo  All servers are starting up!
echo ========================================
echo.
if /i "%DEBUG_MODE%"=="y" (
    echo DEBUG MODE ACTIVE - Check server windows for detailed logs
    echo.
)
echo Server URLs:
echo - Events Controller:       http://localhost:8000
echo - Markets Controller:      http://localhost:8001
echo - Momentum Strategy:       http://localhost:8002
echo - Paper Trading:           http://localhost:8003
echo - Portfolio Orchestrator:  http://localhost:8004
echo.
echo Wait a few seconds for all servers to fully start,
echo then you can run your paper trading demo!
echo.

echo Opening FastAPI documentation pages...
timeout /t 3 /nobreak > nul
start chrome "http://localhost:8000/docs"
start chrome "http://localhost:8001/docs"
start chrome "http://localhost:8002/docs"
start chrome "http://localhost:8003/docs"
start chrome "http://localhost:8004/docs"
echo.
echo ========================================
echo  PRESS ANY KEY TO STOP ALL SERVERS
echo ========================================
pause >nul

echo.
echo Stopping all servers...
call stop_servers.bat