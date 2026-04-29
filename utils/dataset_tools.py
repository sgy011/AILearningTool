"""
数据集标注转换与划分（图片 + 标注）。

支持：
- YOLO txt <-> COCO json（bbox）
- VOC xml -> YOLO txt（bbox）

并提供按比例划分 train/val/test，输出为 zip。
"""

from __future__ import annotations

import io
import json
import logging
import os
import random
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

_IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}


@dataclass(frozen=True)
class DatasetItem:
    image_rel: str
    label_rel: Optional[str]


def _is_zip_safe_member(name: str) -> bool:
    n = (name or "").replace("\\", "/").strip()
    if not n or n.endswith("/"):
        return False
    if n.startswith("/") or re.match(r"^[a-zA-Z]:/", n):
        return False
    if "/../" in f"/{n}/" or n.startswith("../") or n.endswith("/.."):
        return False
    return True


def safe_unzip_bytes(
    zip_bytes: bytes,
    dest_dir: Path,
    *,
    max_files: int = 4000,
    max_uncompressed_bytes: int = 600 * 1024 * 1024,
) -> List[str]:
    """
    解压 zip 到 dest_dir，防 zip slip，限制文件数与解压大小。
    返回归档内成员名列表（文件）。
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    out: List[str] = []
    total = 0
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        if len(infos) > max_files:
            raise RuntimeError(f"压缩包文件过多（{len(infos)}），上限 {max_files}")
        for info in infos:
            name = info.filename
            if not _is_zip_safe_member(name):
                continue
            total += int(info.file_size or 0)
            if total > max_uncompressed_bytes:
                raise RuntimeError("压缩包解压后总大小过大，请减少文件数量或分批处理")
            target = (dest_dir / name).resolve()
            if not str(target).startswith(str(dest_dir.resolve())):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, open(target, "wb") as dst:
                dst.write(src.read())
            out.append(name.replace("\\", "/"))
    return out


def detect_annotation_format(root: Path) -> str:
    """auto 检测：yolo / coco / voc / unknown"""
    # COCO json
    for p in root.rglob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "images" in data and "annotations" in data:
                return "coco"
        except Exception:
            continue
    # VOC xml
    if any(root.rglob("*.xml")):
        return "voc"
    # YOLO txt: labels/*.txt 且非 classes.txt/names.txt
    txts = list(root.rglob("*.txt"))
    if txts:
        for p in txts:
            n = p.name.lower()
            if n in ("classes.txt", "names.txt"):
                continue
            if p.parent.name.lower() in ("labels", "label"):
                return "yolo"
        return "yolo"
    return "unknown"


def collect_items(root: Path, in_format: str = "auto") -> List[DatasetItem]:
    """收集图片与同名标注文件（支持 YOLO .txt / VOC .xml / COCO .json）。
    
    支持的目录结构：
    - images/ + labels/
    - images/ + annotations/
    - 任意目录下图片与同名标注
    - COCO 全局 json
    """
    items: List[DatasetItem] = []

    # 检测是否有 COCO 格式的全局 json
    coco_json_path: Optional[Path] = None
    if in_format in ("auto", "coco"):
        for p in root.rglob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
                if isinstance(data, dict) and "images" in data and "annotations" in data:
                    coco_json_path = p
                    break
            except Exception:
                continue

    # COCO 格式：从 json 中获取图片与标注的对应关系
    if coco_json_path is not None and in_format in ("auto", "coco"):
        coco_data = json.loads(coco_json_path.read_text(encoding="utf-8", errors="ignore"))
        coco_rel = coco_json_path.relative_to(root).as_posix()
        for img_info in coco_data.get("images", []):
            file_name = img_info.get("file_name", "")
            if not file_name:
                continue
            img_path = root / file_name
            if not img_path.is_file():
                for cand in (root / "images" / Path(file_name).name, root / Path(file_name).name):
                    if cand.is_file():
                        img_path = cand
                        file_name = cand.relative_to(root).as_posix()
                        break
            items.append(DatasetItem(image_rel=file_name, label_rel=coco_rel))
        if items:
            return sorted(items, key=lambda x: x.image_rel)

    # 确定标注文件扩展名
    label_exts = [".txt"]  # 默认 YOLO
    if in_format == "voc":
        label_exts = [".xml"]
    elif in_format == "auto":
        label_exts = [".txt", ".xml"]

    # 收集所有图片文件
    all_images: List[Path] = []
    for img in root.rglob("*"):
        if img.is_file() and img.suffix.lower() in _IMG_EXTS:
            all_images.append(img)

    if not all_images:
        raise RuntimeError("未在压缩包中找到图片文件")

    # 尝试找出标注目录：与图片目录同级的 labels/ 或 annotations/
    def _find_label(img_path: Path, stem: str) -> Optional[str]:
        """根据图片路径尝试多种方式匹配标注文件"""
        candidates = []

        # 1) 标准目录结构：images/xxx.jpg -> labels/xxx.txt 或 annotations/xxx.xml
        img_parent = img_path.parent
        if img_parent.name.lower() in ("images",):
            parent2 = img_parent.parent
            for ldir in ("labels", "label", "annotations", "annotation"):
                for ext in label_exts:
                    candidates.append(parent2 / ldir / (stem + ext))

        # 2) 同目录同名标注
        for ext in label_exts:
            candidates.append(img_path.with_suffix(ext))

        # 3) 兄弟目录 labels/ 或 annotations/
        for ldir in ("labels", "label", "annotations", "annotation"):
            for ext in label_exts:
                candidates.append(img_parent / ldir / (stem + ext))
            # 上一级目录下的标注目录
            candidates.append(img_parent.parent / ldir / (stem + ext))

        # 4) 全局搜索同名标注（兜底）
        # 这步开销大，只在上面都没匹配时使用

        for cand in candidates:
            if cand.is_file():
                return cand.relative_to(root).as_posix()

        # 兜底：在 root 下搜索同名标注文件
        for ext in label_exts:
            for match in root.rglob(f"{stem}{ext}"):
                if match.is_file():
                    return match.relative_to(root).as_posix()

        return None

    for img in all_images:
        rel = img.relative_to(root).as_posix()
        label = _find_label(img, img.stem)
        items.append(DatasetItem(image_rel=rel, label_rel=label))

    # 统计未匹配标注的数量，打日志
    no_label = sum(1 for it in items if it.label_rel is None)
    if no_label:
        logger.warning(f"共 {len(items)} 张图片，其中 {no_label} 张未找到对应标注文件")

    return sorted(items, key=lambda x: x.image_rel)


def split_items(
    items: List[DatasetItem],
    train: float,
    val: float,
    test: float,
    *,
    seed: int = 42,
) -> Dict[str, List[DatasetItem]]:
    s = float(train) + float(val) + float(test)
    if not (0.99 <= s <= 1.01):
        raise RuntimeError("train/val/test 比例之和需为 1")
    if train < 0 or val < 0 or test < 0:
        raise RuntimeError("比例不能为负数")
    r = random.Random(int(seed))
    arr = list(items)
    r.shuffle(arr)
    n = len(arr)
    n_train = int(round(n * float(train)))
    n_val = int(round(n * float(val)))
    if n_train + n_val > n:
        n_val = max(0, n - n_train)
    n_test = n - n_train - n_val
    if test == 0:
        n_test = 0
        n_val = n - n_train
    return {
        "train": arr[:n_train],
        "val": arr[n_train : n_train + n_val],
        "test": arr[n_train + n_val : n_train + n_val + n_test],
    }


def _read_yolo_classes(root: Path) -> Optional[List[str]]:
    for name in ("classes.txt", "names.txt"):
        p = root / name
        if p.is_file():
            lines = [ln.strip() for ln in p.read_text(encoding="utf-8", errors="ignore").splitlines()]
            lines = [x for x in lines if x]
            if lines:
                return lines
    # YOLOv5/8 data.yaml (very small parse)
    for p in root.rglob("*.yaml"):
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
            if "names:" not in text:
                continue
            # naive: names: [a,b] or names:\n  0: a
            m = re.search(r"names:\s*\\[(.+?)\\]", text, flags=re.S)
            if m:
                raw = m.group(1)
                parts = [x.strip().strip("'\"") for x in raw.split(",")]
                parts = [x for x in parts if x]
                if parts:
                    return parts
            # mapping
            names: Dict[int, str] = {}
            for ln in text.splitlines():
                mm = re.match(r"\\s*(\\d+)\\s*:\\s*(.+)\\s*$", ln)
                if mm:
                    names[int(mm.group(1))] = mm.group(2).strip().strip("'\"")
            if names:
                return [names[i] for i in sorted(names.keys())]
        except Exception:
            continue
    return None


def _yolo_txt_to_boxes(label_text: str) -> List[Tuple[int, float, float, float, float]]:
    out: List[Tuple[int, float, float, float, float]] = []
    for ln in (label_text or "").splitlines():
        t = ln.strip()
        if not t:
            continue
        parts = t.split()
        if len(parts) < 5:
            continue
        try:
            cls = int(float(parts[0]))
            x, y, w, h = map(float, parts[1:5])
        except Exception:
            continue
        out.append((cls, x, y, w, h))
    return out


def convert_yolo_to_coco(
    root: Path,
    items: List[DatasetItem],
    *,
    classes: Optional[List[str]] = None,
) -> Dict:
    """
    YOLO txt -> COCO json（bbox 为绝对像素，需读取图片尺寸）。
    仅支持 bbox（不处理 segmentation）。
    """
    from PIL import Image  # Pillow 已在 requirements

    names = classes or _read_yolo_classes(root) or []
    cat_ids = sorted({b[0] for it in items for b in _yolo_txt_to_boxes((root / (it.label_rel or "")).read_text(encoding="utf-8", errors="ignore") if it.label_rel else "")})
    if not names:
        # 兜底：生成 class_0..max
        max_id = max(cat_ids) if cat_ids else -1
        names = [f"class_{i}" for i in range(max_id + 1)]

    categories = [{"id": i + 1, "name": names[i] if i < len(names) else f"class_{i}"} for i in range(len(names))]
    images = []
    annotations = []
    ann_id = 1
    img_id_map: Dict[str, int] = {}
    for idx, it in enumerate(items, 1):
        img_path = root / it.image_rel
        with Image.open(img_path) as im:
            w, h = im.size
        img_id = idx
        img_id_map[it.image_rel] = img_id
        images.append({"id": img_id, "file_name": it.image_rel, "width": w, "height": h})
        if not it.label_rel:
            continue
        txt = (root / it.label_rel).read_text(encoding="utf-8", errors="ignore")
        for cls, x, y, bw, bh in _yolo_txt_to_boxes(txt):
            # normalized center -> coco xywh
            abs_w = bw * w
            abs_h = bh * h
            abs_x = (x * w) - abs_w / 2
            abs_y = (y * h) - abs_h / 2
            annotations.append(
                {
                    "id": ann_id,
                    "image_id": img_id,
                    "category_id": int(cls) + 1,
                    "bbox": [float(abs_x), float(abs_y), float(abs_w), float(abs_h)],
                    "area": float(abs_w * abs_h),
                    "iscrowd": 0,
                }
            )
            ann_id += 1
    return {"images": images, "annotations": annotations, "categories": categories}


def convert_voc_to_yolo(root: Path, *, out_labels_dir: Path, classes: Optional[List[str]] = None) -> List[str]:
    """
    VOC xml -> YOLO txt，输出到 out_labels_dir（相对 root 的 labels/）。
    返回 classes 列表（最终）。
    """
    from PIL import Image

    out_labels_dir.mkdir(parents=True, exist_ok=True)
    names = classes or []
    name_to_id: Dict[str, int] = {n: i for i, n in enumerate(names)}

    xml_files = list(root.rglob("*.xml"))
    if not xml_files:
        raise RuntimeError("未找到 VOC XML 标注文件")

    for xp in xml_files:
        try:
            tree = ET.parse(xp)
            ann = tree.getroot()
            filename = (ann.findtext("filename") or "").strip()
            # image path: try same folder, or images/filename
            img_path = None
            for cand in (
                xp.parent / filename,
                root / "images" / filename,
                root / filename,
            ):
                if filename and cand.is_file():
                    img_path = cand
                    break
            if img_path is None:
                # try by stem
                for ext in _IMG_EXTS:
                    cand = root / "images" / (xp.stem + ext)
                    if cand.is_file():
                        img_path = cand
                        break
            if img_path is None or not img_path.is_file():
                continue
            with Image.open(img_path) as im:
                w, h = im.size
            lines = []
            for obj in ann.findall("object"):
                name = (obj.findtext("name") or "").strip()
                if not name:
                    continue
                if name not in name_to_id:
                    name_to_id[name] = len(names)
                    names.append(name)
                cls = name_to_id[name]
                bnd = obj.find("bndbox")
                if bnd is None:
                    continue
                xmin = float(bnd.findtext("xmin") or 0)
                ymin = float(bnd.findtext("ymin") or 0)
                xmax = float(bnd.findtext("xmax") or 0)
                ymax = float(bnd.findtext("ymax") or 0)
                bw = max(0.0, xmax - xmin)
                bh = max(0.0, ymax - ymin)
                cx = xmin + bw / 2
                cy = ymin + bh / 2
                lines.append(f"{cls} {cx / w:.6f} {cy / h:.6f} {bw / w:.6f} {bh / h:.6f}")
            (out_labels_dir / f"{img_path.stem}.txt").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        except Exception:
            continue
    return names


def build_output_zip(
    root: Path,
    splits: Dict[str, List[DatasetItem]],
    *,
    out_format: str,
    in_format: str,
) -> bytes:
    """
    按 splits 输出 zip：
    - images/{split}/...
    - labels/{split}/...（yolo）或 annotations/{split}.json（coco）或 annotations/xml/{split}/...（voc, 暂仅占位）
    """
    out_format = (out_format or "yolo").strip().lower()
    in_format = (in_format or "").strip().lower()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # copy images
        for split, items in splits.items():
            for it in items:
                src = root / it.image_rel
                if not src.is_file():
                    continue
                arc = f"images/{split}/{Path(it.image_rel).name}"
                zf.write(src, arcname=arc)

        if out_format == "coco":
            # For now only support yolo->coco and coco passthrough not implemented
            if in_format != "yolo":
                raise RuntimeError("当前仅支持 YOLO -> COCO 的转换")
            for split, items in splits.items():
                coco = convert_yolo_to_coco(root, items)
                zf.writestr(f"annotations/{split}.json", json.dumps(coco, ensure_ascii=False, indent=2))
        elif out_format == "voc":
            # VOC xml 输出：直接拷贝同名 xml 到 annotations/xml/{split}/
            for split, items in splits.items():
                for it in items:
                    if not it.label_rel:
                        continue
                    src = root / it.label_rel
                    if not src.is_file() or not src.suffix.lower() == ".xml":
                        continue
                    arc = f"annotations/xml/{split}/{src.name}"
                    zf.write(src, arcname=arc)
                    # 也拷贝对应图片（已在上面 images/ 中拷贝）
        else:
            # yolo output
            # If input is voc: convert voc xml -> yolo txt
            if in_format == "voc":
                labels_dir = root / "_tmp_yolo_labels"
                names = convert_voc_to_yolo(root, out_labels_dir=labels_dir)
                zf.writestr("classes.txt", "\n".join(names) + ("\n" if names else ""))
                for split, items in splits.items():
                    for it in items:
                        src = labels_dir / f"{Path(it.image_rel).stem}.txt"
                        arc = f"labels/{split}/{Path(it.image_rel).stem}.txt"
                        if src.is_file():
                            zf.write(src, arcname=arc)
            else:
                names = _read_yolo_classes(root)
                if names:
                    zf.writestr("classes.txt", "\n".join(names) + "\n")
                for split, items in splits.items():
                    for it in items:
                        if not it.label_rel:
                            continue
                        src = root / it.label_rel
                        if not src.is_file():
                            continue
                        # 保留标注原始扩展名，或统一为 .txt
                        label_name = src.name if src.suffix.lower() == ".txt" else f"{Path(it.image_rel).stem}.txt"
                        arc = f"labels/{split}/{label_name}"
                        zf.write(src, arcname=arc)
    return buf.getvalue()

