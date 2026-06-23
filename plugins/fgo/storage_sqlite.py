from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Literal, Optional, Tuple

Region = Literal["cn", "jp", "tw"]
Source = Literal["group", "user", "default"]

DB_PATH = Path("fgo.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_region (
                user_id TEXT PRIMARY KEY,
                region TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS group_region (
                group_id TEXT PRIMARY KEY,
                region TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )


def set_user_region(user_id: str, region: Region, ts: int) -> None:
    init_db()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO user_region(user_id, region, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                region=excluded.region,
                updated_at=excluded.updated_at
            """,
            (user_id, region, ts),
        )


def set_group_region(group_id: str, region: Region, ts: int) -> None:
    init_db()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO group_region(group_id, region, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(group_id) DO UPDATE SET
                region=excluded.region,
                updated_at=excluded.updated_at
            """,
            (group_id, region, ts),
        )


def get_user_region(user_id: str) -> Optional[Region]:
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT region FROM user_region WHERE user_id=?",
            (user_id,),
        ).fetchone()
    return row["region"] if row else None  # type: ignore[return-value]


def get_group_region(group_id: str) -> Optional[Region]:
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT region FROM group_region WHERE group_id=?",
            (group_id,),
        ).fetchone()
    return row["region"] if row else None  # type: ignore[return-value]


def resolve_region(user_id: str, group_id: Optional[str]) -> Tuple[Region, Source]:
    """
    规则：
    - 群聊：群默认 > 用户默认 > cn
    - 私聊：用户默认 > cn
    """
    if group_id:
        gr = get_group_region(group_id)
        if gr:
            return gr, "group"
    ur = get_user_region(user_id)
    if ur:
        return ur, "user"
    return "cn", "default"