"""메인 창: 모의고사 목록 / 응시 / 결과."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QListWidget,
                               QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QStackedWidget, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from .. import storage
from .answer_key import AnswerKeyDialog, AnswerKeyPage
from .create_dialog import CreateDialog
from .exam_page import ExamPage
from .region_editor import RegionEditor, is_region_exam, sections_from_exam
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
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _: self.win.take_exam(full=True))
        body.addWidget(self.list, 1)

        side = QVBoxLayout()
        buttons = [
            ("+ 새 모의고사 만들기", self.win.create_exam, "primary"),
            ("실전 응시 (전 영역)", lambda: self.win.take_exam(full=True), None),
            ("영역 선택 응시", lambda: self.win.take_exam(full=False), None),
            ("응시 기록", self.win.show_history, None),
            ("정답 입력 / 수정", self.win.edit_answers, None),
            ("문항 영역 수정", self.win.edit_exam, None),
            (None, None, None),
            ("내보내기 (파일로 공유)", self.win.export_exam, None),
            ("가져오기", self.win.import_exam, None),
            (None, None, None),
            ("삭제", self.win.delete_exam, "danger"),
        ]
        for text, fn, name in buttons:
            if text is None:
                side.addSpacing(10)
                continue
            b = QPushButton(text)
            b.setMinimumWidth(190)
            if name:
                b.setObjectName(name)
            b.clicked.connect(fn)
            side.addWidget(b)
        side.addStretch()
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
                c = sum(storage.score_section(sec[x["key"]], x["answers"])["correct"]
                        for x in r["sections"] if x["key"] in sec)
                n = sum(len(sec[x["key"]]["questions"]) for x in r["sections"] if x["key"] in sec)
                last = f"\n최근 응시 {r['date'][:10]}  {c}/{n}  (총 {len(results)}회)"
            total = sum(len(s["questions"]) for s in exam["sections"])
            keyed = sum(1 for s in exam["sections"] for q in s["questions"] if q.get("answer"))
            key_info = "정답 입력 완료" if total and keyed == total else f"정답 {keyed}/{total} 입력"
            item = QListWidgetItem(f"{exam['name']}\n{parts}   ·   {key_info}{last}")
            item.setData(Qt.UserRole, exam["id"])
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)

    def selected_id(self) -> str | None:
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item else None


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
                    sc = storage.score_section(sec[x["key"]], x["answers"])
                    scores.append(f"{x['name'][:2]} {sc['correct']}/{sc['total']}")
            for c, v in enumerate([res["date"].replace("T", " "), "실전" if res["mode"] == "full" else "영역",
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

    def create_exam(self):
        dlg = CreateDialog(self)
        if dlg.exec() == QDialog.Accepted:
            self.go_home()

    def edit_exam(self):
        exam = self._selected_exam()
        if not exam:
            return
        if not is_region_exam(exam):
            QMessageBox.information(self, "문항 영역 수정", "가져온 모의고사는 원본 PDF가 없어 문항 영역을 수정할 수 없습니다.\n"
                                                         "정답은 '정답 입력 / 수정'에서 고칠 수 있습니다.")
            return
        pdf = exam["source_pdf"]
        if not Path(pdf).exists():
            QMessageBox.warning(self, "문항 영역 수정", f"원본 PDF를 찾을 수 없습니다.\n{pdf}\n\n"
                                                    "PDF를 원래 위치로 옮긴 뒤 다시 시도하세요.")
            return
        if RegionEditor(exam, sections_from_exam(exam), pdf, self).exec() == QDialog.Accepted:
            self.go_home()

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
        keys = {s["key"] for s in result["sections"]}
        missing = any(not q.get("answer") for s in self.current_exam["sections"] if s["key"] in keys
                      for q in s["questions"])
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

    def _review(self, result: dict, only_wrong: bool, focus):
        if self.exam_page.start_review(self.current_exam, result, only_wrong, focus):
            self.stack.setCurrentWidget(self.exam_page)
