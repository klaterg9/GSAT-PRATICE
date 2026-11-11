"""채점 결과 화면."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
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
    retry = Signal(dict)                 # 틀린 문제만 다시 풀기

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
        lay.addSpacing(6)
        # 한눈에 보는 요약 카드 (맞힌 수 / 정답률 / 푼 문제 정답률 / 소요 시간)
        cards = QHBoxLayout()
        cards.setSpacing(10)
        self.cards: list[tuple[QLabel, QLabel]] = []
        for cap in ("맞힌 문항", "정답률 (전체)", "정답률 (푼 문제)", "소요 시간"):
            box = QFrame()
            box.setObjectName("card")
            bl = QVBoxLayout(box)
            bl.setContentsMargins(16, 10, 16, 12)
            bl.setSpacing(2)
            c = QLabel(cap)
            c.setStyleSheet("color:#6b6f76; font-size:12px;")
            val = QLabel()
            val.setStyleSheet("font-size:24px; font-weight:800;")
            note = QLabel()
            note.setStyleSheet("color:#8a8f98; font-size:12px;")
            bl.addWidget(c)
            bl.addWidget(val)
            bl.addWidget(note)
            cards.addWidget(box)
            self.cards.append((val, note))
        lay.addLayout(cards)
        lay.addSpacing(4)

        self.summary = QTableWidget(0, 7)
        self.summary.setHorizontalHeaderLabels(["영역", "맞음", "틀림", "미응답", "정답률 (전체)", "정답률 (푼 문제)",
                                                "소요 / 제한"])
        self.summary.horizontalHeaderItem(4).setToolTip("안 푼 문제도 틀린 것으로 계산")
        self.summary.horizontalHeaderItem(5).setToolTip("답을 고른 문제 중에서 맞힌 비율 (안 푼 문제 제외)")
        self.summary.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.summary.verticalHeader().setVisible(False)
        self.summary.setEditTriggers(QTableWidget.NoEditTriggers)
        self.summary.setShowGrid(False)
        self.summary.setFocusPolicy(Qt.NoFocus)
        self.summary.setSelectionMode(QTableWidget.NoSelection)
        self.summary.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        lay.addWidget(self.summary)

        hint = QLabel("문항을 더블클릭하면 해당 문제를 다시 볼 수 있습니다.")
        hint.setObjectName("muted")
        lay.addWidget(hint)
        self.detail = QTableWidget(0, 7)
        self.detail.setHorizontalHeaderLabels(["영역", "번호", "내 답", "정답", "결과", "풀이 시간", "다시 푼 기록"])
        self.detail.horizontalHeaderItem(6).setToolTip("틀린 문제 다시 풀기에서 이 문제를 푼 횟수와 맞힌 횟수")
        self.detail.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.detail.verticalHeader().setVisible(False)
        self.detail.setEditTriggers(QTableWidget.NoEditTriggers)
        self.detail.setSelectionBehavior(QTableWidget.SelectRows)
        self.detail.setShowGrid(False)
        self.detail.setAlternatingRowColors(True)
        self.detail.verticalHeader().setDefaultSectionSize(30)
        self.detail.cellDoubleClicked.connect(self._open_row)
        lay.addWidget(self.detail, 1)

        btns = QHBoxLayout()
        home = QPushButton("홈으로")
        home.clicked.connect(self.home.emit)
        all_btn = QPushButton("전체 해설 보기")
        all_btn.clicked.connect(lambda: self.review.emit(self.result, False, None))
        wrong_btn = QPushButton("오답만 다시 보기")
        wrong_btn.clicked.connect(lambda: self.review.emit(self.result, True, None))
        self.retry_btn = QPushButton("틀린 문제 다시 풀기")
        self.retry_btn.setObjectName("primary")
        self.retry_btn.setToolTip("처음 응시에서 틀렸거나 안 푼 문제를 모아 정답을 가린 채 다시 풉니다.\n"
                                  "다시 풀어 맞힌 문제도 계속 포함됩니다 (문항별 다시 푼 횟수/맞은 횟수 표시).")
        self.retry_btn.clicked.connect(lambda: self.retry.emit(self.result))
        key_btn = QPushButton("정답 입력 / 수정")
        key_btn.clicked.connect(lambda: self.edit_key.emit(self.result))
        btns.addWidget(home)
        btns.addWidget(key_btn)
        btns.addStretch()
        btns.addWidget(all_btn)
        btns.addWidget(wrong_btn)
        btns.addWidget(self.retry_btn)
        lay.addLayout(btns)
        self._rows: list[tuple[str, int]] = []

    def show_result(self, exam: dict, result: dict):
        self.result = result
        self.title.setText(f"결과 — {exam['name']}")
        self.subtitle.setText(f"{result['date'].replace('T', ' ')}  ·  {storage.MODE_LABELS.get(result['mode'], '영역 연습')}")
        sections = {s["key"]: s for s in exam["sections"]}
        stats = storage.retry_stats(exam["id"], exam)

        self.summary.setRowCount(0)
        self.detail.setRowCount(0)
        self._rows = []
        tot = {"correct": 0, "wrong": 0, "blank": 0}
        for rs in result["sections"]:
            s = sections.get(rs["key"])
            if not s:
                continue
            s = storage.result_section(s, rs)
            sc = storage.score_section(s, rs["answers"])
            for k in tot:
                tot[k] += sc[k]
            r = self.summary.rowCount()
            self.summary.insertRow(r)
            vals = [s["name"], sc["correct"], sc["wrong"], sc["blank"], f"{sc['rate']:.1f}%",
                    storage.fmt_rate(sc["attempted_rate"]), f"{fmt_time(rs['elapsed'])} / {fmt_time(rs['limit'])}"]
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
                        mark, fmt_duration(rs["times"].get(num, 0)),  # 그 문제 화면에 머문 시간
                        storage.fmt_retry(stats.get((s["key"], q["number"]))).replace("다시 푼 ", "") or "-"]
                for c, v in enumerate(vals):
                    item = QTableWidgetItem(str(v))
                    item.setTextAlignment(Qt.AlignCenter)
                    if c == 4 and color:
                        item.setForeground(QColor(color))
                    self.detail.setItem(r, c, item)
                self._rows.append((s["key"], q["number"]))

        graded = tot["correct"] + tot["wrong"] + tot["blank"]
        attempted = tot["correct"] + tot["wrong"]
        elapsed = sum(s["elapsed"] for s in result["sections"])
        limit = sum(s["limit"] for s in result["sections"])
        rate = tot["correct"] / graded * 100 if graded else 0.0
        vals = [(f"{tot['correct']} / {graded}", f"틀림 {tot['wrong']} · 미응답 {tot['blank']}"),
                (f"{rate:.1f}%", "안 푼 문제도 틀린 것으로 계산"),
                (storage.fmt_rate(tot["correct"] / attempted * 100 if attempted else None), f"{attempted}문항 응답"),
                (fmt_time(elapsed), f"제한 {fmt_time(limit)}")]
        for (val, note), (v, n) in zip(self.cards, vals):
            val.setText(v)
            note.setText(n)

        if len(result["sections"]) > 1:
            r = self.summary.rowCount()
            self.summary.insertRow(r)
            vals = ["합계", tot["correct"], tot["wrong"], tot["blank"],
                    f"{(tot['correct'] / graded * 100) if graded else 0:.1f}%",
                    storage.fmt_rate(tot["correct"] / attempted * 100 if attempted else None),
                    fmt_time(sum(s["elapsed"] for s in result["sections"]))]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(str(v))
                item.setTextAlignment(Qt.AlignCenter)
                f = item.font()
                f.setBold(True)
                item.setFont(f)
                self.summary.setItem(r, c, item)

        base = storage.retry_base(exam["id"], result)
        n_wrong = sum(len(storage.wrong_numbers(sections[rs["key"]], rs))
                      for rs in base["sections"] if rs["key"] in sections)
        self.retry_btn.setEnabled(n_wrong > 0)
        self.retry_btn.setText(f"틀린 문제 다시 풀기 ({n_wrong})" if n_wrong else "틀린 문제 없음")

        # 요약 표 높이를 행 수에 딱 맞춘다 (빈 공간 없이)
        self.summary.resizeRowsToContents()
        h = self.summary.horizontalHeader().sizeHint().height() + sum(
            self.summary.rowHeight(i) for i in range(self.summary.rowCount())) + 4
        self.summary.setFixedHeight(h)

    def _open_row(self, row: int, _col: int):
        if 0 <= row < len(self._rows):
            self.review.emit(self.result, False, self._rows[row])
