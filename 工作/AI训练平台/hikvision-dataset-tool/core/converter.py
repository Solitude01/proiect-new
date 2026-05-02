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

        self._skipped_count = 0

        if not self.annotations_dir.exists():
            raise FileNotFoundError(f"annotations/目录不存在: {self.annotations_dir}")
        if not self.images_dir.exists():
            raise FileNotFoundError(f"images/目录不存在: {self.images_dir}")

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
        """获取图片尺寸，任一维度有效则直接用于对应维度，否则尝试PIL读取"""
        if w > 0 and h > 0:
            return w, h
        try:
            from PIL import Image
            with Image.open(image_path) as img:
                return img.size
        except ImportError:
            return w, h
        except Exception:
            return w, h

    def _parse_annotations(self, data: dict) -> list:
        """从标注JSON中提取annotations列表（统一处理dict/list两种形式）"""
        anns = data.get("annotations") or data.get("annotation") or []
        if isinstance(anns, dict):
            anns = [anns]
        return anns if isinstance(anns, list) else []

    def _build_coco(self, anno_files: List[Path]) -> dict:
        """两遍扫描构建COCO字典"""
        self._skipped_count = 0

        # 第一遍：收集所有唯一 label_name，按首次出现顺序分配 category_id（从1开始）
        category_map: Dict[str, int] = {}  # label_name -> category_id
        valid_files = []

        for anno_path in anno_files:
            try:
                with open(anno_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                print(f"  跳过无效JSON文件: {anno_path.name} ({e})")
                self._skipped_count += 1
                continue

            annotations = self._parse_annotations(data)
            valid_files.append((anno_path, data, annotations))

            for ann in annotations:
                label = ann.get("label_name") or ann.get("label") or ""
                if label and label not in category_map:
                    category_map[label] = len(category_map) + 1

        # 构建 categories 列表
        categories = [
            {"id": cat_id, "name": name}
            for name, cat_id in category_map.items()
        ]

        # 第二遍：构建 images 和 annotations
        images = []
        annotations_list = []
        ann_id = 1

        for image_id, (anno_path, data, anns) in enumerate(valid_files, start=1):
            # 查找对应图片文件：优先用标注中的 file_name，否则按 stem 匹配扩展名
            stem = anno_path.stem
            image_file = None
            orig_file_name = data.get("file_name", "")
            if orig_file_name:
                candidate = self.images_dir / orig_file_name
                if candidate.exists():
                    image_file = candidate
            if image_file is None:
                for ext in (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".tif"):
                    candidate = self.images_dir / (stem + ext)
                    if candidate.exists():
                        image_file = candidate
                        break

            # 获取宽高
            raw_w_val = data.get("width")
            raw_h_val = data.get("height")
            if raw_w_val is None:
                raw_w_val = data.get("imageWidth", 0)
            if raw_h_val is None:
                raw_h_val = data.get("imageHeight", 0)
            try:
                raw_w = int(raw_w_val)
                raw_h = int(raw_h_val)
            except (TypeError, ValueError):
                raw_w, raw_h = 0, 0

            if image_file:
                img_w, img_h = self._get_image_size(image_file, raw_w, raw_h)
                file_name = image_file.name
            else:
                img_w, img_h = raw_w, raw_h
                file_name = orig_file_name or (stem + ".jpg")

            images.append({
                "id": image_id,
                "file_name": file_name,
                "width": img_w,
                "height": img_h
            })

            for ann in anns:
                label = ann.get("label_name") or ann.get("label") or ""
                if not label:
                    self._skipped_count += 1
                    continue

                # 解析bbox：支持 dict {xmin,ymin,xmax,ymax} 和 list [xmin,ymin,xmax,ymax] 两种格式
                bbox_data = ann.get("bbox")
                if bbox_data is None:
                    bbox_data = ann.get("bndbox", {})

                if isinstance(bbox_data, dict):
                    v = bbox_data.get("xmin")
                    xmin = float(v) if v is not None else float(bbox_data.get("x1") or bbox_data.get("left") or 0)
                    v = bbox_data.get("ymin")
                    ymin = float(v) if v is not None else float(bbox_data.get("y1") or bbox_data.get("top") or 0)
                    v = bbox_data.get("xmax")
                    xmax = float(v) if v is not None else float(bbox_data.get("x2") or bbox_data.get("right") or 0)
                    v = bbox_data.get("ymax")
                    ymax = float(v) if v is not None else float(bbox_data.get("y2") or bbox_data.get("bottom") or 0)
                elif isinstance(bbox_data, list) and len(bbox_data) == 4:
                    # 始终按 [xmin, ymin, w, h] 处理（COCO 标准列表格式）
                    xmin, ymin = float(bbox_data[0]), float(bbox_data[1])
                    xmax = xmin + float(bbox_data[2])
                    ymax = ymin + float(bbox_data[3])
                else:
                    self._skipped_count += 1
                    continue

                # 裁剪到图片尺寸范围内
                if img_w > 0:
                    xmin = max(0.0, min(xmin, img_w))
                    xmax = max(0.0, min(xmax, img_w))
                if img_h > 0:
                    ymin = max(0.0, min(ymin, img_h))
                    ymax = max(0.0, min(ymax, img_h))

                bw = xmax - xmin
                bh = ymax - ymin
                if bw <= 0 or bh <= 0:
                    self._skipped_count += 1
                    continue

                category_id = category_map.get(label, 0)
                area = int(bw * bh)

                annotations_list.append({
                    "id": ann_id,
                    "image_id": image_id,
                    "category_id": category_id,
                    "bbox": [xmin, ymin, bw, bh],
                    "area": area,
                    "segmentation": [[xmin, ymin, xmax, ymin, xmax, ymax, xmin, ymax]],
                    "iscrowd": 0
                })
                ann_id += 1

        from datetime import datetime

        return {
            "info": {
                "description": "Converted from Hikvision dataset",
                "date_created": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            },
            "licenses": [],
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
                except Exception as e:
                    print(f"  图片复制失败: {file_name} ({e})")

        # 写出 instances.json
        with open(self.output_path, 'w', encoding='utf-8') as f:
            json.dump(coco, f, ensure_ascii=False, indent=2)
        return self.output_path
