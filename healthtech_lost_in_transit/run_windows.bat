@echo off
setlocal
if not exist .venv (
  py -3 -m venv .venv
  if errorlevel 1 goto error
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 goto error
if not defined SECRET_KEY set SECRET_KEY=local-development-only-change-before-deployment
python app.py
goto end
:error
echo Setup failed. Confirm Python 3.10+ is installed and internet access is available for package installation.
exit /b 1
:end
endlocal
