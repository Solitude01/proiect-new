import json
import sqlite3
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

DB_PATH = "/data/alarms.db"

app = FastAPI(title="Alarm Callback Service")
templates = Jinja2Templates(directory="templates")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS alarms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alarm_id TEXT UNIQUE,
            device_name TEXT,
            level INTEGER,
            status TEXT,
            image_url TEXT,
            video_url TEXT,
            created_at TEXT,
            updated_at TEXT,
            raw_json TEXT
        )
        """
    )
    conn.commit()
    conn.close()


@app.on_event("startup")
def startup():
    init_db()


@app.api_route("/alarm/callback", methods=["POST", "PUT"])
async def alarm_callback(request: Request):
    data = await request.json()
    now = datetime.now().isoformat()

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    if request.method == "POST":
        c.execute(
            """
            INSERT OR IGNORE INTO alarms
            (alarm_id, device_name, level, status, image_url, video_url, created_at, updated_at, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("id"),
                data.get("device", {}).get("name"),
                data.get("level"),
                data.get("alarmStatus"),
                data.get("imageURL"),
                data.get("videoURL"),
                data.get("createdAt"),
                now,
                json.dumps(data, ensure_ascii=False),
            ),
        )

    if request.method == "PUT":
        for alarm_id in data.get("ids", []):
            c.execute(
                """
                UPDATE alarms
                SET status = ?, updated_at = ?, raw_json = ?
                WHERE alarm_id = ?
                """,
                (
                    data.get("alarmStatus"),
                    now,
                    json.dumps(data, ensure_ascii=False),
                    alarm_id,
                ),
            )

    conn.commit()
    conn.close()
    return {"code": 0}


@app.get("/ui", response_class=HTMLResponse)
def ui(request: Request):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute(
        """
        SELECT * FROM alarms
        ORDER BY updated_at DESC
        LIMIT 10
        """
    )
    rows = c.fetchall()
    conn.close()

    return templates.TemplateResponse(
        "index.html", {"request": request, "alarms": rows}
    )


@app.get("/alarm/{alarm_id}", response_class=HTMLResponse)
def alarm_detail(request: Request, alarm_id: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("SELECT * FROM alarms WHERE alarm_id = ?", (alarm_id,))
    row = c.fetchone()
    conn.close()

    return templates.TemplateResponse(
        "detail.html",
        {
            "request": request,
            "alarm": row,
            "json": json.dumps(
                json.loads(row["raw_json"]), indent=2, ensure_ascii=False
            )
            if row
            else "",
        },
    )
