"""정답 입력 화면.

문제를 다 푼 뒤(또는 언제든) 교재의 정답을 보고 입력한다. 입력한 정답은 시험에 저장되어 다음부터 자동 채점된다.

입력 방법
  - 동그라미를 클릭
  - 번호 칸을 고른 뒤 숫자키 1~5 -> 입력하고 다음 문항으로 이동 (Backspace: 지우기, ←/→: 이동)
  - '빠른 입력' 칸에 1번부터 정답을 이어서 붙여넣기 (예: 31425 2...)
"""
from __future__ import annotations

import math

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QScrollArea, QStackedWidget, QVBoxLayout, QWidget)

from .. import storage
from .common import ACCENT, BAD, OK, SectionBar

CELL_W = 300  # 한 칸(번호 + 동그라미 5개) 대략 폭, 열 개수 계산용
CIRCLE_TO_DIGIT = {c: i + 1 for i, c in enumerate("①②③④⑤⑥⑦⑧⑨⑩")}


class KeyCell(QFrame):
    """번호 + ①~⑤ 동그라미 한 줄"""
    picked = Signal(int, int)   # (문항 index, 선택)
    focused = Signal(int)

    def __init__(self, index: int, number: int, n_choices: int):
        super().__init__()
        self.index, self.number = index, number
        self.setCursor(Qt.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 12, 6)
        lay.setSpacing(8)
        self.num = QLabel(f"{number}")
        self.num.setFixedWidth(52)
        self.num.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.num.setStyleSheet("background: transparent;")
        lay.addWidget(self.num)
        lay.addSpacing(4)
        self.buttons = []
        for i in range(1, n_choices + 1):
            b = QPushButton(str(i))
            b.setFixedSize(36, 36)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda _=False, i=i: self.picked.emit(self.index, i))
            lay.addWidget(b)
            self.buttons.append(b)
        lay.addStretch()

    def mousePressEvent(self, event):  # noqa: N802
        self.focused.emit(self.index)
        super().mousePressEvent(event)

    def show_state(self, key: int | None, mine: int | None, current: bool):
        self.setStyleSheet(
            "KeyCell { background: %s; border-radius: 10px; border: %s; }"
            % ("#eef3fe" if current else "transparent", f"1px solid {ACCENT}" if current else "1px solid transparent"))
        mark = ""
        color = "#1d1d1f"
        if key and mine:
            ok = key == mine
            color = OK if ok else BAD
            mark = " ○" if ok else " ✕"
        self.num.setText(f"<span style='font-size:15px; font-weight:bold; color:{color}'>{self.number}{mark}</span>")
        for i, b in enumerate(self.buttons, start=1):
            if i == key:
                style = f"background:{ACCENT}; color:white; border:none;"
            elif i == mine:
                style = "background:white; color:#555; border:2px dashed #9aa0a6;"  # 내가 고른 답
            else:
                style = "background:white; color:#333; border:1px solid #cfd2d8;"
            b.setStyleSheet(f"QPushButton {{ {style} border-radius:18px; font-size:15px; font-weight:bold; padding:0; }}"
                            f"QPushButton:hover {{ border:2px solid {ACCENT}; }}")


class SectionKeyGrid(QWidget):
    changed = Signal()
    section_done = Signal()  # 이 영역 마지막 문항까지 입력함 -> 다음 영역으로

    def __init__(self, section: dict, keys: dict[str, int], mine: dict[str, int] | None):
        super().__init__()
        self.section, self.keys, self.mine = section, keys, mine or {}
        self.questions = section["questions"]
        self.n_choices = max((q.get("num_choices") or 5) for q in self.questions) if self.questions else 5
        self.current = 0
        self._cols = 0
        self.setFocusPolicy(Qt.StrongFocus)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 12, 4, 4)
        lay.setSpacing(10)

        quick = QHBoxLayout()
        quick.setSpacing(8)
        quick.addWidget(QLabel("빠른 입력"))
        self.quick = QLineEdit()
        self.quick.setPlaceholderText("1번부터 정답을 이어서 입력  예) 31425 21354 …   (건너뛸 문항은 0)")
        self.quick.setMinimumHeight(34)
        self.quick.returnPressed.connect(self._apply_quick)
        quick.addWidget(self.quick, 1)
        apply_btn = QPushButton("적용")
        apply_btn.clicked.connect(self._apply_quick)
        quick.addWidget(apply_btn)
        quick.addSpacing(16)
        self.count = QLabel()
        self.count.setStyleSheet("font-size: 15px; font-weight: bold;")
        quick.addWidget(self.count)
        clear_btn = QPushButton("모두 지우기")
        clear_btn.clicked.connect(self._clear_all)
        quick.addWidget(clear_btn)
        lay.addLayout(quick)

        tip = QLabel("동그라미를 클릭하거나, 번호 칸을 고른 뒤 숫자키 1~5를 누르세요 (자동으로 다음 문항으로 이동). "
                     "Backspace: 지우기 · ←/→: 이동" + (" · 점선 동그라미는 내가 고른 답" if mine else ""))
        tip.setObjectName("muted")
        tip.setWordWrap(True)
        lay.addWidget(tip)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        self.grid = QGridLayout(inner)
        self.grid.setContentsMargins(0, 4, 0, 4)
        self.grid.setHorizontalSpacing(36)
        self.grid.setVerticalSpacing(6)
        self.scroll.setWidget(inner)
        lay.addWidget(self.scroll, 1)

        self.cells: list[KeyCell] = []
        for i, q in enumerate(self.questions):
            cell = KeyCell(i, q["number"], q.get("num_choices") or 5)
            cell.picked.connect(self._pick)
            cell.focused.connect(self._focus_cell)
            self.cells.append(cell)
        self._layout_cells()
        self.refresh()

    # ---- 배치 (창 너비에 따라 열 개수 조절, 위에서 아래로 번호가 이어지게)
    def _layout_cells(self):
        n = len(self.cells)
        cols = max(1, min(5, (self.scroll.viewport().width() or 900) // CELL_W))
        cols = min(cols, max(1, n))
        if cols == self._cols:
            return
        self._cols = cols
        for c in self.cells:
            self.grid.removeWidget(c)
        rows = math.ceil(n / cols) if n else 0
        for i, c in enumerate(self.cells):
            self.grid.addWidget(c, i % rows, i // rows)
        self.grid.setRowStretch(rows, 1)
        # 칸은 왼쪽부터 일정한 간격으로, 남는 폭은 오른쪽 빈 열이 차지
        for col in range(6):
            self.grid.setColumnStretch(col, 0)
        self.grid.setColumnStretch(cols, 1)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._layout_cells()

    # ---- 표시
    def refresh(self):
        for i, (q, cell) in enumerate(zip(self.questions, self.cells)):
            num = str(q["number"])
            cell.show_state(self.keys.get(num), self.mine.get(num), i == self.current and self.hasFocus())
        filled = sum(1 for q in self.questions if self.keys.get(str(q["number"])))
        total = len(self.questions)
        color = OK if filled == total else "#1d1d1f"
        self.count.setText(f"<span style='color:{color}'>{filled} / {total} 입력</span>")

    def focusInEvent(self, event):  # noqa: N802
        super().focusInEvent(event)
        self._safe_refresh()

    def focusOutEvent(self, event):  # noqa: N802
        super().focusOutEvent(event)
        self._safe_refresh()

    def _safe_refresh(self):
        # 창이 닫히는 중에는 자식 위젯이 먼저 지워져 있을 수 있다
        try:
            self.refresh()
        except RuntimeError:
            pass

    # ---- 입력
    def _set(self, index: int, value: int | None):
        num = str(self.questions[index]["number"])
        if value:
            self.keys[num] = value
        else:
            self.keys.pop(num, None)
        self.changed.emit()

    def _pick(self, index: int, value: int):
        num = str(self.questions[index]["number"])
        self._set(index, None if self.keys.get(num) == value else value)  # 같은 번호 다시 누르면 지움
        self.current = index
        self.setFocus()
        self.refresh()

    def _focus_cell(self, index: int):
        self.current = index
        self.setFocus()
        self.refresh()

    def _move(self, d: int):
        if self.cells:
            self.current = max(0, min(len(self.cells) - 1, self.current + d))
            self.scroll.ensureWidgetVisible(self.cells[self.current], 0, 40)
            self.refresh()

    def keyPressEvent(self, event):  # noqa: N802
        key, text = event.key(), event.text()
        if not self.cells:
            return super().keyPressEvent(event)
        limit = self.questions[self.current].get("num_choices") or 5
        if text.isdigit() and 1 <= int(text) <= limit:
            self._set(self.current, int(text))
            if self.current == len(self.cells) - 1:
                self.refresh()
                self.section_done.emit()
            else:
                self._move(1)
        elif key in (Qt.Key_Backspace, Qt.Key_Delete):
            num = str(self.questions[self.current]["number"])
            if not self.keys.get(num) and key == Qt.Key_Backspace:
                self._move(-1)  # 빈 칸에서 Backspace -> 앞 칸으로 가서 지움
            self._set(self.current, None)
            self.refresh()
        elif key in (Qt.Key_Right, Qt.Key_Down, Qt.Key_Space):
            self._move(1)
        elif key in (Qt.Key_Left, Qt.Key_Up):
            self._move(-1)
        else:
            super().keyPressEvent(event)

    def _apply_quick(self):
        values = []
        for ch in self.quick.text():
            if ch in CIRCLE_TO_DIGIT:
                values.append(CIRCLE_TO_DIGIT[ch])
            elif ch.isdigit():
                values.append(int(ch))  # 0 = 건너뛰기
        for i, v in enumerate(values[:len(self.questions)]):
            limit = self.questions[i].get("num_choices") or 5
            if 1 <= v <= limit:
                self._set(i, v)
        self.quick.clear()
        self.current = min(len(values), len(self.questions) - 1) if self.questions else 0
        self.setFocus()
        self.refresh()
        if self.filled() == len(self.questions):
            self.section_done.emit()

    def filled(self) -> int:
        return sum(1 for q in self.questions if self.keys.get(str(q["number"])))

    def _clear_all(self):
        for i in range(len(self.questions)):
            self._set(i, None)
        self.current = 0
        self.refresh()


class AnswerKeyWidget(QWidget):
    """맨 위 큰 영역 버튼으로 영역을 고르고 정답 입력. 한 영역을 다 넣으면 다음 영역으로 자동 이동."""

    def __init__(self, exam: dict, section_keys: list[str] | None = None,
                 mine: dict[str, dict[str, int]] | None = None):
        super().__init__()
        self.exam = exam
        self.keys: dict[str, dict[str, int]] = {}
        self.grids: list[SectionKeyGrid] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        sections = [s for s in exam["sections"] if not section_keys or s["key"] in section_keys]
        self.bar = SectionBar([s["name"] for s in sections])
        self.bar.changed.connect(self.show_section)
        lay.addWidget(self.bar)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)
        for s in sections:
            self.keys[s["key"]] = {str(q["number"]): q["answer"] for q in s["questions"] if q.get("answer")}
            grid = SectionKeyGrid(s, self.keys[s["key"]], (mine or {}).get(s["key"]))
            grid.changed.connect(self._update_status)
            grid.section_done.connect(self._next_section)
            self.grids.append(grid)
            self.stack.addWidget(grid)
        self._update_status()

    def show_section(self, i: int):
        if 0 <= i < len(self.grids):
            self.bar.set_current(i)
            self.stack.setCurrentIndex(i)
            self.grids[i].setFocus()

    def _next_section(self):
        """현재 영역을 다 넣었으면 아직 덜 넣은 다음 영역으로"""
        n = len(self.grids)
        cur = self.stack.currentIndex()
        for k in range(1, n):
            i = (cur + k) % n
            if self.grids[i].filled() < len(self.grids[i].questions):
                self.show_section(i)
                return

    def _update_status(self):
        for i, g in enumerate(self.grids):
            filled, total = g.filled(), len(g.questions)
            self.bar.set_status(i, f"{filled} / {total} 입력", bool(total) and filled == total)

    def incomplete(self) -> list[tuple[int, str, int]]:
        """정답을 다 넣지 않은 영역: (index, 이름, 빠진 개수)"""
        out = []
        for i, g in enumerate(self.grids):
            miss = len(g.questions) - g.filled()
            if miss:
                out.append((i, g.section["name"], miss))
        return out

    def missing(self) -> int:
        return sum(m for _, _, m in self.incomplete())

    def save(self):
        """입력한 정답을 시험에 저장"""
        for s in self.exam["sections"]:
            if s["key"] in self.keys:
                for q in s["questions"]:
                    q["answer"] = self.keys[s["key"]].get(str(q["number"]))
        storage.save_exam(self.exam)

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        if self.grids:
            self.grids[self.stack.currentIndex()].setFocus()


def confirm_incomplete(parent, widget: AnswerKeyWidget, action: str) -> bool:
    """빠진 영역이 있으면 알려주고, '입력하러 가기'를 누르면 그 영역을 열고 False"""
    todo = widget.incomplete()
    if not todo:
        return True
    lines = "\n".join(f"  · {name}: {miss}문항 미입력" for _, name, miss in todo)
    box = QMessageBox(parent)
    box.setWindowTitle(action)
    box.setIcon(QMessageBox.Warning)
    box.setText(f"정답을 다 넣지 않은 영역이 있습니다.\n\n{lines}")
    go_fill = box.addButton("빠진 영역 입력하기", QMessageBox.AcceptRole)
    box.addButton(f"그대로 {action}", QMessageBox.DestructiveRole)
    box.setDefaultButton(go_fill)
    box.exec()
    if box.clickedButton() is go_fill:
        widget.show_section(todo[0][0])
        return False
    return True


class AnswerKeyPage(QWidget):
    """응시가 끝난 뒤 나오는 정답 입력 화면"""
    graded = Signal()   # 채점하기
    skipped = Signal()  # 채점 없이 결과 보기

    def __init__(self):
        super().__init__()
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(32, 24, 32, 20)
        self.lay.setSpacing(8)
        title = QLabel("정답 입력")
        title.setObjectName("title")
        self.lay.addWidget(title)
        self.sub = QLabel("교재의 정답을 보고 입력하세요. 입력한 정답은 저장되어 다음부터는 바로 채점됩니다.")
        self.sub.setObjectName("muted")
        self.lay.addWidget(self.sub)
        self.holder = QVBoxLayout()
        self.lay.addLayout(self.holder, 1)
        btns = QHBoxLayout()
        skip = QPushButton("채점 없이 결과 보기")
        skip.clicked.connect(self.skipped.emit)
        go = QPushButton("채점하기 →")
        go.setObjectName("primary")
        go.setMinimumWidth(160)
        go.clicked.connect(self._grade)
        btns.addWidget(skip)
        btns.addStretch()
        btns.addWidget(go)
        self.lay.addLayout(btns)
        self.widget: AnswerKeyWidget | None = None

    def start(self, exam: dict, result: dict):
        if self.widget is not None:
            self.widget.hide()
            self.widget.deleteLater()
        mine = {s["key"]: s["answers"] for s in result["sections"]}
        self.widget = AnswerKeyWidget(exam, list(mine), mine)
        self.holder.addWidget(self.widget)

    def _grade(self):
        if not confirm_incomplete(self, self.widget, "채점하기"):
            return
        self.widget.save()
        self.graded.emit()


class AnswerKeyDialog(QDialog):
    """홈/결과 화면에서 여는 정답 입력·수정 창"""

    def __init__(self, exam: dict, parent=None, mine: dict[str, dict[str, int]] | None = None,
                 section_keys: list[str] | None = None):
        super().__init__(parent)
        self.setWindowTitle(f"정답 입력 / 수정 — {exam['name']}")
        self.resize(1180, 760)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        self.widget = AnswerKeyWidget(exam, section_keys, mine)
        lay.addWidget(self.widget, 1)
        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("취소")
        cancel.clicked.connect(self.reject)
        save = QPushButton("저장")
        save.setObjectName("primary")
        save.setMinimumWidth(120)
        save.clicked.connect(self._save)
        btns.addWidget(cancel)
        btns.addWidget(save)
        lay.addLayout(btns)

    def _save(self):
        if not confirm_incomplete(self, self.widget, "저장하기"):
            return
        self.widget.save()
        self.accept()
