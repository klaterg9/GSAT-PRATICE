"""새 모의고사 만들기: PDF 고르고 영역별 페이지만 적으면 끝. (페이지는 다음 화면에서도 바꿀 수 있음)"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

import pymupdf
from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (QDialog, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QVBoxLayout, QWidget)

from .. import storage
from .region_editor import ESection, RegionEditor


def _num_edit(placeholder: str, value: str = "", width: int = 64) -> QLineEdit:
    e = QLineEdit(value)
    e.setPlaceholderText(placeholder)
    e.setValidator(QIntValidator(0, 9999))
    e.setAlignment(Qt.AlignCenter)
    e.setFixedWidth(width)
    return e


class CreateDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("새 모의고사 만들기")
        self.resize(680, 440)
        self.exam_id: str | None = None
        self.pdf_path: str | None = None
        self.page_count = 0
        self.rows: list[dict] = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 28, 20)
        lay.setSpacing(14)
        title = QLabel("새 모의고사 만들기")
        title.setObjectName("title")
        lay.addWidget(title)

        # 1) PDF 선택
        pdf_row = QHBoxLayout()
        pick = QPushButton("PDF 파일 선택")
        pick.setObjectName("primary")
        pick.setMinimumHeight(38)
        pick.clicked.connect(self._browse)
        pdf_row.addWidget(pick)
        self.pdf_label = QLabel("문제가 들어 있는 PDF를 골라주세요.")
        self.pdf_label.setObjectName("muted")
        pdf_row.addWidget(self.pdf_label, 1)
        lay.addLayout(pdf_row)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("시험 이름"))
        self.name_edit = QLineEdit(f"모의고사 {datetime.now():%m/%d}")
        self.name_edit.setMinimumHeight(32)
        self._name_touched = False
        self.name_edit.textEdited.connect(lambda _: setattr(self, "_name_touched", True))
        name_row.addWidget(self.name_edit, 1)
        lay.addLayout(name_row)

        # 2) 영역: 이름 | 시작 ~ 끝쪽 | 문항 | 분 | 삭제
        box = QWidget()
        self.grid = QGridLayout(box)
        self.grid.setContentsMargins(0, 6, 0, 0)
        self.grid.setHorizontalSpacing(10)
        self.grid.setVerticalSpacing(8)
        for col, text in enumerate(["영역", "페이지", "", "", "", "문항 수", "시간(분)"]):
            if text:
                h = QLabel(text)
                h.setObjectName("muted")
                self.grid.addWidget(h, 0, col, Qt.AlignLeft if col == 0 else Qt.AlignCenter)
        self.grid.setColumnStretch(0, 1)
        lay.addWidget(box)
        for s in storage.DEFAULT_SECTIONS:
            self._add_row(s["name"], s["count"], s["minutes"])

        add = QPushButton("+ 영역 추가")
        add.clicked.connect(lambda: self._add_row("", 40, 15))
        add_row = QHBoxLayout()
        add_row.addWidget(add)
        add_row.addStretch()
        lay.addLayout(add_row)

        hint = QLabel("페이지를 비워두면 PDF 전체가 보입니다. 페이지 범위는 다음 화면에서 언제든 바꿀 수 있어요.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        lay.addStretch()

        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("취소")
        cancel.clicked.connect(self.reject)
        go = QPushButton("다음: 문항 영역 선택 →")
        go.setObjectName("primary")
        go.setMinimumHeight(38)
        go.clicked.connect(self._run)
        btns.addWidget(cancel)
        btns.addWidget(go)
        lay.addLayout(btns)

    # ---- 입력
    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "PDF 선택", "", "PDF (*.pdf)")
        if path:
            self.set_pdf(path)

    def set_pdf(self, path: str):
        try:
            with pymupdf.open(path) as d:
                self.page_count = d.page_count
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "오류", f"PDF를 열 수 없습니다.\n{e}")
            return
        self.pdf_path = path
        self.pdf_label.setText(f"<b>{Path(path).name}</b>  ·  {self.page_count}쪽")
        self.pdf_label.setObjectName("")
        self.pdf_label.setStyleSheet("")
        if not self._name_touched:
            self.name_edit.setText(Path(path).stem)

    def _add_row(self, name: str, count: int, minutes: int):
        r = len(self.rows) + 1
        row = {
            "name": QLineEdit(name),
            "start": _num_edit("시작"),
            "end": _num_edit("끝"),
            "count": _num_edit("", str(count), 56),
            "minutes": _num_edit("", str(minutes), 56),
            "remove": QPushButton("✕"),
        }
        row["name"].setPlaceholderText("영역 이름")
        row["name"].setMinimumHeight(32)
        row["remove"].setFixedSize(34, 32)
        row["remove"].setStyleSheet("font-size: 16px; padding: 0; color: #888;")
        row["remove"].setToolTip("이 영역 삭제")
        row["remove"].clicked.connect(lambda: self._remove_row(row))
        tilde, unit = QLabel("~"), QLabel("쪽")
        row["extras"] = [tilde, unit]
        widgets = [row["name"], row["start"], tilde, row["end"], unit, row["count"], row["minutes"], row["remove"]]
        for col, w in enumerate(widgets):
            self.grid.addWidget(w, r, col)
        self.rows.append(row)

    def _remove_row(self, row: dict):
        for key in ("name", "start", "end", "count", "minutes", "remove"):
            row[key].hide()
            row[key].deleteLater()
        for w in row["extras"]:
            w.hide()
            w.deleteLater()
        self.rows.remove(row)

    # ---- 다음 단계
    def _run(self):
        if not self.pdf_path:
            QMessageBox.warning(self, "확인", "먼저 PDF 파일을 선택하세요.")
            return
        sections = []
        for i, row in enumerate(self.rows):
            name = row["name"].text().strip() or f"영역 {i + 1}"
            start = int(row["start"].text() or 0)
            end = int(row["end"].text() or 0)
            if not start and not end:
                start, end = 1, self.page_count      # 비워두면 전체
            start, end = start or end, end or start
            if start > end:
                start, end = end, start
            if start < 1 or end > self.page_count:
                QMessageBox.warning(self, "입력 확인", f"[{name}] 페이지는 1~{self.page_count} 사이로 입력하세요.")
                return
            sections.append(ESection(f"s{len(sections) + 1}", name, int(row["minutes"].text() or 15),
                                     int(row["count"].text() or 0), list(range(start - 1, end))))
        if not sections:
            QMessageBox.warning(self, "확인", "영역을 하나 이상 추가하세요.")
            return

        exam_id, path = storage.new_exam_dir()
        exam = {"id": exam_id, "name": self.name_edit.text().strip() or Path(self.pdf_path).stem,
                "created": datetime.now().isoformat(timespec="seconds"), "source": Path(self.pdf_path).name,
                "source_pdf": str(Path(self.pdf_path).resolve()), "sections": []}
        try:
            editor = RegionEditor(exam, sections, self.pdf_path, self, new=True)
        except Exception as e:  # noqa: BLE001
            shutil.rmtree(path, ignore_errors=True)
            QMessageBox.critical(self, "오류", f"PDF를 열 수 없습니다.\n{e}")
            return
        if editor.exec() == QDialog.Accepted:
            self.exam_id = exam_id
            self.accept()
        else:
            shutil.rmtree(path, ignore_errors=True)
