# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI项目成果展示系统 - A project showcase platform for the Intelligent Manufacturing Department (智能制造推进部). Displays AI projects with three different visualization views: management table, business cards, and 3D planet view.

## Tech Stack

- **Frontend**: Vanilla HTML5/CSS3/JavaScript (no build system)
- **3D Rendering**: Three.js for planet view, CSS 3D transforms + Canvas 2D for Saturn ring effect
- **Backend**: Python FastAPI with SQLAlchemy ORM
- **Database**: MySQL 8.0 (charset: utf8mb4)
- **Deployment**: Docker + Nginx (port 8080), FastAPI (port 8089)

## Architecture

```
Frontend (Static Files)          Backend (FastAPI)
├── index.html (管理页面)         └── backend/
├── business.html (业务展示)          ├── main.py (API endpoints)
├── planet.html (3D星球视图)          ├── models.py (SQLAlchemy Project model)
│                                     └── database.py (MySQL connection)
├── shared.js (API client, shared utilities)
├── app.js (管理页面 logic)
├── business.js (业务展示 logic)
├── planet.js (Saturn ring 3D animation)
└── styles.css (all pages share this)
```

### Data Flow

1. Frontend calls `/api/projects` via `shared.js:getProjectData()`
2. Backend returns snake_case fields from MySQL
3. Frontend normalizes to camelCase via `shared.js:normalizeProject()`
4. All pages use `shared.js` for common functions: `getStatusClass()`, `getStatusColor()`, `calculateProjectStats()`, `renderDetailCardContent()`

## Commands

### Data Import (Preferred Method)

```bash
# Import Excel data to MySQL (drops and recreates table)
python import_excel.py CCC.xlsx
```

This script:
- Extracts embedded images from Excel using openpyxl
- Saves images to `images/` folder locally
- Creates `projects` table with utf8mb4 charset
- Images must be manually copied to NAS: `/vol1/1000/webdemo/uploads/images/`

### Run Backend Locally

```bash
cd backend
pip install fastapi uvicorn sqlalchemy pymysql pandas openpyxl
uvicorn main:app --host 0.0.0.0 --port 8089 --reload
```

### Database Connection

Production MySQL is at `10.30.43.199:3306`, database `ai_projects`. The import script connects directly; the Docker backend uses container name `mysql-aiprojects`.

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/projects` | List projects (supports `?factory=&status=` filters) |
| GET | `/api/projects/{id}` | Single project detail |
| GET | `/api/stats` | Aggregate statistics |
| GET | `/api/filters` | Available factory/status options |
| GET | `/api/health` | Health check |
| POST | `/api/projects/upload` | Upload Excel file (clears existing data) |

## Key Code Patterns

### Status Classification

Status strings are matched case-insensitively in `shared.js`:
- **online**: contains "上线", "已完成", "运行中"
- **progress**: contains "进行中", "开发中", "审核中"
- **cancelled**: contains "取消", "终止", "暂停"
- **pending**: contains "待", "申请"

### Planet View (planet.js)

Uses CSS 3D transforms for Saturn ring effect with Canvas 2D particle system. Key parameters:
- `RING_INNER_RATIO = 0.22`, `RING_OUTER_RATIO = 0.46` - ring band dimensions
- Simulates Cassini Division gap at ~55% of ring width
- Kepler-like orbital speeds (outer nodes move slower)

### Theme Support

`business.js` includes `ThemeManager` for light/dark theme toggle. Theme persists in localStorage key `ai-project-theme`.

## Excel Column Format (for import_excel.py)

| Column | Field |
|--------|-------|
| A | project_name |
| B | factory_name |
| C | project_goal |
| D | benefit_desc |
| E | money_benefit (万元) |
| F | time_saved (小时/月) |
| G | applicant |
| H | create_time |
| I | submit_time |
| J | developer |
| K | audit_time |
| L | online_time |
| M | cancel_time |
| N | status |
| O | (images extracted by row position) |
