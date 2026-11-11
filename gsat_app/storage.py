"""모의고사/응시 기록 저장.

data/exams/<시험ID>/exam.json       시험 정보 (영역, 문항, 정답)
data/exams/<시험ID>/source.pdf      원본 PDF 복사본 (문항 영역 수정용. 내보내기에는 넣지 않음)
data/exams/<시험ID>/s1/q001.png     문항 이미지 (저장할 때마다 새 폴더에 쓰고 exam.json 의 "dir" 로 가리킴)
data/exams/<시험ID>/results/*.json  응시 기록
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
import uuid
import zipfile
from datetime import datetime
from pathlib import Path


def _data_root() -> Path:
    """데이터 폴더.

    - 소스로 실행: 프로젝트 폴더/data
    - EXE 로 실행: EXE 옆 data 폴더 (USB 등으로 통째로 옮기기 쉬움).
      EXE 가 Program Files 처럼 쓰기 금지된 곳에 있으면 %LOCALAPPDATA%/GSAT모의고사/data
    - 맥 앱으로 실행: ~/Library/Application Support/GSAT모의고사/data
      (.app 안에 저장하면 앱을 업데이트할 때 지워지고 서명도 깨진다)
    """
    if os.environ.get("GSAT_DATA_DIR"):  # 테스트 등에서 다른 폴더를 쓰고 싶을 때
        return Path(os.environ["GSAT_DATA_DIR"])
    if not getattr(sys, "frozen", False):
        return Path(__file__).resolve().parent.parent / "data"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "GSAT모의고사" / "data"
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


def section_dir(exam_id: str, section: dict) -> Path:
    """영역의 문항 이미지 폴더. 예전 시험은 영역 키(s1) 폴더, 새로 저장한 시험은 "dir" 에 적힌 폴더."""
    return exam_dir(exam_id) / (section.get("dir") or section["key"])


def retry(fn, tries: int = 6, wait: float = 0.25):
    """OneDrive/백신이 방금 쓴 파일을 잠깐 잡고 있으면 Windows 에서 PermissionError 가 나므로 몇 번 다시 시도"""
    for i in range(tries):
        try:
            return fn()
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(wait * (i + 1))


def new_section_dir(exam_id: str, key: str) -> tuple[str, Path]:
    """저장용 새 이미지 폴더 (항상 새 이름이라 지우지 못한 예전 폴더와 부딪히지 않음)"""
    name = f"{key}_{datetime.now():%Y%m%d%H%M%S}_{uuid.uuid4().hex[:6]}"
    path = exam_dir(exam_id) / name
    path.mkdir(parents=True)
    return name, path


def remove_unused_dirs(exam: dict) -> None:
    """exam.json 이 더 이상 가리키지 않는 예전 이미지 폴더를 지운다. 못 지우면(동기화 중 등) 다음 저장 때 다시 시도."""
    folder = exam_dir(exam["id"])
    used = {s.get("dir") or s["key"] for s in exam["sections"]} | {"results"}
    keys = {s["key"] for s in exam["sections"]}
    for d in folder.iterdir() if folder.exists() else []:
        if not d.is_dir() or d.name in used:
            continue
        base = d.name.split("_")[0]
        if base in keys or d.name.endswith("_new"):  # 이 프로그램이 만든 이미지 폴더만
            shutil.rmtree(d, ignore_errors=True)


PDF_NAME = "source.pdf"


def stored_pdf(exam_id: str) -> Path:
    return exam_dir(exam_id) / PDF_NAME


def find_pdf(exam: dict) -> Path | None:
    """문항 영역 수정에 쓸 PDF: 시험 폴더의 복사본 -> 없으면 처음 만들 때의 원래 경로"""
    copy = stored_pdf(exam["id"])
    if copy.exists():
        return copy
    src = exam.get("source_pdf")
    if src and Path(src).exists():
        return Path(src)
    return None


def store_pdf(exam_id: str, src: str | Path) -> Path:
    """원본 PDF 를 시험 폴더에 복사한다 (원본을 옮기거나 지워도 계속 수정할 수 있도록)."""
    dest = stored_pdf(exam_id)
    if dest.exists() and Path(src).resolve() == dest.resolve():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f"{PDF_NAME}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        shutil.copyfile(src, tmp)
        retry(lambda: os.replace(tmp, dest))
    finally:
        tmp.unlink(missing_ok=True)
    return dest


def save_exam(exam: dict) -> None:
    path = exam_dir(exam["id"]) / "exam.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    # 임시 파일에 다 쓴 뒤 바꿔치기 -> 저장 도중 꺼져도 exam.json 이 반쯤 쓰인 채로 남지 않음
    tmp = path.with_name(f"exam.json.{uuid.uuid4().hex[:8]}.tmp")
    tmp.write_text(json.dumps(exam, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        retry(lambda: os.replace(tmp, path))
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


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
    dirs = {s["key"]: section_dir(exam_id, s) for s in exam["sections"]}
    for s in exam["sections"]:
        s.pop("dir", None)  # 파일 안에서는 영역 키(s1) 폴더로 넣는다 -> 예전 버전에서도 가져오기 가능
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("exam.json", json.dumps(exam, ensure_ascii=False, indent=1))
        for s in exam["sections"]:
            names = {n for q in s["questions"] for n in (q.get("image"), q.get("image_full")) if n}
            names |= {p["image"] for p in s.get("passages", []) if p.get("image")}  # 보기(공통 자료)
            for name in sorted(names):
                path = dirs[s["key"]] / name
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
    attempted = correct + wrong  # 실제로 답을 고른 문항
    return {"correct": correct, "wrong": wrong, "blank": blank, "no_key": no_key,
            "total": len(section["questions"]), "rate": (correct / graded * 100) if graded else 0.0,
            "attempted_rate": (correct / attempted * 100) if attempted else None}


def fmt_rate(rate: float | None) -> str:
    return "-" if rate is None else f"{rate:.1f}%"
