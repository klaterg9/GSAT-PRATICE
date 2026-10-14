# PyInstaller 빌드 설정.  실행: build.bat  (또는 pyinstaller GSAT_Practice.spec)
#
#   build.bat          -> dist/GSAT_Practice.exe            (파일 하나, 배포 편함, 첫 실행이 몇 초 느림)
#   build.bat folder   -> dist/GSAT_Practice/GSAT_Practice.exe (폴더째 배포, 실행 빠름)
import os

ONEFILE = os.environ.get("GSAT_BUILD_MODE", "onefile") != "folder"

datas, binaries, hiddenimports = [], [], []

# 쓰지 않는 Qt 모듈 / 큰 라이브러리 제외 (용량 절약)
EXCLUDES = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.Qt3DCore", "PySide6.QtMultimedia",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtNetwork", "PySide6.QtOpenGL", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtBluetooth",
    "tkinter", "matplotlib", "scipy", "pandas", "IPython", "cv2", "winrt",
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=EXCLUDES,
    noarchive=False,
)

pyz = PYZ(a.pure)

if ONEFILE:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="GSAT_Practice", console=False, upx=False)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="GSAT_Practice", console=False, upx=False)
    coll = COLLECT(exe, a.binaries, a.datas, name="GSAT_Practice", upx=False)
