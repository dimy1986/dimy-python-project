# 账户与交易查询系统

基于 Flask + SQLite 的内网账户/交易信息查询 Web 应用。

## 功能

| 模块 | 说明 |
|------|------|
| 账户信息查询 | 按**账号**或**户名**（模糊匹配）检索账户基本信息，结果可下载为 Excel |
| 交易信息查询 | 按**时间范围** + **客户号 / 账号 / 户名**（三选一，模糊匹配）查询交易流水，结果可下载为 Excel |

---

## 方式一：直接用 Python 运行（开发 / 有 Python 的机器）

### 环境要求

- Python 3.8+
- 依赖包见 `requirements.txt`

### 启动

```bash
cd account_system
pip install -r requirements.txt
python app.py
```

服务启动后：
- 本机访问：`http://localhost:5000`
- 局域网其他机器访问：`http://<本机IP>:5000`

> 首次运行会自动创建 `bank_data.db` 数据库并写入示例数据。

---

## 方式二：打包为独立 exe，拷贝到没有 Python 的内网电脑运行

### 打包步骤（在一台安装了 Python 的 Windows 机器上执行一次）

```bat
cd account_system
build_windows.bat
```

脚本会自动安装 PyInstaller 和依赖，然后生成 `dist\query_system\` 文件夹。

### 分发

将整个 `dist\query_system\` 文件夹**完整拷贝**到目标内网电脑（无需安装 Python）。

### 在目标电脑上运行

双击 `query_system.exe`，程序自动启动并打开浏览器访问查询系统。

> **注意**：`bank_data.db` 数据库文件会在 `query_system.exe` 同目录下自动创建（首次运行）。
> 升级 exe 时，只需替换 `query_system.exe`，数据库文件会保留。

### Linux / macOS 打包

```bash
cd account_system
bash build_linux.sh
# 产物位于 dist/query_system/query_system
```

---

## 对接真实数据库

若需替换为 MySQL / PostgreSQL，修改 `database.py` 中的 `get_db()` 和 `init_db()` 函数：
1. 将 `sqlite3.connect(DB_PATH)` 替换为相应数据库驱动的连接调用
2. 更新 SQL 方言（如日期函数、LIKE 语法等）
3. 删除 `init_db()` 中的示例数据插入部分，指向实际业务表

---

## 目录结构

```
account_system/
├── app.py                    # Flask 主程序（路由、下载、打包路径处理）
├── database.py               # 数据库连接与初始化（打包路径兼容）
├── query_system.spec         # PyInstaller 打包配置
├── build_windows.bat         # Windows 一键打包脚本
├── build_linux.sh            # Linux/macOS 一键打包脚本
├── requirements.txt          # Python 依赖
├── bank_data.db              # SQLite 数据库（运行时自动创建，不提交到 git）
└── templates/
    ├── base.html             # 公共布局
    ├── index.html            # 首页
    ├── account_query.html    # 账户信息查询页
    └── transaction_query.html # 交易信息查询页
```

