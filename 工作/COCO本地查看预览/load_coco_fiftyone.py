"""
FiftyOne COCO 标注数据集查看器
用法: python load_coco_fiftyone.py
依赖: pip install fiftyone
"""

import os
import sys
import fiftyone as fo


# ─── 配置区（按实际路径修改）────────────────────────────────────────────────

IMAGES_DIR = r"D:\本地素材\5-1-N10板件_物体检测N10板件_物体检测\aaa\dataset_100157988_20260501_115238\COCO\images"                   # 图片目录
ANNOTATIONS_FILE = r"D:\本地素材\5-1-N10板件_物体检测N10板件_物体检测\aaa\dataset_100157988_20260501_115238\COCO\annotations\instances.json"   # COCO JSON 标注文件
DATASET_NAME = "my_coco_dataset"           # 数据集名称（任意命名）

# 要加载的标注类型，按需开启：
#   "detections"   → 目标检测（bbox）
#   "segmentations" → 实例分割（mask/polygon）
#   "keypoints"    → 关键点
LABEL_TYPES = ["detections", "segmentations"]

# ──────────────────────────────────────────────────────────────────────────────


def check_paths():
    """检查路径是否存在"""
    ok = True
    if not os.path.isdir(IMAGES_DIR):
        print(f"[错误] 图片目录不存在: {IMAGES_DIR}")
        ok = False
    if not os.path.isfile(ANNOTATIONS_FILE):
        print(f"[错误] 标注文件不存在: {ANNOTATIONS_FILE}")
        ok = False
    return ok


def load_dataset():
    """加载或复用已存在的数据集"""

    # 若同名数据集已存在则直接复用，避免重复加载
    if DATASET_NAME in fo.list_datasets():
        print(f"[提示] 数据集 '{DATASET_NAME}' 已存在，直接加载...")
        return fo.load_dataset(DATASET_NAME)

    print(f"[加载] 正在从 COCO 标注文件加载数据集...")
    print(f"       图片目录: {IMAGES_DIR}")
    print(f"       标注文件: {ANNOTATIONS_FILE}")

    dataset = fo.Dataset.from_dir(
        dataset_type=fo.types.COCODetectionDataset,
        data_path=IMAGES_DIR,
        labels_path=ANNOTATIONS_FILE,
        label_types=LABEL_TYPES,
        name=DATASET_NAME,
        persistent=True,   # 持久化，下次可直接复用
    )

    return dataset


def print_summary(dataset):
    """打印数据集基本信息"""
    print("\n" + "=" * 50)
    print(f"  数据集名称 : {dataset.name}")
    print(f"  图片总数   : {len(dataset)}")

    # 统计各类别数量
    if dataset.has_field("ground_truth"):
        label_counts = dataset.count_values("ground_truth.detections.label")
        if label_counts:
            print(f"  类别分布   :")
            for label, count in sorted(label_counts.items(), key=lambda x: -x[1]):
                print(f"    {label:<20} {count} 个实例")

    print("=" * 50 + "\n")


def launch_viewer(dataset):
    """启动 FiftyOne 可视化界面"""
    print("[启动] 正在打开浏览器可视化界面...")
    print("       关闭脚本（Ctrl+C）即可退出\n")

    session = fo.launch_app(dataset)

    # 示例：只展示包含特定类别的图片（取消注释即可使用）
    # view = dataset.filter_labels("ground_truth", fo.ViewField("label") == "person")
    # session.view = view

    session.wait()   # 阻塞，保持界面打开


def main():
    if not check_paths():
        sys.exit(1)

    dataset = load_dataset()
    print_summary(dataset)
    launch_viewer(dataset)


if __name__ == "__main__":
    main()