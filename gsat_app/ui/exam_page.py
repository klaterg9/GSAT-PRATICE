"""응시 화면 (타이머, OMR 답안지) 과 해설(다시 보기) 화면."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QElapsedTimer, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton, QScrollArea,
                               QStackedWidget, QVBoxLayout, QWidget)

from .. import storage
from .common import ACCENT, BAD, OK, QuestionView, circled


def fmt_time(sec: float) -> str:
    sec = max(0, int(sec))
    return f"{sec // 60:02d}:{sec % 60:02d}"


class OmrPanel(QScrollArea):
    """오른쪽 OMR 답안지. 번호를 누르면 이동, 동그라미를 누르면 마킹."""
    jump = Signal(int)
    mark = Signal(int, int)  # (문항 index, 선택)

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFixedWidth(215)
        self.setStyleSheet("QScrollArea { border-left: 1px solid #e5e7eb; }")
        self.inner = QWidget()
        self.grid = QGridLayout(self.inner)
        self.grid.setContentsMargins(10, 10, 10, 10)
        self.grid.setHorizontalSpacing(3)
        self.grid.setVerticalSpacing(4)
        self.setWidget(self.inner)
        self.num_buttons: list[QPushButton] = []
        self.bubbles: list[list[QPushButton]] = []

    def build(self, questions: list[dict]):
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.hide()  # 바로 지우지 않고 숨김 -> 아래 deleteLater 로 안전하게 삭제
                w.deleteLater()
        self.num_buttons, self.bubbles = [], []
        for r, q in enumerate(questions):
            nb = QPushButton(str(q["number"]))
            nb.setFixedSize(38, 24)
            nb.clicked.connect(lambda _=False, r=r: self.jump.emit(r))
            self.grid.addWidget(nb, r, 0)
            self.num_buttons.append(nb)
            row = []
            for i in range(1, (q.get("num_choices") or 5) + 1):
                b = QPushButton(str(i))
                b.setFixedSize(26, 24)
                b.clicked.connect(lambda _=False, r=r, i=i: self.mark.emit(r, i))
                self.grid.addWidget(b, r, i)
                row.append(b)
            self.bubbles.append(row)
        self.grid.setRowStretch(len(questions), 1)

    def update_marks(self, questions, answers: dict, current: int, show_answer: bool = False):
        for r, q in enumerate(questions):
            mine = answers.get(str(q["number"]))
            key = q.get("answer")
            cur = r == current
            self.num_buttons[r].setStyleSheet(
                "padding:0; font-size:12px;" + (f"background:{ACCENT}; color:white; border:none;" if cur else ""))
            for i, b in enumerate(self.bubbles[r], start=1):
                color = None
                if show_answer and key is not None:
                    if i == key:
                        color = OK
                    elif i == mine:
                        color = BAD
                elif i == mine:
                    color = "#222"
                b.setStyleSheet("padding:0; border-radius:12px; font-size:11px;"
                                + (f"background:{color}; color:white; border:none;" if color else "background:white;"))
        if 0 <= current < len(self.num_buttons):
            self.ensureWidgetVisible(self.num_buttons[current], 0, 60)


class ExamPage(QWidget):
    finished = Signal(dict)  # 응시 완료 -> 결과
    closed = Signal()        # 중단/해설 닫기

    def __init__(self):
        super().__init__()
        self.exam: dict = {}
        self.review = False
        self._q_i = self.r_i = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        bar = QFrame()
        bar.setStyleSheet("QFrame { background: #f7f8fa; border-bottom: 1px solid #e5e7eb; }")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(18, 10, 18, 10)
        self.section_label = QLabel()
        self.section_label.setStyleSheet("font-size: 16px; font-weight: bold; background: transparent;")
        self.count_label = QLabel()
        self.count_label.setStyleSheet("color:#6b6f76; background: transparent;")
        self.timer_label = QLabel()
        self.timer_label.setStyleSheet("font-size: 22px; font-weight: bold; background: transparent;")
        self.quit_btn = QPushButton("그만두기")
        self.quit_btn.clicked.connect(self._quit)
        self.submit_btn = QPushButton("영역 제출")
        self.submit_btn.setObjectName("primary")
        self.submit_btn.clicked.connect(self._submit_clicked)
        bl.addWidget(self.section_label)
        bl.addSpacing(16)
        bl.addWidget(self.count_label)
        bl.addStretch()
        bl.addWidget(self.timer_label)
        bl.addStretch()
        # 문제 크기 조절 (Ctrl+휠로도 가능, 다음 실행에도 유지)
        self.zoom_label = QLabel()
        self.zoom_label.setStyleSheet("background: transparent; color:#555;")
        for text, d in (("−", -0.1), ("+", 0.1)):
            b = QPushButton(text)
            b.setFixedWidth(34)
            b.setToolTip("문제 크기 (Ctrl+휠)")
            b.clicked.connect(lambda _=False, d=d: self.view.set_zoom(self.view.zoom + d))
            if d < 0:
                bl.addWidget(QLabel("문제 크기"))
                bl.addWidget(b)
                bl.addWidget(self.zoom_label)
            else:
                bl.addWidget(b)
        bl.addSpacing(16)
        bl.addWidget(self.quit_btn)
        bl.addWidget(self.submit_btn)
        root.addWidget(bar)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        # 영역 시작 안내
        self.intro = QWidget()
        il = QVBoxLayout(self.intro)
        il.addStretch()
        self.intro_title = QLabel()
        self.intro_title.setAlignment(Qt.AlignCenter)
        self.intro_title.setStyleSheet("font-size: 30px; font-weight: 800;")
        self.intro_info = QLabel()
        self.intro_info.setAlignment(Qt.AlignCenter)
        self.intro_info.setStyleSheet("font-size: 16px; color: #555;")
        tip = QLabel("숫자키 1~5: 답 선택   ·   ← / → : 이전 / 다음 문항\n"
                     "영역을 제출하거나 시간이 끝나면 이전 영역으로 돌아갈 수 없습니다.")
        tip.setAlignment(Qt.AlignCenter)
        tip.setObjectName("muted")
        start = QPushButton("시작하기")
        start.setObjectName("primary")
        start.setFixedSize(200, 48)
        start.clicked.connect(self._begin_section)
        il.addWidget(self.intro_title)
        il.addWidget(self.intro_info)
        il.addSpacing(10)
        il.addWidget(tip)
        il.addSpacing(24)
        il.addWidget(start, 0, Qt.AlignCenter)
        il.addStretch()
        self.stack.addWidget(self.intro)

        # 문제 풀이
        work = QWidget()
        wl = QHBoxLayout(work)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(0)
        left = QVBoxLayout()
        left.setSpacing(0)
        self.view = QuestionView()
        self.view.answered.connect(self._answer)
        self.settings = QSettings("GSATPractice", "GSATPractice")
        self.view.zoom = float(self.settings.value("zoom", 1.0))
        self.view.zoom_changed.connect(self._zoom_changed)
        left.addWidget(self.view, 1)
        nav = QHBoxLayout()
        nav.setContentsMargins(18, 8, 18, 12)
        self.prev_btn = QPushButton("◀ 이전")
        self.prev_btn.clicked.connect(lambda: self._go(self.q_i - 1))
        self.next_btn = QPushButton("다음 ▶")
        self.next_btn.clicked.connect(lambda: self._go(self.q_i + 1))
        nav.addWidget(self.prev_btn)
        nav.addStretch()
        nav.addWidget(self.next_btn)
        left.addLayout(nav)
        wl.addLayout(left, 1)
        self.omr = OmrPanel()
        self.omr.jump.connect(self._go)
        self.omr.mark.connect(self._omr_mark)
        wl.addWidget(self.omr)
        self.stack.addWidget(work)

        self.tick = QTimer(self)
        self.tick.timeout.connect(self._on_tick)
        self.section_clock = QElapsedTimer()
        self.question_clock = QElapsedTimer()

        self.zoom_label.setText(f"{round(self.view.zoom * 100)}%")
        for key, fn in [(Qt.Key_Right, lambda: self._go(self.q_i + 1)), (Qt.Key_Left, lambda: self._go(self.q_i - 1))]:
            QShortcut(QKeySequence(key), self, fn, context=Qt.WidgetWithChildrenShortcut)
        for n in range(1, 10):
            QShortcut(QKeySequence(str(n)), self, lambda n=n: self._answer(n), context=Qt.WidgetWithChildrenShortcut)

    def _zoom_changed(self, z: float):
        self.zoom_label.setText(f"{round(z * 100)}%")
        self.settings.setValue("zoom", z)

    # ------------------------------------------------------------ 응시
    def start_exam(self, exam: dict, section_keys: list[str]):
        self.exam = exam
        self.review = False
        self.exam_path = storage.exam_dir(exam["id"])
        self.sections = [s for s in exam["sections"] if s["key"] in section_keys and s["questions"]]
        self.answers = {s["key"]: {} for s in self.sections}
        self.times = {s["key"]: {} for s in self.sections}
        self.elapsed: dict[str, float] = {}
        self.mode = "full" if len(self.sections) == len(exam["sections"]) else "section"
        self.sec_i = 0
        self.quit_btn.setText("그만두기")
        self.submit_btn.show()
        self._show_intro()

    def _show_intro(self):
        s = self.sections[self.sec_i]
        self.section_label.setText(f"{self.exam['name']}")
        self.count_label.setText(f"영역 {self.sec_i + 1} / {len(self.sections)}")
        self.timer_label.setText("")
        self.intro_title.setText(s["name"])
        self.intro_info.setText(f"{len(s['questions'])}문항  ·  {s['minutes']}분")
        self.submit_btn.setEnabled(False)
        self.stack.setCurrentIndex(0)

    def _begin_section(self):
        s = self.sections[self.sec_i]
        self.questions = s["questions"]
        self.limit = s["minutes"] * 60
        self.omr.build(self.questions)
        self.q_i = 0
        self.section_clock.start()
        self.tick.start(500)
        self.submit_btn.setEnabled(True)
        self.submit_btn.setText("영역 제출" if self.sec_i + 1 < len(self.sections) else "최종 제출")
        self.stack.setCurrentIndex(1)
        self._render()
        self._on_tick()

    def _section(self) -> dict:
        return self.sections[self.sec_i]

    def _on_tick(self):
        if self.review:
            return
        remain = self.limit - self.section_clock.elapsed() / 1000
        self.timer_label.setText(f"⏱ {fmt_time(remain)}")
        self.timer_label.setStyleSheet(
            f"font-size: 22px; font-weight: bold; background: transparent; color: {BAD if remain <= 60 else '#1d1d1f'};")
        if remain <= 0:
            self._end_section(timeout=True)

    def _record_time(self):
        if self.review or not self.question_clock.isValid():
            return
        key = str(self.questions[self.q_i]["number"])
        t = self.times[self._section()["key"]]
        t[key] = t.get(key, 0) + self.question_clock.elapsed() / 1000
        self.question_clock.invalidate()

    def _render(self):
        if self.review:
            self._render_review()
            return
        s = self._section()
        q = self.questions[self.q_i]
        ans = self.answers[s["key"]]
        self.section_label.setText(s["name"])
        self.count_label.setText(f"응답 {len(ans)} / {len(self.questions)}")
        self.view.show_question(self.exam_path, s, q, self.q_i, len(self.questions), ans.get(str(q["number"])))
        self.omr.update_marks(self.questions, ans, self.q_i)
        self.prev_btn.setEnabled(self.q_i > 0)
        self.next_btn.setEnabled(self.q_i < len(self.questions) - 1)
        self.question_clock.start()

    def _go(self, idx: int):
        if self.stack.currentIndex() != 1:
            return
        if self.review:
            if 0 <= idx < len(self.review_items):
                self.r_i = idx
                self._render_review()
            return
        if 0 <= idx < len(self.questions) and idx != self.q_i:
            self._record_time()
            self.q_i = idx
            self._render()

    def _answer(self, choice: int):
        if self.review or self.stack.currentIndex() != 1:
            return
        q = self.questions[self.q_i]
        if choice > (q.get("num_choices") or 5):
            return
        ans = self.answers[self._section()["key"]]
        key = str(q["number"])
        if ans.get(key) == choice:
            del ans[key]  # 같은 번호 다시 누르면 취소
        else:
            ans[key] = choice
        self._record_time()
        self._render()

    def _omr_mark(self, row: int, choice: int):
        if self.review:
            self._go(self._review_index(self._review_section_key, row))
            return
        if row != self.q_i:
            self._record_time()
            self.q_i = row
        self._answer(choice)

    def _submit_clicked(self):
        blank = len(self.questions) - len(self.answers[self._section()["key"]])
        msg = f"{self._section()['name']}을(를) 제출할까요?"
        if blank:
            msg += f"\n아직 풀지 않은 문항이 {blank}개 있습니다."
        if QMessageBox.question(self, "제출", msg) == QMessageBox.Yes:
            self._end_section()

    def _end_section(self, timeout: bool = False):
        self.tick.stop()
        self._record_time()
        s = self._section()
        self.elapsed[s["key"]] = min(self.limit, self.section_clock.elapsed() / 1000)
        if timeout:
            QMessageBox.information(self, "시간 종료", f"{s['name']} 시간이 끝났습니다.")
        self.sec_i += 1
        if self.sec_i < len(self.sections):
            self._show_intro()
            return
        result = {
            "exam_id": self.exam["id"], "exam_name": self.exam["name"],
            "date": datetime.now().isoformat(timespec="seconds"), "mode": self.mode,
            "sections": [{"key": s["key"], "name": s["name"], "answers": self.answers[s["key"]],
                          "times": {k: round(v, 1) for k, v in self.times[s["key"]].items()},
                          "elapsed": round(self.elapsed.get(s["key"], 0), 1), "limit": s["minutes"] * 60}
                         for s in self.sections],
        }
        storage.save_result(self.exam["id"], result)
        self.finished.emit(result)

    def _quit(self):
        if self.review:
            self.closed.emit()
            return
        if QMessageBox.question(self, "그만두기", "응시를 중단할까요? 기록은 저장되지 않습니다.") == QMessageBox.Yes:
            self.tick.stop()
            self.closed.emit()

    # ------------------------------------------------------------ 해설(다시 보기)
    def start_review(self, exam: dict, result: dict, only_wrong: bool = False, focus: tuple[str, int] | None = None):
        self.exam = exam
        self.review = True
        self.exam_path = storage.exam_dir(exam["id"])
        self.result_answers = {s["key"]: s["answers"] for s in result["sections"]}
        keys = [s["key"] for s in result["sections"]]
        self.review_items = []
        for s in exam["sections"]:
            if s["key"] not in keys:
                continue
            for q in s["questions"]:
                mine = self.result_answers[s["key"]].get(str(q["number"]))
                if only_wrong and (q.get("answer") is None or mine == q.get("answer")):
                    continue
                self.review_items.append((s, q))
        if not self.review_items:
            QMessageBox.information(self, "다시 보기", "틀린 문항이 없습니다. 👏")
            return False
        self.r_i = 0
        if focus:
            for i, (s, q) in enumerate(self.review_items):
                if s["key"] == focus[0] and q["number"] == focus[1]:
                    self.r_i = i
        self._review_section_key = None
        self.tick.stop()
        self.timer_label.setText("해설 보기")
        self.timer_label.setStyleSheet("font-size: 18px; font-weight: bold; background: transparent;")
        self.quit_btn.setText("결과로 돌아가기")
        self.submit_btn.hide()
        self.stack.setCurrentIndex(1)
        self._render_review()
        return True

    def _review_index(self, section_key, row):
        s = next(s for s in self.exam["sections"] if s["key"] == section_key)
        q = s["questions"][row]
        for i, (rs, rq) in enumerate(self.review_items):
            if rs["key"] == section_key and rq is q:
                return i
        return -1

    def _render_review(self):
        s, q = self.review_items[self.r_i]
        answers = self.result_answers[s["key"]]
        if self._review_section_key != s["key"]:
            self.omr.build(s["questions"])
            self._review_section_key = s["key"]
        idx = s["questions"].index(q)
        self.section_label.setText(s["name"])
        self.count_label.setText(f"{self.r_i + 1} / {len(self.review_items)}")
        self.view.show_question(self.exam_path, s, q, idx, len(s["questions"]),
                                answers.get(str(q["number"])), show_answer=True)
        self.omr.update_marks(s["questions"], answers, idx, show_answer=True)
        self.prev_btn.setEnabled(self.r_i > 0)
        self.next_btn.setEnabled(self.r_i < len(self.review_items) - 1)

    # 해설 모드에서는 q_i 대신 r_i 를 쓴다
    @property
    def q_i(self):
        return self.r_i if self.review else self._q_i

    @q_i.setter
    def q_i(self, v):
        self._q_i = v
