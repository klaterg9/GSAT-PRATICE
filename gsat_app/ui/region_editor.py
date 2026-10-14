"""문항 영역 직접 선택 화면.

PDF 페이지 위에서 마우스로 드래그해 문항 영역을 지정한다. (PDF 파일 자체는 수정하지 않음)
- 번호는 페이지 순서 -> 위에서 아래 순서로 자동으로 매겨진다. ('2단' 옵션: 왼쪽 단 먼저)
- [이어 붙이기] 버튼 + 드래그: 선택한 문항에 영역 이어 붙이기 (단/페이지를 넘어가는 지문)
- 박스 이동, 가장자리 드래그로 크기 조절, Delete 로 삭제
정답은 여기서 넣지 않고, 문제를 다 푼 뒤 정답 입력 화면에서 입력한다.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QKeySequence, QPainter, QPen, QPixmap, QShortcut, QTransform
from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QGridLayout, QGraphicsItem, QGraphicsRectItem, QGraphicsScene,
                               QGraphicsSimpleTextItem, QGraphicsView, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QMenu, QMessageBox, QProgressDialog, QPushButton, QScrollArea, QSpinBox,
                               QSplitter, QVBoxLayout, QWidget)

from .. import storage
from ..pages import PageRef, PdfPages, stitch, trim_white
from .common import ACCENT, UI_FONTS, SectionBar

HELP = ("<b>드래그</b>: 새 문항 영역 추가<br>"
        "<b>[이어 붙이기]</b> 켜고 드래그: 선택 문항에 영역 추가<br>"
        "(단/페이지를 넘어가는 지문용, 한 번 쓰면 자동으로 꺼짐)<br>"
        "<b>박스 끌기 / 가장자리</b>: 이동 / 크기 조절<br>"
        "<b>박스 오른쪽 클릭</b>: 분리 / 삭제<br>"
        "<b>Delete</b>: 선택 영역 삭제<br>"
        "<b>Ctrl+휠</b>: 확대/축소 &nbsp; <b>PgUp/PgDn</b>: 페이지")


@dataclass
class Part:
    ref: PageRef
    rect: tuple[float, float, float, float]  # 페이지 이미지 기준 0~1


@dataclass
class EQuestion:
    parts: list[Part]
    answer: int | None = None  # 정답 입력 화면에서 넣은 값 (영역을 고쳐도 유지)
    choices: int | None = None  # 이 문항만의 선지 수 (None 이면 영역의 기본 선지 수)


@dataclass
class ESection:
    key: str
    name: str
    minutes: int
    expected: int
    pages: list[int]          # PDF 페이지 (0부터)
    refs: list[PageRef] = field(default_factory=list)
    questions: list[EQuestion] = field(default_factory=list)
    two_column: bool = False
    start: int = 1
    choices: int = 4  # 기본 선지 수

    def ordered(self) -> list[EQuestion]:
        """페이지 순 -> (2단이면 왼쪽 단 먼저) -> 위에서 아래 순"""
        order = {r: i for i, r in enumerate(self.refs)}

        def key(q: EQuestion):
            p = q.parts[0]
            col = 0
            if self.two_column:
                col = 0 if (p.rect[0] + p.rect[2]) / 2 < 0.5 else 1
            return order.get(p.ref, 10 ** 6), col, p.rect[1], p.rect[0]
        return sorted(self.questions, key=key)


def to_pixmap(img) -> QPixmap:
    if img.mode == "L":
        q = QImage(img.tobytes(), img.width, img.height, img.width, QImage.Format_Grayscale8)
    else:
        rgb = img.convert("RGB")
        q = QImage(rgb.tobytes(), rgb.width, rgb.height, rgb.width * 3, QImage.Format_RGB888)
    return QPixmap.fromImage(q.copy())


# ---------------------------------------------------------------- 그래픽 아이템
class RegionItem(QGraphicsRectItem):
    def __init__(self, view: "PageView", q: EQuestion, part: Part, rect: QRectF):
        super().__init__(rect)
        self.view, self.q, self.part = view, q, part
        self.setFlags(QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemIsMovable)
        self.setAcceptHoverEvents(True)
        self._edges: set[str] = set()
        self.tag_bg = QGraphicsRectItem(self)
        self.tag_bg.setFlag(QGraphicsItem.ItemIgnoresTransformations)
        self.tag_bg.setPen(QPen(Qt.NoPen))
        self.tag = QGraphicsSimpleTextItem(self.tag_bg)
        font = QFont()
        font.setFamilies(UI_FONTS)
        font.setPointSize(11)
        font.setBold(True)
        self.tag.setFont(font)
        self.tag.setBrush(QBrush(Qt.white))

    def set_label(self, text: str, current: bool):
        color = QColor(ACCENT) if current else QColor("#e8590c")
        self.setPen(QPen(color, 0))  # 0 = 확대해도 1픽셀
        pen = self.pen()
        pen.setCosmetic(True)
        pen.setWidth(3 if current else 2)
        self.setPen(pen)
        fill = QColor(color)
        fill.setAlpha(28 if current else 18)
        self.setBrush(QBrush(fill))
        self.tag.setText(text)
        br = self.tag.boundingRect()
        self.tag_bg.setRect(QRectF(0, 0, br.width() + 10, br.height() + 4))
        self.tag.setPos(5, 2)
        self.tag_bg.setBrush(QBrush(color))
        self.tag_bg.setPos(self.rect().topLeft())

    def _edges_at(self, pos) -> set[str]:
        r = self.rect()
        tol = 8 / max(0.01, self.view.transform().m11())
        e = set()
        inside_x = r.left() - tol <= pos.x() <= r.right() + tol
        inside_y = r.top() - tol <= pos.y() <= r.bottom() + tol
        if inside_y and abs(pos.x() - r.left()) < tol:
            e.add("l")
        if inside_y and abs(pos.x() - r.right()) < tol:
            e.add("r")
        if inside_x and abs(pos.y() - r.top()) < tol:
            e.add("t")
        if inside_x and abs(pos.y() - r.bottom()) < tol:
            e.add("b")
        return e

    def hoverMoveEvent(self, event):  # noqa: N802
        e = self._edges_at(event.pos())
        if e in ({"l"}, {"r"}):
            self.setCursor(Qt.SizeHorCursor)
        elif e in ({"t"}, {"b"}):
            self.setCursor(Qt.SizeVerCursor)
        elif e in ({"l", "t"}, {"r", "b"}):
            self.setCursor(Qt.SizeFDiagCursor)
        elif e in ({"r", "t"}, {"l", "b"}):
            self.setCursor(Qt.SizeBDiagCursor)
        else:
            self.setCursor(Qt.SizeAllCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):  # noqa: N802
        self._edges = self._edges_at(event.pos()) if event.button() == Qt.LeftButton else set()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        if not self._edges:
            super().mouseMoveEvent(event)
            return
        r = QRectF(self.rect())
        p = event.pos()
        if "l" in self._edges:
            r.setLeft(p.x())
        if "r" in self._edges:
            r.setRight(p.x())
        if "t" in self._edges:
            r.setTop(p.y())
        if "b" in self._edges:
            r.setBottom(p.y())
        self.setRect(r.normalized())
        self.tag_bg.setPos(self.rect().topLeft())

    def mouseReleaseEvent(self, event):  # noqa: N802
        super().mouseReleaseEvent(event)
        self._edges = set()
        self.view.item_changed(self)


PAGE_W = 1400   # 화면에 그리는 페이지 폭 (장면 좌표)
PAGE_GAP = 28   # 페이지 사이 간격


class PageView(QGraphicsView):
    """영역의 모든 페이지를 세로로 이어 붙여 스크롤로 보는 뷰. 페이지 이미지는 화면에 보일 때 불러온다."""
    region_drawn = Signal(object, object, bool)  # (페이지, 0~1 사각형, 이어 붙이기 여부)
    changed = Signal(object)                     # RegionItem 이동/크기 변경
    context_requested = Signal(object, object)   # (RegionItem, 화면 좌표)
    current_page_changed = Signal(int)

    def __init__(self, loader):
        super().__init__()
        self.loader = loader  # ref -> PIL 이미지
        self.append_mode = False  # '이어 붙이기' 버튼이 켜져 있으면 다음 드래그를 선택 문항에 붙인다
        self.region_items: list[RegionItem] = []
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setBackgroundBrush(QColor("#e9ebef"))
        self.refs: list[PageRef] = []
        self.slots: list[QRectF] = []          # 페이지마다 장면 좌표 사각형
        self.page_items: list = []             # 흰 바탕(불러오기 전) / 페이지 이미지
        self.loaded: set[int] = set()
        self._origin = None
        self._origin_page = -1
        self._rubber = None
        self._append = False
        self._fit = True
        self._current = -1
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)

    # ---- 페이지 배치
    def set_pages(self, refs: list[PageRef], aspects: list[float]):
        self.clear_regions()
        for it in self.page_items:
            self.scene().removeItem(it)
        self.page_items, self.slots, self.loaded = [], [], set()
        self.refs = list(refs)
        y = 0.0
        for aspect in aspects:
            rect = QRectF(0, y, PAGE_W, PAGE_W * aspect)
            self.slots.append(rect)
            bg = self.scene().addRect(rect, QPen(QColor("#c9ccd2")), QBrush(Qt.white))
            bg.setZValue(-2)
            self.page_items.append(bg)
            y += rect.height() + PAGE_GAP
        self.setSceneRect(QRectF(-PAGE_GAP, -PAGE_GAP, PAGE_W + 2 * PAGE_GAP, max(1.0, y + PAGE_GAP)))
        self._current = -1
        if self._fit:
            self.fit_width()
        self.verticalScrollBar().setValue(self.verticalScrollBar().minimum())
        self._on_scroll()

    def _visible_pages(self) -> list[int]:
        area = self.mapToScene(self.viewport().rect()).boundingRect()
        return [i for i, r in enumerate(self.slots) if r.intersects(area)]

    def _on_scroll(self, *_):
        visible = self._visible_pages()
        if not visible:
            return
        # 보이는 쪽 + 바로 다음 쪽을 미리 불러온다
        for i in visible + [visible[-1] + 1]:
            if 0 <= i < len(self.slots) and i not in self.loaded:
                self._load(i)
        center = self.mapToScene(self.viewport().rect().center()).y()
        cur = min(range(len(self.slots)), key=lambda i: 0 if self.slots[i].top() <= center <= self.slots[i].bottom()
                  else min(abs(center - self.slots[i].top()), abs(center - self.slots[i].bottom())))
        if cur != self._current:
            self._current = cur
            self.current_page_changed.emit(cur)

    def _load(self, i: int):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            img = self.loader(self.refs[i])
        finally:
            QApplication.restoreOverrideCursor()
        dpr = self.devicePixelRatioF()
        pix = to_pixmap(img)
        slot = self.slots[i]
        pix = pix.scaled(int(slot.width() * dpr), int(slot.height() * dpr), Qt.IgnoreAspectRatio,
                         Qt.SmoothTransformation)
        item = self.scene().addPixmap(pix)
        item.setScale(1 / dpr)
        item.setPos(slot.topLeft())
        item.setZValue(-1)
        self.page_items.append(item)
        self.loaded.add(i)

    def scroll_to_page(self, i: int):
        if 0 <= i < len(self.slots):
            top = self.mapFromScene(self.slots[i].topLeft()).y()
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() + top - 8)

    def page_at(self, p) -> int:
        for i, r in enumerate(self.slots):
            if r.contains(p):
                return i
        return -1

    def to_norm(self, i: int, r: QRectF) -> tuple[float, float, float, float]:
        s = self.slots[i]
        return (max(0.0, (r.left() - s.left()) / s.width()), max(0.0, (r.top() - s.top()) / s.height()),
                min(1.0, (r.right() - s.left()) / s.width()), min(1.0, (r.bottom() - s.top()) / s.height()))

    def from_norm(self, i: int, rect) -> QRectF:
        s = self.slots[i]
        x0, y0, x1, y1 = rect
        return QRectF(s.left() + x0 * s.width(), s.top() + y0 * s.height(),
                      (x1 - x0) * s.width(), (y1 - y0) * s.height())

    def add_region_item(self, item: "RegionItem"):
        self.scene().addItem(item)
        self.region_items.append(item)

    def clear_regions(self):
        for it in self.region_items:
            self.scene().removeItem(it)
        self.region_items = []

    def fit_width(self):
        s = (self.viewport().width() - 8) / (PAGE_W + 2 * PAGE_GAP)
        self.setTransform(QTransform.fromScale(s, s))
        self._fit = True
        self._on_scroll()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        if self._fit:
            self.fit_width()

    def wheelEvent(self, event):  # noqa: N802
        if event.modifiers() & Qt.ControlModifier:
            f = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(f, f)
            self._fit = False
            self._on_scroll()
        else:
            super().wheelEvent(event)

    def item_changed(self, item: RegionItem):
        # 아이템 자신의 마우스 이벤트 처리 중에 아이템을 다시 그리면(삭제) 충돌하므로 이벤트가 끝난 뒤 처리
        QTimer.singleShot(0, lambda: self.changed.emit(item))

    def _region_at(self, pos) -> RegionItem | None:
        item = self.itemAt(pos)
        while item is not None and not isinstance(item, RegionItem) and item.parentItem() is not None:
            item = item.parentItem()
        return item if isinstance(item, RegionItem) else None

    def contextMenuEvent(self, event):  # noqa: N802
        item = self._region_at(event.pos())
        if item is not None:
            self.context_requested.emit(item, event.globalPos())
            return
        super().contextMenuEvent(event)

    def mousePressEvent(self, event):  # noqa: N802
        item = self._region_at(event.position().toPoint())
        origin = self.mapToScene(event.position().toPoint())
        page = self.page_at(origin)
        if event.button() == Qt.LeftButton and item is None and page >= 0:
            self._origin, self._origin_page = origin, page
            self._append = self.append_mode
            if not self._append:
                self.scene().clearSelection()
            pen = QPen(QColor(ACCENT), 0, Qt.DashLine)
            pen.setCosmetic(True)
            pen.setWidth(2)
            self._rubber = self.scene().addRect(QRectF(self._origin, self._origin), pen)
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._rubber is not None:
            p = self.mapToScene(event.position().toPoint())
            # 영역은 드래그를 시작한 페이지 안으로 제한
            r = QRectF(self._origin, p).normalized() & self.slots[self._origin_page]
            self._rubber.setRect(r)
            # 화면 끝에 닿으면 자동 스크롤 (긴 문항을 아래로 끌 때)
            y = event.position().y()
            bar = self.verticalScrollBar()
            if y > self.viewport().height() - 30:
                bar.setValue(bar.value() + 20)
            elif y < 30:
                bar.setValue(bar.value() - 20)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if self._rubber is not None:
            r = self._rubber.rect()
            self.scene().removeItem(self._rubber)
            self._rubber = None
            if r.width() > 15 and r.height() > 15:
                i = self._origin_page
                self.region_drawn.emit(self.refs[i], self.to_norm(i, r), self._append)
            return
        super().mouseReleaseEvent(event)


# ---------------------------------------------------------------- 편집 창
class RegionEditor(QDialog):
    def __init__(self, exam: dict, sections: list[ESection], pdf_path: str, parent=None, new: bool = False):
        super().__init__(parent)
        self.exam, self.sections = exam, sections
        self.pages = PdfPages(pdf_path)
        for s in sections:
            s.refs = self.pages.refs(s.pages)
        self.sec_i = 0
        self.page_i = 0
        self.sel_q: EQuestion | None = None
        self._syncing = False

        self.setWindowTitle(f"문항 영역 선택 — {exam['name']}")
        self.resize(1400, 920)
        self.setWindowState(Qt.WindowMaximized)
        self.setMinimumSize(760, 520)
        root = QVBoxLayout(self)
        root.setSpacing(10)

        # 맨 위: 영역 선택 (크게, 진행 상황 표시)
        self.section_bar = SectionBar([sec.name for sec in sections])
        self.section_bar.changed.connect(self._switch_section)
        root.addWidget(self.section_bar)

        # 가운데: 페이지 목록 | PDF | 오른쪽 패널  (경계를 끌어 폭 조절, 좁아지면 페이지 목록 자동 숨김)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.page_list = QListWidget()
        self.page_list.setMinimumWidth(90)
        self.page_list.currentRowChanged.connect(self._goto_page)
        self.splitter.addWidget(self.page_list)

        center_w = QWidget()
        center = QVBoxLayout(center_w)
        center.setContentsMargins(0, 0, 0, 0)
        self.view = PageView(self.pages.display_image)
        self.view.setMinimumWidth(320)
        self.view.region_drawn.connect(self._add_region)
        self.view.current_page_changed.connect(self._on_current_page)
        self.view.changed.connect(self._region_changed)
        self.view.context_requested.connect(self._region_menu)
        self.view.scene().selectionChanged.connect(self._scene_selection)
        center.addWidget(self.view, 1)
        nav = QHBoxLayout()
        prev_btn = QPushButton("◀")
        prev_btn.setToolTip("이전 쪽 (PgUp)")
        prev_btn.clicked.connect(lambda: self._step_page(-1))
        next_btn = QPushButton("▶")
        next_btn.setToolTip("다음 쪽 (PgDn)")
        next_btn.clicked.connect(lambda: self._step_page(1))
        fit_btn = QPushButton("폭 맞춤")
        fit_btn.clicked.connect(self.view.fit_width)
        self.append_btn = QPushButton("이어 붙이기")
        self.append_btn.setCheckable(True)
        self.append_btn.setToolTip("켜고 드래그하면 선택한 문항에 영역이 추가됩니다 (한 번 쓰면 자동으로 꺼짐)")
        self.append_btn.toggled.connect(self._append_toggled)
        self.page_label = QLabel()
        nav.addWidget(prev_btn)
        nav.addWidget(self.page_label)
        nav.addWidget(next_btn)
        nav.addStretch()
        nav.addWidget(self.append_btn)
        nav.addWidget(fit_btn)
        center.addLayout(nav)
        self.splitter.addWidget(center_w)

        # 오른쪽 패널: 영역 설정 + 문항 목록 (세로로 넘치면 스크롤)
        side_w = QWidget()
        side = QVBoxLayout(side_w)
        side.setContentsMargins(4, 0, 0, 0)
        side.setSpacing(8)
        settings = QGridLayout()
        settings.setHorizontalSpacing(6)
        settings.setVerticalSpacing(6)
        title = QLabel("이 영역 설정")
        title.setStyleSheet("font-weight: bold;")
        settings.addWidget(title, 0, 0, 1, 4)
        settings.addWidget(QLabel("페이지"), 1, 0)
        self.first_spin, self.last_spin = QSpinBox(), QSpinBox()
        for sp in (self.first_spin, self.last_spin):
            sp.setRange(1, self.pages.page_count)
            sp.setMinimumWidth(78)  # 세 자리 쪽수까지 보이게
            sp.setAlignment(Qt.AlignCenter)
            sp.setKeyboardTracking(False)  # 숫자를 다 친 뒤에만 반영 (12 입력 중 1 로 바뀌지 않게)
            sp.editingFinished.connect(self._page_range_changed)
        settings.addWidget(self.first_spin, 1, 1)
        settings.addWidget(QLabel("~"), 1, 2, Qt.AlignCenter)
        settings.addWidget(self.last_spin, 1, 3)
        total = QLabel(f"전체 {self.pages.page_count}쪽 · Enter 로 적용")
        total.setObjectName("muted")
        settings.addWidget(total, 2, 1, 1, 3)
        settings.addWidget(QLabel("시작 번호"), 3, 0)
        self.start_spin = QSpinBox()
        self.start_spin.setRange(1, 999)
        self.start_spin.valueChanged.connect(self._options_changed)
        settings.addWidget(self.start_spin, 3, 1)
        settings.addWidget(QLabel("기본 선지 수"), 4, 0)
        self.choice_spin = QSpinBox()
        self.choice_spin.setRange(2, 10)
        self.choice_spin.setToolTip("새로 만드는 문항의 선지 개수. 문항마다 아래 목록에서 따로 바꿀 수 있습니다.")
        self.choice_spin.valueChanged.connect(self._options_changed)
        settings.addWidget(self.choice_spin, 4, 1)
        self.two_col = QCheckBox("2단 편집 (왼쪽 단 먼저 번호)")
        self.two_col.toggled.connect(self._options_changed)
        settings.addWidget(self.two_col, 5, 0, 1, 4)
        settings.setColumnStretch(1, 1)
        settings.setColumnStretch(3, 1)
        side.addLayout(settings)

        list_title = QLabel("문항 목록  ·  선지 수는 문항마다 바꿀 수 있어요")
        list_title.setStyleSheet("font-weight: bold; padding-top: 6px;")
        list_title.setWordWrap(True)
        side.addWidget(list_title)
        self.q_list = QListWidget()
        self.q_list.setMinimumHeight(160)
        self.q_list.currentRowChanged.connect(self._list_selected)
        side.addWidget(self.q_list, 1)
        del_btn = QPushButton("선택 문항 삭제")
        del_btn.setObjectName("danger")
        del_btn.clicked.connect(self._delete_question)
        side.addWidget(del_btn)
        help_label = QLabel(HELP)
        help_label.setWordWrap(True)
        help_label.setStyleSheet("background:#f5f6f8; border-radius:6px; padding:8px; font-size:12px;")
        side.addWidget(help_label)
        note = QLabel("정답은 문제를 다 푼 뒤 정답 입력 화면에서 입력합니다.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        side.addWidget(note)
        side_scroll = QScrollArea()
        side_scroll.setWidgetResizable(True)
        side_scroll.setWidget(side_w)
        side_scroll.setMinimumWidth(270)
        self.splitter.addWidget(side_scroll)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        self.splitter.setSizes([120, 900, 320])
        root.addWidget(self.splitter, 1)

        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("취소" if new else "닫기")
        cancel.clicked.connect(self.reject)
        save = QPushButton("저장")
        save.setObjectName("primary")
        save.setMinimumWidth(110)
        save.clicked.connect(self._save)
        btns.addWidget(cancel)
        btns.addWidget(save)
        root.addLayout(btns)

        QShortcut(QKeySequence(Qt.Key_Delete), self, self._delete_selected)
        QShortcut(QKeySequence(Qt.Key_PageDown), self, lambda: self._step_page(1))
        QShortcut(QKeySequence(Qt.Key_PageUp), self, lambda: self._step_page(-1))

        self._switch_section(0)

    # ------------------------------------------------------------ 상태
    @property
    def sec(self) -> ESection:
        return self.sections[self.sec_i]

    def _number(self, q: EQuestion) -> int:
        return self.sec.start + self.sec.ordered().index(q)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        # 좁은 화면에서는 페이지 목록을 숨겨 PDF 와 오른쪽 패널 자리를 확보
        self.page_list.setVisible(self.width() >= 1150)

    def _switch_section(self, i: int):
        self.sec_i = i
        self.section_bar.set_current(i)
        s = self.sec
        self._syncing = True
        self.two_col.setChecked(s.two_column)
        self.start_spin.setValue(s.start)
        self.choice_spin.setValue(s.choices)
        self.first_spin.setValue(min(s.pages) + 1 if s.pages else 1)
        self.last_spin.setValue(max(s.pages) + 1 if s.pages else self.pages.page_count)
        self._syncing = False
        self.sel_q = None
        self._load_pages()

    def _load_pages(self):
        s = self.sec
        self.page_list.blockSignals(True)
        self.page_list.clear()
        for ref in s.refs:
            self.page_list.addItem(self.pages.label(ref))
        self.page_list.blockSignals(False)
        self.page_i = 0
        self.view.set_pages(s.refs, [self.pages.aspect(r) for r in s.refs])
        self._refresh()

    def _page_range_changed(self):
        """페이지 범위 변경: 범위 밖으로 빠지는 쪽에 그린 영역이 있으면 확인 후 지운다."""
        if self._syncing:
            return
        first, last = self.first_spin.value(), self.last_spin.value()
        if last < first:
            first, last = last, first
        new_pages = list(range(first - 1, last))
        s = self.sec
        if new_pages == s.pages:
            return
        new_refs = self.pages.refs(new_pages)
        keep = set(new_refs)
        dropped = [(q, p) for q in s.questions for p in q.parts if p.ref not in keep]
        if dropped:
            nq = len({id(q) for q, _ in dropped})
            if QMessageBox.question(
                    self, "페이지 범위 변경",
                    f"범위에서 빠지는 쪽에 선택한 영역이 {len(dropped)}개 있습니다 (문항 {nq}개).\n"
                    "이 영역들을 지우고 범위를 바꿀까요?") != QMessageBox.Yes:
                self._syncing = True
                self.first_spin.setValue(min(s.pages) + 1)
                self.last_spin.setValue(max(s.pages) + 1)
                self._syncing = False
                return
            for q, p in dropped:
                q.parts.remove(p)
            s.questions = [q for q in s.questions if q.parts]
            if self.sel_q is not None and self.sel_q not in s.questions:
                self.sel_q = None
        self._syncing = True
        self.first_spin.setValue(first)
        self.last_spin.setValue(last)
        self._syncing = False
        s.pages, s.refs = new_pages, new_refs
        self._load_pages()

    def _update_section_status(self):
        for i, sec in enumerate(self.sections):
            n, exp = len(sec.questions), sec.expected
            self.section_bar.set_status(i, f"{n} / {exp}문항" if exp else f"{n}문항", bool(exp) and n == exp)

    def _question_choices_changed(self, q: EQuestion, v: int):
        # 기본값과 같으면 '기본값 따름' 으로 둔다 (나중에 기본 선지 수를 바꾸면 같이 바뀌게)
        q.choices = None if v == self.sec.choices else v

    def _options_changed(self):
        if self._syncing:
            return
        s = self.sec
        s.two_column = self.two_col.isChecked()
        s.start = self.start_spin.value()
        s.choices = self.choice_spin.value()
        self._refresh()

    def _goto_page(self, i: int):
        """페이지 목록/버튼 -> 해당 쪽으로 스크롤"""
        if 0 <= i < len(self.sec.refs):
            self.view.scroll_to_page(i)

    def _on_current_page(self, i: int):
        """스크롤하면 지금 보고 있는 쪽 표시를 따라 바꾼다"""
        refs = self.sec.refs
        if not 0 <= i < len(refs):
            return
        self.page_i = i
        self.page_list.blockSignals(True)
        self.page_list.setCurrentRow(i)
        self.page_list.blockSignals(False)
        self.page_label.setText(f"  {self.pages.label(refs[i])}  ({i + 1} / {len(refs)})  ")

    def _step_page(self, d: int):
        self._goto_page(self.page_i + d)

    # ------------------------------------------------------------ 그리기
    def _draw_items(self):
        self._syncing = True
        self.view.clear_regions()
        self._syncing = False
        if not self.sec.refs:
            return
        index = {r: i for i, r in enumerate(self.sec.refs)}
        ordered = self.sec.ordered()
        self._syncing = True
        for num, q in enumerate(ordered, start=self.sec.start):
            for k, part in enumerate(q.parts):
                if part.ref not in index:
                    continue
                item = RegionItem(self.view, q, part, self.view.from_norm(index[part.ref], part.rect))
                self.view.add_region_item(item)
                item.set_label(f"{num}번{' (이어짐)' if k else ''}", q is self.sel_q)
                if q is self.sel_q:
                    item.setSelected(True)
        self._syncing = False

    def _refresh(self):
        ordered = self.sec.ordered()
        self._syncing = True
        self.q_list.clear()
        sel_row = -1
        for i, q in enumerate(ordered):
            p = q.parts[0]
            extra = f" +{len(q.parts) - 1}" if len(q.parts) > 1 else ""
            item = QListWidgetItem(self.q_list)
            row = QWidget()
            row.setStyleSheet("background: transparent;")
            h = QHBoxLayout(row)
            h.setContentsMargins(6, 2, 6, 2)
            label = QLabel(f"<b>{self.sec.start + i}번</b>&nbsp;&nbsp;<span style='color:#6b6f76'>"
                           f"{self.pages.label(p.ref)}{extra}</span>")
            label.setStyleSheet("background: transparent;")
            h.addWidget(label, 1)
            h.addWidget(QLabel("선지"))
            spin = QSpinBox()
            spin.setRange(2, 10)
            spin.setValue(q.choices or self.sec.choices)
            spin.setFixedWidth(62)
            spin.valueChanged.connect(lambda v, q=q: self._question_choices_changed(q, v))
            h.addWidget(spin)
            item.setSizeHint(row.sizeHint())
            self.q_list.setItemWidget(item, row)
            if q is self.sel_q:
                sel_row = i
        self.q_list.setCurrentRow(sel_row)
        self._syncing = False
        self._update_section_status()
        counts: dict[PageRef, int] = {}
        for q in ordered:
            counts[q.parts[0].ref] = counts.get(q.parts[0].ref, 0) + 1
        for i, ref in enumerate(self.sec.refs):
            c = counts.get(ref, 0)
            self.page_list.item(i).setText(self.pages.label(ref) + (f"  ({c})" if c else ""))
        self._draw_items()

    # ------------------------------------------------------------ 편집 동작
    def _append_toggled(self, on: bool):
        if on and self.sel_q is None:
            QMessageBox.information(self, "이어 붙이기", "먼저 영역을 이어 붙일 문항을 선택하세요.")
            self.append_btn.setChecked(False)
            return
        self.view.append_mode = on
        self.append_btn.setStyleSheet(f"background:{ACCENT}; color:white; border:none;" if on else "")

    def _add_region(self, ref: PageRef, rect, append: bool):
        part = Part(ref, rect)
        if append and self.sel_q is not None:
            self.sel_q.parts.append(part)
        else:
            q = EQuestion([part])
            self.sec.questions.append(q)
            self.sel_q = q
        self.append_btn.setChecked(False)  # 이어 붙이기는 한 번만
        self._refresh()

    def _region_menu(self, item: RegionItem, global_pos):
        menu = QMenu(self)
        q, part = item.q, item.part
        split = menu.addAction("별도 문항으로 분리") if q.parts.index(part) > 0 else None
        attach = menu.addAction("이 문항에 영역 이어 붙이기…")
        menu.addSeparator()
        delete = menu.addAction("이 영역 삭제")
        chosen = menu.exec(global_pos)
        if chosen is None:
            return
        if chosen is split:
            q.parts.remove(part)
            new_q = EQuestion([part])
            self.sec.questions.append(new_q)
            self.sel_q = new_q
        elif chosen is attach:
            self.sel_q = q
            self._refresh()
            self.append_btn.setChecked(True)
            return
        elif chosen is delete:
            q.parts.remove(part)
            if not q.parts:
                self.sec.questions.remove(q)
                if self.sel_q is q:
                    self.sel_q = None
        self._refresh()

    def _region_changed(self, item: RegionItem):
        r = item.mapRectToScene(item.rect())
        i = self.view.page_at(r.center())
        if i < 0:  # 페이지 밖으로 끌어낸 경우: 가장 가까운 페이지로
            i = min(range(len(self.view.slots)), key=lambda k: abs(self.view.slots[k].center().y() - r.center().y()))
        r = r & self.view.slots[i]
        if r.width() > 5 and r.height() > 5:
            item.part.ref = self.sec.refs[i]
            item.part.rect = self.view.to_norm(i, r)
        self.sel_q = item.q
        self._refresh()

    def _scene_selection(self):
        if self._syncing:
            return
        items = [i for i in self.view.scene().selectedItems() if isinstance(i, RegionItem)]
        if items and items[0].q is not self.sel_q:
            self.sel_q = items[0].q
            self._update_selection_ui()  # 클릭 중인 박스를 다시 만들면 안 되므로 표시만 갱신

    def _update_selection_ui(self):
        ordered = self.sec.ordered()
        self._syncing = True
        self.q_list.setCurrentRow(ordered.index(self.sel_q) if self.sel_q in ordered else -1)
        for it in self.view.region_items:
            if it.q in ordered:
                num = self.sec.start + ordered.index(it.q)
                k = it.q.parts.index(it.part) if it.part in it.q.parts else 0
                it.set_label(f"{num}번{' (이어짐)' if k else ''}", it.q is self.sel_q)
        self._syncing = False

    def _list_selected(self, row: int):
        if self._syncing or row < 0:
            return
        self.sel_q = self.sec.ordered()[row]
        self._refresh()
        self._show_selected()

    def _show_selected(self):
        """선택한 문항의 첫 영역이 보이도록 스크롤"""
        for it in self.view.region_items:
            if it.q is self.sel_q and it.part is self.sel_q.parts[0]:
                self.view.ensureVisible(it, 40, 80)
                break

    def _delete_selected(self):
        items = [i for i in self.view.scene().selectedItems() if isinstance(i, RegionItem)]
        if not items:
            if self.q_list.hasFocus():
                self._delete_question()
            return
        for it in items:
            if it.part in it.q.parts:
                it.q.parts.remove(it.part)
            if not it.q.parts and it.q in self.sec.questions:
                self.sec.questions.remove(it.q)
                if self.sel_q is it.q:
                    self.sel_q = None
        self._refresh()

    def _delete_question(self):
        if self.sel_q is not None and self.sel_q in self.sec.questions:
            self.sec.questions.remove(self.sel_q)
            self.sel_q = None
            self._refresh()

    # ------------------------------------------------------------ 저장
    def _save(self):
        problems = []
        for s in self.sections:
            n = len(s.questions)
            if s.expected and n != s.expected:
                problems.append(f"{s.name}: {n}문항 선택 (설정 {s.expected})")
        if not any(s.questions for s in self.sections):
            QMessageBox.warning(self, "저장", "선택한 문항이 없습니다.")
            return
        if problems and QMessageBox.question(
                self, "저장", "\n".join(problems) + "\n\n그래도 저장할까요?"
        ) != QMessageBox.Yes:
            return

        total = sum(len(s.questions) for s in self.sections)
        progress = QProgressDialog("문항 이미지 저장 중...", None, 0, total, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        done = 0
        base = storage.exam_dir(self.exam["id"])
        sections_json = []
        try:
            for s in self.sections:
                tmp = base / f"{s.key}_new"
                shutil.rmtree(tmp, ignore_errors=True)
                tmp.mkdir(parents=True)
                qs_json = []
                for i, q in enumerate(s.ordered()):
                    num = s.start + i
                    progress.setLabelText(f"[{s.name}] {num}번 저장 중")
                    QApplication.processEvents()
                    img = stitch([trim_white(self.pages.crop(p.ref, p.rect)) for p in q.parts])
                    name = f"q{num:03d}.png"
                    img.save(tmp / name)
                    qs_json.append({
                        "number": num, "stem": "", "choices": None, "num_choices": q.choices or s.choices,
                        "image": None, "image_full": name, "choice_mode": "image", "answer": q.answer,
                        "regions": [{"page": p.ref[0], "half": p.ref[1], "rect": list(p.rect)} for p in q.parts],
                    })
                    done += 1
                    progress.setValue(done)
                final = base / s.key
                shutil.rmtree(final, ignore_errors=True)
                tmp.rename(final)
                sections_json.append({
                    "key": s.key, "name": s.name, "minutes": s.minutes, "expected": s.expected,
                    "pages": s.pages, "two_column": s.two_column,
                    "start": s.start, "choices": s.choices, "questions": qs_json,
                })
        except Exception as e:  # noqa: BLE001
            progress.close()
            QMessageBox.critical(self, "저장 실패", str(e))
            return
        progress.close()
        self.exam["sections"] = sections_json
        storage.save_exam(self.exam)
        self._cleanup()
        self.accept()

    def reject(self):
        self._cleanup()
        super().reject()

    def _cleanup(self):
        # 창이 닫히며 장면이 지워질 때 선택 변경 신호가 이미 삭제된 뷰를 건드리지 않도록 (한 번만)
        if getattr(self, "_cleaned", False):
            return
        self._cleaned = True
        try:
            self.view.scene().selectionChanged.disconnect(self._scene_selection)
        except (RuntimeError, TypeError):
            pass
        self.pages.close()


def sections_from_exam(exam: dict) -> list[ESection]:
    """저장된 시험(직접 선택으로 만든 것) -> 편집용 구조"""
    out = []
    for s in exam["sections"]:
        sec = ESection(s["key"], s["name"], s.get("minutes", 15), s.get("expected", 0), s.get("pages", []),
                       two_column=s.get("two_column", False), start=s.get("start", 1), choices=s.get("choices", 4))
        for q in s["questions"]:
            parts = [Part((r["page"], r["half"]), tuple(r["rect"])) for r in q.get("regions", [])]
            if parts:
                n = q.get("num_choices")
                sec.questions.append(EQuestion(parts, q.get("answer"), None if n in (None, sec.choices) else n))
        out.append(sec)
    return out


def is_region_exam(exam: dict) -> bool:
    return bool(exam.get("source_pdf")) and all(
        q.get("regions") for s in exam["sections"] for q in s["questions"])
