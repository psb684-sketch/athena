@echo off
chcp 65001 >nul
setlocal
pushd "%~dp0"
title ATHENA - Local ERP
py -3 -c "import sys,sqlite3; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if not errorlevel 1 goto run_py
python -c "import sys,sqlite3; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if not errorlevel 1 goto run_python
echo.
echo Python 3.10 이상을 찾지 못했습니다.
echo Python 설치 후 다시 실행해 주세요. 사용 안내는 README.md에 있습니다.
echo 공식 설치 안내: https://www.python.org/downloads/windows/
echo.
pause
popd
exit /b 1
:run_py
py -3 run.py %*
goto finished
:run_python
python run.py %*
:finished
if errorlevel 1 (
 echo.
 echo 실행 중 오류가 발생했습니다. 위의 오류 내용을 확인해 주세요.
 pause
)
popd
endlocal
