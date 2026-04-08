#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库连接模块 — 通过 SSH 隧道连接 Inceptor (Hive/LDAP)

连接参数从外部 config.ini 读取，代码中不硬编码任何地址或密码。
SQL 查询语句从外部 queries/*.sql 文件加载，不在代码中写死。
"""

import configparser
import os
import sys
from typing import Any, Dict, List, Tuple

from pyhive import hive
from sshtunnel import SSHTunnelForwarder


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


# ──────────────────────────── SSH 隧道（按节点名索引）────────────────────────────

# 每个 Inceptor 节点维护一个独立的 SSH 隧道，以节点名（config.ini 中的 section 名）为键。
_tunnels: Dict[str, Tuple[SSHTunnelForwarder, int]] = {}


def start_tunnel(section: str = "inceptor") -> int:
    """
    启动到指定 Inceptor 节点的 SSH 隧道，返回本地绑定端口。
    若该节点的隧道已激活则直接返回已绑定端口。

    :param section: config.ini 中对应 Inceptor 节点的 section 名，默认为 "inceptor"。
                    例如 "inceptor"、"inceptor2"，与 config.ini 及 queries/*.json 中的
                    "inceptor" 字段保持一致。
    """
    global _tunnels

    existing = _tunnels.get(section)
    if existing is not None:
        tunnel, port = existing
        if tunnel.is_active:
            return port

    cfg = _load_config()
    if not cfg.has_section(section):
        raise ValueError(
            f"config.ini 中未找到节点 [{section}]，"
            f"请参照 config.ini.example 添加该节点的配置。"
        )

    ssh_host = cfg.get("ssh", "host")
    ssh_port = cfg.getint("ssh", "port", fallback=22)
    ssh_user = cfg.get("ssh", "username")
    ssh_pass = cfg.get("ssh", "password")
    inc_host = cfg.get(section, "host")
    inc_port = cfg.getint(section, "port")
    local_port = cfg.getint(section, "local_port", fallback=9999)

    tunnel = SSHTunnelForwarder(
        (ssh_host, ssh_port),
        ssh_username=ssh_user,
        ssh_password=ssh_pass,
        remote_bind_address=(inc_host, inc_port),
        local_bind_address=("127.0.0.1", local_port),
    )
    tunnel.start()
    bound_port = tunnel.local_bind_port
    _tunnels[section] = (tunnel, bound_port)
    return bound_port


def stop_tunnel() -> None:
    """关闭所有已启动的 SSH 隧道（应用退出时调用）。"""
    global _tunnels
    for tunnel, _ in _tunnels.values():
        tunnel.stop()
    _tunnels.clear()


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
    params: Tuple[Any, ...] = (),
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
    cursor = conn.cursor()
    # pyhive 内部用 Python 的 % 格式化来替换 %s 占位符。
    # 若 SQL 中存在 Hive 日期格式化函数的格式串（如 '%Y%m%d'、'%m' 等），
    # 这些字面量 % 会被 pyhive 误作格式说明符，导致
    # "not enough arguments for format string" 错误。
    # 解决方法：
    #   1. 先将所有 %s 占位符替换为不可能出现在 SQL 中的临时令牌
    #   2. 将剩余的所有字面量 % 转义为 %%
    #   3. 将临时令牌还原为 %s
    if params:
        _PLACEHOLDER = "\x00__PYHIVE_PARAM__\x00"
        sql = sql.replace("%s", _PLACEHOLDER).replace("%", "%%").replace(_PLACEHOLDER, "%s")
    cursor.execute(sql, params if params else None)
    if not cursor.description:
        return []
    # 去除 Hive 列名中可能携带的表名前缀（tablename.column → column）
    columns = [desc[0].split(".")[-1] for desc in cursor.description]
    rows = cursor.fetchall()
    return [dict(zip(columns, row)) for row in rows]

