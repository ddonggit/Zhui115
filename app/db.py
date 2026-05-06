"""Zhui115 数据库管理

表结构:
  - episodes: 已处理的剧集记录（去重用）
  - offline_tasks: 115 离线任务状态跟踪
  - retry_queue: 失败重试队列
  - history: 操作日志
  - gap_log: 断集检测日志
"""

import sqlite3
import threading
from datetime import datetime, timezone
from .config import DB_PATH

_lock = threading.Lock()


def get_conn():
    """获取数据库连接（自动创建表）"""
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _init_tables(conn)
    return conn


def _init_tables(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS episodes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            source_name TEXT    NOT NULL,
            link_hash   TEXT    NOT NULL,
            title       TEXT    NOT NULL,
            link        TEXT    NOT NULL,
            episode     INTEGER DEFAULT 0,
            season      INTEGER DEFAULT 0,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            UNIQUE(link_hash)
        );
        CREATE INDEX IF NOT EXISTS idx_episodes_source ON episodes(source_name);
        CREATE INDEX IF NOT EXISTS idx_episodes_created ON episodes(created_at);

        CREATE TABLE IF NOT EXISTS offline_tasks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            source_name TEXT    NOT NULL,
            title       TEXT    NOT NULL,
            link        TEXT    NOT NULL,
            link_hash   TEXT    NOT NULL,
            info_hash   TEXT    DEFAULT '',
            task_id     TEXT    DEFAULT '',
            status      TEXT    NOT NULL DEFAULT '等待提交',
            -- status: 等待提交 / 已提交 / 失败 / 已完成
            retry_count INTEGER DEFAULT 0,
            episode_num INTEGER DEFAULT 0,
            season_num  INTEGER DEFAULT 0,
            quality     TEXT    DEFAULT '',
            image_url   TEXT    DEFAULT '',
            message     TEXT    DEFAULT '',
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_tasks_status ON offline_tasks(status);
        CREATE INDEX IF NOT EXISTS idx_tasks_source ON offline_tasks(source_name);

        CREATE TABLE IF NOT EXISTS retry_queue (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id     INTEGER NOT NULL UNIQUE,
            retry_after TEXT    NOT NULL,
            retry_count INTEGER DEFAULT 0,
            max_retries INTEGER DEFAULT 5,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (task_id) REFERENCES offline_tasks(id)
        );
        CREATE INDEX IF NOT EXISTS idx_retry_after ON retry_queue(retry_after);

        CREATE TABLE IF NOT EXISTS history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            event       TEXT    NOT NULL,
            detail      TEXT    DEFAULT '',
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_history_created ON history(created_at);

        CREATE TABLE IF NOT EXISTS gap_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            show_name   TEXT    NOT NULL,
            season      INTEGER DEFAULT 0,
            gaps        TEXT    NOT NULL,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        -- 配置表（key-value 存储，用来存备份恢复等元信息）
        CREATE TABLE IF NOT EXISTS meta (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
    """)

    # 迁移：为已有数据库添加新列
    _migrate_columns(conn)
    conn.commit()


def _migrate_columns(conn):
    """为已存在的表添加新列（兼容旧数据库）"""
    _add_col(conn, "offline_tasks", "episode_num", "INTEGER DEFAULT 0")
    _add_col(conn, "offline_tasks", "season_num", "INTEGER DEFAULT 0")
    _add_col(conn, "offline_tasks", "quality", "TEXT DEFAULT ''")
    _add_col(conn, "offline_tasks", "image_url", "TEXT DEFAULT ''")


def _add_col(conn, table, col, col_def):
    """安全地添加列（列已存在时忽略）"""
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")
    except sqlite3.OperationalError:
        pass  # 列已存在，忽略


# ── 剧集去重 ──

def episode_exists(link_hash: str) -> bool:
    with _lock:
        conn = get_conn()
        try:
            row = conn.execute(
                "SELECT 1 FROM episodes WHERE link_hash=?", (link_hash,)
            ).fetchone()
            return row is not None
        finally:
            conn.close()


def add_episode(source_name: str, link_hash: str, title: str, link: str,
                episode: int = 0, season: int = 0) -> bool:
    with _lock:
        conn = get_conn()
        try:
            conn.execute(
                """INSERT OR IGNORE INTO episodes
                   (source_name, link_hash, title, link, episode, season)
                   VALUES (?,?,?,?,?,?)""",
                (source_name, link_hash, title, link, episode, season),
            )
            conn.commit()
            return conn.total_changes > 0
        finally:
            conn.close()


# ── 离线任务 ──

def add_offline_task(source_name: str, title: str, link: str,
                     link_hash: str,
                     episode_num: int = 0, season_num: int = 0,
                     quality: str = "", image_url: str = "") -> int:
    with _lock:
        conn = get_conn()
        try:
            cur = conn.execute(
                """INSERT INTO offline_tasks
                   (source_name, title, link, link_hash,
                    episode_num, season_num, quality, image_url, status)
                   VALUES (?,?,?,?,?,?,?,?,'等待提交')""",
                (source_name, title, link, link_hash,
                 episode_num, season_num, quality, image_url),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()


def update_offline_task(task_id: int, status: str = None,
                        info_hash: str = None, message: str = None,
                        retry_count: int = None,
                        image_url: str = None) -> bool:
    with _lock:
        conn = get_conn()
        try:
            sets = []
            vals = []
            if status:
                sets.append("status=?")
                vals.append(status)
            if info_hash is not None:
                sets.append("info_hash=?")
                vals.append(info_hash)
            if message is not None:
                sets.append("message=?")
                vals.append(message)
            if retry_count is not None:
                sets.append("retry_count=?")
                vals.append(retry_count)
            if image_url is not None:
                sets.append("image_url=?")
                vals.append(image_url)
            sets.append("updated_at=datetime('now')")
            vals.append(task_id)
            sql = f"UPDATE offline_tasks SET {', '.join(sets)} WHERE id=?"
            conn.execute(sql, vals)
            conn.commit()
            return conn.total_changes > 0
        finally:
            conn.close()


def get_pending_tasks() -> list[dict]:
    """获取待提交的任务"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM offline_tasks WHERE status='等待提交' ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_retryable_tasks() -> list[dict]:
    """获取到时间的重试任务"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT t.*, r.retry_after, r.retry_count AS retry_queue_count,
                      r.max_retries
               FROM offline_tasks t
               INNER JOIN retry_queue r ON r.task_id = t.id
               WHERE r.retry_after <= datetime('now')
               ORDER BY r.retry_after""",
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_retry(task_id: int, retry_after: str, retry_count: int,
              max_retries: int = 5) -> bool:
    with _lock:
        conn = get_conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO retry_queue
                   (task_id, retry_after, retry_count, max_retries)
                   VALUES (?,?,?,?)""",
                (task_id, retry_after, retry_count, max_retries),
            )
            conn.commit()
            return True
        finally:
            conn.close()


def remove_retry(task_id: int) -> bool:
    with _lock:
        conn = get_conn()
        try:
            conn.execute("DELETE FROM retry_queue WHERE task_id=?", (task_id,))
            conn.commit()
            return conn.total_changes > 0
        finally:
            conn.close()


def get_task_stats() -> dict:
    """获取任务统计"""
    conn = get_conn()
    try:
        total = conn.execute("SELECT COUNT(*) FROM offline_tasks").fetchone()[0]
        by_status = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM offline_tasks GROUP BY status"
        ).fetchall()
        pending_retry = conn.execute(
            "SELECT COUNT(*) FROM retry_queue"
        ).fetchone()[0]
        stats = {"total": total, "pending_retry": pending_retry}
        for r in by_status:
            stats[r["status"]] = r["cnt"]
        return stats
    finally:
        conn.close()


def list_offline_tasks(page: int = 1, page_size: int = 20,
                       status: str = None, source: str = None) -> dict:
    """分页查询离线任务"""
    conn = get_conn()
    try:
        where = []
        vals = []
        if status:
            where.append("status=?")
            vals.append(status)
        if source:
            where.append("source_name=?")
            vals.append(source)
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        count = conn.execute(
            f"SELECT COUNT(*) FROM offline_tasks {where_sql}", vals
        ).fetchone()[0]

        offset = (page - 1) * page_size
        rows = conn.execute(
            f"SELECT * FROM offline_tasks {where_sql} ORDER BY id DESC LIMIT ? OFFSET ?",
            vals + [page_size, offset],
        ).fetchall()

        return {
            "total": count,
            "page": page,
            "page_size": page_size,
            "items": [dict(r) for r in rows],
        }
    finally:
        conn.close()


# ── 历史日志 ──

def add_history(event: str, detail: str = ""):
    with _lock:
        conn = get_conn()
        try:
            conn.execute(
                "INSERT INTO history (event, detail) VALUES (?,?)",
                (event, detail),
            )
            conn.commit()
        finally:
            conn.close()


def list_history(page: int = 1, page_size: int = 50) -> dict:
    conn = get_conn()
    try:
        count = conn.execute("SELECT COUNT(*) FROM history").fetchone()[0]
        offset = (page - 1) * page_size
        rows = conn.execute(
            "SELECT * FROM history ORDER BY id DESC LIMIT ? OFFSET ?",
            (page_size, offset),
        ).fetchall()
        return {
            "total": count,
            "page": page,
            "page_size": page_size,
            "items": [dict(r) for r in rows],
        }
    finally:
        conn.close()


# ── 数据清理 ──

def vacuum(keep_days: int = 60):
    """清理旧数据（VACUUM 需临时退出 WAL 模式）"""
    # DELETE 操作在锁内执行
    with _lock:
        conn = sqlite3.connect(str(DB_PATH), timeout=10)
        try:
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.execute(
                "DELETE FROM episodes WHERE created_at < datetime('now', ?)",
                (f"-{keep_days} days",),
            )
            conn.execute(
                "DELETE FROM history WHERE created_at < datetime('now', ?)",
                (f"-{keep_days} days",),
            )
            conn.execute(
                """DELETE FROM retry_queue WHERE task_id IN
                   (SELECT id FROM offline_tasks WHERE status IN ('已完成','失败'))"""
            )
            conn.commit()
            conn.execute("VACUUM")
            # 切回 WAL 模式，确保下次连接用 WAL
            conn.execute("PRAGMA journal_mode=WAL")
            conn.commit()
        except Exception as e:
            raise RuntimeError(f"清理失败: {e}")
        finally:
            conn.close()
    # add_history 在锁外调用，避免死锁
    add_history("vacuum", f"清理完成，保留{keep_days}天")


# ── 备份 / 恢复 ──

def export_db(target_path: str) -> bool:
    """导出数据库到文件"""
    try:
        with _lock:
            conn = get_conn()
            try:
                backup = sqlite3.connect(target_path)
                conn.backup(backup, pages=100)
                backup.close()
            finally:
                conn.close()
        return True
    except Exception:
        return False


def import_db(source_path: str) -> bool:
    """从文件恢复数据库"""
    try:
        with _lock:
            conn = get_conn()
            try:
                source = sqlite3.connect(source_path)
                source.backup(conn, pages=100)
                source.close()
            finally:
                conn.close()
        return True
    except Exception:
        return False
