# 海康数据集下载器

从海康威视AI训练平台（ai.hikvision.com）批量下载训练数据集和标注数据的Chrome插件。

## 功能特点

- **自动拦截API响应** - 捕获平台返回的图片列表和标注数据
- **批量下载原图** - 下载平台图片到本地
- **导出标注数据** - 导出四边形标注为JSON格式
- **实时统计** - 显示数据集图片数量、标注数量等信息

## 安装方法

1. 打开Chrome浏览器，访问 `chrome://extensions/`
2. 开启右上角的"开发者模式"
3. 点击"加载已解压的扩展程序"
4. 选择 `web-annotator` 文件夹

## 使用方法

### 1. 打开数据集页面
在海康AI训练平台打开需要下载的数据集页面，例如：
```
https://ai.hikvision.com/.../datasets/{datasetId}/{versionId}/gallery
```

### 2. 等待数据捕获
- 插件会自动拦截页面API响应
- 浏览图片列表时，插件会捕获图片URL和标注信息
- 点击插件图标查看已捕获的数据统计

### 3. 导出数据
- **导出已捕获数据** - 下载标注JSON和图片（如勾选）
- **仅导出标注JSON** - 只下载标注数据文件

### 4. 翻页浏览
由于平台分页加载，需要翻页浏览所有图片以捕获完整数据集。

## 输出格式

### 原始JSON格式（默认）
```json
{
  "datasetId": "100089473",
  "versionId": "100239915",
  "exportTime": "2024-03-12T10:30:00.000Z",
  "source": "ai.hikvision.com",
  "totalImages": 160,
  "images": [
    {
      "id": "fec0dffee5e741929024290a8a1a01aa",
      "fileName": "10.153.100.241_19_20241029092159151.jpg",
      "cloudUrl": "https://...",
      "width": 2560,
      "height": 1440,
      "annotations": [
        {
          "labelName": "棕化板",
          "labelItemName": "正",
          "labelSetName": "状态",
          "tagCoord": "1586 366 1688 1183 766 1281 670 483",
          "validRegion": "0"
        }
      ]
    }
  ]
}
```

### 文件组织
```
hikvision_datasets/
├── images/
│   ├── 10.153.100.241_19_20241029092159151.jpg
│   └── ...
└── dataset_xxx_annotations_2024-03-12.json
```

## 注意事项

1. **OSS URL有效期** - 图片URL带有签名，有过期时间，捕获后需尽快下载
2. **分页加载** - 平台分页加载图片，需翻页才能获取全部数据
3. **下载位置** - 文件默认下载到浏览器的下载文件夹中的 `hikvision_datasets/` 目录

## 技术实现

### API拦截
插件通过重写 `fetch` 和 `XMLHttpRequest` 来拦截平台API响应：
- `/file/offset-list/query` - 图片列表
- `/files/targets/query` - 标注数据
- `/label-status/statistic` - 统计信息

### 权限需求
- `activeTab` - 访问当前标签页
- `storage` - 本地存储
- `downloads` - 文件下载
- `scripting` - 脚本注入
- `https://ai.hikvision.com/*` - 海康平台访问

## 文件结构

```
web-annotator/
├── manifest.json      # 扩展配置
├── popup.html         # 弹出窗口界面
├── popup.css          # 弹出窗口样式
├── popup.js           # 弹出窗口逻辑
├── content.js         # API拦截和数据捕获
├── background.js      # 后台服务脚本
├── icons/             # 图标文件夹
│   └── icon.svg       # 扩展图标
└── README.md          # 使用说明
```

## 更新日志

### v2.0.0
- 全新改版为海康数据集下载器
- 支持自动API拦截
- 支持批量下载图片和标注数据
- 支持实时数据统计

---

**原项目**: web-annotator (网页标注工具)
**当前版本**: 2.0.0
**适用平台**: 海康威视AI训练平台 (ai.hikvision.com)
