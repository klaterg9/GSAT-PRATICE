"""모의고사/응시 기록 저장.

data/exams/<시험ID>/exam.json       시험 정보 (영역, 문항, 정답)
data/exams/<시험ID>/s1/q001.png     문항 이미지
data/exams/<시험ID>/results/*.json  응시 기록
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path


def _data_root() -> Path:
    """데이터 폴더.

    - 소스로 실행: 프로젝트 폴더/data
    - EXE 로 실행: EXE 옆 data 폴더 (USB 등으로 통째로 옮기기 쉬움).
      EXE 가 Program Files 처럼 쓰기 금지된 곳에 있으면 %LOCALAPPDATA%/GSAT모의고사/data
    """
    if not getattr(sys, "frozen", False):
        return Path(__file__).resolve().parent.parent / "data"
    beside = Path(sys.executable).resolve().parent / "data"
    try:
        beside.mkdir(parents=True, exist_ok=True)
        probe = beside / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return beside
    except OSError:
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home())
        return base / "GSAT모의고사" / "data"


DATA_DIR = _data_root() / "exams"

DEFAULT_SECTIONS = [
    {"name": "수리영역", "count": 40, "minutes": 15},
    {"name": "추리영역", "count": 40, "minutes": 20},
    {"name": "지각능력(시각적 사고)", "count": 40, "minutes": 10},
]


def new_exam_dir() -> tuple[str, Path]:
    exam_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = DATA_DIR / exam_id
    n = 1
    while path.exists():
        n += 1
        path = DATA_DIR / f"{exam_id}_{n}"
    path.mkdir(parents=True)
    return path.name, path


def exam_dir(exam_id: str) -> Path:
    return DATA_DIR / exam_id


def save_exam(exam: dict) -> None:
    path = exam_dir(exam["id"]) / "exam.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(exam, ensure_ascii=False, indent=1), encoding="utf-8")


def load_exam(exam_id: str) -> dict:
    return json.loads((exam_dir(exam_id) / "exam.json").read_text(encoding="utf-8"))


def list_exams() -> list[dict]:
    if not DATA_DIR.exists():
        return []
    exams = []
    for d in sorted(DATA_DIR.iterdir(), reverse=True):
        if (d / "exam.json").exists():
            try:
                exams.append(load_exam(d.name))
            except (OSError, json.JSONDecodeError):
                continue
    return exams


def delete_exam(exam_id: str) -> None:
    shutil.rmtree(exam_dir(exam_id), ignore_errors=True)


def save_result(exam_id: str, result: dict) -> None:
    folder = exam_dir(exam_id) / "results"
    folder.mkdir(parents=True, exist_ok=True)
    name = datetime.now().strftime("%Y%m%d_%H%M%S") + ".json"
    result["file"] = name
    (folder / name).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")


def list_results(exam_id: str) -> list[dict]:
    folder = exam_dir(exam_id) / "results"
    if not folder.exists():
        return []
    out = []
    for f in sorted(folder.glob("*.json"), reverse=True):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return out


EXPORT_EXT = ".gsat"


def export_exam(exam_id: str, dest: Path) -> None:
    """시험 하나를 .gsat 파일(zip)로 내보낸다. 응시 기록과 원본 PDF 경로는 넣지 않는다."""
    exam = load_exam(exam_id)
    for key in ("source_pdf",):
        exam.pop(key, None)  # 받는 사람 PC 에는 없는 경로
    folder = exam_dir(exam_id)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("exam.json", json.dumps(exam, ensure_ascii=False, indent=1))
        for s in exam["sections"]:
            for q in s["questions"]:
                for name in {q.get("image"), q.get("image_full")} - {None}:
                    path = folder / s["key"] / name
                    if path.exists():
                        z.write(path, f"{s['key']}/{name}")


def import_exam(src: Path) -> dict:
    """.gsat 파일을 새 시험으로 가져온다. 같은 시험을 여러 번 가져와도 따로 저장된다."""
    with zipfile.ZipFile(src) as z:
        try:
            exam = json.loads(z.read("exam.json").decode("utf-8"))
        except KeyError as e:
            raise ValueError("모의고사 파일이 아닙니다 (exam.json 없음).") from e
        if not isinstance(exam.get("sections"), list):
            raise ValueError("모의고사 파일 형식이 올바르지 않습니다.")
        new_id, folder = new_exam_dir()
        try:
            for info in z.infolist():
                name = info.filename
                parts = Path(name).parts
                # 폴더 밖으로 빠져나가는 경로(../ 등)는 무시
                if info.is_dir() or name == "exam.json" or ".." in parts or Path(name).is_absolute():
                    continue
                if len(parts) != 2 or not parts[1].lower().endswith(".png"):
                    continue
                target = folder / parts[0] / parts[1]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(info))
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise
    exam["id"] = new_id
    exam["imported"] = datetime.now().isoformat(timespec="seconds")
    save_exam(exam)
    return exam


def score_section(section: dict, answers: dict) -> dict:
    """answers: {"번호(str)": 선택} -> 채점 요약"""
    correct = wrong = blank = no_key = 0
    for q in section["questions"]:
        mine = answers.get(str(q["number"]))
        if q.get("answer") is None:
            no_key += 1
        elif mine is None:
            blank += 1
        elif mine == q["answer"]:
            correct += 1
        else:
            wrong += 1
    graded = correct + wrong + blank
    return {"correct": correct, "wrong": wrong, "blank": blank, "no_key": no_key,
            "total": len(section["questions"]), "rate": (correct / graded * 100) if graded else 0.0}
