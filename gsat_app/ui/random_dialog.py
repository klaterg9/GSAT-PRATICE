"""랜덤 모의고사 만들기: 만들어 둔 모의고사들에서 영역별로 문항을 무작위로 골라 새 모의고사를 만든다."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
                               QVBoxLayout)

from .. import storage


class RandomDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("랜덤 모의고사 만들기")
        self.resize(780, 760)
        self.exam: dict | None = None
        self._rows: list[dict] = []   # {"name", "spin", "min", "touched"}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 20, 26, 18)
        lay.setSpacing(10)
        title = QLabel("랜덤 모의고사 만들기")
        title.setObjectName("title")
        lay.addWidget(title)
        sub = QLabel("만들어 둔 모의고사에서 영역별로 문항을 무작위로 골라 새 모의고사를 만듭니다.\n"
                     "같은 이름의 영역(예: 수리영역)끼리 모아서 고릅니다.")
        sub.setObjectName("muted")
        lay.addWidget(sub)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("시험 이름"))
        self.name_edit = QLineEdit(f"랜덤 모의고사 {datetime.now():%m/%d %H:%M}")
        name_row.addWidget(self.name_edit, 1)
        lay.addLayout(name_row)

        head = QLabel("1. 문제를 가져올 모의고사")
        head.setObjectName("section")
        lay.addWidget(head)
        self.sources = QListWidget()
        self.sources.setMaximumHeight(140)
        for exam in storage.list_exams():
            n = sum(len(s["questions"]) for s in exam["sections"])
            tag = "  (랜덤)" if exam.get("random") else ""
            item = QListWidgetItem(f"{exam['name']}{tag}  ·  {n}문항")
            item.setData(Qt.UserRole, exam["id"])
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            # 랜덤 모의고사는 다른 시험에서 복사한 문항이라 기본으로 빼서 같은 문제가 겹치지 않게
            item.setCheckState(Qt.Unchecked if exam.get("random") else Qt.Checked)
            self.sources.addItem(item)
        self.sources.itemChanged.connect(lambda _: self._reload())
        lay.addWidget(self.sources)
        self.answered = QCheckBox("정답이 입력된 문제만 (채점할 수 있게)")
        self.answered.setChecked(True)
        self.answered.toggled.connect(lambda _: self._reload())
        lay.addWidget(self.answered)

        head2 = QLabel("2. 영역별 문항 수와 시간")
        head2.setObjectName("section")
        lay.addWidget(head2)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["영역", "가져올 수 있는 문항", "문항 수 (0이면 제외)", "시간 (분)"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)
        lay.addWidget(self.table, 1)
        self.info = QLabel()
        self.info.setObjectName("muted")
        lay.addWidget(self.info)

        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("취소")
        cancel.clicked.connect(self.reject)
        self.ok = QPushButton("만들기")
        self.ok.setObjectName("primary")
        self.ok.clicked.connect(self._create)
        btns.addWidget(cancel)
        btns.addWidget(self.ok)
        lay.addLayout(btns)
        self._reload()

    def _chosen(self) -> list[str]:
        return [self.sources.item(i).data(Qt.UserRole) for i in range(self.sources.count())
                if self.sources.item(i).checkState() == Qt.Checked]

    def _reload(self):
        """고른 모의고사가 바뀌면 영역 목록/문항 수를 다시 계산 (이미 적은 문항 수는 유지)"""
        old = {r["name"]: (r["spin"].value(), r["min"].value(), r["touched"]) for r in self._rows}
        self.pool = storage.question_pool(self._chosen(), self.answered.isChecked())
        defaults = {d["name"]: d for d in storage.DEFAULT_SECTIONS}
        self.table.setRowCount(0)
        self._rows = []
        for name, items in self.pool.items():
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c, v in enumerate([name, f"{len(items)}문항"]):
                it = QTableWidgetItem(v)
                it.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(r, c, it)
            row = {"name": name, "mpq": storage.minutes_per_question(items), "touched": False}
            spin = QSpinBox()
            spin.setRange(0, len(items))
            spin.setAlignment(Qt.AlignCenter)
            mins = QSpinBox()
            mins.setRange(1, 600)
            mins.setAlignment(Qt.AlignCenter)
            row["spin"], row["min"] = spin, mins
            if name in old:
                count, minute, touched = old[name]
                spin.setValue(min(count, len(items)))
                mins.setValue(minute)
                row["touched"] = touched
            else:
                spin.setValue(min(len(items), defaults.get(name, {}).get("count", 20)))
                mins.setValue(self._auto_minutes(row, spin.value()))
            spin.valueChanged.connect(lambda v, row=row: self._count_changed(row, v))
            mins.valueChanged.connect(lambda _v, row=row: row.__setitem__("touched", True))
            self.table.setCellWidget(r, 2, spin)
            self.table.setCellWidget(r, 3, mins)
            self._rows.append(row)
        self._update_info()

    @staticmethod
    def _auto_minutes(row: dict, count: int) -> int:
        return max(1, round(row["mpq"] * count))

    def _count_changed(self, row: dict, count: int):
        if not row["touched"]:  # 시간을 직접 바꾸지 않았으면 문항 수에 맞춰 자동 조절
            row["min"].blockSignals(True)
            row["min"].setValue(self._auto_minutes(row, count))
            row["min"].blockSignals(False)
        self._update_info()

    def _update_info(self):
        total = sum(r["spin"].value() for r in self._rows)
        minutes = sum(r["min"].value() for r in self._rows if r["spin"].value())
        if not self._rows:
            self.info.setText("가져올 문제가 없습니다. 위에서 모의고사를 고르거나, 정답을 먼저 입력하세요.")
        else:
            self.info.setText(f"총 {total}문항 · {minutes}분.  시간은 원래 모의고사의 문항당 시간에 맞춰 자동으로 정해집니다.")
        self.ok.setEnabled(total > 0)

    def _create(self):
        plan = [{"name": r["name"], "count": r["spin"].value(), "minutes": r["min"].value()}
                for r in self._rows if r["spin"].value() > 0]
        if not plan:
            return
        name = self.name_edit.text().strip() or "랜덤 모의고사"
        try:
            self.exam = storage.build_random_exam(name, plan, self._chosen(), self.answered.isChecked())
        except (OSError, ValueError) as e:
            QMessageBox.critical(self, "랜덤 모의고사", f"만들 수 없습니다.\n{e}")
            return
        self.accept()
