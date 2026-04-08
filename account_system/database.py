#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库初始化与示例数据
使用 SQLite，可根据需要替换为 MySQL / PostgreSQL
"""

import sqlite3
import os
from datetime import date, timedelta
import random

DB_PATH = os.path.join(os.path.dirname(__file__), "bank_data.db")


def get_db():
    """返回数据库连接（row_factory 支持字典访问）"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """建表并写入示例数据（仅首次运行）"""
    conn = get_db()
    cur = conn.cursor()

    # 账户表
    cur.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            account_no  TEXT    NOT NULL UNIQUE,   -- 账号
            account_name TEXT   NOT NULL,          -- 户名
            customer_no TEXT    NOT NULL,          -- 客户号
            id_card     TEXT,                      -- 证件号码
            open_date   TEXT,                      -- 开户日期
            status      TEXT    DEFAULT '正常',    -- 账户状态
            balance     REAL    DEFAULT 0.0,       -- 余额
            currency    TEXT    DEFAULT 'CNY',     -- 币种
            branch      TEXT                       -- 开户网点
        )
    """)

    # 交易流水表
    cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            trans_date      TEXT    NOT NULL,          -- 交易日期
            trans_time      TEXT,                      -- 交易时间
            account_no      TEXT    NOT NULL,          -- 账号
            account_name    TEXT    NOT NULL,          -- 户名
            customer_no     TEXT    NOT NULL,          -- 客户号
            trans_type      TEXT,                      -- 交易类型
            amount          REAL,                      -- 交易金额
            direction       TEXT,                      -- 借/贷
            balance_after   REAL,                      -- 交易后余额
            channel         TEXT,                      -- 交易渠道
            remark          TEXT                       -- 摘要
        )
    """)

    # 若已有数据则跳过
    if cur.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] > 0:
        conn.close()
        return

    # -------- 示例数据 --------
    accounts_data = [
        ("6222021234567890", "张三",   "C10001", "110101199001011234", "2015-03-10", "正常",  58632.50,  "CNY", "北京朝阳支行"),
        ("6222021234567891", "李四",   "C10002", "310101198505152345", "2018-07-22", "正常",  12500.00,  "CNY", "上海浦东支行"),
        ("6222021234567892", "王五",   "C10003", "440101199210203456", "2020-01-05", "正常",  203400.00, "CNY", "广州天河支行"),
        ("6222021234567893", "赵六",   "C10004", "330101197803074567", "2012-11-30", "冻结",  0.00,      "CNY", "杭州西湖支行"),
        ("6222021234567894", "孙七",   "C10005", "210101200001015678", "2022-06-15", "正常",  3200.00,   "CNY", "沈阳和平支行"),
        ("6222021234567895", "周八",   "C10006", "510101196812126789", "2009-04-18", "正常",  987654.00, "CNY", "成都锦江支行"),
        ("6222021234567896", "吴九",   "C10007", "320101199507307890", "2019-09-09", "注销",  0.00,      "CNY", "南京鼓楼支行"),
        ("6222021234567897", "郑十",   "C10008", "130101198901018901", "2017-02-14", "正常",  45000.00,  "CNY", "石家庄桥西支行"),
        ("6222021234567898", "陈一一", "C10009", "420101200103030012", "2023-03-01", "正常",  8800.00,   "CNY", "武汉武昌支行"),
        ("6222021234567899", "林二二", "C10010", "350101197606061234", "2011-08-20", "正常",  320000.00, "CNY", "福州台江支行"),
    ]

    cur.executemany("""
        INSERT INTO accounts
            (account_no, account_name, customer_no, id_card, open_date, status, balance, currency, branch)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, accounts_data)

    # 为每个账户生成近 90 天的随机交易记录
    today = date.today()
    trans_types = ["转账汇款", "消费支出", "工资收入", "利息入账", "ATM取款", "手机支付", "网银支付", "跨行转账"]
    channels = ["网银", "手机银行", "柜台", "ATM", "POS", "第三方支付"]
    remarks = ["日常消费", "工资", "转账", "取现", "利息", "还款", "充值", "退款"]

    for acc_no, acc_name, cust_no, *_ in accounts_data:
        balance = random.uniform(1000, 50000)
        for day_offset in range(90):
            trans_date = (today - timedelta(days=day_offset)).strftime("%Y-%m-%d")
            n = random.randint(0, 3)
            for _ in range(n):
                amount = round(random.uniform(10, 5000), 2)
                direction = random.choice(["贷", "借"])
                if direction == "贷":
                    balance += amount
                else:
                    balance = max(0, balance - amount)
                cur.execute("""
                    INSERT INTO transactions
                        (trans_date, trans_time, account_no, account_name, customer_no,
                         trans_type, amount, direction, balance_after, channel, remark)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    trans_date,
                    f"{random.randint(8, 22):02d}:{random.randint(0, 59):02d}:{random.randint(0, 59):02d}",
                    acc_no, acc_name, cust_no,
                    random.choice(trans_types),
                    amount, direction,
                    round(balance, 2),
                    random.choice(channels),
                    random.choice(remarks),
                ))

    conn.commit()
    conn.close()
    print("数据库初始化完成，示例数据已写入。")
