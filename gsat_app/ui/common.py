"""공통 위젯: 문항 화면, 스타일."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy,
                               QVBoxLayout, QWidget)

from ..pages import ZOOM

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"
BASE_SCALE = 1.9  # 문항 이미지 기본 크기: PDF 원래 크기의 약 1.4배 (화면 너비가 허락하는 한)

ACCENT = "#2f6fed"
OK = "#1e9e5a"
BAD = "#d64545"

STYLE = f"""
* {{ font-family: "Malgun Gothic", "맑은 고딕", sans-serif; }}
QWidget {{ background: #ffffff; color: #1d1d1f; font-size: 14px; }}
QPushButton {{ background: #f2f3f5; border: 1px solid #d9dbe0; border-radius: 6px; padding: 7px 14px; }}
QPushButton:hover {{ background: #e8eaee; }}
QPushButton:disabled {{ color: #a0a0a0; }}
QPushButton#primary {{ background: {ACCENT}; color: white; border: none; font-weight: bold; }}
QPushButton#primary:hover {{ background: #2560d6; }}
QPushButton#danger {{ color: {BAD}; }}
QLineEdit, QPlainTextEdit, QSpinBox, QComboBox {{ border: 1px solid #cfd2d8; border-radius: 5px; padding: 4px 6px; }}
QListWidget, QTableWidget {{ border: 1px solid #e1e3e8; border-radius: 6px; }}
QListWidget::item {{ padding: 6px; }}
QListWidget::item:selected, QTableWidget::item:selected {{ background: #e6eefc; color: #1d1d1f; }}
QHeaderView::section {{ background: #f5f6f8; border: none; border-bottom: 1px solid #e1e3e8; padding: 6px; }}
QTabBar::tab {{ padding: 8px 16px; }}
QTabBar::tab:selected {{ color: {ACCENT}; font-weight: bold; }}
QScrollArea {{ border: none; }}
QLabel#muted {{ color: #6b6f76; }}
QLabel#title {{ font-size: 22px; font-weight: bold; }}
"""


def circled(n: int) -> str:
    return CIRCLED[n - 1] if 1 <= n <= len(CIRCLED) else str(n)


class ClickableFrame(QFrame):
    clicked = Signal()

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class ChoiceRow(ClickableFrame):
    """'① 선지 내용' 한 줄."""

    def __init__(self, number: int, text: str, font_px: int = 15):
        super().__init__()
        self.setCursor(Qt.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 9, 10, 9)
        lay.setSpacing(14)
        self.badge = QLabel(str(number))
        self.badge.setFixedSize(26, 26)
        self.badge.setAlignment(Qt.AlignCenter)
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(Qt.NoTextInteraction)
        self.label.setStyleSheet(f"font-size: {font_px}px; background: transparent;")
        lay.addWidget(self.badge, 0, Qt.AlignTop)
        lay.addWidget(self.label, 1)
        self.set_state("normal")

    def set_state(self, state: str) -> None:
        color = {"normal": "#1d1d1f", "selected": ACCENT, "correct": OK, "wrong": BAD}[state]
        filled = state != "normal"
        self.badge.setStyleSheet(
            f"border: 1.5px solid {color}; border-radius: 13px; font-weight: bold;"
            f"color: {'white' if filled else color}; background: {color if filled else 'transparent'};")
        bg = {"normal": "transparent", "selected": "#eef3fe", "correct": "#e9f7ef", "wrong": "#fdeeee"}[state]
        self.setStyleSheet(f"ChoiceRow {{ background: {bg}; border-radius: 8px; }}")


class QuestionView(QScrollArea):
    """문항 하나를 스크린샷처럼 그린다: 'N번 / 전체', 발문, 자료 이미지, 선지."""
    answered = Signal(int)
    zoom_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.zoom = 1.0
        self.setWidgetResizable(True)
        self.body = QWidget()
        self.lay = QVBoxLayout(self.body)
        self.lay.setContentsMargins(28, 22, 28, 28)
        self.lay.setSpacing(14)
        self.setWidget(self.body)
        self._pixmap: QPixmap | None = None
        self._image_label: QLabel | None = None
        self._choice_wrap: QWidget | None = None
        self._img_width = 0
        self.rows: list[ChoiceRow | QPushButton] = []

    def clear(self) -> None:
        while self.lay.count():
            w = self.lay.takeAt(0).widget()
            if w:
                # 즉시 숨기고 삭제는 이벤트가 끝난 뒤에 (클릭 처리 중인 버튼을 바로 지우면 프로그램이 죽는다)
                w.hide()
                w.deleteLater()
        self.rows = []
        self._pixmap = None
        self._image_label = None
        self._choice_wrap = None
        self._img_width = 0

    def show_question(self, exam_path: Path, section: dict, q: dict, index: int, total: int,
                      selected: int | None = None, show_answer: bool = False) -> None:
        self._last = (exam_path, section, q, index, total, selected, show_answer)
        self.clear()
        z = self.zoom
        head = QLabel(f"<span style='font-size:26px; font-weight:800'>{q['number']}번</span>"
                      f"<span style='font-size:15px; color:#555'>&nbsp;/ {total}</span>"
                      f"<span style='font-size:13px; color:#999'>&nbsp;&nbsp;{section['name']} · {index + 1}번째</span>")
        self.lay.addWidget(head)

        if q.get("stem"):
            stem = QLabel(q["stem"])
            stem.setWordWrap(True)
            stem.setStyleSheet(f"font-size: {round(17 * z)}px; font-weight: bold;")
            stem.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.lay.addWidget(stem)

        text_mode = q.get("choice_mode") == "text" and q.get("choices")
        img_name = q.get("image") if text_mode else (q.get("image_full") or q.get("image"))
        if img_name:
            pix = QPixmap(str(exam_path / section["key"] / img_name))
            if not pix.isNull():
                self._pixmap = pix
                self._image_label = QLabel()
                self._image_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
                self._image_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
                self.lay.addWidget(self._image_label)
                self._fit_image()

        answer = q.get("answer")
        n = q.get("num_choices") or 5

        def state_for(i: int) -> str:
            if show_answer and answer is not None:
                if i == answer:
                    return "correct"
                if i == selected:
                    return "wrong"
                return "normal"
            return "selected" if i == selected else "normal"

        if text_mode:
            box = QVBoxLayout()
            box.setSpacing(4)
            for i, text in enumerate(q["choices"], start=1):
                row = ChoiceRow(i, text, round(15 * z))
                row.set_state(state_for(i))
                row.clicked.connect(lambda i=i: self.answered.emit(i))
                box.addWidget(row)
                self.rows.append(row)
            wrap = QWidget()
            wrap.setLayout(box)
            self.lay.addWidget(wrap)
        else:
            # 선지 버튼을 문제 이미지 폭에 맞춰 양 끝까지 같은 간격으로 펼친다
            line = QHBoxLayout()
            line.setContentsMargins(8, 4, 8, 4)
            line.setSpacing(0)
            for i in range(1, n + 1):
                if i > 1:
                    line.addStretch(1)
                btn = QPushButton(circled(i))
                btn.setFixedSize(round(64 * max(1.0, z)), round(44 * max(1.0, z)))
                btn.setCursor(Qt.PointingHandCursor)
                st = state_for(i)
                color = {"normal": None, "selected": ACCENT, "correct": OK, "wrong": BAD}[st]
                btn.setStyleSheet(f"font-size: {round(20 * max(1.0, z))}px;" + (f"background:{color}; color:white; border:none;" if color else ""))
                btn.clicked.connect(lambda _=False, i=i: self.answered.emit(i))
                line.addWidget(btn)
                self.rows.append(btn)
            wrap = QWidget()
            wrap.setLayout(line)
            self._choice_wrap = wrap
            if self._image_label is not None and self._img_width:
                wrap.setFixedWidth(self._img_width)
            self.lay.addWidget(wrap)

        if show_answer:
            mine = circled(selected) if selected else "미응답"
            key = circled(answer) if answer else "정답 없음"
            ok = selected is not None and selected == answer
            info = QLabel(f"내 답: <b>{mine}</b> &nbsp;&nbsp; 정답: <b style='color:{OK}'>{key}</b>"
                          + ("" if answer is None else f" &nbsp;&nbsp; <b style='color:{OK if ok else BAD}'>{'정답' if ok else '오답'}</b>"))
            info.setStyleSheet("font-size: 15px; padding-top: 6px;")
            self.lay.addWidget(info)
        self.lay.addStretch()
        self._sync_size()
        self.verticalScrollBar().setValue(0)

    def set_zoom(self, z: float) -> None:
        self.zoom = round(max(0.6, min(2.5, z)), 2)
        if getattr(self, "_last", None):
            pos = self.verticalScrollBar().value()
            self.show_question(*self._last)  # 글자 크기까지 다시 맞춘다
            self.verticalScrollBar().setValue(pos)
        self.zoom_changed.emit(self.zoom)

    def wheelEvent(self, event):  # noqa: N802
        if event.modifiers() & Qt.ControlModifier:  # Ctrl+휠: 문제 확대/축소
            self.set_zoom(self.zoom + (0.1 if event.angleDelta().y() > 0 else -0.1))
            return
        super().wheelEvent(event)

    def _fit_image(self) -> None:
        if not self._pixmap or not self._image_label:
            return
        # 창 너비에 맞춰 크게 보여주되(반응형), 작은 문항이 지나치게 커지지 않도록 원본의 BASE_SCALE 배까지만
        avail = max(200, self.viewport().width() - 60)
        natural = int(self._pixmap.width() / ZOOM * BASE_SCALE * self.zoom)
        width = min(avail, natural)
        dpr = self.devicePixelRatioF()
        scaled = self._pixmap.scaledToWidth(int(width * dpr), Qt.SmoothTransformation)
        scaled.setDevicePixelRatio(dpr)
        self._image_label.setPixmap(scaled)
        self._image_label.setFixedHeight(int(scaled.height() / dpr))
        self._img_width = int(scaled.width() / dpr)
        if self._choice_wrap is not None:
            self._choice_wrap.setFixedWidth(self._img_width)
        self._sync_size()  # 높이가 바뀐 즉시 아래 선지들을 다시 배치 (겹쳐 보이지 않게)

    def _sync_size(self) -> None:
        # 새로 넣은 위젯은 Qt 가 다음 이벤트 때 표시해서, 그 전에는 높이가 0으로 계산돼 겹쳐 그려진다 -> 바로 표시하고 맞춘다
        for i in range(self.lay.count()):
            w = self.lay.itemAt(i).widget()
            if w is not None and not w.isVisible():
                w.show()
        self.lay.activate()
        h = max(self.viewport().height(), self.body.minimumSizeHint().height())
        self.body.resize(self.viewport().width(), h)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._fit_image()
