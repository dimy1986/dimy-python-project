#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
账户与交易查询系统 — Flask 主程序
运行: python app.py
访问: http://0.0.0.0:5000 (内网可通过 http://<本机IP>:5000 访问)

生产环境建议使用 Gunicorn 等 WSGI 服务器启动:
    pip install gunicorn
    gunicorn -w 4 -b 0.0.0.0:5000 app:app
"""

import io
import os
import sqlite3

import pandas as pd
from flask import (
    Flask,
    g,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from database import DB_PATH, get_db, init_db

app = Flask(__name__)

# Allowlist of column names that may be used in dynamic SQL fragments.
# These must exactly match column names in the transactions table.
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

    if request.method == "POST":
        keyword = request.form.get("keyword", "").strip()
        search_type = request.form.get("search_type", "account_no")
        searched = True

        if keyword:
            db = get_connection()
            if search_type == "account_no":
                rows = db.execute(
                    "SELECT * FROM accounts WHERE account_no LIKE ?",
                    (f"%{keyword}%",),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM accounts WHERE account_name LIKE ?",
                    (f"%{keyword}%",),
                ).fetchall()
            results = [dict(r) for r in rows]

    return render_template(
        "account_query.html",
        results=results,
        keyword=keyword,
        search_type=search_type,
        searched=searched,
    )


@app.route("/account/download", methods=["POST"])
def account_download():
    keyword = request.form.get("keyword", "").strip()
    search_type = request.form.get("search_type", "account_no")

    db = get_connection()
    if search_type == "account_no":
        rows = db.execute(
            "SELECT * FROM accounts WHERE account_no LIKE ?",
            (f"%{keyword}%",),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM accounts WHERE account_name LIKE ?",
            (f"%{keyword}%",),
        ).fetchall()

    columns = ["id", "account_no", "account_name", "customer_no", "id_card",
               "open_date", "status", "balance", "currency", "branch"]
    column_names = ["序号", "账号", "户名", "客户号", "证件号码",
                    "开户日期", "账户状态", "余额", "币种", "开户网点"]

    df = pd.DataFrame([dict(r) for r in rows], columns=columns)
    df.columns = column_names

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
            db = get_connection()
            field_map = {
                "customer_no": "customer_no",
                "account_no": "account_no",
                "account_name": "account_name",
            }
            field = field_map.get(search_type, "account_no")
            # Explicit allowlist check before string interpolation into SQL
            if field not in _TRANS_FIELD_ALLOWLIST:
                field = "account_no"
            sql = (
                f"SELECT * FROM transactions "
                f"WHERE trans_date BETWEEN ? AND ? "
                f"AND {field} LIKE ? "
                f"ORDER BY trans_date DESC, trans_time DESC"
            )
            rows = db.execute(sql, (date_from, date_to, f"%{keyword}%")).fetchall()
            results = [dict(r) for r in rows]

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

    field_map = {
        "customer_no": "customer_no",
        "account_no": "account_no",
        "account_name": "account_name",
    }
    field = field_map.get(search_type, "account_no")
    # Explicit allowlist check before string interpolation into SQL
    if field not in _TRANS_FIELD_ALLOWLIST:
        field = "account_no"

    db = get_connection()
    sql = (
        f"SELECT * FROM transactions "
        f"WHERE trans_date BETWEEN ? AND ? "
        f"AND {field} LIKE ? "
        f"ORDER BY trans_date DESC, trans_time DESC"
    )
    rows = db.execute(sql, (date_from, date_to, f"%{keyword}%")).fetchall()

    columns = ["id", "trans_date", "trans_time", "account_no", "account_name",
               "customer_no", "trans_type", "amount", "direction",
               "balance_after", "channel", "remark"]
    column_names = ["序号", "交易日期", "交易时间", "账号", "户名",
                    "客户号", "交易类型", "金额", "借贷方向",
                    "交易后余额", "交易渠道", "摘要"]

    df = pd.DataFrame([dict(r) for r in rows], columns=columns)
    df.columns = column_names

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
    init_db()
    # host="0.0.0.0" 使局域网内其他机器也能访问
    app.run(host="0.0.0.0", port=5000, debug=False)
