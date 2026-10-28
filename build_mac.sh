#!/bin/sh
# GSAT 모의고사 맥 앱 빌드 -> dist/GSAT_Practice.app
# 사용법: 터미널에서  sh build_mac.sh
set -e
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv
fi
.venv/bin/python -m pip install -r requirements-build.txt
.venv/bin/python -m PyInstaller --noconfirm --clean GSAT_Practice.spec

echo
echo "빌드 완료: dist/GSAT_Practice.app"
