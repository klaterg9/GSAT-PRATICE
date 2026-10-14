"""테스트용 샘플 모의고사 PDF(문제/정답)를 만든다.

    python tools/make_sample_pdf.py
-> samples/sample_exam.pdf (+ 스캔본, 펼침면 스캔본)
"""
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
FONT = r"C:\Windows\Fonts\malgun.ttf"
FONT_B = r"C:\Windows\Fonts\malgunbd.ttf"
W, H = 595, 842


def new_page(doc, title, page_no):
    page = doc.new_page(width=W, height=H)
    page.insert_font(fontname="R", fontfile=FONT)
    page.insert_font(fontname="B", fontfile=FONT_B)
    page.insert_text((40, 35), f"2026 GSAT 실전 모의고사 | {title}", fontname="R", fontsize=9, color=(0.4, 0.4, 0.4))
    page.draw_line((40, 45), (W - 40, 45), color=(0.6, 0.6, 0.6), width=0.7)
    page.insert_text((W / 2 - 8, H - 25), f"- {page_no} -", fontname="R", fontsize=9)
    # 워터마크 (연한 색)
    page.insert_text((120, 450), "SAMPLE", fontname="B", fontsize=90, color=(0.9, 0.93, 0.97))
    return page


def text(page, x, y, s, size=10.5, bold=False):
    page.insert_text((x, y), s, fontname="B" if bold else "R", fontsize=size)


def table(page, x, y, headers, rows, col_w, row_h=20):
    cols = len(headers)
    page.draw_rect(pymupdf.Rect(x, y, x + col_w * cols, y + row_h), color=None, fill=(0.88, 0.88, 0.88))
    for r in range(len(rows) + 2):
        page.draw_line((x, y + r * row_h), (x + col_w * cols, y + r * row_h), width=0.6)
    for c in range(cols + 1):
        page.draw_line((x + c * col_w, y), (x + c * col_w, y + row_h * (len(rows) + 1)), width=0.6)
    for c, hd in enumerate(headers):
        text(page, x + c * col_w + 6, y + 14, hd, 9)
    for r, row in enumerate(rows):
        for c, v in enumerate(row):
            text(page, x + c * col_w + 6, y + (r + 1) * row_h + 14, str(v), 9)
    return y + row_h * (len(rows) + 1)


def vertical_choices(page, x, y, items, gap=20):
    for i, s in enumerate(items):
        text(page, x, y + i * gap, f"{'①②③④⑤'[i]}  {s}", 10)
    return y + len(items) * gap


def make_exam(path: Path):
    doc = pymupdf.open()
    # ---------------- 수리 (1단) p1~p2
    p = new_page(doc, "수리영역", 1)
    text(p, 40, 80, "1. 다음은 플랫폼별 월간 활성 사용자 수에 관한 자료이다. 이에 대한 설명으로", bold=True)
    text(p, 40, 96, "옳지 않은 것은?", bold=True)
    text(p, 230, 120, "<표> 플랫폼별 월간 활성 사용자 수", 9.5, bold=True)
    yb = table(p, 60, 130, ["구분", "2021년", "2022년", "2023년", "2024년", "2025년"],
               [["A", 350, 420, 480, 530, 560], ["B", 500, 480, 450, 410, 350], ["C", 200, 300, 380, 550, 680],
                ["D", 150, 150, 160, 170, 170], ["E", 400, 450, 420, 440, 480]], 78)
    vertical_choices(p, 50, yb + 30, [
        "조사기간 내내 E플랫폼의 월간 활성 사용자 수가 가장 많은 해는 2025년이다.",
        "2025년 월간 활성 사용자의 2022년 대비 증가율은 C플랫폼이 E플랫폼보다 높다.",
        "2022년 A~E플랫폼 월간 활성 사용자의 합 중 E플랫폼의 비중은 20% 이상이다.",
        "2022~2025년 내내 전년 대비 증감 추이가 A플랫폼과 E플랫폼이 동일하다.",
        "조사기간 동안 B플랫폼의 월간 활성 사용자의 평균은 430만 명 이상이다."])
    text(p, 40, 470, "2. 어떤 일을 A가 혼자 하면 12일, B가 혼자 하면 6일이 걸린다. A와 B가 함께", bold=True)
    text(p, 40, 486, "일을 하면 며칠이 걸리는가?", bold=True)
    text(p, 50, 516, "① 2일      ② 3일      ③ 4일      ④ 5일      ⑤ 6일", 10)
    text(p, 40, 570, "3. 다음 수열의 빈칸에 들어갈 알맞은 수를 고르시오.", bold=True)
    p.draw_rect(pymupdf.Rect(60, 585, 535, 615), width=0.8)
    text(p, 200, 605, "3    7    15    31    (    )    127")
    vertical_choices(p, 50, 640, ["61", "62", "63", "64", "65"], 18)

    p = new_page(doc, "수리영역", 2)
    text(p, 40, 80, "4. 다음 그래프에 대한 설명으로 옳은 것은?", bold=True)
    for i, v in enumerate([60, 90, 120, 80]):
        p.draw_rect(pymupdf.Rect(100 + i * 90, 260 - v, 150 + i * 90, 260), color=None, fill=(0.3, 0.5, 0.8))
        text(p, 110 + i * 90, 275, f"{2022 + i}년", 9)
    p.draw_line((80, 260), (480, 260), width=0.8)
    vertical_choices(p, 50, 310, [
        "2024년의 값이 가장 크다.",
        "2023년은 전년 대비 50% 증가하였다.",
        "2025년은 전년 대비 증가하였다.",
        "4년간 값의 합은 400 이상이다.",
        "2022년의 값이 가장 크다."])

    # ---------------- 추리 (2단) p3~p4
    def two_col_page(no):
        pg = new_page(doc, "추리영역", no)
        pg.draw_line((W / 2, 60), (W / 2, H - 60), width=0.5, color=(0.5, 0.5, 0.5))
        return pg

    p = two_col_page(3)
    L, R = 35, W / 2 + 15
    text(p, L, 80, "1. 다음 명제가 모두 참일 때, 반드시", 10, True)
    text(p, L, 95, "참인 것은?", 10, True)
    p.draw_rect(pymupdf.Rect(L + 5, 105, W / 2 - 15, 165), width=0.6)
    text(p, L + 12, 125, "· 운동을 하는 사람은 건강하다.", 9.5)
    text(p, L + 12, 142, "· 건강한 사람은 행복하다.", 9.5)
    text(p, L + 12, 159, "· 행복한 사람은 웃는다.", 9.5)
    vertical_choices(p, L + 5, 190, ["운동을 하는 사람은 웃는다.", "웃는 사람은 운동을 한다.",
                                     "건강한 사람은 운동을 한다.", "행복한 사람은 건강하다.",
                                     "웃지 않는 사람은 행복하다."], 18)
    text(p, L, 320, "2. 일정한 규칙으로 수를 나열할 때,", 10, True)
    text(p, L, 335, "빈칸에 들어갈 수는?", 10, True)
    text(p, L + 30, 365, "2   5   11   23   (  )")
    text(p, L + 5, 395, "① 45   ② 46   ③ 47   ④ 48   ⑤ 49", 10)
    text(p, L, 450, "3. 다음 도형의 규칙을 적용했을 때", 10, True)
    text(p, L, 465, "물음표에 들어갈 문자는?", 10, True)
    text(p, L + 30, 500, "A → C → F → J → ?")
    vertical_choices(p, L + 5, 540, ["M", "N", "O", "P", "Q"], 18)
    text(p, R, 80, "4. A~E 다섯 명이 일렬로 줄을 섰다.", 10, True)
    text(p, R, 95, "다음 조건을 만족할 때 세 번째에", 10, True)
    text(p, R, 110, "서 있는 사람은?", 10, True)
    p.draw_rect(pymupdf.Rect(R + 5, 120, W - 30, 200), width=0.6)
    for i, s in enumerate(["· A는 맨 앞에 서지 않는다.", "· B는 C 바로 뒤에 선다.",
                           "· D는 맨 뒤에 선다.", "· E는 A보다 앞에 선다."]):
        text(p, R + 12, 140 + i * 17, s, 9.5)
    # 5번은 오른쪽 단 아래에서 시작해 다음 페이지로 이어짐
    vertical_choices(p, R + 5, 225, ["A", "B", "C", "D", "E"], 18)
    text(p, R, 400, "5. 다음 글의 내용과 일치하는 것은?", 10, True)
    p.draw_rect(pymupdf.Rect(R + 5, 410, W - 30, 760), width=0.6)
    for i in range(18):
        text(p, R + 12, 430 + i * 18, f"지문 내용 {i + 1}번째 줄입니다. 글이 계속 이어집니다.", 9)

    p = two_col_page(4)
    vertical_choices(p, L + 5, 80, ["지문은 18줄로 이루어져 있다.", "지문은 다음 페이지로 이어진다.",
                                    "지문에는 표가 있다.", "지문은 영어로 되어 있다.", "지문은 없다."], 18)
    text(p, L, 220, "6. 다음 중 나머지와 성격이 다른", 10, True)
    text(p, L, 235, "하나는?", 10, True)
    vertical_choices(p, L + 5, 265, ["사과", "배", "포도", "당근", "딸기"], 18)

    # ---------------- 지각능력 (그림 선지) p5
    p = new_page(doc, "지각능력", 5)
    text(p, 40, 80, "1. 다음 제시된 도형과 같은 것을 고르시오.", bold=True)
    p.draw_rect(pymupdf.Rect(260, 95, 330, 165), width=1.2)
    p.draw_line((260, 95), (330, 165), width=1.2)
    for i in range(5):
        x = 60 + i * 100
        text(p, x - 15, 200, "①②③④⑤"[i], 11)
        p.draw_rect(pymupdf.Rect(x, 190, x + 60, 250), width=1.2)
        if i == 2:
            p.draw_line((x, 190), (x + 60, 250), width=1.2)
        else:
            p.draw_line((x + 60, 190), (x, 250), width=1.2)
    text(p, 40, 320, "2. 다음 중 제시된 문자와 다른 것은?", bold=True)
    text(p, 200, 350, "ABCDEFGH", 16)
    text(p, 50, 390, "① ABCDEFGH    ② ABCDEFGH    ③ ABCDEFHG    ④ ABCDEFGH    ⑤ ABCDEFGH", 10)
    doc.save(path)



def _scan_look(img, seed: int):
    """종이색, 제본 그림자, 기울어짐, 노이즈를 넣어 스캔본처럼 만든다."""
    import random

    from PIL import Image, ImageChops, ImageFilter
    rnd = random.Random(seed)
    img = img.convert("L")
    img = img.rotate(rnd.uniform(-1.2, 1.2), resample=Image.BICUBIC, expand=False, fillcolor=255)
    w, h = img.size
    shade = Image.linear_gradient("L").rotate(90, expand=True).resize((w, h))  # 왼쪽 어둡게
    shade = shade.point(lambda v: 255 - max(0, (v - 200)) * 2)
    img = ImageChops.multiply(img, shade)
    img = img.point(lambda v: int(v * 0.88 + 12))  # 누런 종이
    noise = Image.effect_noise((w, h), 18).point(lambda v: 255 if v > 90 else 200)
    img = ImageChops.multiply(img, noise.filter(ImageFilter.GaussianBlur(0.6)))
    return img


def make_scanned(src: Path, path: Path, spread: bool = False):
    """텍스트 PDF를 이미지로만 된 '스캔본' PDF로 만든다. spread=True 면 두 쪽씩 펼침면으로."""
    from PIL import Image
    src_doc = pymupdf.open(src)
    imgs = []
    for i, page in enumerate(src_doc):
        pix = page.get_pixmap(dpi=200)
        imgs.append(_scan_look(Image.frombytes("RGB", (pix.width, pix.height), pix.samples), i))
    if spread:
        pairs = [imgs[i:i + 2] for i in range(0, len(imgs), 2)]
        merged = []
        for pair in pairs:
            w = sum(p.width for p in pair) if len(pair) == 2 else pair[0].width * 2
            canvas = Image.new("L", (w, pair[0].height), 235)
            x = 0
            for p in pair:
                canvas.paste(p, (x, 0))
                x += p.width
            merged.append(canvas)
        imgs = merged
    doc = pymupdf.open()
    for img in imgs:
        import io
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        pw, ph = img.width * 72 / 200, img.height * 72 / 200
        page = doc.new_page(width=pw, height=ph)
        page.insert_image(page.rect, stream=buf.getvalue())
    doc.save(path)


if __name__ == "__main__":
    out = ROOT / "samples"
    out.mkdir(exist_ok=True)
    make_exam(out / "sample_exam.pdf")
    make_scanned(out / "sample_exam.pdf", out / "sample_exam_scan.pdf")
    make_scanned(out / "sample_exam.pdf", out / "sample_exam_scan_spread.pdf", spread=True)
    print("생성 완료:", out)
