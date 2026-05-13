#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
海康本地平台格式导出转换器
将 API 下载的扁平 JSON 标注转换为海康本地平台 calibInfo 嵌套格式

支持两种导出模式：
- simple:   简化模板格式（仅核心标注字段）
- official: 官方完整格式（与海康标注工具导出完全一致，含汇总 JSON）

输出结构（official 模式）：
{output_dir}/
├── image001.jpg
├── image002.jpg
└── Result/
    ├── image001.json              # 每图独立 calibInfo（MediaType=1）
    ├── image002.json
    └── {output_dir.name}.json     # 汇总 JSON（MediaType=3，合并全部图片）
"""

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ==== Constants =====================================
CEREAL_CLASS_VERSION = 22
FORMAT_VERSION = "1.0"

BASIC_CONFIG = {
    "cereal_class_version": CEREAL_CLASS_VERSION,
    "AlgorithmValue": 1,
    "EventValue": 1,
    "FrameStepLength": 10,
    "MinObjWidth": 10,
    "MinObjHeight": 10,
}

GENERAL_TAG = {
    "cereal_class_version": CEREAL_CLASS_VERSION,
    "SceneType": -1,
    "Weather": "",
}

MAIN_TAG_PAGE = {
    "cereal_class_version": CEREAL_CLASS_VERSION,
    "PropertyPageName": "",
    "PropertyPageDescript": "",
    "TagGroups": [],
    "IsDisplay": "",
}

FRAME_PROPERTY_PAGES = [{
    "PropertyPageName": "",
    "PropertyPageDescript": "",
    "TagGroups": [],
    "IsDisplay": "",
}]

VIDEO_CHAN_INFO = {
    "cereal_class_version": CEREAL_CLASS_VERSION,
    "Description": "",
}


@dataclass
class HikvisionExportResult:
    """Export result statistics"""
    images_count: int = 0
    annotations_count: int = 0
    skipped_count: int = 0
    no_target_count: int = 0
    format_type: str = "single"
    mode: str = "simple"
    output_dir: Optional[Path] = None
    result_dir: Optional[Path] = None
    summary_path: Optional[Path] = None


class HikvisionFormatConverter:
    """Convert downloaded dataset to Hikvision local calibInfo format."""

    def __init__(self, dataset_folder: Path, output_dir: Optional[Path] = None, mode: str = "simple"):
        self.dataset_folder = Path(dataset_folder)
        self.annotations_dir = self.dataset_folder / "annotations"
        self.images_dir = self.dataset_folder / "images"
        self.mode = mode

        if not self.annotations_dir.exists():
            raise FileNotFoundError(f"annotations/ not found: {self.annotations_dir}")
        if not self.images_dir.exists():
            raise FileNotFoundError(f"images/ not found: {self.images_dir}")

        if output_dir is None:
            suffix = "_hikvision_official" if mode == "official" else "_hikvision"
            self.output_dir = self.dataset_folder.parent / f"{self.dataset_folder.name}{suffix}"
        else:
            self.output_dir = Path(output_dir)
        self.result_dir = self.output_dir / "Result"

        self._skipped_count = 0
        self._next_id = 0

    # ================================================
    # Public entry
    # ================================================

    def convert(self) -> HikvisionExportResult:
        if self.mode == "official":
            return self._convert_official()
        else:
            return self._convert_simple()

    # ================================================
    # Official format (complete, matches platform export)
    # ================================================

    def _convert_official(self) -> HikvisionExportResult:
        anno_files = self._load_annotation_files()
        if not anno_files:
            raise ValueError(f"No JSON files in: {self.annotations_dir}")

        format_type = self._detect_format_type(anno_files)
        is_mixed = (format_type == "mixed")

        # 包含目标：有标注图片 + Result/ 汇总 JSON
        target_dir = self.output_dir / "包含目标"
        self.result_dir = target_dir / "Result"
        target_dir.mkdir(parents=True, exist_ok=True)
        self.result_dir.mkdir(parents=True, exist_ok=True)

        self._skipped_count = 0
        self._next_id = 0
        total_annotations = 0
        images_copied = 0
        no_target_count = 0
        no_target_dir = self.output_dir / "不包含目标"
        all_frame_infos = []
        last_target_id = 0

        for anno_path in anno_files:
            result = self._build_official_single(anno_path, is_mixed, last_target_id, target_dir)
            if result is None:
                # 无标注图片：复制到 不包含目标/ 目录
                try:
                    with open(anno_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    file_name = data.get("file_name", anno_path.stem + ".jpg")
                except Exception:
                    file_name = anno_path.stem + ".jpg"
                image_file = self._find_image(anno_path.stem, file_name)
                if image_file:
                    no_target_dir.mkdir(parents=True, exist_ok=True)
                    dst = no_target_dir / image_file.name
                    if not dst.exists():
                        try:
                            shutil.copy2(image_file, dst)
                        except Exception as e:
                            print(f"  Image copy failed: {image_file.name} ({e})")
                    no_target_count += 1
                continue

            calib_json, file_name, ann_count, max_target_id = result
            last_target_id = max_target_id

            # 有标注图片：复制到 包含目标/ 目录
            image_file = self._find_image(anno_path.stem, file_name)
            if image_file:
                dst = target_dir / image_file.name
                if not dst.exists():
                    try:
                        shutil.copy2(image_file, dst)
                    except Exception as e:
                        print(f"  Image copy failed: {image_file.name} ({e})")
                images_copied += 1

            frame_info = calib_json["calibInfo"]["VideoChannels"][0]["VideoInfo"]["mapFrameInfos"]
            all_frame_infos.extend(frame_info)
            total_annotations += ann_count

        # Generate summary JSON — only in 包含目标/Result/
        summary_path = None
        if all_frame_infos:
            summary_path = self._build_official_summary(all_frame_infos, anno_files, target_dir)

        return HikvisionExportResult(
            images_count=images_copied,
            annotations_count=total_annotations,
            skipped_count=self._skipped_count,
            no_target_count=no_target_count,
            format_type=format_type,
            mode="official",
            output_dir=self.output_dir,
            result_dir=self.result_dir,
            summary_path=summary_path,
        )

    def _build_official_single(self, anno_path: Path, is_mixed: bool, prev_target_id: int, target_dir: Path):
        try:
            with open(anno_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"  Skip invalid JSON: {anno_path.name} ({e})")
            return None

        file_name = data.get("file_name", "")
        raw_w = data.get("width") or data.get("imageWidth") or 0
        raw_h = data.get("height") or data.get("imageHeight") or 0
        try:
            width, height = int(raw_w), int(raw_h)
        except (TypeError, ValueError):
            width, height = 0, 0
        if width <= 0 or height <= 0:
            img = self._find_image(anno_path.stem, file_name)
            width, height = self._get_image_size(img, width, height)

        abs_path = str((target_dir / file_name).resolve()).replace("\\", "/")

        annotations = self._parse_annotations(data)
        map_targets = []
        target_id = prev_target_id + 1

        for ann in annotations:
            label = ann.get("label_name") or ann.get("label") or ""
            if not label:
                continue
            bbox_data = ann.get("bbox") or ann.get("bndbox", {})
            vertex = self._normalize_bbox_official(bbox_data, width, height)
            if vertex is None:
                continue
            pp = self._build_official_property_page(label, ann, is_mixed)
            map_targets.append({
                "key": target_id,
                "value": {
                    "cereal_class_version": CEREAL_CLASS_VERSION,
                    "TargetID": target_id,
                    "TargetType": 1,
                    "Vertex": vertex,
                    "PropertyPages": [pp],
                }
            })
            target_id += 1

        if not map_targets:
            return None

        max_target_id = target_id - 1
        media_info = {
            "cereal_class_version": CEREAL_CLASS_VERSION,
            "MediaType": 1,
            "FilePath": abs_path,
            "FileTime": 0,
            "FrameNum": 1,
            "FrameWidth": width,
            "FrameHeight": height,
            "breakFrameNum": "0",
        }
        calib = self._build_calib_skeleton(media_info, map_targets, "0", 1)
        return calib, file_name, len(map_targets), max_target_id

    def _build_official_summary(self, all_frame_infos, anno_files, target_dir: Path):
        first_fname = anno_files[0].stem + ".jpg"
        try:
            with open(anno_files[0], "r", encoding="utf-8") as f:
                first_fname = json.load(f).get("file_name", first_fname)
        except Exception:
            pass

        output_abs = str(target_dir.resolve()).replace("\\", "/")

        # Fix frame infos: per-image has FrameNum="0", MediaType=1;
        # summary needs FrameNum=<filename>, MediaType=3
        updated = []
        for i, fi in enumerate(all_frame_infos):
            if i < len(anno_files):
                try:
                    with open(anno_files[i], "r", encoding="utf-8") as f:
                        adata = json.load(f)
                    img_name = adata.get("file_name", anno_files[i].stem + ".jpg")
                except Exception:
                    img_name = anno_files[i].stem + ".jpg"
            else:
                img_name = f"img_{i}.jpg"
            fi["key"] = {
                "cereal_class_version": CEREAL_CLASS_VERSION,
                "FrameNum": img_name,
                "MediaType": 3,
            }
            fi["value"]["FrameNum"] = img_name
            updated.append(fi)

        media_info = {
            "cereal_class_version": CEREAL_CLASS_VERSION,
            "MediaType": 3,
            "FilePath": output_abs,
            "FileTime": 0,
            "FrameNum": len(anno_files),
            "FrameWidth": -1,
            "FrameHeight": -1,
            "breakFrameNum": first_fname,
        }
        calib = self._build_calib_skeleton(media_info, [], "", 3)
        calib["calibInfo"]["VideoChannels"][0]["VideoInfo"]["mapFrameInfos"] = updated

        summary_name = f"{self.output_dir.name}.json"
        summary_path = self.result_dir / summary_name
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(calib, f, ensure_ascii=False, indent="\t")
        return summary_path

    def _build_official_property_page(self, label, ann, is_mixed):
        pp_name = str(self._next_id); self._next_id += 1
        pp = {"PropertyPageName": pp_name, "PropertyPageDescript": label, "IsDisplay": "1"}
        if is_mixed:
            set_name = ann.get("label_set_name")
            item_name = ann.get("label_item_name")
            tg_name = str(self._next_id); self._next_id += 1
            tg = {"cereal_class_version": CEREAL_CLASS_VERSION, "TagGroupName": tg_name, "TagGroupDescript": "", "Tags": []}
            if set_name is not None and str(set_name).strip() != "":
                tag_name = str(self._next_id); self._next_id += 1
                tag = {"cereal_class_version": CEREAL_CLASS_VERSION, "TagName": tag_name, "TagDescript": str(set_name), "SubTags": []}
                if item_name is not None and str(item_name).strip() != "":
                    st_name = str(self._next_id); self._next_id += 1
                    st_value = str(self._next_id); self._next_id += 1
                    tag["SubTags"].append({
                        "cereal_class_version": CEREAL_CLASS_VERSION,
                        "SubTagName": st_name, "SubTagDescript": str(item_name), "SubTagValue": st_value,
                    })
                tg["Tags"].append(tag)
            pp["TagGroups"] = [tg]
        else:
            pp["TagGroups"] = []
        return pp

    def _build_calib_skeleton(self, media_info, map_targets, frame_num, media_type):
        fi = {
            "key": {"cereal_class_version": CEREAL_CLASS_VERSION, "FrameNum": frame_num, "MediaType": media_type},
            "value": {
                "cereal_class_version": CEREAL_CLASS_VERSION,
                "FrameNum": frame_num, "TimeStamp": 0, "OsdTime": 0,
                "mapRules": [], "mapTargets": map_targets, "mapFrameEvents": [],
                "PropertyPages": FRAME_PROPERTY_PAGES,
            }
        }
        return {
            "calibInfo": {
                "cereal_class_version": CEREAL_CLASS_VERSION,
                "FormatVersion": FORMAT_VERSION,
                "VideoChannels": [{
                    "cereal_class_version": CEREAL_CLASS_VERSION,
                    "VideoChannelID": 0,
                    "VideoChanInfo": dict(VIDEO_CHAN_INFO),
                    "MediaInfo": media_info,
                    "BasicConfig": dict(BASIC_CONFIG),
                    "GeneralTag": dict(GENERAL_TAG),
                    "VideoInfo": {
                        "cereal_class_version": CEREAL_CLASS_VERSION,
                        "MainTagPage": dict(MAIN_TAG_PAGE),
                        "mapFrameInfos": [fi],
                        "VideoChanEvents": [],
                    }
                }],
                "AudioChannels": [],
                "GlobalEvents": [],
            }
        }

    # ================================================
    # Simple template format (legacy, kept for compat)
    # ================================================

    def _convert_simple(self):
        anno_files = self._load_annotation_files()
        if not anno_files:
            raise ValueError(f"No JSON files in: {self.annotations_dir}")

        format_type = self._detect_format_type(anno_files)
        is_mixed = (format_type == "mixed")

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.result_dir.mkdir(parents=True, exist_ok=True)

        self._skipped_count = 0
        total_annotations = 0
        images_copied = 0

        for anno_path in anno_files:
            result = self._build_simple_single(anno_path, is_mixed)
            if result is None:
                self._skipped_count += 1
                continue
            calib, fname, ann_count = result
            json_path = self.result_dir / (anno_path.stem + ".json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(calib, f, ensure_ascii=False, indent="\t")
            img = self._find_image(anno_path.stem, fname)
            if img:
                dst = self.output_dir / img.name
                if not dst.exists():
                    try:
                        shutil.copy2(img, dst)
                    except Exception as e:
                        print(f"  Image copy failed: {img.name} ({e})")
                images_copied += 1
            total_annotations += ann_count

        return HikvisionExportResult(
            images_count=images_copied, annotations_count=total_annotations,
            skipped_count=self._skipped_count, format_type=format_type, mode="simple",
            output_dir=self.output_dir, result_dir=self.result_dir,
        )

    def _build_simple_single(self, anno_path, is_mixed):
        try:
            with open(anno_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"  Skip invalid JSON: {anno_path.name} ({e})")
            return None
        file_name = data.get("file_name", "")
        raw_w = data.get("width") or data.get("imageWidth") or 0
        raw_h = data.get("height") or data.get("imageHeight") or 0
        try:
            width, height = int(raw_w), int(raw_h)
        except (TypeError, ValueError):
            width, height = 0, 0
        if width <= 0 or height <= 0:
            img = self._find_image(anno_path.stem, file_name)
            width, height = self._get_image_size(img, width, height)

        anns = self._parse_annotations(data)
        map_targets = []
        for ann in anns:
            label = ann.get("label_name") or ann.get("label") or ""
            if not label:
                continue
            bbox_data = ann.get("bbox") or ann.get("bndbox", {})
            vertex = self._normalize_bbox(bbox_data, width, height)
            if vertex is None:
                continue
            pp = {"PropertyPageDescript": label}
            if is_mixed:
                sn = ann.get("label_set_name")
                it = ann.get("label_item_name")
                if sn is not None and str(sn).strip() != "":
                    sd = str(it) if it is not None else ""
                    pp["TagGroups"] = [{"Tags": [{"TagDescript": str(sn), "SubTags": [{"SubTagDescript": sd}]}]}]
                else:
                    pp["TagGroups"] = []
            map_targets.append({"value": {"TargetType": 1, "Vertex": vertex, "PropertyPages": [pp]}})
        if not map_targets:
            return None
        calib = {"calibInfo": {"VideoChannels": [{"VideoInfo": {"mapFrameInfos": [{"value": {"FrameNum": file_name, "mapTargets": map_targets}}]}}]}}
        return calib, file_name, len(map_targets)

    # ================================================
    # Shared utilities
    # ================================================

    def _load_annotation_files(self):
        return sorted(self.annotations_dir.glob("*.json"))

    def _find_image(self, stem, orig_name):
        if orig_name:
            c = self.images_dir / orig_name
            if c.exists():
                return c
        for ext in (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".tif"):
            c = self.images_dir / (stem + ext)
            if c.exists():
                return c
        return None

    def _get_image_size(self, img_path, w, h):
        if w > 0 and h > 0:
            return w, h
        if img_path and img_path.exists():
            try:
                from PIL import Image
                with Image.open(img_path) as im:
                    return im.size
            except Exception:
                pass
        return w, h

    def _detect_format_type(self, anno_files):
        for ap in anno_files:
            try:
                with open(ap, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue
            for ann in self._parse_annotations(data):
                sn = ann.get("label_set_name")
                if sn is not None and str(sn).strip() != "":
                    return "mixed"
        return "single"

    def _parse_annotations(self, data):
        anns = data.get("annotations") or data.get("annotation") or []
        if isinstance(anns, dict):
            anns = [anns]
        return anns if isinstance(anns, list) else []

    @staticmethod
    def _clamp(v, lo=0.0, hi=1.0):
        return max(lo, min(v, hi))

    def _normalize_bbox(self, bbox, width, height):
        if not isinstance(bbox, dict) or width <= 0 or height <= 0:
            return None
        xmin = bbox.get("xmin") or bbox.get("x1") or bbox.get("left")
        ymin = bbox.get("ymin") or bbox.get("y1") or bbox.get("top")
        xmax = bbox.get("xmax") or bbox.get("x2") or bbox.get("right")
        yv = bbox.get("ymax")
        ymax = yv if yv is not None else (bbox.get("y2") or bbox.get("bottom"))
        if xmin is None or ymin is None or xmax is None or ymax is None:
            return None
        try:
            xf, yf, xm, ym = float(xmin), float(ymin), float(xmax), float(ymax)
        except (TypeError, ValueError):
            return None
        if xf > xm:
            xf, xm = xm, xf
        if yf > ym:
            yf, ym = ym, yf
        if xm - xf <= 0 or ym - yf <= 0:
            return None
        w, h = float(width), float(height)
        return [
            {"fX": self._clamp(xf / w), "fY": self._clamp(yf / h)},
            {"fX": self._clamp(xm / w), "fY": self._clamp(yf / h)},
            {"fX": self._clamp(xm / w), "fY": self._clamp(ym / h)},
            {"fX": self._clamp(xf / w), "fY": self._clamp(ym / h)},
        ]

    def _normalize_bbox_official(self, bbox, width, height):
        vertex = self._normalize_bbox(bbox, width, height)
        if vertex is None:
            return None
        vertex[0]["cereal_class_version"] = CEREAL_CLASS_VERSION
        return vertex


# ====================================================
# Smoke test
# ====================================================

def test_hikvision_converter():
    base = Path(__file__).parent.parent / "标准格式" / "实际下载样例"
    all_pass = True

    for label, subdir in [
        ("单检测", "单检测实例数据/dataset_100160324_20260511_195446"),
        ("混合标注", "混合标注实例数据/dataset_100160323_20260511_195632"),
    ]:
        print("=" * 60)
        print(f"Smoke test (official): {label}")
        test_dir = base / subdir
        if not test_dir.exists():
            print(f"  SKIP: dir not found {test_dir}")
            continue
        converter = HikvisionFormatConverter(test_dir, mode="official")
        result = converter.convert()
        print(f"  Format: {result.format_type}, Images: {result.images_count}, Annotations: {result.annotations_count}")
        if result.no_target_count > 0:
            print(f"  No-target images: {result.no_target_count}")
        print(f"  Output: {result.output_dir}")
        if result.summary_path:
            print(f"  Summary: {result.summary_path}")
        exp = "mixed" if "混合" in label else "single"
        if result.format_type != exp:
            print(f"  FAIL: expected {exp}")
            all_pass = False
        else:
            print("  PASS")

    print("=" * 60)
    print("All smoke tests PASS" if all_pass else "Some tests FAILED")


if __name__ == "__main__":
    test_hikvision_converter()
