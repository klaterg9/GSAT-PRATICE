"""스캔(이미지) PDF 페이지 보정.

- 펼침면(두 쪽이 한 장)이면 가운데 제본선에서 둘로 나눈다.
- 종이색/제본 그림자를 하얗게 만들고(조명 보정), 기울어진 스캔을 바로 세운다.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter

SCAN_DPI = 300


def is_scanned(page) -> bool:
    """글자가 거의 없고 이미지가 페이지 대부분을 덮으면 스캔 페이지로 본다."""
    if len(page.get_text("text").strip()) > 30:
        return False
    area = page.rect.width * page.rect.height
    for info in page.get_image_info():
        x0, y0, x1, y1 = info["bbox"]
        if (x1 - x0) * (y1 - y0) > 0.5 * area:
            return True
    return False


def page_images(page) -> list[np.ndarray]:
    """PDF 페이지 -> 흑백 이미지 목록 (펼침면이면 2장)."""
    pix = page.get_pixmap(dpi=SCAN_DPI, colorspace="gray")
    gray = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width).copy()
    h, w = gray.shape
    if w > h * 1.15:
        # 가운데 40~60% 구간에서 글자가 가장 적은 세로줄 = 제본선
        ink = (gray < 128).sum(axis=0).astype(float)
        lo, hi = int(w * 0.4), int(w * 0.6)
        smooth = np.convolve(ink, np.ones(15) / 15, mode="same")
        cut = lo + int(np.argmin(smooth[lo:hi]))
        return [gray[:, :cut], gray[:, cut:]]
    return [gray]


def _normalize(gray: np.ndarray) -> np.ndarray:
    """조명 보정: 배경(종이색, 그림자)을 추정해서 나눠 하얗게 만든다."""
    img = Image.fromarray(gray)
    small = img.resize((max(1, img.width // 8), max(1, img.height // 8)), Image.BOX)
    bg = small.filter(ImageFilter.MaxFilter(15)).filter(ImageFilter.MedianFilter(15))
    bg = np.asarray(bg.resize(img.size, Image.BILINEAR), dtype=np.float32)
    norm = gray.astype(np.float32) * 255.0 / np.maximum(bg, 1.0)
    # 대비 살짝 올리기 (연한 회색 -> 흰색)
    return np.clip((norm - 20) * 255.0 / 215.0, 0, 255).astype(np.uint8)


def _deskew(gray: np.ndarray) -> np.ndarray:
    """글줄이 가장 또렷해지는 각도(-3~3도)를 찾아 바로 세운다."""
    img = Image.fromarray(gray)
    small = np.asarray(img.resize((max(1, int(img.width * 0.35)), max(1, int(img.height * 0.35))), Image.BOX))
    ys, xs = np.nonzero(small < 140)
    if len(xs) < 500:
        return gray
    if len(xs) > 80000:
        idx = np.random.default_rng(0).choice(len(xs), 80000, replace=False)
        xs, ys = xs[idx], ys[idx]
    best, best_score = 0.0, -1.0
    for angle in np.arange(-3.0, 3.01, 0.1):
        t = np.deg2rad(angle)
        proj = (ys * np.cos(t) - xs * np.sin(t)).astype(int)
        hist = np.bincount(proj - proj.min())
        score = float((hist.astype(np.float64) ** 2).sum())
        if score > best_score:
            best, best_score = angle, score
    if abs(best) < 0.15:
        return gray
    return np.asarray(img.rotate(best, resample=Image.BICUBIC, fillcolor=255))


def clean_page(gray: np.ndarray) -> np.ndarray:
    """조명 보정 + 기울기 보정."""
    return _deskew(_normalize(gray))
