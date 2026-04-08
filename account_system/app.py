#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
账户与交易查询系统 — Flask 主程序
运行: python app.py
访问: http://localhost:5000 (内网可通过 http://<本机IP>:5000 访问)

数据库连接参数由 config.ini 提供，不在代码中硬编码。
SQL 查询语句由 queries/*.sql 文件提供，不在代码中写死。
"""

import atexit
import io
import os
import sys
import threading
import webbrowser

import pandas as pd
from flask import (
    Flask,
    g,
    render_template,
    request,
    send_file,
)

from database import get_db, load_query, query_db, start_tunnel, stop_tunnel


def _get_template_folder() -> str:
    """
    返回模板目录路径，兼容 PyInstaller 打包后的运行环境。
    打包后所有 datas 文件被释放到 sys._MEIPASS 目录。
    """
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return os.path.join(meipass, "templates")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")


app = Flask(__name__, template_folder=_get_template_folder())

# 账户查询允许作为筛选字段的列名白名单
_ACCOUNT_FIELD_ALLOWLIST = {"account_no", "account_name"}

# 交易查询允许作为筛选字段的列名白名单
_TRANS_FIELD_ALLOWLIST = {"customer_no", "account_no", "account_name"}

# ──────────────────────────── 数据库连接管理 ────────────────────────────

def get_connection():
    if "db" not in g:
        g.db = get_db()
    return g.db


@app.teardown_appcontext
def close_connection(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# ──────────────────────────── 首页 ────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ──────────────────────────── 账户信息查询 ────────────────────────────

@app.route("/account", methods=["GET", "POST"])
def account_query():
    results = []
    keyword = ""
    search_type = "account_no"
    searched = False
    error = ""

    if request.method == "POST":
        keyword = request.form.get("keyword", "").strip()
        search_type = request.form.get("search_type", "account_no")
        searched = True

        if keyword:
            field = search_type if search_type in _ACCOUNT_FIELD_ALLOWLIST else "account_no"
            try:
                sql_template = load_query("account_query")
                sql = sql_template.format(field=field)
                db = get_connection()
                results = query_db(db, sql, (f"%{keyword}%",))
            except Exception as exc:
                error = f"查询失败：{exc}"

    return render_template(
        "account_query.html",
        results=results,
        keyword=keyword,
        search_type=search_type,
        searched=searched,
        error=error,
    )


@app.route("/account/download", methods=["POST"])
def account_download():
    keyword = request.form.get("keyword", "").strip()
    search_type = request.form.get("search_type", "account_no")

    field = search_type if search_type in _ACCOUNT_FIELD_ALLOWLIST else "account_no"
    sql_template = load_query("account_query")
    sql = sql_template.format(field=field)
    db = get_connection()
    rows = query_db(db, sql, (f"%{keyword}%",))

    df = pd.DataFrame(rows)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="账户查询结果")
    output.seek(0)

    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="账户查询结果.xlsx",
    )


# ──────────────────────────── 交易信息查询 ────────────────────────────

@app.route("/transaction", methods=["GET", "POST"])
def transaction_query():
    results = []
    date_from = ""
    date_to = ""
    keyword = ""
    search_type = "account_no"
    searched = False
    error = ""

    if request.method == "POST":
        date_from = request.form.get("date_from", "").strip()
        date_to = request.form.get("date_to", "").strip()
        keyword = request.form.get("keyword", "").strip()
        search_type = request.form.get("search_type", "account_no")
        searched = True

        if not date_from or not date_to:
            error = "请填写查询起止日期。"
        elif date_from > date_to:
            error = "开始日期不能晚于结束日期。"
        elif not keyword:
            error = "请输入客户号、账号或户名中的至少一项。"
        else:
            field = search_type if search_type in _TRANS_FIELD_ALLOWLIST else "account_no"
            try:
                sql_template = load_query("transaction_query")
                sql = sql_template.format(field=field)
                db = get_connection()
                results = query_db(db, sql, (date_from, date_to, f"%{keyword}%"))
            except Exception as exc:
                error = f"查询失败：{exc}"

    return render_template(
        "transaction_query.html",
        results=results,
        date_from=date_from,
        date_to=date_to,
        keyword=keyword,
        search_type=search_type,
        searched=searched,
        error=error,
    )


@app.route("/transaction/download", methods=["POST"])
def transaction_download():
    date_from = request.form.get("date_from", "").strip()
    date_to = request.form.get("date_to", "").strip()
    keyword = request.form.get("keyword", "").strip()
    search_type = request.form.get("search_type", "account_no")

    field = search_type if search_type in _TRANS_FIELD_ALLOWLIST else "account_no"
    sql_template = load_query("transaction_query")
    sql = sql_template.format(field=field)
    db = get_connection()
    rows = query_db(db, sql, (date_from, date_to, f"%{keyword}%"))

    df = pd.DataFrame(rows)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="交易查询结果")
    output.seek(0)

    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="交易查询结果.xlsx",
    )


# ──────────────────────────── 入口 ────────────────────────────

if __name__ == "__main__":
    # 启动 SSH 隧道（失败时给出清晰提示后退出）
    try:
        local_port = start_tunnel()
        print(f"SSH 隧道已建立，本地端口: {local_port}")
    except Exception as exc:
        print(f"[错误] SSH 隧道启动失败: {exc}")
        sys.exit(1)

    # 注册退出时关闭隧道
    atexit.register(stop_tunnel)

    port = 5000
    url = f"http://localhost:{port}"

    # 延迟 1.2 秒后自动打开默认浏览器（给 Flask 启动时间）
    def _open_browser():
        import time
        time.sleep(1.2)
        webbrowser.open(url)

    browser_thread = threading.Thread(target=_open_browser, daemon=True)
    browser_thread.start()

    print(f"启动成功，请在浏览器访问: {url}")
    print("按 Ctrl+C 退出程序")
    # host="0.0.0.0" 使局域网内其他机器也能访问
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
