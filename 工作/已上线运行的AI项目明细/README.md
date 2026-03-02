# AI 项目成果展示系统

智能制造推进部 2025 年度 AI 项目成果展示平台

## 功能概述

- **管理页面** (`index.html`) - 数据表格展示、筛选、打印
- **业务展示** (`business.html`) - 卡片式项目展示
- **星球视图** (`planet.html`) - 3D 星球可视化，项目作为星球上的节点

## 技术栈

| 组件 | 技术 |
|------|------|
| 前端 | HTML5 + CSS3 + JavaScript |
| 3D渲染 | Three.js |
| 后端 | Python FastAPI |
| 数据库 | MySQL 8.0 |
| 部署 | Docker + Nginx |

## 目录结构

```
├── index.html          # 管理页面
├── business.html       # 业务展示页面
├── planet.html         # 3D 星球视图
├── styles.css          # 公共样式
├── shared.js           # 公共 JS (API 调用等)
├── app.js              # 管理页面逻辑
├── business.js         # 业务展示逻辑
├── planet.js           # 3D 星球逻辑
├── three.min.js        # Three.js 库
├── import_excel.py     # Excel 数据导入脚本
├── backend/            # 后端代码
│   ├── main.py         # FastAPI 主程序
│   ├── models.py       # 数据库模型
│   └── database.py     # 数据库连接
└── images/             # 项目图片
```

## 部署架构

```
┌─────────────────────────────────────────┐
│             Nginx (8080)                │
│  ┌────────────┬──────────┬───────────┐  │
│  │ 静态文件   │  /api/*  │ /uploads/ │  │
│  │ HTML/JS   │ 反向代理  │   图片    │  │
│  └────────────┴────┬─────┴───────────┘  │
│                    │                     │
│              ┌─────▼─────┐              │
│              │  FastAPI  │              │
│              │  (8089)   │              │
│              └─────┬─────┘              │
│                    │                     │
│              ┌─────▼─────┐              │
│              │   MySQL   │              │
│              │  (3306)   │              │
│              └───────────┘              │
└─────────────────────────────────────────┘
```

## 数据导入

### 使用 Python 脚本导入 Excel

```bash
# 进入项目目录
cd D:\proiect\工作\已上线运行的AI项目明细

# 执行导入
python import_excel.py CCC.xlsx
```

### Excel 列格式要求

| 列序 | 字段 |
|------|------|
| A | 项目名称 |
| B | 工厂名称 |
| C | 项目目标 |
| D | 收益说明 |
| E | 折算成金额收益(万元) |
| F | 结余时间(小时/月) |
| G | 申请人 |
| H | 创建时间 |
| I | 提交时间 |
| J | 开发人 |
| K | 审核时间 |
| L | 上线时间 |
| M | 项目取消时间 |
| N | 项目状态 |
| O | 报警图例 |

### 图片处理

图片通过 VBA 宏按行号导出到 `AAA/` 文件夹，格式为 `{行号}.png`。

导入后需手动复制到 NAS:
```bash
cp images/* /vol1/1000/webdemo/uploads/images/
```

## 数据库配置

```python
DB_CONFIG = {
    'host': '10.30.43.199',
    'port': 3306,
    'user': 'aiprojects',
    'password': '********',
    'database': 'ai_projects',
    'charset': 'utf8mb4',
}
```

## API 接口

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | /api/projects | 获取项目列表 |
| GET | /api/projects/{id} | 获取项目详情 |
| GET | /api/stats | 获取统计数据 |
| GET | /api/filters | 获取筛选选项 |
| GET | /api/health | 健康检查 |

## 星球视图操作

| 操作 | 说明 |
|------|------|
| 拖拽 | 旋转星球 |
| 滚轮 | 放大/缩小 |
| 悬停节点 | 显示项目信息 |
| 点击节点 | 打开项目详情 |

## 访问地址

- 内网: `http://10.30.43.199:8080/ai-projects/`
