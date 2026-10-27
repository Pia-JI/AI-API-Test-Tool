"""SQLite 报告存储（data/ai_api_toolbox.db）。

只保存测试报告的结构化数据（JSON 文本），便于历史回溯与再次导出。
"""

import json
import os
import sqlite3
import threading
import time

from . import paths

DB_FILENAME = "ai_api_toolbox.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT NOT NULL,
    kind        TEXT NOT NULL,
    title       TEXT NOT NULL,
    api_url     TEXT,
    models      TEXT,
    summary     TEXT,
    payload     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reports_created ON reports(created_at DESC);
"""


class ReportStore(object):
    """报告表的最小化封装，线程安全（供后台线程保存报告）。"""

    def __init__(self, path=None):
        self.path = path or paths.path_in_data(DB_FILENAME)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.DatabaseError:
            pass
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    # ------------------------------------------------------------- 写入
    def save(self, report):
        """保存一份报告，返回自增 ID。"""
        created = report.get("created_at") or time.strftime("%Y-%m-%d %H:%M:%S")
        report.setdefault("created_at", created)
        models = report.get("models") or []
        if isinstance(models, str):
            models = [models]
        with self._lock:
            cursor = self._conn.execute(
                "INSERT INTO reports (created_at, kind, title, api_url, models, summary, payload)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    created,
                    report.get("kind", "unknown"),
                    report.get("title", "未命名报告"),
                    report.get("api_url", ""),
                    ", ".join(str(m) for m in models),
                    report.get("summary_text", ""),
                    json.dumps(report, ensure_ascii=False),
                ),
            )
            self._conn.commit()
            return cursor.lastrowid

    # ------------------------------------------------------------- 读取
    def list(self, limit=200):
        """返回报告摘要列表（不含完整 payload）。"""
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, created_at, kind, title, api_url, models, summary"
                " FROM reports ORDER BY id DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        return [dict(row) for row in rows]

    def get(self, report_id):
        """按 ID 读取完整报告。"""
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM reports WHERE id = ?", (int(report_id),)
            ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row["payload"])
        except ValueError:
            return None

    def delete(self, report_id):
        with self._lock:
            self._conn.execute("DELETE FROM reports WHERE id = ?", (int(report_id),))
            self._conn.commit()

    def clear(self):
        with self._lock:
            self._conn.execute("DELETE FROM reports")
            self._conn.commit()

    def count(self):
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS c FROM reports").fetchone()
        return int(row["c"]) if row else 0

    def close(self):
        with self._lock:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass

    def exists(self):
        return os.path.exists(self.path)
