"""GSAT 모의고사 프로그램 실행 파일 (PyCharm에서 Shift+F10)."""
import sys


def selftest() -> int:
    """EXE 빌드 확인용: `GSAT_Practice.exe --selftest` -> 실행 폴더에 selftest.txt 작성."""
    from pathlib import Path

    lines = []
    try:
        import numpy as np
        import pymupdf

        from gsat_app import scan, storage
        lines.append(f"data dir: {storage.DATA_DIR}")
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 72), "selftest")
        pix = page.get_pixmap(dpi=72)
        lines.append(f"pdf render: {pix.width}x{pix.height}")
        cleaned = scan.clean_page(np.full((400, 300), 200, np.uint8))
        lines.append(f"scan clean: {cleaned.shape}")
        lines.append("OK")
        code = 0
    except Exception as e:  # noqa: BLE001
        lines.append(f"FAIL: {type(e).__name__}: {e}")
        code = 1
    print("\n".join(lines))  # CI(GitHub Actions) 로그에서 확인용
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
    try:
        (base / "selftest.txt").write_text("\n".join(lines), encoding="utf-8")
    except OSError:
        pass
    return code


def main():
    if "--selftest" in sys.argv:
        sys.exit(selftest())

    import faulthandler
    import traceback
    from datetime import datetime

    from PySide6.QtWidgets import QApplication, QMessageBox

    from gsat_app import storage
    from gsat_app.ui.common import STYLE
    from gsat_app.ui.main_window import MainWindow

    # 프로그램이 갑자기 꺼지거나 오류가 나면 data 폴더 옆 error.log 에 원인을 남긴다
    log_path = storage.DATA_DIR.parent / "error.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(log_path, "a", encoding="utf-8")  # noqa: SIM115  (프로그램이 끝날 때까지 열어둠)
    log_file.write(f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S} 시작 ===\n")
    log_file.flush()
    faulthandler.enable(log_file)

    def on_error(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        log_file.write(text)
        log_file.flush()
        sys.__stderr__ and sys.__stderr__.write(text)
        QMessageBox.critical(None, "오류", f"오류가 발생했습니다.\n{exc}\n\n자세한 내용: {log_path}")
    sys.excepthook = on_error

    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    win = MainWindow()
    # 노트북 화면(세로 1000 미만)에서는 최대화해서 시작
    screen = app.primaryScreen().availableGeometry()
    if screen.height() < 1000 or screen.width() < 1400:
        win.showMaximized()
    else:
        win.show()
    # .gsat 파일을 EXE 아이콘에 끌어다 놓거나 '연결 프로그램'으로 열면 바로 가져오기
    for arg in sys.argv[1:]:
        if arg.lower().endswith(".gsat"):
            win.import_exam(arg)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
