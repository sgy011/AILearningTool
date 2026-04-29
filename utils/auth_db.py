from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from werkzeug.security import check_password_hash, generate_password_hash


PROJECT_ROOT = Path(__file__).resolve().parent.parent
INSTANCE_DIR = PROJECT_ROOT / "instance"
AUTH_DB = INSTANCE_DIR / "auth.db"


def _conn() -> sqlite3.Connection:
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(AUTH_DB))
    con.row_factory = sqlite3.Row
    return con


def init_auth_db() -> None:
    with _conn() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              username TEXT NOT NULL,
              email TEXT NOT NULL UNIQUE,
              password_hash TEXT NOT NULL,
              created_at INTEGER NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS email_codes (
              email TEXT PRIMARY KEY,
              code_hash TEXT NOT NULL,
              expires_at INTEGER NOT NULL,
              created_at INTEGER NOT NULL,
              attempts INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS password_reset_codes (
              email TEXT PRIMARY KEY,
              code_hash TEXT NOT NULL,
              expires_at INTEGER NOT NULL,
              created_at INTEGER NOT NULL,
              attempts INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        con.commit()


def seed_default_user() -> None:
    """
    预置账号（用户要求）：
    username=LK, email=2139424961@qq.com, password=123456SS
    """
    username = os.getenv("SEED_USER_NAME", "LK").strip() or "LK"
    email = os.getenv("SEED_USER_EMAIL", "2139424961@qq.com").strip() or "2139424961@qq.com"
    password = os.getenv("SEED_USER_PASSWORD", "123456SS")
    with _conn() as con:
        cur = con.execute("SELECT id FROM users WHERE email=?", (email,))
        row = cur.fetchone()
        if row:
            return
        con.execute(
            "INSERT INTO users (username, email, password_hash, created_at) VALUES (?,?,?,?)",
            (username, email, generate_password_hash(password), int(time.time())),
        )
        con.commit()


def get_user_by_email(email: str) -> Optional[sqlite3.Row]:
    with _conn() as con:
        cur = con.execute("SELECT * FROM users WHERE email=?", ((email or "").strip().lower(),))
        return cur.fetchone()


def get_user_by_id(user_id: int) -> Optional[sqlite3.Row]:
    try:
        uid = int(user_id)
    except Exception:
        return None
    with _conn() as con:
        cur = con.execute("SELECT * FROM users WHERE id=?", (uid,))
        return cur.fetchone()


def create_user(username: str, email: str, password: str) -> int:
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO users (username, email, password_hash, created_at) VALUES (?,?,?,?)",
            (
                (username or "").strip(),
                (email or "").strip().lower(),
                generate_password_hash(password),
                int(time.time()),
            ),
        )
        con.commit()
        return int(cur.lastrowid)


def verify_login(email: str, password: str) -> Tuple[bool, Optional[int], str]:
    u = get_user_by_email(email)
    if not u:
        return False, None, "邮箱或密码错误"
    if not check_password_hash(u["password_hash"], password or ""):
        return False, None, "邮箱或密码错误"
    return True, int(u["id"]), ""


def upsert_email_code(email: str, code_hash: str, expires_at: int) -> None:
    now = int(time.time())
    with _conn() as con:
        con.execute(
            """
            INSERT INTO email_codes (email, code_hash, expires_at, created_at, attempts)
            VALUES (?,?,?,?,0)
            ON CONFLICT(email) DO UPDATE SET
              code_hash=excluded.code_hash,
              expires_at=excluded.expires_at,
              created_at=excluded.created_at,
              attempts=0
            """,
            ((email or "").strip().lower(), code_hash, int(expires_at), now),
        )
        con.commit()


def check_email_code(email: str, code_hash: str) -> Tuple[bool, str]:
    now = int(time.time())
    em = (email or "").strip().lower()
    with _conn() as con:
        row = con.execute("SELECT * FROM email_codes WHERE email=?", (em,)).fetchone()
        if not row:
            return False, "请先获取验证码"
        if int(row["expires_at"]) < now:
            return False, "验证码已过期，请重新获取"
        if str(row["code_hash"]) != str(code_hash):
            con.execute("UPDATE email_codes SET attempts=attempts+1 WHERE email=?", (em,))
            con.commit()
            return False, "验证码错误"
        # success: delete
        con.execute("DELETE FROM email_codes WHERE email=?", (em,))
        con.commit()
        return True, ""


def upsert_password_reset_code(email: str, code_hash: str, expires_at: int) -> None:
    now = int(time.time())
    with _conn() as con:
        con.execute(
            """
            INSERT INTO password_reset_codes (email, code_hash, expires_at, created_at, attempts)
            VALUES (?,?,?,?,0)
            ON CONFLICT(email) DO UPDATE SET
              code_hash=excluded.code_hash,
              expires_at=excluded.expires_at,
              created_at=excluded.created_at,
              attempts=0
            """,
            ((email or "").strip().lower(), code_hash, int(expires_at), now),
        )
        con.commit()


def check_password_reset_code(email: str, code_hash: str) -> Tuple[bool, str]:
    now = int(time.time())
    em = (email or "").strip().lower()
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM password_reset_codes WHERE email=?", (em,)
        ).fetchone()
        if not row:
            return False, "请先获取验证码"
        if int(row["expires_at"]) < now:
            return False, "验证码已过期，请重新获取"
        if str(row["code_hash"]) != str(code_hash):
            con.execute("UPDATE password_reset_codes SET attempts=attempts+1 WHERE email=?", (em,))
            con.commit()
            return False, "验证码错误"
        con.execute("DELETE FROM password_reset_codes WHERE email=?", (em,))
        con.commit()
        return True, ""


def update_user_password(email: str, new_password: str) -> None:
    em = (email or "").strip().lower()
    if not em:
        raise RuntimeError("邮箱为空")
    with _conn() as con:
        row = con.execute("SELECT id FROM users WHERE email=?", (em,)).fetchone()
        if not row:
            raise RuntimeError("该邮箱未注册")
        con.execute(
            "UPDATE users SET password_hash=? WHERE email=?",
            (generate_password_hash(new_password), em),
        )
        con.commit()


def upsert_password_reset_code(email: str, code_hash: str, expires_at: int) -> None:
    now = int(time.time())
    with _conn() as con:
        con.execute(
            """
            INSERT INTO password_reset_codes (email, code_hash, expires_at, created_at, attempts)
            VALUES (?,?,?,?,0)
            ON CONFLICT(email) DO UPDATE SET
              code_hash=excluded.code_hash,
              expires_at=excluded.expires_at,
              created_at=excluded.created_at,
              attempts=0
            """,
            ((email or "").strip().lower(), code_hash, int(expires_at), now),
        )
        con.commit()


def check_password_reset_code(email: str, code_hash: str) -> Tuple[bool, str]:
    now = int(time.time())
    em = (email or "").strip().lower()
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM password_reset_codes WHERE email=?", (em,)
        ).fetchone()
        if not row:
            return False, "请先获取验证码"
        if int(row["expires_at"]) < now:
            return False, "验证码已过期，请重新获取"
        if str(row["code_hash"]) != str(code_hash):
            con.execute("UPDATE password_reset_codes SET attempts=attempts+1 WHERE email=?", (em,))
            con.commit()
            return False, "验证码错误"
        con.execute("DELETE FROM password_reset_codes WHERE email=?", (em,))
        con.commit()
        return True, ""


def update_user_password(email: str, new_password: str) -> None:
    em = (email or "").strip().lower()
    if not em:
        raise RuntimeError("邮箱为空")
    with _conn() as con:
        row = con.execute("SELECT id FROM users WHERE email=?", (em,)).fetchone()
        if not row:
            raise RuntimeError("该邮箱未注册")
        con.execute(
            "UPDATE users SET password_hash=? WHERE email=?",
            (generate_password_hash(new_password), em),
        )
        con.commit()

