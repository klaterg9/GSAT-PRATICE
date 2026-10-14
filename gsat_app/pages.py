"""PDF 페이지를 화면/캡처용 이미지로 제공한다.

- 텍스트 PDF 페이지: 그대로 렌더링 (ZOOM 배율)
- 스캔 페이지: 종이색/그림자/기울기 보정한 이미지. 펼침면이면 왼쪽/오른쪽 두 쪽으로 나눔.

쪽 하나는 (PDF 페이지 번호, 반쪽 번호) 로 가리킨다. 반쪽 번호는 펼침면이 아니면 항상 0.
"""
from __future__ import annotations

from collections import OrderedDict

import numpy as np
import pymupdf
from PIL import Image

from . import scan

PageRef = tuple[int, int]  # (pdf 페이지, 반쪽)
ZOOM = 2.5  # 문항 이미지 배율 (PDF 1pt = 2.5px, 약 180dpi)
DISPLAY_W = 1600  # 화면 표시용 이미지 폭 (픽셀)


class PdfPages:
    def __init__(self, path: str, cache_size: int = 8):
        self.path = path
        self.doc = pymupdf.open(path)
        self._cache: OrderedDict[PageRef, Image.Image] = OrderedDict()
        self._cache_size = cache_size
        self._scanned: dict[int, bool] = {}
        self._display: dict[PageRef, Image.Image] = {}

    @property
    def page_count(self) -> int:
        return self.doc.page_count

    def close(self):
        if not self.doc.is_closed:
            self.doc.close()

    def is_scanned(self, pno: int) -> bool:
        if pno not in self._scanned:
            self._scanned[pno] = scan.is_scanned(self.doc[pno])
        return self._scanned[pno]

    def is_spread(self, pno: int) -> bool:
        r = self.doc[pno].rect
        return self.is_scanned(pno) and r.width > r.height * 1.15

    def refs(self, pnos: list[int]) -> list[PageRef]:
        out: list[PageRef] = []
        for p in pnos:
            out.extend([(p, 0), (p, 1)] if self.is_spread(p) else [(p, 0)])
        return out

    def label(self, ref: PageRef) -> str:
        p, half = ref
        if self.is_spread(p):
            return f"{p + 1}쪽 {'왼쪽' if half == 0 else '오른쪽'}"
        return f"{p + 1}쪽"

    def aspect(self, ref: PageRef) -> float:
        """세로/가로 비율 (이미지를 만들지 않고 계산; 화면 배치용)"""
        r = self.doc[ref[0]].rect
        width = r.width / 2 if self.is_spread(ref[0]) else r.width
        return r.height / width

    def display_image(self, ref: PageRef, width: int = DISPLAY_W) -> Image.Image:
        """화면 표시용 (작게 줄인) 이미지. 한 번 만든 것은 계속 보관."""
        if ref in self._display:
            return self._display[ref]
        p = ref[0]
        if self.is_scanned(p):
            full = self.image(ref)
            img = full.resize((width, max(1, round(full.height * width / full.width))), Image.LANCZOS)
        else:
            page = self.doc[p]
            z = width / page.rect.width
            pix = page.get_pixmap(matrix=pymupdf.Matrix(z, z), alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        self._display[ref] = img
        return img

    def crop_scale(self, ref: PageRef) -> float:
        """페이지 이미지 픽셀 -> 문항 이미지 픽셀 배율 (모든 문항 이미지를 ZOOM 배율로 맞춤)"""
        return ZOOM / (scan.SCAN_DPI / 72) if self.is_scanned(ref[0]) else 1.0

    def image(self, ref: PageRef) -> Image.Image:
        if ref in self._cache:
            self._cache.move_to_end(ref)
            return self._cache[ref]
        p, half = ref
        page = self.doc[p]
        if self.is_scanned(p):
            grays = scan.page_images(page)
            for i, g in enumerate(grays):
                self._put((p, i), Image.fromarray(scan.clean_page(g)))
        else:
            pix = page.get_pixmap(matrix=pymupdf.Matrix(ZOOM, ZOOM), alpha=False)
            self._put((p, 0), Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
        return self._cache[ref]

    def _put(self, ref: PageRef, img: Image.Image):
        self._cache[ref] = img
        self._cache.move_to_end(ref)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)

    def crop(self, ref: PageRef, rect: tuple[float, float, float, float]) -> Image.Image:
        """rect: 페이지 이미지 기준 0~1 비율 좌표"""
        img = self.image(ref)
        w, h = img.size
        box = (int(rect[0] * w), int(rect[1] * h), int(rect[2] * w), int(rect[3] * h))
        part = img.crop(box).convert("RGB")
        s = self.crop_scale(ref)
        if s != 1.0:
            part = part.resize((max(1, int(part.width * s)), max(1, int(part.height * s))), Image.LANCZOS)
        return part


def stitch(parts: list[Image.Image], gap: int = 10) -> Image.Image:
    width = max(p.width for p in parts)
    canvas = Image.new("RGB", (width, sum(p.height for p in parts) + gap * (len(parts) - 1)), "white")
    y = 0
    for p in parts:
        canvas.paste(p, (0, y))
        y += p.height + gap
    return canvas


def trim_white(img: Image.Image, pad: int = 12) -> Image.Image:
    """사용자가 넉넉하게 잡은 여백만 살짝 정리 (내용은 자르지 않음)"""
    arr = np.asarray(img.convert("L"))
    ys, xs = np.nonzero(arr < 200)
    if len(xs) == 0:
        return img
    x0, x1 = max(0, xs.min() - pad), min(img.width, xs.max() + pad + 1)
    y0, y1 = max(0, ys.min() - pad), min(img.height, ys.max() + pad + 1)
    return img.crop((x0, y0, x1, y1))
