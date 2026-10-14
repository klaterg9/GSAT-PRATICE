# PyInstaller 빌드 설정.
#
#   Windows: build.bat          -> dist/GSAT_Practice.exe               (파일 하나)
#            build.bat folder   -> dist/GSAT_Practice/GSAT_Practice.exe (폴더째 배포, 실행 빠름)
#   macOS  : ./build_mac.sh     -> dist/GSAT_Practice.app
#
# GitHub Actions(.github/workflows/release.yml)도 이 파일로 빌드한다.
import os
import sys

IS_MAC = sys.platform == "darwin"
ONEFILE = not IS_MAC and os.environ.get("GSAT_BUILD_MODE", "onefile") != "folder"
VERSION = os.environ.get("GSAT_VERSION", "1.0.0")

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

if IS_MAC:
    # 맥은 .app 번들 (폴더형). 서명은 PyInstaller 가 ad-hoc 으로 해준다 (Apple Silicon 실행에 필요).
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="GSAT_Practice", console=False, upx=False)
    coll = COLLECT(exe, a.binaries, a.datas, name="GSAT_Practice", upx=False)
    app = BUNDLE(
        coll,
        name="GSAT_Practice.app",
        bundle_identifier="io.github.klaterg9.gsat-practice",
        version=VERSION,
        info_plist={
            "CFBundleDisplayName": "GSAT 모의고사",
            "CFBundleShortVersionString": VERSION,
            "NSHighResolutionCapable": True,
        },
    )
elif ONEFILE:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="GSAT_Practice", console=False, upx=False)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="GSAT_Practice", console=False, upx=False)
    coll = COLLECT(exe, a.binaries, a.datas, name="GSAT_Practice", upx=False)
