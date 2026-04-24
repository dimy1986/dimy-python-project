#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库连接模块 — 通过 SSH 隧道连接 Inceptor (Hive/LDAP)

连接参数从外部 config.ini 读取，代码中不硬编码任何地址或密码。
SQL 查询语句从外部 queries/*.sql 文件加载，不在代码中写死。
"""

import configparser
import os
import re
import sqlite3
import sys
import time
from typing import Any, Dict, Generator, List, Optional

from pyhive import hive
from sshtunnel import SSHTunnelForwarder
import threading
from werkzeug.security import check_password_hash, generate_password_hash


import socket

_last_query_time = 0  # 记录最后一次查询的时间
_tunnel_cleanup_thread = None

def _is_port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            return True
    except:
        return False

def _is_tunnel_alive(section: str) -> bool:
    global _shared_tunnel, _section_port_map

    if _shared_tunnel is None:
        return False

    if not _shared_tunnel.is_active:
        return False

    if section not in _section_port_map:
        return False

    port = _section_port_map[section]

    return _is_port_open(port)

# ──────────────────────────── 路径解析 ────────────────────────────

def _base_dir() -> str:
    """
    返回运行时基准目录：
    - 打包为 exe 后：exe 所在目录
    - 普通 Python 运行：本文件所在目录
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _get_config_path() -> str:
    return os.path.join(_base_dir(), "config.ini")


def get_queries_dir() -> str:
    """返回 SQL / JSON 查询文件所在目录（供外部模块调用）。"""
    return _get_queries_dir()


def load_auth_config() -> tuple:
    """
    从 config.ini 的 [auth] 节读取登录凭据，返回 (username, password)。
    若 [auth] 节不存在则返回 (None, None)，由调用方决定是否启用认证。
    """
    cfg = _load_config()
    if not cfg.has_section("auth"):
        return (None, None)
    username = cfg.get("auth", "username", fallback=None)
    password = cfg.get("auth", "password", fallback=None)
    return (username, password)


# ──────────────────────────── 用户数据库（多用户认证）────────────────────────────

def _get_users_db_path() -> str:
    """返回存储登录用户的 SQLite 数据库路径（与 config.ini 同目录）。"""
    return os.path.join(_base_dir(), "users.db")


def _users_db_conn() -> sqlite3.Connection:
    """打开并返回用户数据库连接（行工厂为 sqlite3.Row）。"""
    conn = sqlite3.connect(_get_users_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_users_db(migrate_from_config: bool = True) -> None:
    """
    初始化用户表（若不存在则创建）。
    若 migrate_from_config=True 且表中尚无用户，自动将 config.ini [auth] 节中的
    凭据迁移到数据库（密码以 Werkzeug pbkdf2 哈希存储）。
    """
    with _users_db_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                is_admin      INTEGER NOT NULL DEFAULT 0,
                created_at    TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
            """
        )
        conn.commit()

        if not migrate_from_config:
            return

        row = conn.execute("SELECT COUNT(*) FROM users").fetchone()
        if row[0] > 0:
            return

    # 表为空时，尝试从 config.ini 迁移
    try:
        legacy_user, legacy_pass = load_auth_config()
    except Exception:
        legacy_user, legacy_pass = None, None

    if legacy_user and legacy_pass:
        add_user(legacy_user, legacy_pass, is_admin=True)


def verify_user(username: str, password: str) -> bool:
    """
    验证用户名和密码，返回 True 表示认证通过。
    使用 Werkzeug 安全哈希比较，防止时序攻击。
    """
    with _users_db_conn() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()
    if row is None:
        return False
    return check_password_hash(row["password_hash"], password)


def add_user(username: str, password: str, is_admin: bool = False) -> None:
    """
    新增用户，密码以 Werkzeug pbkdf2_sha256 哈希存储。

    :raises ValueError: 若用户名已存在
    """
    hashed = generate_password_hash(password)
    try:
        with _users_db_conn() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)",
                (username, hashed, 1 if is_admin else 0),
            )
            conn.commit()
    except sqlite3.IntegrityError:
        raise ValueError(f"用户名 '{username}' 已存在")


def list_users() -> List[Dict[str, Any]]:
    """返回所有用户列表（不含密码哈希）。"""
    with _users_db_conn() as conn:
        rows = conn.execute(
            "SELECT id, username, is_admin, created_at FROM users ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]


def delete_user(username: str) -> None:
    """删除指定用户。"""
    with _users_db_conn() as conn:
        conn.execute("DELETE FROM users WHERE username = ?", (username,))
        conn.commit()


def change_password(username: str, new_password: str) -> None:
    """修改指定用户的密码。"""
    hashed = generate_password_hash(new_password)
    with _users_db_conn() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (hashed, username),
        )
        conn.commit()


def user_count() -> int:
    """返回当前用户总数（用于判断是否启用认证）。"""
    with _users_db_conn() as conn:
        row = conn.execute("SELECT COUNT(*) FROM users").fetchone()
    return row[0]


def _get_queries_dir() -> str:
    """
    返回 SQL 查询文件目录：
    - 优先使用运行目录下的 queries/（用户可自定义）
    - 打包模式下若运行目录没有，则回退到 _MEIPASS 中的打包副本
    """
    candidate = os.path.join(_base_dir(), "queries")
    if os.path.isdir(candidate):
        return candidate
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            fallback = os.path.join(meipass, "queries")
            if os.path.isdir(fallback):
                return fallback
    return candidate


# ──────────────────────────── 配置加载 ────────────────────────────

def _load_config() -> configparser.ConfigParser:
    """加载 config.ini，若文件不存在则抛出清晰的错误提示。"""
    cfg = configparser.ConfigParser()
    path = _get_config_path()
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"配置文件未找到: {path}\n"
            f"请将 config.ini.example 复制为 config.ini，并填写实际连接参数。"
        )
    cfg.read(path, encoding="utf-8")
    return cfg


# ──────────────────────────── SQL 文件加载 ────────────────────────────

def load_query(name: str) -> str:
    """
    从 queries/<name>.sql 文件中读取 SQL 模板字符串。

    SQL 文件中可使用：
      {field}  — 列名占位符，由调用方用白名单校验后的值替换
      %s       — pyhive 参数占位符，对应 cursor.execute() 的 parameters 元组

    :param name: SQL 文件名（不含 .sql 后缀），如 "account_query"
    :raises FileNotFoundError: 若 SQL 文件不存在
    """
    path = os.path.join(_get_queries_dir(), f"{name}.sql")
    if not os.path.exists(path):
        raise FileNotFoundError(f"SQL 查询文件未找到: {path}")
    with open(path, encoding="utf-8") as f:
        return f.read()


# ──────────────────────────── SSH 隧道（单连接多端口转发）────────────────────────────

# 所有 inceptor 节点共用一个 SSHTunnelForwarder（单条 SSH 连接），
# 通过 remote_bind_addresses 同时转发多个端口，避免对同一跳板机建立多条 SSH 连接
# 导致 "Could not establish session to SSH gateway" 错误。
_shared_tunnel: Optional[SSHTunnelForwarder] = None
_section_port_map: Dict[str, int] = {}     # section 名 → 本地已绑定端口
_tunnel_lock = threading.Lock()


def _inceptor_sections(cfg: configparser.ConfigParser) -> List[str]:
    """返回 config.ini 中所有以 'inceptor' 开头的节（按字典序排列）。"""
    return sorted(s for s in cfg.sections() if s.startswith("inceptor"))


def start_tunnel(section: str = "inceptor") -> int:
    global _shared_tunnel, _section_port_map

    # 快速路径（已有直接返回）
    if _is_tunnel_alive(section):
        return _section_port_map[section]

    with _tunnel_lock:
        if _is_tunnel_alive(section):
            return _section_port_map[section]

        # 走到这里说明隧道不可用 → 强制重建
        if _shared_tunnel is not None:
            print("SSH tunnel失效，准备重建")
            try:
                _shared_tunnel.stop()
            except Exception as e:
                print(f"stop tunnel异常: {e}")
            finally:
                _shared_tunnel = None
                _section_port_map.clear()

        cfg = _load_config()
        if not cfg.has_section(section):
            raise ValueError(
                f"config.ini 中未找到节点 [{section}]"
            )

        ssh_host = cfg.get("ssh", "host")
        ssh_port = cfg.getint("ssh", "port", fallback=22)
        ssh_user = cfg.get("ssh", "username")
        ssh_pass = cfg.get("ssh", "password")

        sections = _inceptor_sections(cfg)

        remote_binds = [
            (cfg.get(s, "host"), cfg.getint(s, "port"))
            for s in sections
        ]
        local_binds = [
            ("127.0.0.1", cfg.getint(s, "local_port", fallback=9999))
            for s in sections
        ]

        # ❗关键：只在没有 tunnel 或失效时创建
        if _shared_tunnel is None or not _shared_tunnel.is_active:
            _shared_tunnel = SSHTunnelForwarder(
                (ssh_host, ssh_port),
                ssh_username=ssh_user,
                ssh_password=ssh_pass,
                remote_bind_addresses=remote_binds,
                local_bind_addresses=local_binds,
                set_keepalive=30  # 非常关键
            )
            _shared_tunnel.start()

            _section_port_map = {
                s: _shared_tunnel.local_bind_ports[i]
                for i, s in enumerate(sections)
            }

            print("SSH tunnel started")

        if section not in _section_port_map:
            raise ValueError(f"节点 [{section}] 未建立映射")

        return _section_port_map[section]


def stop_tunnel() -> None:
    """关闭共享 SSH 隧道（应用退出时调用）。"""
    global _shared_tunnel, _section_port_map
    if _shared_tunnel is not None:
        _shared_tunnel.stop()
        _shared_tunnel = None
    _section_port_map.clear()


# ──────────────────────────── Inceptor 连接 ────────────────────────────

def get_db(section: str = "inceptor") -> hive.Connection:
    """
    建立并返回一个 Inceptor (Hive/LDAP) 连接。
    连接通过 SSH 隧道的本地端口转发到真实 Inceptor 服务。
    每次请求创建新连接，由 Flask teardown 负责关闭。

    :param section: config.ini 中对应 Inceptor 节点的 section 名，默认为 "inceptor"。
    """
    local_port = start_tunnel(section)
    cfg = _load_config()
    username = cfg.get(section, "username")
    password = cfg.get(section, "password")
    database = cfg.get(section, "database", fallback="default")

    conn = hive.Connection(
        host="127.0.0.1",
        port=local_port,
        username=username,
        password=password,
        auth="LDAP",
        database=database,
    )
    return conn


# ──────────────────────────── 查询工具 ────────────────────────────

def query_db(
    conn: hive.Connection,
    sql: str,
    params: tuple = (),
) -> List[Dict[str, Any]]:
    """
    执行参数化 SQL 并以字典列表形式返回结果。

    使用 cursor.description 获取列名，自动去除 Hive 返回列名中的表名前缀
    （如 "accounts.account_no" → "account_no"）。

    :param conn:   Hive 连接对象
    :param sql:    SQL 语句（%s 为 pyhive 参数占位符）
    :param params: 对应 SQL 中每个 %s 的参数元组
    :returns:      查询结果，每行为一个字典
    """
    global _last_query_time
    _last_query_time = time.time()  # ← 记录查询时间
    cursor = conn.cursor()
    # pyhive 内部用 Python 的 % 格式化来替换 %s 占位符。
    # SQL 注释（-- ...）中常含有 "%s" 说明文字和 "%张三%" 通配符示例，
    # 这些字面量 % 会被 pyhive 误作格式说明符，导致
    # "not enough arguments for format string" 错误。
    # 解决方法：
    #   1. 先剥除所有 SQL 行注释（-- ...），注释对执行无影响
    #   2. 再将所有 %s 占位符替换为临时令牌，转义其余字面量 % 为 %%，最后还原占位符
    sql_exec = re.sub(r"--[^\n]*", "", sql)   # 去掉行注释
    if params:
        _PLACEHOLDER = "\x00__PYHIVE_PARAM__\x00"
        sql_exec = (
            sql_exec.replace("%s", _PLACEHOLDER)
                    .replace("%", "%%")
                    .replace(_PLACEHOLDER, "%s")
        )
    cursor.execute(sql_exec, params if params else None)
    if not cursor.description:
        return []
    # 去除 Hive 列名中可能携带的表名前缀（tablename.column → column）
    columns = [desc[0].split(".")[-1] for desc in cursor.description]
    rows = cursor.fetchall()
    return [dict(zip(columns, row)) for row in rows]


def iter_query_db(
    conn: hive.Connection,
    sql: str,
    params: tuple = (),
    chunk_size: int = 2000,
) -> Generator[Dict[str, Any], None, None]:
    """
    执行参数化 SQL，以生成器方式按块（chunk_size 行）返回结果字典。

    与 query_db 共享相同的 SQL 预处理逻辑（注释清理、占位符转义）。
    使用 cursor.fetchmany() 分批拉取数据，每次仅将 chunk_size 行保留在内存中，
    适合几十万行级别的大数据量 Excel 导出场景。

    :param conn:       Hive 连接对象
    :param sql:        SQL 语句（%s 为 pyhive 参数占位符）
    :param params:     对应 SQL 中每个 %s 的参数元组
    :param chunk_size: 每次 fetchmany 拉取的行数，默认 2000
    :yields:           每行数据字典
    """
    global _last_query_time
    _last_query_time = time.time()  # ← 记录查询时间

    cursor = conn.cursor()
    sql_exec = re.sub(r"--[^\n]*", "", sql)
    if params:
        _PLACEHOLDER = "\x00__PYHIVE_PARAM__\x00"
        sql_exec = (
            sql_exec.replace("%s", _PLACEHOLDER)
                    .replace("%", "%%")
                    .replace(_PLACEHOLDER, "%s")
        )
    cursor.execute(sql_exec, params if params else None)
    if not cursor.description:
        return
    columns = [desc[0].split(".")[-1] for desc in cursor.description]
    while True:
        batch = cursor.fetchmany(chunk_size)
        if not batch:
            break
        for row in batch:
            yield dict(zip(columns, row))


def _tunnel_cleanup_worker():
    """
    后台线程：定期检查隧道是否空闲。
    若超过 3 分钟无查询则自动关闭隧道。
    """
    global _shared_tunnel, _last_query_time

    print("[INFO] Tunnel cleanup worker started (idle timeout: 300s)")

    while True:
        try:
            time.sleep(60)  # 每 60 秒检查一次

            if _shared_tunnel is None or not _shared_tunnel.is_active:
                continue

            current_time = time.time()
            idle_time = current_time - _last_query_time

            if idle_time > 150:  # 3 分钟 = 130 秒
                print(f"[INFO] SSH tunnel idle for {int(idle_time / 60)} minutes, closing...")
                try:
                    stop_tunnel()
                    print("[INFO] SSH tunnel closed successfully")
                except Exception as e:
                    print(f"[ERROR] Failed to close tunnel: {e}")
        except Exception as e:
            print(f"[ERROR] Tunnel cleanup worker error: {e}")