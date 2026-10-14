"""채점 결과 화면."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from .. import storage
from .common import BAD, OK, circled
from .exam_page import fmt_time


def fmt_duration(sec: float) -> str:
    """43 -> '43초', 90 -> '1분 30초', 120 -> '2분'"""
    sec = max(0, round(sec))
    m, s = divmod(sec, 60)
    if not m:
        return f"{s}초"
    return f"{m}분 {s}초" if s else f"{m}분"


class ResultPage(QWidget):
    review = Signal(dict, bool, object)  # (result, 오답만, (영역키, 번호) | None)
    home = Signal()
    edit_key = Signal(dict)              # 정답 입력/수정

    def __init__(self):
        super().__init__()
        self.result: dict = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 28, 22)
        self.title = QLabel()
        self.title.setObjectName("title")
        lay.addWidget(self.title)
        self.subtitle = QLabel()
        self.subtitle.setObjectName("muted")
        lay.addWidget(self.subtitle)

        self.summary = QTableWidget(0, 6)
        self.summary.setHorizontalHeaderLabels(["영역", "맞음", "틀림", "미응답", "정답률", "소요 / 제한"])
        self.summary.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.summary.verticalHeader().setVisible(False)
        self.summary.setEditTriggers(QTableWidget.NoEditTriggers)
        self.summary.setMaximumHeight(170)
        lay.addWidget(self.summary)

        hint = QLabel("문항을 더블클릭하면 해당 문제를 다시 볼 수 있습니다.")
        hint.setObjectName("muted")
        lay.addWidget(hint)
        self.detail = QTableWidget(0, 6)
        self.detail.setHorizontalHeaderLabels(["영역", "번호", "내 답", "정답", "결과", "풀이 시간"])
        self.detail.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.detail.verticalHeader().setVisible(False)
        self.detail.setEditTriggers(QTableWidget.NoEditTriggers)
        self.detail.setSelectionBehavior(QTableWidget.SelectRows)
        self.detail.cellDoubleClicked.connect(self._open_row)
        lay.addWidget(self.detail, 1)

        btns = QHBoxLayout()
        home = QPushButton("홈으로")
        home.clicked.connect(self.home.emit)
        all_btn = QPushButton("전체 해설 보기")
        all_btn.clicked.connect(lambda: self.review.emit(self.result, False, None))
        wrong_btn = QPushButton("오답만 다시 보기")
        wrong_btn.setObjectName("primary")
        wrong_btn.clicked.connect(lambda: self.review.emit(self.result, True, None))
        key_btn = QPushButton("정답 입력 / 수정")
        key_btn.clicked.connect(lambda: self.edit_key.emit(self.result))
        btns.addWidget(home)
        btns.addWidget(key_btn)
        btns.addStretch()
        btns.addWidget(all_btn)
        btns.addWidget(wrong_btn)
        lay.addLayout(btns)
        self._rows: list[tuple[str, int]] = []

    def show_result(self, exam: dict, result: dict):
        self.result = result
        self.title.setText(f"결과 — {exam['name']}")
        self.subtitle.setText(f"{result['date'].replace('T', ' ')}  ·  {'실전(전 영역)' if result['mode'] == 'full' else '영역 연습'}")
        sections = {s["key"]: s for s in exam["sections"]}

        self.summary.setRowCount(0)
        self.detail.setRowCount(0)
        self._rows = []
        tot = {"correct": 0, "wrong": 0, "blank": 0}
        for rs in result["sections"]:
            s = sections.get(rs["key"])
            if not s:
                continue
            sc = storage.score_section(s, rs["answers"])
            for k in tot:
                tot[k] += sc[k]
            r = self.summary.rowCount()
            self.summary.insertRow(r)
            vals = [s["name"], sc["correct"], sc["wrong"], sc["blank"], f"{sc['rate']:.1f}%",
                    f"{fmt_time(rs['elapsed'])} / {fmt_time(rs['limit'])}"]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(str(v))
                item.setTextAlignment(Qt.AlignCenter)
                self.summary.setItem(r, c, item)

            for q in s["questions"]:
                num = str(q["number"])
                mine, key = rs["answers"].get(num), q.get("answer")
                if key is None:
                    mark, color = "정답 없음", None
                elif mine is None:
                    mark, color = "미응답", BAD
                elif mine == key:
                    mark, color = "O", OK
                else:
                    mark, color = "X", BAD
                r = self.detail.rowCount()
                self.detail.insertRow(r)
                vals = [s["name"], q["number"], circled(mine) if mine else "-", circled(key) if key else "-",
                        mark, fmt_duration(rs["times"].get(num, 0))]  # 그 문제 화면에 머문 시간
                for c, v in enumerate(vals):
                    item = QTableWidgetItem(str(v))
                    item.setTextAlignment(Qt.AlignCenter)
                    if c == 4 and color:
                        item.setForeground(QColor(color))
                    self.detail.setItem(r, c, item)
                self._rows.append((s["key"], q["number"]))

        if len(result["sections"]) > 1:
            graded = tot["correct"] + tot["wrong"] + tot["blank"]
            r = self.summary.rowCount()
            self.summary.insertRow(r)
            vals = ["합계", tot["correct"], tot["wrong"], tot["blank"],
                    f"{(tot['correct'] / graded * 100) if graded else 0:.1f}%",
                    fmt_time(sum(s["elapsed"] for s in result["sections"]))]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(str(v))
                item.setTextAlignment(Qt.AlignCenter)
                f = item.font()
                f.setBold(True)
                item.setFont(f)
                self.summary.setItem(r, c, item)

    def _open_row(self, row: int, _col: int):
        if 0 <= row < len(self._rows):
            self.review.emit(self.result, False, self._rows[row])
