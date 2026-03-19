#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
海康威视数据集 → COCO V1.0 格式转换器
只转换检测标注（bbox+label），丢弃所有分类属性（TagGroups）

输出目录结构:
dataset_xxx_20250101_120000/
├── images/                    # 原始图片（不动）
├── annotations/               # 原始标注（不动）
└── COCO/                      # 新建的COCO标准格式
    ├── annotations/
    │   └── instances.json     # 转换后的COCO标注
    └── images/                # 原始图片的副本
        ├── image001.jpg
        └── image002.jpg
"""

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple, Optional


@dataclass
class ConversionResult:
    images_count: int = 0
    annotations_count: int = 0
    categories_count: int = 0
    skipped_count: int = 0
    output_path: Optional[Path] = None
    coco_dir: Optional[Path] = None  # COCO根目录，方便调用方展示


class COCOConverter:
    """将海康威视JSON标注转换为COCO格式"""

    def __init__(self, dataset_folder: Path):
        self.dataset_folder = Path(dataset_folder)
        self.annotations_dir = self.dataset_folder / "annotations"
        self.images_dir = self.dataset_folder / "images"

        # COCO标准输出目录结构
        self.coco_dir = self.dataset_folder / "COCO"
        self.coco_images_dir = self.coco_dir / "images"
        self.coco_anno_dir = self.coco_dir / "annotations"
        self.output_path = self.coco_anno_dir / "instances.json"

        if not self.annotations_dir.exists():
            raise FileNotFoundError(f"annotations/目录不存在: {self.annotations_dir}")

    def convert(self) -> ConversionResult:
        """执行转换，返回统计结果"""
        anno_files = self._load_annotation_files()
        if not anno_files:
            raise ValueError(f"annotations/目录中没有JSON文件: {self.annotations_dir}")

        coco = self._build_coco(anno_files)
        output_path = self._write_output(coco)

        result = ConversionResult(
            images_count=len(coco["images"]),
            annotations_count=len(coco["annotations"]),
            categories_count=len(coco["categories"]),
            skipped_count=self._skipped_count,
            output_path=output_path,
            coco_dir=self.coco_dir
        )
        return result

    def _load_annotation_files(self) -> List[Path]:
        """获取所有JSON标注文件"""
        return sorted(self.annotations_dir.glob("*.json"))

    def _get_image_size(self, image_path: Path, w: int, h: int) -> Tuple[int, int]:
        """获取图片尺寸，标注中有值则直接用，否则尝试PIL读取"""
        if w > 0 and h > 0:
            return w, h
        try:
            from PIL import Image
            with Image.open(image_path) as img:
                return img.size  # (width, height)
        except Exception:
            return 0, 0

    def _build_coco(self, anno_files: List[Path]) -> dict:
        """两遍扫描构建COCO字典"""
        self._skipped_count = 0

        # 第一遍：收集所有唯一 label_name，按首次出现顺序分配 category_id（从0开始）
        category_map: Dict[str, int] = {}  # label_name -> category_id
        valid_files = []

        for anno_path in anno_files:
            try:
                with open(anno_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._skipped_count += 1
                continue

            valid_files.append((anno_path, data))

            annotations = data.get("annotations") or data.get("annotation") or []
            if isinstance(annotations, dict):
                annotations = [annotations]

            for ann in annotations:
                label = ann.get("label_name") or ann.get("label") or ""
                if label and label not in category_map:
                    category_map[label] = len(category_map)

        # 构建 categories 列表
        categories = [
            {"id": cat_id, "name": name}
            for name, cat_id in sorted(category_map.items(), key=lambda x: x[1])
        ]

        # 第二遍：构建 images 和 annotations
        images = []
        annotations_list = []
        ann_id = 1

        for image_id, (anno_path, data) in enumerate(valid_files, start=1):
            # 查找对应图片文件
            stem = anno_path.stem
            image_file = None
            for ext in (".jpg", ".jpeg", ".png", ".bmp", ".webp"):
                candidate = self.images_dir / (stem + ext)
                if candidate.exists():
                    image_file = candidate
                    break

            # 获取宽高
            raw_w = data.get("width") or data.get("imageWidth") or 0
            raw_h = data.get("height") or data.get("imageHeight") or 0
            try:
                raw_w = int(raw_w)
                raw_h = int(raw_h)
            except (TypeError, ValueError):
                raw_w, raw_h = 0, 0

            if image_file:
                img_w, img_h = self._get_image_size(image_file, raw_w, raw_h)
                file_name = image_file.name
            else:
                img_w, img_h = raw_w, raw_h
                file_name = stem + ".jpg"

            images.append({
                "id": image_id,
                "file_name": file_name,
                "width": img_w,
                "height": img_h
            })

            # 解析标注
            anns = data.get("annotations") or data.get("annotation") or []
            if isinstance(anns, dict):
                anns = [anns]

            for ann in anns:
                label = ann.get("label_name") or ann.get("label") or ""
                if not label:
                    self._skipped_count += 1
                    continue

                # 支持两种bbox格式
                bbox_data = ann.get("bbox") or ann.get("bndbox") or {}
                if isinstance(bbox_data, list) and len(bbox_data) == 4:
                    # [xmin, ymin, xmax, ymax] 或 [x, y, w, h]
                    xmin, ymin = float(bbox_data[0]), float(bbox_data[1])
                    if bbox_data[2] > xmin and bbox_data[3] > ymin:
                        # 已经是 xmax, ymax
                        xmax, ymax = float(bbox_data[2]), float(bbox_data[3])
                    else:
                        xmax = xmin + float(bbox_data[2])
                        ymax = ymin + float(bbox_data[3])
                elif isinstance(bbox_data, dict):
                    xmin = float(bbox_data.get("xmin") or bbox_data.get("x1") or bbox_data.get("left") or 0)
                    ymin = float(bbox_data.get("ymin") or bbox_data.get("y1") or bbox_data.get("top") or 0)
                    xmax = float(bbox_data.get("xmax") or bbox_data.get("x2") or bbox_data.get("right") or 0)
                    ymax = float(bbox_data.get("ymax") or bbox_data.get("y2") or bbox_data.get("bottom") or 0)
                else:
                    self._skipped_count += 1
                    continue

                bw = xmax - xmin
                bh = ymax - ymin
                if bw <= 0 or bh <= 0:
                    self._skipped_count += 1
                    continue

                category_id = category_map.get(label, 0)
                area = bw * bh
                segmentation = [[xmin, ymin, xmax, ymin, xmax, ymax, xmin, ymax]]

                annotations_list.append({
                    "id": ann_id,
                    "image_id": image_id,
                    "category_id": category_id,
                    "bbox": [xmin, ymin, bw, bh],
                    "area": area,
                    "segmentation": segmentation,
                    "iscrowd": 0
                })
                ann_id += 1

        return {
            "images": images,
            "annotations": annotations_list,
            "categories": categories
        }

    def _write_output(self, coco: dict) -> Path:
        """创建COCO目录结构，拷贝图片，写出JSON文件"""
        # 创建目录
        self.coco_anno_dir.mkdir(parents=True, exist_ok=True)
        self.coco_images_dir.mkdir(parents=True, exist_ok=True)

        # 拷贝图片到 COCO/images/（跳过已存在）
        for img_info in coco.get("images", []):
            file_name = img_info.get("file_name", "")
            if not file_name:
                continue
            src = self.images_dir / file_name
            dst = self.coco_images_dir / file_name
            if src.exists() and not dst.exists():
                try:
                    shutil.copy2(src, dst)
                except Exception:
                    pass  # 忽略拷贝失败

        # 写出 instances.json
        with open(self.output_path, 'w', encoding='utf-8') as f:
            json.dump(coco, f, ensure_ascii=False, indent=2)
        return self.output_path
