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


APP_DIR_NAME = "GSAT모의고사"


def _user_dir() -> Path:
    """사용자별 프로그램 폴더 (설정 파일 위치, 맥의 기본 데이터 위치)"""
    if os.environ.get("GSAT_CONFIG_DIR"):  # 테스트용
        return Path(os.environ["GSAT_CONFIG_DIR"])
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / APP_DIR_NAME


CONFIG_PATH = _user_dir() / "config.json"


def load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_config(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")


def default_data_root() -> Path:
    """설정을 따로 안 했을 때의 데이터 폴더.

    - 소스로 실행: 프로젝트 폴더/data
    - Windows EXE: EXE 옆 data 폴더 (폴더째 옮기기 쉬움). 쓰기 금지된 곳이면 %LOCALAPPDATA%/GSAT모의고사/data
    - 맥 앱: ~/Library/Application Support/GSAT모의고사/data (.app 안에 저장하면 업데이트 때 지워지고 서명이 깨짐)
    """
    if not getattr(sys, "frozen", False):
        return Path(__file__).resolve().parent.parent / "data"
    if sys.platform == "darwin":
        return _user_dir() / "data"
    beside = Path(sys.executable).resolve().parent / "data"
    try:
        beside.mkdir(parents=True, exist_ok=True)
        probe = beside / f".write_test_{uuid.uuid4().hex[:6]}"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return beside
    except OSError:
        return _user_dir() / "data"


def _has_exams(root: Path) -> bool:
    d = root / "exams"
    return d.is_dir() and any((x / "exam.json").exists() for x in d.iterdir() if x.is_dir())


ADOPTED_V141 = False  # v1.4.1 사용자 폴더 데이터를 이어서 쓰게 됐는지 (처음 실행 안내용)


def _data_root() -> Path:
    """데이터 폴더: 테스트용 환경변수 -> 사용자가 정한 위치(저장 위치 설정) -> 기본 위치"""
    global ADOPTED_V141
    if os.environ.get("GSAT_DATA_DIR"):  # 테스트 등에서 다른 폴더를 쓰고 싶을 때
        return Path(os.environ["GSAT_DATA_DIR"])
    custom = load_config().get("data_dir")
    if custom:
        return Path(custom)
    if getattr(sys, "frozen", False) and sys.platform != "darwin":
        # v1.4.1 은 사용자 폴더에 저장했다. 거기에 모의고사가 있으면 계속 그 위치를 쓰도록 설정해 둔다
        # (기본 위치를 다시 EXE 옆으로 바꾸면서 모의고사가 안 보이는 일이 없도록)
        v141 = _user_dir() / "data"
        if _has_exams(v141):
            try:
                save_config({**load_config(), "data_dir": str(v141)})
                ADOPTED_V141 = True
            except OSError:
                pass
            return v141
    return default_data_root()


DATA_DIR = _data_root() / "exams"


def data_root() -> Path:
    return DATA_DIR.parent


def copy_exams(src_root: Path, dest_root: Path | None = None) -> int:
    """src_root/exams 의 모의고사를 dest_root/exams 로 복사. 같은 이름(같은 시험)은 건너뛴다. 복사한 수를 돌려준다."""
    src = src_root / "exams"
    dest = (dest_root or data_root()) / "exams"
    if not src.is_dir() or (dest.exists() and src.resolve() == dest.resolve()):
        return 0
    dest.mkdir(parents=True, exist_ok=True)
    moved = 0
    for d in sorted(src.iterdir()):
        if not d.is_dir() or not (d / "exam.json").exists() or (dest / d.name).exists():
            continue
        tmp = dest / f".{d.name}.copying"
        shutil.rmtree(tmp, ignore_errors=True)
        try:
            shutil.copytree(d, tmp)
            tmp.rename(dest / d.name)
            moved += 1
        except OSError:
            shutil.rmtree(tmp, ignore_errors=True)
    return moved


def set_data_root(new_root: Path | None, copy_existing: bool = True) -> int:
    """저장 위치 변경. None 이면 기본 위치로. copy_existing 이면 지금 모의고사를 새 위치로 복사(원래 위치는 그대로).
    복사한 모의고사 수를 돌려준다."""
    global DATA_DIR
    target = Path(new_root) if new_root else default_data_root()
    target.mkdir(parents=True, exist_ok=True)
    probe = target / f".write_test_{uuid.uuid4().hex[:6]}"
    probe.write_text("ok", encoding="utf-8")  # 쓸 수 없는 폴더면 여기서 OSError
    probe.unlink()
    moved = copy_exams(data_root(), target) if copy_existing else 0
    cfg = load_config()
    if new_root:
        cfg["data_dir"] = str(target)
    else:
        cfg.pop("data_dir", None)
    save_config(cfg)
    DATA_DIR = target / "exams"
    return moved


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
    stem = datetime.now().strftime("%Y%m%d_%H%M%S")
    name, n = stem + ".json", 1
    while (folder / name).exists():  # 같은 초에 저장된 기록을 덮어쓰지 않도록
        n += 1
        name = f"{stem}_{n}.json"
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


MODE_LABELS = {"full": "실전(전 영역)", "section": "영역 연습", "retry": "오답 다시 풀기"}
MODE_SHORT = {"full": "실전", "section": "영역", "retry": "오답"}


def result_section(section: dict, rs: dict) -> dict:
    """응시 기록의 한 영역에 실제로 나온 문항만 남긴 영역 (오답 다시 풀기는 일부 문항만 풂)"""
    nums = rs.get("numbers")
    if not nums:
        return section
    keep = set(nums)
    return {**section, "questions": [q for q in section["questions"] if q["number"] in keep]}


def load_result(exam_id: str, file: str) -> dict | None:
    path = exam_dir(exam_id) / "results" / file
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def retry_base(exam_id: str, result: dict) -> dict:
    """오답 다시 풀기의 기준이 되는 원래 응시 기록 (다시 푼 기록에서 또 누르면 처음 응시 기준)"""
    if result.get("mode") == "retry" and result.get("base"):
        base = load_result(exam_id, result["base"])
        if base is not None:
            return base
    return result


def retry_stats(exam_id: str, exam: dict) -> dict[tuple[str, int], tuple[int, int]]:
    """문항별 (다시 푼 횟수, 그중 맞힌 횟수). 오답 다시 풀기 기록만 센다."""
    answers = {(s["key"], q["number"]): q.get("answer") for s in exam["sections"] for q in s["questions"]}
    stats: dict[tuple[str, int], list[int]] = {}
    for r in list_results(exam_id):
        if r.get("mode") != "retry":
            continue
        for rs in r["sections"]:
            for n in rs.get("numbers", []):
                key = answers.get((rs["key"], n))
                st = stats.setdefault((rs["key"], n), [0, 0])
                st[0] += 1
                if key is not None and rs["answers"].get(str(n)) == key:
                    st[1] += 1
    return {k: (a, b) for k, (a, b) in stats.items()}


def fmt_retry(st: tuple[int, int] | None) -> str:
    return f"다시 푼 {st[0]}회 · 맞음 {st[1]}회" if st else ""


def wrong_numbers(section: dict, rs: dict) -> list[int]:
    """그 응시에서 틀렸거나 안 푼 문항 번호 (정답이 입력된 문항만)"""
    out = []
    for q in result_section(section, rs)["questions"]:
        if q.get("answer") is not None and rs["answers"].get(str(q["number"])) != q["answer"]:
            out.append(q["number"])
    return out


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


# ---------------------------------------------------------------- 랜덤 모의고사
def question_pool(exam_ids: list[str], answered_only: bool = True) -> dict[str, list[tuple[dict, dict, dict]]]:
    """영역 이름별 문항 모음: {영역 이름: [(시험, 영역, 문항), ...]} (시험 순서 -> 영역 순서대로)"""
    pool: dict[str, list[tuple[dict, dict, dict]]] = {}
    for eid in exam_ids:
        try:
            exam = load_exam(eid)
        except (OSError, json.JSONDecodeError):
            continue
        for s in exam["sections"]:
            items = pool.setdefault(s["name"].strip(), [])
            for q in s["questions"]:
                if q.get("image_full") or q.get("image"):
                    if not answered_only or q.get("answer") is not None:
                        items.append((exam, s, q))
    return {k: v for k, v in pool.items() if v}


def minutes_per_question(items: list[tuple[dict, dict, dict]]) -> float:
    """원래 시험들의 문항당 평균 시간(분)"""
    seen = {}
    for exam, s, _q in items:
        seen[(exam["id"], s["key"])] = (s.get("minutes", 15), len(s["questions"]) or 1)
    total_min = sum(m for m, _ in seen.values())
    total_q = sum(n for _, n in seen.values())
    return total_min / total_q if total_q else 0.5


def build_random_exam(name: str, plan: list[dict], exam_ids: list[str], answered_only: bool = True,
                      rng=None) -> dict:
    """plan: [{"name": 영역 이름, "count": 문항 수, "minutes": 시간}] -> 문항을 무작위로 골라 새 모의고사로 저장.
    문항 이미지(와 연결된 보기)를 새 시험 폴더로 복사하므로 원래 시험을 지워도 그대로 풀 수 있다."""
    import random
    rng = rng or random.Random()
    pool = question_pool(exam_ids, answered_only)
    exam_id, folder = new_exam_dir()
    sections = []
    try:
        for i, p in enumerate(plan, start=1):
            items = pool.get(p["name"], [])
            n = min(int(p["count"]), len(items))
            if n <= 0:
                continue
            key = f"s{i}"
            (folder / key).mkdir()
            picked = rng.sample(items, n)
            passages, pmap, qs = [], {}, []
            for num, (exam, s, q) in enumerate(picked, start=1):
                src = section_dir(exam["id"], s)
                new_q = {k: v for k, v in q.items() if k not in ("regions", "passage")}
                new_q["number"] = num
                new_q["num_choices"] = q.get("num_choices") or s.get("choices") or 5
                for field, prefix in (("image_full", "q"), ("image", "t")):
                    if q.get(field):
                        dest = f"{prefix}{num:03d}.png"
                        shutil.copyfile(src / q[field], folder / key / dest)
                        new_q[field] = dest
                pid = q.get("passage")
                psg = next((x for x in s.get("passages", []) if x.get("id") == pid), None) if pid else None
                if psg and psg.get("image") and (src / psg["image"]).exists():
                    ref = (exam["id"], s["key"], pid)
                    if ref not in pmap:
                        k = len(passages) + 1
                        shutil.copyfile(src / psg["image"], folder / key / f"p{k:02d}.png")
                        pmap[ref] = f"p{k}"
                        passages.append({"id": f"p{k}", "label": psg.get("label", f"보기 {k}"),
                                         "image": f"p{k:02d}.png", "range": None})
                    new_q["passage"] = pmap[ref]
                new_q["origin"] = {"exam": exam["id"], "exam_name": exam["name"], "section": s["key"],
                                   "number": q["number"]}
                qs.append(new_q)
            sections.append({"key": key, "name": p["name"], "minutes": max(1, int(p["minutes"])),
                             "expected": n, "passages": passages, "questions": qs})
        if not sections:
            raise ValueError("고를 수 있는 문항이 없습니다.")
        exam = {"id": exam_id, "name": name, "created": datetime.now().isoformat(timespec="seconds"),
                "random": True, "sources": exam_ids, "sections": sections}
        save_exam(exam)
        return exam
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
