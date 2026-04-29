"""
图片数据增强：对每张原图按所选类型各生成一张增强图（PIL，无额外依赖）。
"""

from __future__ import annotations

import io
import os
import zipfile
from typing import Any, Callable, Dict, List, Tuple

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

# id -> (展示名, 处理函数)
_AUGMENT_REGISTRY: Dict[str, Tuple[str, Callable[[Image.Image], Image.Image]]] = {}


def _reg(op_id: str, label: str, fn: Callable[[Image.Image], Image.Image]) -> None:
    _AUGMENT_REGISTRY[op_id] = (label, fn)


def _to_rgb(img: Image.Image) -> Image.Image:
    if img.mode in ("RGB", "RGBA"):
        return img
    if img.mode == "P":
        return img.convert("RGBA")
    return img.convert("RGB")


_reg("hflip", "水平翻转", lambda im: im.transpose(Image.FLIP_LEFT_RIGHT))
_reg("vflip", "垂直翻转", lambda im: im.transpose(Image.FLIP_TOP_BOTTOM))
_reg("rot90", "逆时针旋转 90°", lambda im: im.transpose(Image.ROTATE_90))
_reg("rot180", "旋转 180°", lambda im: im.transpose(Image.ROTATE_180))
_reg("rot270", "逆时针旋转 270°", lambda im: im.transpose(Image.ROTATE_270))
_reg("brightness_up", "亮度提高", lambda im: ImageEnhance.Brightness(im).enhance(1.28))
_reg("brightness_down", "亮度降低", lambda im: ImageEnhance.Brightness(im).enhance(0.82))
_reg("contrast_up", "对比度提高", lambda im: ImageEnhance.Contrast(im).enhance(1.35))
_reg("color_up", "饱和度提高", lambda im: ImageEnhance.Color(im).enhance(1.35))
_reg("sharpness", "锐化", lambda im: ImageEnhance.Sharpness(im).enhance(1.45))
_reg("blur", "轻度模糊", lambda im: im.filter(ImageFilter.GaussianBlur(radius=1.15)))
_reg(
    "edge_enhance",
    "边缘增强",
    lambda im: im.filter(ImageFilter.EDGE_ENHANCE),
)
_reg(
    "grayscale",
    "灰度（转 RGB 导出）",
    lambda im: ImageOps.grayscale(_to_rgb(im)).convert("RGB"),
)


def list_augment_options() -> List[Dict[str, str]]:
    return [{"id": k, "label": v[0]} for k, v in _AUGMENT_REGISTRY.items()]


def allowed_op_ids() -> frozenset:
    return frozenset(_AUGMENT_REGISTRY.keys())


def prepare_image(img: Image.Image) -> Image.Image:
    img = ImageOps.exif_transpose(img)
    img.load()
    return _to_rgb(img)


def apply_op(img: Image.Image, op_id: str) -> Image.Image:
    if op_id not in _AUGMENT_REGISTRY:
        raise ValueError(f"未知增强类型: {op_id}")
    _, fn = _AUGMENT_REGISTRY[op_id]
    out = fn(img.copy())
    if out.mode not in ("RGB", "RGBA"):
        out = out.convert("RGB")
    return out


def build_augment_zip(
    items: List[Tuple[str, bytes]],
    op_ids: List[str],
    output_format: str,
    quality: int = 90,
) -> bytes:
    """
    items: (原始文件名, 文件字节)
    op_ids: 已校验的增强 id 列表
    返回 zip 字节内容
    """
    fmt = (output_format or "png").lower()
    if fmt == "jpeg":
        fmt = "jpg"
    if fmt not in ("png", "jpg", "webp"):
        fmt = "png"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for orig_name, raw in items:
            base, _ext = os.path.splitext(orig_name)
            base = "".join(c for c in base if c.isalnum() or c in ("-", "_", "."))[:80] or "image"
            try:
                with Image.open(io.BytesIO(raw)) as im:
                    im = prepare_image(im)
                    for op_id in op_ids:
                        aug = apply_op(im, op_id)
                        out_io = io.BytesIO()
                        save_kw: Dict[str, Any] = {}
                        if fmt in ("jpg", "jpeg"):
                            if aug.mode == "RGBA":
                                bg = Image.new("RGB", aug.size, (255, 255, 255))
                                bg.paste(aug, mask=aug.split()[3])
                                aug = bg
                            save_kw["quality"] = quality
                            save_kw["optimize"] = True
                            ext = ".jpg"
                            save_fmt = "JPEG"
                        elif fmt == "webp":
                            save_kw["quality"] = quality
                            save_kw["method"] = 4
                            ext = ".webp"
                            save_fmt = "WEBP"
                        else:
                            ext = ".png"
                            save_fmt = "PNG"
                            save_kw["optimize"] = True
                        aug.save(out_io, format=save_fmt, **save_kw)
                        arcname = f"{base}_{op_id}{ext}"
                        zf.writestr(arcname, out_io.getvalue())
            except Exception as e:
                err_name = f"{base}_ERROR.txt"
                zf.writestr(err_name, f"{orig_name}: {e}\n".encode("utf-8"))

    return buf.getvalue()
