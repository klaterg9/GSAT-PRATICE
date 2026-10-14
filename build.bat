@echo off
rem GSAT 모의고사 Windows 빌드
rem   build.bat          : dist\GSAT_Practice\ 폴더 (기본, 폴더째 옮기면 데이터까지 같이 이동)
rem   build.bat onefile  : dist\GSAT_Practice.exe 파일 하나
chcp 65001 > nul
cd /d %~dp0

if not exist .venv\Scripts\python.exe (
    echo [오류] .venv 가상환경이 없습니다. PyCharm 에서 프로젝트를 먼저 열어주세요.
    exit /b 1
)

.venv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller
if errorlevel 1 exit /b 1

if /i "%1"=="onefile" (set GSAT_BUILD_MODE=onefile) else (set GSAT_BUILD_MODE=folder)
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean GSAT_Practice.spec
if errorlevel 1 exit /b 1

if /i not "%1"=="onefile" copy /y packaging\README.txt dist\GSAT_Practice\README.txt > nul

echo.
echo 빌드 완료: dist 폴더를 확인하세요.
