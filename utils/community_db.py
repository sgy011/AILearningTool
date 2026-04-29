"""AI 社区数据库：帖子、回复、项目附件"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INSTANCE_DIR = PROJECT_ROOT / "instance"
COMMUNITY_DB = INSTANCE_DIR / "community.db"

CATEGORIES = [
    "机器学习",
    "深度学习",
    "自然语言处理",
    "计算机视觉",
    "强化学习",
    "数据挖掘",
    "知识图谱",
    "语音识别",
    "推荐系统",
    "大模型与AIGC",
    "其他",
]


def _conn() -> sqlite3.Connection:
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(COMMUNITY_DB))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_community_db() -> None:
    with _conn() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS posts (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL,
              username TEXT NOT NULL,
              title TEXT NOT NULL,
              content TEXT NOT NULL DEFAULT '',
              category TEXT NOT NULL DEFAULT '其他',
              post_type TEXT NOT NULL DEFAULT 'question',
              attachment_name TEXT,
              attachment_path TEXT,
              project_link TEXT,
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS replies (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              post_id INTEGER NOT NULL,
              user_id INTEGER NOT NULL,
              username TEXT NOT NULL,
              content TEXT NOT NULL,
              created_at REAL NOT NULL,
              FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
            )
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_posts_category ON posts(category)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_posts_post_type ON posts(post_type)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_posts_created ON posts(created_at DESC)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_replies_post ON replies(post_id)")


# ---------- 帖子 ----------

def create_post(
    user_id: int,
    username: str,
    title: str,
    content: str,
    category: str,
    post_type: str,
    attachment_name: Optional[str] = None,
    attachment_path: Optional[str] = None,
    project_link: Optional[str] = None,
) -> int:
    now = time.time()
    with _conn() as con:
        cur = con.execute(
            """
            INSERT INTO posts (user_id, username, title, content, category, post_type,
                               attachment_name, attachment_path, project_link, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, username, title, content, category, post_type,
             attachment_name, attachment_path, project_link, now, now),
        )
        return cur.lastrowid


def list_posts(
    *,
    category: Optional[str] = None,
    post_type: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """返回 {items: [...], total: int}"""
    con = _conn()
    where_clauses = []
    params: list = []
    if category and category != "全部":
        where_clauses.append("category = ?")
        params.append(category)
    if post_type and post_type != "all":
        where_clauses.append("post_type = ?")
        params.append(post_type)
    if keyword and keyword.strip():
        where_clauses.append("(title LIKE ? OR content LIKE ?)")
        kw = f"%{keyword.strip()}%"
        params.extend([kw, kw])
    where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    total = con.execute(f"SELECT COUNT(*) FROM posts{where_sql}", params).fetchone()[0]

    offset = (page - 1) * page_size
    rows = con.execute(
        f"""
        SELECT p.*, (SELECT COUNT(*) FROM replies r WHERE r.post_id = p.id) AS reply_count
        FROM posts p{where_sql}
        ORDER BY p.created_at DESC
        LIMIT ? OFFSET ?
        """,
        params + [page_size, offset],
    ).fetchall()
    con.close()

    items = []
    for r in rows:
        items.append({
            "id": r["id"],
            "user_id": r["user_id"],
            "username": r["username"],
            "title": r["title"],
            "content": r["content"],
            "category": r["category"],
            "post_type": r["post_type"],
            "attachment_name": r["attachment_name"],
            "project_link": r["project_link"],
            "reply_count": r["reply_count"],
            "created_at": r["created_at"],
        })
    return {"items": items, "total": total}


def get_post(post_id: int) -> Optional[dict]:
    con = _conn()
    r = con.execute(
        """
        SELECT p.*, (SELECT COUNT(*) FROM replies r WHERE r.post_id = p.id) AS reply_count
        FROM posts p WHERE p.id = ?
        """,
        (post_id,),
    ).fetchone()
    con.close()
    if not r:
        return None
    return {
        "id": r["id"],
        "user_id": r["user_id"],
        "username": r["username"],
        "title": r["title"],
        "content": r["content"],
        "category": r["category"],
        "post_type": r["post_type"],
        "attachment_name": r["attachment_name"],
        "attachment_path": r["attachment_path"],
        "project_link": r["project_link"],
        "reply_count": r["reply_count"],
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
    }


def delete_post(post_id: int, user_id: int) -> bool:
    con = _conn()
    cur = con.execute("DELETE FROM posts WHERE id = ? AND user_id = ?", (post_id, user_id))
    con.commit()
    con.close()
    return cur.rowcount > 0


# ---------- 回复 ----------

def create_reply(post_id: int, user_id: int, username: str, content: str) -> int:
    now = time.time()
    con = _conn()
    cur = con.execute(
        "INSERT INTO replies (post_id, user_id, username, content, created_at) VALUES (?, ?, ?, ?, ?)",
        (post_id, user_id, username, content, now),
    )
    con.execute("UPDATE posts SET updated_at = ? WHERE id = ?", (now, post_id))
    con.commit()
    rid = cur.lastrowid
    con.close()
    return rid


def list_replies(post_id: int) -> list[dict]:
    con = _conn()
    rows = con.execute(
        "SELECT * FROM replies WHERE post_id = ? ORDER BY created_at ASC",
        (post_id,),
    ).fetchall()
    con.close()
    return [
        {
            "id": r["id"],
            "post_id": r["post_id"],
            "user_id": r["user_id"],
            "username": r["username"],
            "content": r["content"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]
