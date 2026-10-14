PDF 모의고사(텍스트 PDF, 제본 스캔본, 펼침면 스캔본)에서 문항 영역을 직접 선택해 GSAT 실전처럼 풀어보는 프로그램입니다.

### 다운로드
| 운영체제 | 파일 |
|---|---|
| Windows 10/11 (64비트) | `GSAT_Practice.exe` |
| macOS (Apple Silicon, M1 이후) | `GSAT_Practice-mac-AppleSilicon.zip` |

Python 설치는 필요 없습니다.

### Windows
- `GSAT_Practice.exe`를 전용 폴더에 넣고 실행하세요. 만든 모의고사는 **EXE 옆 `data` 폴더**에 저장됩니다.
- 서명되지 않은 실행 파일이라 SmartScreen 경고가 나오면 **추가 정보 → 실행**을 누르세요.

### macOS
1. zip을 풀고 `GSAT_Practice.app`을 **응용 프로그램** 폴더로 옮깁니다.
2. 처음 열 때 "Apple에서 확인할 수 없습니다" 경고가 나옵니다 (Apple 개발자 서명이 없는 앱).
   - **시스템 설정 → 개인정보 보호 및 보안 → 아래쪽 "그래도 열기"**를 누르세요. (macOS 14 이하는 앱을 오른쪽 클릭 → **열기**도 됩니다.)
   - 또는 터미널에서: `xattr -dr com.apple.quarantine /Applications/GSAT_Practice.app`
3. 만든 모의고사는 `~/Library/Application Support/GSAT모의고사/data`에 저장됩니다.

### ⚠️ 저작권 안내
- 이 배포에는 **프로그램만** 포함되어 있습니다. 도서, 문제집, 모의고사 등 **프로그램 이외의 어떠한 저작권물도 포함하거나 공유하지 않습니다.**
- 저작권법에 따라 **직접 구매한 도서를 본인이 스캔하여 개인 학습 목적으로 사용하는 것을 권장**합니다.
- 저작권이 있는 도서 내용으로 만든 모의고사나 `.gsat` 파일은 다른 사람에게 배포하거나 공유하지 마세요. 저작권물의 무단 복제·배포에 대한 책임은 사용자 본인에게 있습니다.
