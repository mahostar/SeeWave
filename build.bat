@echo off
echo Building SeeWav application...

REM Activate virtual environment
call .\venv\Scripts\activate

REM Ensure required files exist
if not exist logo.png (
    echo ERROR: logo.png not found in current directory!
    exit /b 1
)
if not exist image.svg (
    echo ERROR: image.svg not found in current directory!
    exit /b 1
)

REM Install PyInstaller
pip install pyinstaller

REM Clean previous builds
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM Build the application
pyinstaller --clean seewav.spec

if %ERRORLEVEL% NEQ 0 (
    echo Build failed with error code %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)

echo Build complete! Check the dist folder for the executable.
echo Opening dist folder...
explorer dist 