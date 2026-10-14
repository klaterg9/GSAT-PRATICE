@echo off
rem GSAT 모의고사 EXE 빌드
rem   build.bat         : dist\GSAT_Practice.exe 파일 하나
rem   build.bat folder  : dist\GSAT_Practice\ 폴더 (실행이 더 빠름)
chcp 65001 > nul
cd /d %~dp0

if not exist .venv\Scripts\python.exe (
    echo [오류] .venv 가상환경이 없습니다. PyCharm 에서 프로젝트를 먼저 열어주세요.
    exit /b 1
)

.venv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller
if errorlevel 1 exit /b 1

if /i "%1"=="folder" (set GSAT_BUILD_MODE=folder) else (set GSAT_BUILD_MODE=onefile)
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean GSAT_Practice.spec
if errorlevel 1 exit /b 1

echo.
echo 빌드 완료: dist 폴더를 확인하세요.
