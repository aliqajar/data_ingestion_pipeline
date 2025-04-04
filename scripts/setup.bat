@echo off

:: Set environment name
set ENV_NAME=weather_pipeline_env

:: Create virtual environment
python -m venv %ENV_NAME%

:: Activate virtual environment
call .\%ENV_NAME%\Scripts\activate.bat

:: Upgrade pip
python -m pip install --upgrade pip

:: Install base dependencies
pip install -r requirements/base.txt

:: Install service-specific dependencies
pip install -r requirements/collector.txt
pip install -r requirements/consumer.txt
pip install -r requirements/query.txt

:: Create .env file from template if it doesn't exist
if not exist .env (
    copy .env.example .env
    echo Created .env file from template. Please update the values in .env file.
)

echo Setup completed successfully!
echo.
echo To activate the virtual environment in a new terminal:
echo In Git Bash: .\%ENV_NAME%\Scripts\activate
echo In CMD: .\%ENV_NAME%\Scripts\activate.bat
echo.
pause 