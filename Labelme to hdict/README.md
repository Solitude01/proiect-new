# LabelMe 标注转 HALCON .hdict 格式工具

## 📖 简介

本工具用于将 **LabelMe** 标注的 JSON 文件转换为 **HALCON 深度学习工具** 使用的 `.hdict` 格式数据集，适用于 HALCON 目标检测（Object Detection）模型的训练。

## ✨ 功能特性

- ✅ 支持矩形框（rectangle）标注转换
- ✅ 支持多边形（polygon）自动转外接矩形
- ✅ 支持数据集自动划分（train/val/test）
- ✅ 自动补全图像尺寸信息
- ✅ 双模式输出：
  - **模式 A**：直接生成 `.hdict` 文件（需安装 `halconpy`）
  - **模式 B**：生成 JSON + HDevelop 脚本（无需 `halconpy`）
- ✅ 类别统计与数据集分析

## 📦 安装依赖

### 基础依赖（必需）
```bash
pip install pillow
```

### 可选依赖（用于直接生成 .hdict）
```bash
pip install halconpy
```
> **注意**：`halconpy` 需要 HALCON 运行时环境。如果未安装，工具会自动切换到 JSON 中间文件模式。

## 🚀 使用方法

### 基本用法

```bash
# 将 LabelMe JSON 目录转换为 .hdict 文件
python labelme_to_hdict.py --input ./annotations --output dataset.hdict

# 指定独立的图像目录
python labelme_to_hdict.py --input ./annotations --images ./images --output dataset.hdict
```

### 高级用法

```bash
# 自动划分训练集/验证集/测试集（8:1:1）
python labelme_to_hdict.py --input ./annotations --output dataset.hdict --split 0.8 0.1 0.1

# 只处理矩形框，忽略多边形标注
python labelme_to_hdict.py --input ./annotations --output dataset.hdict --types rectangle

# 无 halconpy 时，输出到目录（生成 JSON + HDevelop 脚本）
python labelme_to_hdict.py --input ./annotations --output ./output
```

### 参数说明

| 参数 | 说明 | 必需 |
|------|------|------|
| `--input, -i` | LabelMe JSON 标注文件目录 | ✅ |
| `--images` | 图像文件目录（默认与 `--input` 相同） | ❌ |
| `--output, -o` | 输出路径（`.hdict` 文件或输出目录） | ✅ |
| `--split` | 数据集划分比例，如 `0.8 0.1 0.1` | ❌ |
| `--types` | 接受的标注类型（默认：`rectangle polygon`） | ❌ |

## 📁 目录结构示例

```
dataset/
├── images/
│   ├── img001.jpg
│   ├── img002.jpg
│   └── ...
└── annotations/
    ├── img001.json
    ├── img002.json
    └── ...
```

## 🔄 转换流程

### 输入格式（LabelMe JSON）
```json
{
  "imagePath": "img001.jpg",
  "imageWidth": 1920,
  "imageHeight": 1080,
  "shapes": [
    {
      "label": "car",
      "shape_type": "rectangle",
      "points": [[100, 200], [300, 400]]
    },
    {
      "label": "person",
      "shape_type": "polygon",
      "points": [[150, 250], [200, 250], [200, 400], [150, 400]]
    }
  ]
}
```

### 输出格式（HALCON DLDataset）
```python
{
  'image_dir': '/path/to/images',
  'class_names': ['car', 'person'],
  'num_classes': 2,
  'samples': [
    {
      'image_file_name': 'img001.jpg',
      'image_width': 1920,
      'image_height': 1080,
      'bbox_row1': [200.0, 250.0],      # 左上角 y 坐标
      'bbox_col1': [100.0, 150.0],      # 左上角 x 坐标
      'bbox_row2': [400.0, 400.0],      # 右下角 y 坐标
      'bbox_col2': [300.0, 200.0],      # 右下角 x 坐标
      'bbox_label_id': [0, 1],
      'bbox_label_name': ['car', 'person'],
      'split': 'train'  # 可选
    }
  ]
}
```

## 🛠️ 工作原理

### 1. 标注类型处理
- **矩形框（rectangle）**：直接使用两个对角点 `[[x1,y1],[x2,y2]]`
- **多边形（polygon）**：自动计算外接矩形（取所有点的最小/最大 x,y 值）
- **其他类型**：可通过 `--types` 参数指定接受的标注类型

### 2. 坐标系转换
LabelMe 使用图像坐标系 `(x, y)`，其中 x 为水平方向，y 为垂直方向。  
HALCON 使用 `(row, col)` 坐标系，其中：
- `row = y`（行号，从上到下递增）
- `col = x`（列号，从左到右递增）

### 3. 输出模式
- **模式 A（推荐）**：安装 `halconpy` 后直接生成 `.hdict` 文件
- **模式 B**：未安装 `halconpy` 时生成：
  - `dataset_halcon.json`：标准 JSON 格式数据集
  - `load_and_save.hdev`：HDevelop 脚本，在 HALCON 中运行即可生成 `.hdict`

## 📊 输出示例

运行转换后，工具会输出统计信息：

```
=======================================================
  LabelMe → HALCON .hdict 转换器
=======================================================
[INFO] 找到 150 个 JSON 文件，开始解析...
[INFO] 有效样本：148，类别：['car', 'person', 'bicycle']
[INFO] 数据集划分：train=118  val=15  test=15
[INFO] 总框数：523

────────────────────────────────────────
  类别统计
────────────────────────────────────────
  [  0] car                   312 框
  [  1] person                156 框
  [  2] bicycle                55 框
────────────────────────────────────────

✅ 转换完成！
```

## ⚠️ 注意事项

1. **图像路径问题**：
   - LabelMe 的 `imagePath` 通常是相对于 JSON 文件的相对路径
   - 如果图像文件丢失，工具会尝试在同目录查找同名图像（.jpg/.png 等）

2. **图像尺寸**：
   - 如果 JSON 中缺少 `imageWidth`/`imageHeight`，工具会尝试从图像文件读取（需安装 Pillow）

3. **空标注文件**：
   - 没有任何标注框的 JSON 文件会被跳过（除非所有形状都被过滤）

4. **HALCON 版本**：
   - 生成的 `.hdict` 格式适用于 HALCON 13.0+ 的深度学习工具

## 🤝 贡献

如有问题或建议，欢迎提交 Issue 或 Pull Request。

## 📄 许可证

MIT License

---

**相关资源**：
- [LabelMe 官网](http://labelme.csail.mit.edu/)
- [HALCON 深度学习文档](https://www.mvtec.com/products/halcon/deep-learning)
