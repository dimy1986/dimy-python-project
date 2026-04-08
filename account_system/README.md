# 账户与交易查询系统

基于 Flask + SQLite 的内网账户/交易信息查询 Web 应用。

## 功能

| 模块 | 说明 |
|------|------|
| 账户信息查询 | 按**账号**或**户名**（模糊匹配）检索账户基本信息，结果可下载为 Excel |
| 交易信息查询 | 按**时间范围** + **客户号 / 账号 / 户名**（三选一，模糊匹配）查询交易流水，结果可下载为 Excel |

## 环境要求

- Python 3.8+
- 依赖包见 `requirements.txt`

## 快速启动

```bash
cd account_system

# 安装依赖（仅首次）
pip install -r requirements.txt

# 启动服务
python app.py
```

服务启动后：
- 本机访问：`http://localhost:5000`
- 局域网其他机器访问：`http://<本机IP>:5000`

> 首次运行会自动创建 `bank_data.db` 数据库并写入示例数据。

## 对接真实数据库

若需替换为 MySQL / PostgreSQL，修改 `database.py` 中的 `get_db()` 和 `init_db()` 函数：
1. 将 `sqlite3.connect(DB_PATH)` 替换为相应数据库驱动的连接调用
2. 更新 SQL 方言（如日期函数、LIKE 语法等）
3. 删除 `init_db()` 中的示例数据插入部分，指向实际业务表

## 目录结构

```
account_system/
├── app.py              # Flask 主程序（路由、下载）
├── database.py         # 数据库连接与初始化
├── requirements.txt    # Python 依赖
├── bank_data.db        # SQLite 数据库（自动创建）
└── templates/
    ├── base.html            # 公共布局
    ├── index.html           # 首页
    ├── account_query.html   # 账户信息查询页
    └── transaction_query.html # 交易信息查询页
```
