"""
LabelMe 标注  →  HALCON DLDataset .hdict 转换器
================================================
支持的标注类型：
  rectangle  矩形框（目标检测主要用途）
  polygon    多边形（自动转外接矩形框）

LabelMe JSON 结构：
  imagePath              图像文件名（相对路径）
  imageWidth / imageHeight
  shapes[]:
    label                类别名
    shape_type           "rectangle" / "polygon" / "circle" 等
    points               矩形：[[x1,y1],[x2,y2]]
                         多边形：[[x1,y1],[x2,y2],...]

输出模式（自动检测）：
  模式 A：安装了 halconpy → 直接生成 .hdict
  模式 B：未安装 halconpy → 输出 HALCON 兼容 JSON + HDevelop 脚本

依赖：
  pip install pillow     （可选，补全图像尺寸）
  pip install halconpy   （可选，直接写 hdict）

用法：
  python labelme_to_hdict.py --input ./annotations --output dataset.hdict
  python labelme_to_hdict.py --input ./annotations --output ./output --split 0.8 0.1 0.1
  python labelme_to_hdict.py --input ./annotations --output dataset.hdict --types rectangle polygon
"""

import argparse
import json
import os
import random
import sys
from pathlib import Path

try:
    from PIL import Image as PILImage
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


# ─────────────────────────────────────────────
#  1. 读取单个 LabelMe JSON
# ─────────────────────────────────────────────

def parse_labelme_json(json_path: str, accepted_types: list) -> dict | None:
    """
    解析一个 LabelMe JSON 文件，返回规范化的样本字典。
    返回 None 表示该文件无有效标注。
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    image_path = data.get('imagePath', '')
    width  = data.get('imageWidth',  0)
    height = data.get('imageHeight', 0)

    row1s, col1s, row2s, col2s = [], [], [], []
    label_names = []
    skipped = 0

    for shape in data.get('shapes', []):
        stype = shape.get('shape_type', '').lower()
        label = shape.get('label', 'unknown').strip()
        pts   = shape.get('points', [])

        if stype not in accepted_types:
            skipped += 1
            continue

        # ── 矩形：points = [[x1,y1],[x2,y2]]
        if stype == 'rectangle':
            if len(pts) < 2:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            x1, y1 = min(xs), min(ys)
            x2, y2 = max(xs), max(ys)

        # ── 多边形 / 折线：取外接矩形
        elif stype in ('polygon', 'linestrip', 'line'):
            if len(pts) < 2:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            x1, y1 = min(xs), min(ys)
            x2, y2 = max(xs), max(ys)

        else:
            skipped += 1
            continue

        bw = x2 - x1
        bh = y2 - y1
        if bw <= 0 or bh <= 0:
            continue

        # HALCON 坐标：row=y，col=x
        col1s.append(float(x1))
        row1s.append(float(y1))
        col2s.append(float(x2))
        row2s.append(float(y2))
        label_names.append(label)

    if skipped:
        pass  # 静默跳过不支持的类型

    return {
        '_image_path': image_path,    # 临时字段，后续处理
        'image_width':  int(width),
        'image_height': int(height),
        'bbox_row1':    row1s,
        'bbox_col1':    col1s,
        'bbox_row2':    row2s,
        'bbox_col2':    col2s,
        'bbox_label_name': label_names,
    }


# ─────────────────────────────────────────────
#  2. 扫描目录，收集所有标注
# ─────────────────────────────────────────────

def scan_labelme_dir(input_dir: str, accepted_types: list) -> tuple[list, list]:
    """
    递归扫描目录下所有 LabelMe JSON 文件。
    返回 (samples_raw, class_names_ordered)
    """
    input_path = Path(input_dir)
    json_files = sorted(input_path.rglob('*.json'))

    if not json_files:
        raise FileNotFoundError(f"目录中未找到任何 .json 文件：{input_dir}")

    print(f"[INFO] 找到 {len(json_files)} 个 JSON 文件，开始解析...")

    samples_raw = []
    all_labels  = set()
    bad_files   = 0

    for jf in json_files:
        try:
            sample = parse_labelme_json(str(jf), accepted_types)
        except Exception as e:
            print(f"  [WARN] 解析失败 {jf.name}：{e}")
            bad_files += 1
            continue

        if sample is None:
            continue

        # 推断图像文件所在目录
        # LabelMe imagePath 通常是相对于 JSON 所在目录的相对路径
        img_rel = sample.pop('_image_path')
        img_abs = jf.parent / img_rel
        if not img_abs.exists():
            # 降级：同目录同名查找
            for ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff']:
                candidate = jf.with_suffix(ext)
                if candidate.exists():
                    img_abs = candidate
                    break

        sample['image_file_name'] = img_rel          # 相对路径存入 hdict
        sample['_img_abs']        = str(img_abs)     # 临时，用于读尺寸

        # 若尺寸缺失，尝试从图像读取
        if (not sample['image_width'] or not sample['image_height']) and HAS_PIL:
            if img_abs.exists():
                try:
                    with PILImage.open(img_abs) as im:
                        sample['image_width'], sample['image_height'] = im.size
                except Exception:
                    pass

        all_labels.update(sample['bbox_label_name'])
        samples_raw.append(sample)

    if bad_files:
        print(f"  [WARN] {bad_files} 个文件解析失败")

    # 类别名排序（确保每次运行 id 一致）
    class_names = sorted(all_labels)
    print(f"[INFO] 有效样本：{len(samples_raw)}，类别：{class_names}")
    return samples_raw, class_names


# ─────────────────────────────────────────────
#  3. 组装 HALCON DLDataset 字典
# ─────────────────────────────────────────────

def build_dldataset(samples_raw: list, class_names: list,
                    image_dir: str, split_ratio: list | None) -> dict:
    """
    将原始样本列表组装成 HALCON DLDataset 标准格式。

    split_ratio: [train, val, test]，如 [0.8, 0.1, 0.1]
                 None 表示不添加 split 字段
    """
    label_to_id = {name: i for i, name in enumerate(class_names)}

    # 可选：shuffle + split
    if split_ratio:
        random.seed(42)
        random.shuffle(samples_raw)
        n = len(samples_raw)
        n_train = int(n * split_ratio[0])
        n_val   = int(n * split_ratio[1])
        splits  = (['train'] * n_train
                   + ['val']   * n_val
                   + ['test']  * (n - n_train - n_val))
    else:
        splits = [None] * len(samples_raw)

    samples_out = []
    total_boxes = 0

    for sample, split_tag in zip(samples_raw, splits):
        # 将 label_name 列表转换为 label_id 列表
        label_ids = [label_to_id[name] for name in sample['bbox_label_name']]
        total_boxes += len(label_ids)

        s = {
            'image_file_name': sample['image_file_name'],
            'image_width':     sample['image_width'],
            'image_height':    sample['image_height'],
            'bbox_row1':       sample['bbox_row1'],
            'bbox_col1':       sample['bbox_col1'],
            'bbox_row2':       sample['bbox_row2'],
            'bbox_col2':       sample['bbox_col2'],
            'bbox_label_id':   label_ids,
            'bbox_label_name': sample['bbox_label_name'],
        }
        if split_tag:
            s['split'] = split_tag

        samples_out.append(s)

    dataset = {
        'image_dir':   str(Path(image_dir).resolve()),
        'class_names': class_names,
        'num_classes': len(class_names),
        'samples':     samples_out,
    }

    if split_ratio:
        counts = {t: splits.count(t) for t in ['train', 'val', 'test']}
        print(f"[INFO] 数据集划分：train={counts['train']}  "
              f"val={counts['val']}  test={counts['test']}")

    print(f"[INFO] 总框数：{total_boxes}")
    return dataset


# ─────────────────────────────────────────────
#  4A. 模式 A：通过 halconpy 写 .hdict
# ─────────────────────────────────────────────

def write_hdict_via_halcon(dataset: dict, output_path: str):
    try:
        import halcon as ha
    except ImportError:
        raise RuntimeError("halconpy 未安装")

    def to_hdict(py_dict: dict) -> object:
        h = ha.create_dict()
        for k, v in py_dict.items():
            if isinstance(v, dict):
                ha.set_dict_object(to_hdict(v), h, k)
            elif isinstance(v, list):
                if v and isinstance(v[0], dict):
                    ha.set_dict_tuple([to_hdict(item) for item in v], h, k)
                else:
                    ha.set_dict_tuple(v if v else [], h, k)
            else:
                ha.set_dict_tuple(v, h, k)
        return h

    print("[INFO] 通过 halconpy 构建 HDict 并写出...")
    ha.write_dict(to_hdict(dataset), output_path, [], [])
    print(f"[MODE A] .hdict 已写出：{output_path}")


# ─────────────────────────────────────────────
#  4B. 模式 B：输出 JSON + HDevelop 脚本
# ─────────────────────────────────────────────

def write_fallback(dataset: dict, output_dir: str, hdict_name: str):
    os.makedirs(output_dir, exist_ok=True)
    json_path  = Path(output_dir) / 'dataset_halcon.json'
    hdev_path  = Path(output_dir) / 'load_and_save.hdev'
    hdict_path = Path(output_dir) / hdict_name

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)

    hdev_code = f"""\
* ============================================================
*  HALCON HDevelop Script — 由 labelme_to_hdict.py 自动生成
*  功能：加载转换结果 JSON → 保存为 .hdict
* ============================================================

JsonPath  := '{json_path.resolve().as_posix()}'
HdictPath := '{hdict_path.resolve().as_posix()}'

read_dict (JsonPath, [], [], DatasetDict)

get_dict_tuple (DatasetDict, 'samples', Samples)
tuple_length (Samples, NumSamples)
disp_message (3600, 'Loaded ' + NumSamples + ' samples', 'window', 12, 12, 'black', 'true')

write_dict (DatasetDict, HdictPath, [], [])
disp_message (3600, 'Saved: ' + HdictPath, 'window', 40, 12, 'forest green', 'true')
"""
    with open(hdev_path, 'w', encoding='utf-8') as f:
        f.write(hdev_code)

    print(f"[MODE B] HALCON JSON  → {json_path}")
    print(f"[MODE B] HDevelop脚本 → {hdev_path}")
    print()
    print("  ★ 在 HALCON HDevelop 中打开并运行 load_and_save.hdev")
    print(f"  ★ 将在同目录生成 {hdict_name}")


# ─────────────────────────────────────────────
#  5. 打印统计摘要
# ─────────────────────────────────────────────

def print_summary(dataset: dict):
    samples     = dataset['samples']
    class_names = dataset['class_names']
    box_counts  = {n: 0 for n in class_names}
    no_box      = 0

    for s in samples:
        if not s['bbox_label_name']:
            no_box += 1
        for name in s['bbox_label_name']:
            box_counts[name] = box_counts.get(name, 0) + 1

    print()
    print("─" * 40)
    print("  类别统计")
    print("─" * 40)
    for i, name in enumerate(class_names):
        print(f"  [{i:3d}] {name:<20s}  {box_counts.get(name, 0):>5d} 框")
    if no_box:
        print(f"\n  [注意] {no_box} 张图像无任何标注框（背景图）")
    print("─" * 40)


# ─────────────────────────────────────────────
#  6. 主入口
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='LabelMe 标注 JSON → HALCON DLDataset .hdict 转换器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 基本用法（JSON 所在目录即图像目录）
  python labelme_to_hdict.py --input ./annotations --output dataset.hdict

  # 指定独立的图像目录
  python labelme_to_hdict.py --input ./annotations --images ./images --output dataset.hdict

  # 自动划分 train/val/test（8:1:1）
  python labelme_to_hdict.py --input ./annotations --output dataset.hdict --split 0.8 0.1 0.1

  # 只处理矩形框，忽略多边形
  python labelme_to_hdict.py --input ./annotations --output dataset.hdict --types rectangle

  # 无 halconpy，输出中间文件到目录
  python labelme_to_hdict.py --input ./annotations --output ./output
        """
    )
    parser.add_argument('--input',  '-i', required=True,
                        help='LabelMe JSON 标注文件目录')
    parser.add_argument('--images', default=None,
                        help='图像文件目录（默认与 --input 相同）')
    parser.add_argument('--output', '-o', required=True,
                        help='输出路径：.hdict 文件（有 halconpy）或输出目录（无 halconpy）')
    parser.add_argument('--split',  nargs=3, type=float, metavar=('TRAIN', 'VAL', 'TEST'),
                        default=None,
                        help='数据集划分比例，如 0.8 0.1 0.1')
    parser.add_argument('--types',  nargs='+',
                        default=['rectangle', 'polygon'],
                        choices=['rectangle', 'polygon', 'linestrip', 'line'],
                        help='接受的标注类型（默认：rectangle polygon）')
    args = parser.parse_args()

    print("=" * 55)
    print("  LabelMe → HALCON .hdict 转换器")
    print("=" * 55)

    if not os.path.isdir(args.input):
        print(f"[ERROR] 输入目录不存在：{args.input}")
        sys.exit(1)

    images_dir = args.images or args.input

    # 验证 split 比例
    if args.split:
        total = sum(args.split)
        if abs(total - 1.0) > 1e-6:
            print(f"[ERROR] split 比例之和必须为 1.0，当前为 {total:.3f}")
            sys.exit(1)

    # Step 1: 扫描 LabelMe JSON
    samples_raw, class_names = scan_labelme_dir(args.input, args.types)
    if not samples_raw:
        print("[ERROR] 未解析到任何有效样本，请检查输入目录和标注类型。")
        sys.exit(1)

    # Step 2: 组装 DLDataset
    dataset = build_dldataset(samples_raw, class_names, images_dir, args.split)

    # Step 3: 打印统计
    print_summary(dataset)

    # Step 4: 输出
    output = args.output
    try:
        import halcon  # noqa
        has_halcon = True
    except ImportError:
        has_halcon = False

    if has_halcon and output.endswith('.hdict'):
        write_hdict_via_halcon(dataset, output)
    else:
        if has_halcon:
            print("[INFO] 输出路径未以 .hdict 结尾，切换到 JSON 中间文件模式")
        else:
            print("[INFO] 未检测到 halconpy，输出 JSON 中间文件 + HDevelop 脚本")
        out_dir    = output if not output.endswith('.hdict') else str(Path(output).parent)
        hdict_name = Path(output).name if output.endswith('.hdict') else 'dataset.hdict'
        write_fallback(dataset, out_dir, hdict_name)

    print("\n✅ 转换完成！")


if __name__ == '__main__':
    main()
