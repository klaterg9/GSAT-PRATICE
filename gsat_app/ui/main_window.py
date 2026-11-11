"""메인 창: 모의고사 목록 / 응시 / 결과."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
                               QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QStackedWidget,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .. import storage
from .answer_key import AnswerKeyDialog, AnswerKeyPage
from .common import ACCENT
from .create_dialog import CreateDialog
from .random_dialog import RandomDialog
from .exam_page import ExamPage
from ..pages import PdfPages
from .region_editor import RegionEditor, has_regions, max_page_used, sections_from_exam
from .result_page import ResultPage


class HomePage(QWidget):
    def __init__(self, win: "MainWindow"):
        super().__init__()
        self.win = win
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 26, 32, 26)
        title = QLabel("GSAT 모의고사")
        title.setObjectName("title")
        lay.addWidget(title)
        sub = QLabel("PDF로 모의고사를 만들고 실전처럼 풀어보세요.  (.gsat 파일을 이 창에 끌어다 놓으면 가져옵니다)")
        sub.setObjectName("muted")
        lay.addWidget(sub)
        lay.addSpacing(8)

        body = QHBoxLayout()
        body.setSpacing(18)
        self.list = QListWidget()
        self.list.setObjectName("examList")
        self.list.setSpacing(4)
        self.list.setStyleSheet(
            "QListWidget#examList { background: #f6f7f9; border: none; border-radius: 12px; padding: 6px; }"
            " QListWidget#examList::item { background: white; border: 1px solid #e4e6eb; border-radius: 10px;"
            " padding: 0; margin: 2px 4px; }"
            " QListWidget#examList::item:hover { border-color: #c4cfe6; }"
            f" QListWidget#examList::item:selected {{ background: #f2f6fe; border: 2px solid {ACCENT}; }}")
        self.list.itemDoubleClicked.connect(lambda _: self.win.take_exam(full=True))
        body.addWidget(self.list, 1)
        self.empty = QLabel("아직 모의고사가 없습니다.\n오른쪽 '+ 새 모의고사 만들기'로 PDF에서 만들거나,\n"
                            ".gsat 파일을 이 창에 끌어다 놓으세요.")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setStyleSheet("background: #f6f7f9; border-radius: 12px; font-size: 15px; color: #6b6f76;")
        body.addWidget(self.empty, 1)

        side = QVBoxLayout()
        side.setSpacing(6)
        buttons = [
            (None, "응시"),
            ("실전 응시 (전 영역)", lambda: self.win.take_exam(full=True), "primary"),
            ("영역 선택 응시", lambda: self.win.take_exam(full=False)),
            ("랜덤 모의고사 만들기", self.win.create_random),
            ("응시 기록", self.win.show_history),
            (None, "편집"),
            ("정답 입력 / 수정", self.win.edit_answers),
            ("문항 영역 수정", self.win.edit_exam),
            (None, "모의고사 파일"),
            ("+ 새 모의고사 만들기", self.win.create_exam),
            ("내보내기 (파일로 공유)", self.win.export_exam),
            ("가져오기", self.win.import_exam),
            ("데이터 폴더 열기", self.win.open_data_folder),
            ("예전 버전 데이터 가져오기", self.win.import_legacy),
        ]
        for text, fn, *rest in buttons:
            if text is None:
                if side.count():
                    side.addSpacing(10)
                head = QLabel(fn)
                head.setObjectName("section")
                side.addWidget(head)
                continue
            b = QPushButton(text)
            b.setMinimumWidth(200)
            b.setMinimumHeight(36)
            if rest:
                b.setObjectName(rest[0])
            b.clicked.connect(fn)
            side.addWidget(b)
        side.addStretch()
        delete = QPushButton("삭제")
        delete.setObjectName("danger")
        delete.clicked.connect(self.win.delete_exam)
        side.addWidget(delete)
        body.addLayout(side)
        lay.addLayout(body, 1)

    def refresh(self):
        self.list.clear()
        for exam in storage.list_exams():
            parts = " · ".join(f"{s['name']} {len(s['questions'])}문항/{s['minutes']}분" for s in exam["sections"])
            results = storage.list_results(exam["id"])
            last = ""
            if results:
                r = results[0]
                sec = {s["key"]: s for s in exam["sections"]}
                c = sum(storage.score_section(storage.result_section(sec[x["key"]], x), x["answers"])["correct"]
                        for x in r["sections"] if x["key"] in sec)
                n = sum(len(storage.result_section(sec[x["key"]], x)["questions"])
                        for x in r["sections"] if x["key"] in sec)
                kind = " (오답)" if r.get("mode") == "retry" else ""
                last = f"최근 응시{kind} {r['date'][:10]} · {c}/{n} · 총 {len(results)}회"
            total = sum(len(s["questions"]) for s in exam["sections"])
            keyed = sum(1 for s in exam["sections"] for q in s["questions"] if q.get("answer"))
            key_info = "정답 입력 완료" if total and keyed == total else f"정답 {keyed}/{total} 입력"
            item = QListWidgetItem()
            item.setData(Qt.UserRole, exam["id"])
            item.setToolTip("더블클릭하면 실전 응시를 시작합니다")
            title = f"🎲 {exam['name']}" if exam.get("random") else exam["name"]
            card = _exam_card(title, parts, key_info, bool(total) and keyed == total, last)
            item.setSizeHint(card.sizeHint())
            self.list.addItem(item)
            self.list.setItemWidget(item, card)
        has = self.list.count() > 0
        self.list.setVisible(has)
        self.empty.setVisible(not has)
        if has:
            self.list.setCurrentRow(0)

    def select(self, exam_id: str):
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.UserRole) == exam_id:
                self.list.setCurrentRow(i)
                return

    def selected_id(self) -> str | None:
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item else None


def _exam_card(name: str, parts: str, key_info: str, key_done: bool, last: str) -> QWidget:
    """홈 목록의 모의고사 한 줄 (제목 + 영역 구성 + 정답/최근 응시 배지)"""
    w = QWidget()
    w.setAttribute(Qt.WA_TransparentForMouseEvents)  # 클릭/더블클릭은 목록이 받도록
    w.setStyleSheet("background: transparent;")
    v = QVBoxLayout(w)
    v.setContentsMargins(16, 12, 16, 12)
    v.setSpacing(4)
    title = QLabel(name)
    title.setStyleSheet("font-size: 16px; font-weight: bold;")
    v.addWidget(title)
    info = QLabel(parts)
    info.setStyleSheet("color: #6b6f76; font-size: 13px;")
    info.setWordWrap(True)
    v.addWidget(info)
    tags = QHBoxLayout()
    tags.setSpacing(6)
    tags.setContentsMargins(0, 4, 0, 0)

    def tag(text, fg, bg):
        t = QLabel(text)
        t.setStyleSheet(f"color:{fg}; background:{bg}; border-radius:9px; padding:2px 9px; font-size:12px;")
        tags.addWidget(t)
    tag(key_info, "#1b7a47" if key_done else "#a15c00", "#e6f5ec" if key_done else "#fdf1e0")
    if last:
        tag(last, "#2456c4", "#e8effd")
    tags.addStretch()
    v.addLayout(tags)
    return w


class HistoryDialog(QDialog):
    def __init__(self, exam: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"응시 기록 — {exam['name']}")
        self.resize(640, 420)
        self.chosen: dict | None = None
        self.results = storage.list_results(exam["id"])
        sec = {s["key"]: s for s in exam["sections"]}
        lay = QVBoxLayout(self)
        table = QTableWidget(len(self.results), 3)
        table.setHorizontalHeaderLabels(["날짜", "방식", "영역별 맞힌 수"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        for r, res in enumerate(self.results):
            scores = []
            for x in res["sections"]:
                if x["key"] in sec:
                    sc = storage.score_section(storage.result_section(sec[x["key"]], x), x["answers"])
                    scores.append(f"{x['name'][:2]} {sc['correct']}/{sc['total']}")
            for c, v in enumerate([res["date"].replace("T", " "), storage.MODE_SHORT.get(res["mode"], "영역"),
                                   "  ".join(scores)]):
                table.setItem(r, c, QTableWidgetItem(v))
        table.cellDoubleClicked.connect(lambda r, _c: self._pick(r))
        lay.addWidget(QLabel("더블클릭하면 결과를 볼 수 있습니다."))
        lay.addWidget(table)

    def _pick(self, row):
        self.chosen = self.results[row]
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GSAT 모의고사")
        self.resize(1280, 860)
        self.setAcceptDrops(True)  # .gsat 파일 끌어다 놓기
        self.setMinimumSize(900, 600)
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.home = HomePage(self)
        self.exam_page = ExamPage()
        self.result_page = ResultPage()
        self.key_page = AnswerKeyPage()
        for w in (self.home, self.exam_page, self.result_page, self.key_page):
            self.stack.addWidget(w)
        self.key_page.graded.connect(self._show_result)
        self.key_page.skipped.connect(self._show_result)
        self.result_page.edit_key.connect(self._edit_key_from_result)
        self.exam_page.finished.connect(self._on_finished)
        self.exam_page.closed.connect(self._on_exam_closed)
        self.result_page.home.connect(self.go_home)
        self.result_page.review.connect(self._review)
        self.result_page.retry.connect(self._retry)
        self.current_exam: dict | None = None
        self.go_home()

    def go_home(self):
        self.home.refresh()
        self.stack.setCurrentWidget(self.home)

    def _selected_exam(self) -> dict | None:
        exam_id = self.home.selected_id()
        if not exam_id:
            QMessageBox.information(self, "안내", "먼저 모의고사를 선택하세요. 없으면 '새 모의고사 만들기'를 눌러주세요.")
            return None
        return storage.load_exam(exam_id)

    def open_data_folder(self):
        folder = storage.DATA_DIR.parent
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def import_legacy(self):
        """예전 버전(EXE 옆 data 폴더)에서 만든 모의고사를 가져온다. 프로그램 폴더, data 폴더, exams 폴더 아무거나 골라도 됨."""
        picked = QFileDialog.getExistingDirectory(self, "예전 GSAT_Practice 폴더(또는 그 안의 data 폴더) 선택",
                                                  str(Path.home()))
        if not picked:
            return
        p = Path(picked)
        candidates = [p / "data", p, p.parent] if p.name != "exams" else [p.parent]
        src = next((c for c in candidates if (c / "exams").is_dir()), None)
        if src is None:
            QMessageBox.warning(self, "예전 데이터 가져오기", "이 폴더에서 모의고사를 찾지 못했습니다.\n"
                                                         "예전 GSAT_Practice 폴더나 그 안의 data 폴더를 골라 주세요.")
            return
        n = storage.migrate_legacy_data([src])
        self.go_home()
        QMessageBox.information(self, "예전 데이터 가져오기",
                                f"모의고사 {n}개를 가져왔습니다." if n else "새로 가져올 모의고사가 없습니다 (이미 모두 있습니다).")

    def create_random(self):
        if not storage.list_exams():
            QMessageBox.information(self, "랜덤 모의고사", "먼저 모의고사를 하나 이상 만들어 주세요.")
            return
        dlg = RandomDialog(self)
        if dlg.exec() != QDialog.Accepted or not dlg.exam:
            return
        self.go_home()
        self.home.select(dlg.exam["id"])
        n = sum(len(s["questions"]) for s in dlg.exam["sections"])
        msg = f"'{dlg.exam['name']}' ({n}문항)을 만들었습니다.\n바로 풀어볼까요?"
        if QMessageBox.question(self, "랜덤 모의고사", msg) == QMessageBox.Yes:
            self.take_exam(full=True)

    def create_exam(self):
        dlg = CreateDialog(self)
        if dlg.exec() == QDialog.Accepted:
            self.go_home()

    def edit_exam(self):
        exam = self._selected_exam()
        if not exam:
            return
        if exam.get("random"):
            QMessageBox.information(self, "문항 영역 수정", "랜덤 모의고사는 다른 모의고사에서 문항을 모은 것이라 영역을 수정할 수 없습니다.\n"
                                                         "원래 모의고사에서 수정하세요. 정답은 '정답 입력 / 수정'에서 고칠 수 있습니다.")
            return
        if not has_regions(exam):
            QMessageBox.information(self, "문항 영역 수정", "이 모의고사에는 문항 영역 정보가 없어 수정할 수 없습니다.\n"
                                                         "정답은 '정답 입력 / 수정'에서 고칠 수 있습니다.")
            return
        found = storage.find_pdf(exam)
        if found is None:
            # 예전에 만든 모의고사인데 원본 PDF 를 옮겼거나, 가져온 모의고사 -> 원본 PDF 를 다시 지정
            pdf = self._relink_pdf(exam)
            if not pdf:
                return
        else:
            pdf = str(found)
        if Path(pdf) != storage.stored_pdf(exam["id"]):
            # 아직 복사본이 없으면 지금 시험 폴더에 복사해 둔다 (다음부터는 원본이 없어도 수정 가능)
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                pdf = str(storage.store_pdf(exam["id"], pdf))
            except OSError:
                pass  # 복사 실패해도 이번에는 원래 PDF 로 편집
            finally:
                QApplication.restoreOverrideCursor()
        if RegionEditor(exam, sections_from_exam(exam), pdf, self).exec() == QDialog.Accepted:
            self.go_home()

    def _relink_pdf(self, exam: dict) -> str | None:
        """원본 PDF 를 찾을 수 없을 때 사용자가 다시 골라 연결한다. 연결한 경로를 저장하고 돌려준다."""
        old = exam.get("source_pdf") or ""
        hint = exam.get("source") or (Path(old).name if old else "")
        msg = ("원본 PDF를 찾을 수 없습니다." + (f"\n{old}" if old else "") +
               "\n\n문항 영역을 수정하려면 이 모의고사를 만들 때 사용한 PDF를 다시 선택해 주세요." +
               (f"\n(원래 파일 이름: {hint})" if hint else ""))
        if QMessageBox.question(self, "원본 PDF 연결", msg, QMessageBox.Ok | QMessageBox.Cancel) != QMessageBox.Ok:
            return None
        start = str(Path(old).parent) if old and Path(old).parent.exists() else str(Path.home())
        path, _ = QFileDialog.getOpenFileName(self, f"원본 PDF 선택{f' — {hint}' if hint else ''}", start,
                                              "PDF (*.pdf)")
        if not path:
            return None
        need = max_page_used(exam) + 1
        try:
            src = PdfPages(path)
            count = src.page_count
            src.close()
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "원본 PDF 연결", f"PDF를 열 수 없습니다.\n{e}")
            return None
        if count < need:
            QMessageBox.warning(self, "원본 PDF 연결", f"선택한 PDF는 {count}쪽인데, 이 모의고사는 {need}쪽까지 사용합니다.\n"
                                                    "만들 때 사용한 PDF가 맞는지 확인하세요.")
            return None
        if hint and Path(path).name != hint and QMessageBox.question(
                self, "원본 PDF 연결", f"파일 이름이 원래와 다릅니다.\n원래: {hint}\n선택: {Path(path).name}\n\n"
                                     "이 PDF로 연결할까요? (다른 PDF면 문항 위치가 어긋납니다)") != QMessageBox.Yes:
            return None
        exam["source_pdf"] = str(Path(path).resolve())
        exam.setdefault("source", Path(path).name)
        storage.save_exam(exam)
        return exam["source_pdf"]

    def edit_answers(self):
        exam = self._selected_exam()
        if exam and AnswerKeyDialog(exam, self).exec() == QDialog.Accepted:
            self.go_home()

    def export_exam(self):
        exam = self._selected_exam()
        if not exam:
            return
        safe = "".join(c for c in exam["name"] if c not in '\\/:*?"<>|').strip() or "모의고사"
        path, _ = QFileDialog.getSaveFileName(self, "모의고사 내보내기", str(Path.home() / "Desktop" / f"{safe}.gsat"),
                                              "GSAT 모의고사 (*.gsat)")
        if not path:
            return
        if not path.lower().endswith(storage.EXPORT_EXT):
            path += storage.EXPORT_EXT
        try:
            storage.export_exam(exam["id"], Path(path))
        except OSError as e:
            QMessageBox.critical(self, "내보내기 실패", str(e))
            return
        n = sum(len(s["questions"]) for s in exam["sections"])
        size = Path(path).stat().st_size / 1024 / 1024
        QMessageBox.information(self, "내보내기 완료",
                                f"{n}문항을 내보냈습니다 ({size:.1f}MB).\n{path}\n\n"
                                "받는 사람은 이 프로그램에서 '가져오기'를 누르거나 파일을 창에 끌어다 놓으면 됩니다.\n"
                                "(응시 기록은 포함되지 않습니다)")

    def import_exam(self, path: str | None = None):
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, "모의고사 가져오기", "", "GSAT 모의고사 (*.gsat)")
            if not path:
                return
        try:
            exam = storage.import_exam(Path(path))
        except (OSError, ValueError, zipfile.BadZipFile, json.JSONDecodeError) as e:
            QMessageBox.critical(self, "가져오기 실패", f"모의고사 파일을 열 수 없습니다.\n{e}")
            return
        self.go_home()
        QMessageBox.information(self, "가져오기 완료", f"'{exam['name']}'을(를) 가져왔습니다.")

    def dragEnterEvent(self, event):  # noqa: N802
        if any(u.toLocalFile().lower().endswith(storage.EXPORT_EXT) for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):  # noqa: N802
        for u in event.mimeData().urls():
            if u.toLocalFile().lower().endswith(storage.EXPORT_EXT):
                self.import_exam(u.toLocalFile())

    def delete_exam(self):
        exam = self._selected_exam()
        if exam and QMessageBox.question(self, "삭제", f"'{exam['name']}'과 응시 기록을 모두 삭제할까요?") == QMessageBox.Yes:
            storage.delete_exam(exam["id"])
            self.go_home()

    def take_exam(self, full: bool):
        exam = self._selected_exam()
        if not exam:
            return
        keys = [s["key"] for s in exam["sections"] if s["questions"]]
        if not full:
            names = [s["name"] for s in exam["sections"] if s["questions"]]
            name, ok = QInputDialog.getItem(self, "영역 선택", "응시할 영역", names, 0, False)
            if not ok:
                return
            keys = [s["key"] for s in exam["sections"] if s["name"] == name]
        if not keys:
            QMessageBox.information(self, "안내", "문항이 없습니다.")
            return
        self.current_exam = exam
        self.exam_page.start_exam(exam, keys)
        self.stack.setCurrentWidget(self.exam_page)

    def show_history(self):
        exam = self._selected_exam()
        if not exam:
            return
        if not storage.list_results(exam["id"]):
            QMessageBox.information(self, "응시 기록", "아직 응시 기록이 없습니다.")
            return
        dlg = HistoryDialog(exam, self)
        if dlg.exec() == QDialog.Accepted and dlg.chosen:
            self.current_exam = exam
            self.last_result = dlg.chosen
            self._show_result()

    def _on_finished(self, result: dict):
        """응시 완료 -> 정답이 비어 있으면 정답 입력 화면, 다 있으면 바로 결과"""
        self.current_exam = storage.load_exam(self.current_exam["id"])
        self.last_result = result
        by_key = {rs["key"]: rs for rs in result["sections"]}
        missing = any(not q.get("answer") for s in self.current_exam["sections"] if s["key"] in by_key
                      for q in storage.result_section(s, by_key[s["key"]])["questions"])
        if missing:
            self.key_page.start(self.current_exam, result)
            self.stack.setCurrentWidget(self.key_page)
        else:
            self._show_result()

    def _show_result(self):
        self.current_exam = storage.load_exam(self.current_exam["id"])
        self.result_page.show_result(self.current_exam, self.last_result)
        self.stack.setCurrentWidget(self.result_page)

    def _edit_key_from_result(self, result: dict):
        mine = {s["key"]: s["answers"] for s in result["sections"]}
        dlg = AnswerKeyDialog(self.current_exam, self, mine=mine, section_keys=list(mine))
        if dlg.exec() == QDialog.Accepted:
            self.last_result = result
            self._show_result()

    def _on_exam_closed(self):
        if self.exam_page.review:
            self.stack.setCurrentWidget(self.result_page)
        else:
            self.go_home()

    def _retry(self, result: dict):
        """결과 화면 -> 처음 응시에서 틀렸거나 안 푼 문제를 모아서 다시 풀기.
        다시 푼 기록에서 눌러도 처음 응시 기준이라, 한 번 맞힌 문제도 계속 다시 풀 수 있다."""
        exam = storage.load_exam(self.current_exam["id"])
        sec = {s["key"]: s for s in exam["sections"]}
        base = storage.retry_base(exam["id"], result)
        only = {rs["key"]: storage.wrong_numbers(sec[rs["key"]], rs) for rs in base["sections"] if rs["key"] in sec}
        only = {k: v for k, v in only.items() if v}
        if not only:
            QMessageBox.information(self, "틀린 문제 다시 풀기", "틀린 문제가 없습니다. 👏")
            return
        self.current_exam = exam
        self.exam_page.start_exam(exam, list(only), only=only, base=base.get("file"))
        self.stack.setCurrentWidget(self.exam_page)

    def _review(self, result: dict, only_wrong: bool, focus):
        if self.exam_page.start_review(self.current_exam, result, only_wrong, focus):
            self.stack.setCurrentWidget(self.exam_page)
