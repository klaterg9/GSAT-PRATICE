"""틀린 문제 다시 풀기: 풀 문제 고르기.

열 = 영역, 행 = 그 영역의 틀린 문제. 다시 풀어서 아직 한 번도 못 맞힌 문제는 처음부터 선택되어 있고,
다시 풀어서 한 번이라도 맞힌 문제는 선택이 꺼져 있다.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from .common import ACCENT, BAD, OK


class RetryPickDialog(QDialog):
    def __init__(self, exam: dict, wrong: dict[str, list[int]], stats: dict, parent=None):
        """wrong: {영역키: [처음 응시에서 틀린 문항 번호]}, stats: {(영역키, 번호): (다시 푼 횟수, 맞힌 횟수)}"""
        super().__init__(parent)
        self.setWindowTitle("틀린 문제 다시 풀기")
        self.resize(820, 640)
        self.selected: dict[str, list[int]] = {}
        sections = [s for s in exam["sections"] if wrong.get(s["key"])]
        self.boxes: list[tuple[str, int, QCheckBox, bool]] = []  # (영역키, 번호, 체크, 맞힌 적 있음)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 18, 24, 16)
        lay.setSpacing(10)
        title = QLabel("틀린 문제 다시 풀기")
        title.setObjectName("title")
        lay.addWidget(title)
        sub = QLabel("풀 문제를 고르세요. 시간 제한 없이 풉니다.\n"
                     "다시 풀어서 아직 못 맞힌 문제는 선택되어 있고, 한 번이라도 맞힌 문제는 선택이 꺼져 있습니다.")
        sub.setObjectName("muted")
        lay.addWidget(sub)

        quick = QHBoxLayout()
        for text, fn in (("못 맞힌 문제만", lambda: self._set_all(lambda solved: not solved)),
                         ("전체 선택", lambda: self._set_all(lambda _s: True)),
                         ("전체 해제", lambda: self._set_all(lambda _s: False))):
            b = QPushButton(text)
            b.clicked.connect(fn)
            quick.addWidget(b)
        quick.addStretch()
        legend = QLabel(f"<span style='color:{BAD}'>■</span> 아직 못 맞힘 &nbsp; "
                        f"<span style='color:{OK}'>■</span> 다시 풀어 맞힌 적 있음 &nbsp; "
                        f"<span style='color:#9aa0a6'>■</span> 처음 다시 풀기")
        legend.setStyleSheet("color:#6b6f76; font-size:12px;")
        quick.addWidget(legend)
        lay.addLayout(quick)

        # 행렬: 열 = 영역, 행 = 문제
        grid_w = QWidget()
        grid = QGridLayout(grid_w)
        grid.setContentsMargins(4, 4, 4, 4)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        for c, s in enumerate(sections):
            head = QFrame()
            head.setObjectName("card")
            hl = QVBoxLayout(head)
            hl.setContentsMargins(10, 6, 10, 6)
            hl.setSpacing(2)
            name = QLabel(f"<b>{s['name']}</b>")
            name.setAlignment(Qt.AlignCenter)
            hl.addWidget(name)
            toggle = QPushButton(f"{len(wrong[s['key']])}문제 · 이 영역 전체")
            toggle.setStyleSheet("padding:3px 8px; font-size:12px;")
            toggle.clicked.connect(lambda _=False, k=s["key"]: self._toggle_section(k))
            hl.addWidget(toggle)
            grid.addWidget(head, 0, c)
            for r, num in enumerate(sorted(wrong[s["key"]]), start=1):
                tries, right = stats.get((s["key"], num), (0, 0))
                solved = right > 0
                cell = QFrame()
                cell.setObjectName("cell")
                color = OK if solved else (BAD if tries else "#9aa0a6")
                cell.setStyleSheet(f"QFrame#cell {{ background:white; border:1px solid #e4e6eb; border-left:4px solid {color};"
                                   " border-radius:8px; } QFrame#cell QLabel, QFrame#cell QCheckBox { background:transparent; }")
                cl = QHBoxLayout(cell)
                cl.setContentsMargins(8, 4, 8, 4)
                box = QCheckBox(f"{num}번")
                box.setStyleSheet("font-weight:bold;")
                box.setChecked(not solved)
                box.toggled.connect(self._update)
                cl.addWidget(box)
                cl.addStretch()
                info = QLabel(f"{tries}회 · 맞음 {right}" if tries else "처음")
                info.setStyleSheet(f"font-size:12px; color:{color};")
                cl.addWidget(info)
                grid.addWidget(cell, r, c)
                self.boxes.append((s["key"], num, box, solved))
        for c in range(len(sections)):
            grid.setColumnStretch(c, 1)
        grid.setRowStretch(max(len(v) for v in wrong.values()) + 1 if wrong else 1, 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(grid_w)
        scroll.setStyleSheet("QScrollArea { background:#f6f7f9; border-radius:10px; }"
                             " QScrollArea > QWidget > QWidget { background:#f6f7f9; }")
        lay.addWidget(scroll, 1)

        bottom = QHBoxLayout()
        self.count = QLabel()
        self.count.setStyleSheet("font-size:15px;")
        bottom.addWidget(self.count)
        bottom.addStretch()
        cancel = QPushButton("취소")
        cancel.clicked.connect(self.reject)
        self.ok = QPushButton()
        self.ok.setObjectName("primary")
        self.ok.setMinimumHeight(38)
        self.ok.clicked.connect(self._accept)
        bottom.addWidget(cancel)
        bottom.addWidget(self.ok)
        lay.addLayout(bottom)
        self._update()

    def _set_all(self, rule):
        for _k, _n, box, solved in self.boxes:
            box.setChecked(rule(solved))

    def _toggle_section(self, key: str):
        boxes = [b for k, _n, b, _s in self.boxes if k == key]
        on = not all(b.isChecked() for b in boxes)  # 다 선택돼 있으면 해제, 아니면 전체 선택
        for b in boxes:
            b.setChecked(on)

    def _update(self, *_):
        n = sum(1 for *_x, box, _s in self.boxes if box.isChecked())
        self.count.setText(f"<b style='color:{ACCENT}'>{n}</b>문제 선택")
        self.ok.setText(f"선택한 {n}문제 풀기")
        self.ok.setEnabled(n > 0)

    def _accept(self):
        out: dict[str, list[int]] = {}
        for key, num, box, _s in self.boxes:
            if box.isChecked():
                out.setdefault(key, []).append(num)
        self.selected = out
        self.accept()
