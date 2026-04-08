# 账户与交易查询系统

基于 Flask + Inceptor (Hive/LDAP) 的内网账户/交易信息查询 Web 应用。
通过 SSH 隧道安全连接内网 Inceptor 服务，连接参数从外部配置文件读取，SQL 查询从外部文件加载。

## 功能

| 模块 | 说明 |
|------|------|
| 账户信息查询 | 按**账号**或**户名**（模糊匹配）检索账户基本信息，结果可下载为 Excel |
| 交易信息查询 | 按**时间范围** + **客户号 / 账号 / 户名**（三选一，模糊匹配）查询交易流水，结果可下载为 Excel |

---

## 首次配置（必须）

### 1. 创建 config.ini

将 `config.ini.example` 复制为 `config.ini`（与 `app.py` 或 `query_system.exe` 同级目录），
然后填写实际的 SSH 跳板机和 Inceptor 连接参数：

```ini
[ssh]
host     = YOUR_SSH_JUMP_HOST    # SSH 跳板机真实 IP 或域名
port     = 22
username = YOUR_SSH_USERNAME
password = 你的SSH密码

[inceptor]
host       = YOUR_INCEPTOR_HOST  # Inceptor 内网真实 IP 或域名
port       = 10002
local_port = 9999               # 本地空闲端口，不冲突即可
username   = YOUR_INCEPTOR_USERNAME
password   = 你的Inceptor密码
database   = YOUR_DATABASE_NAME
```

> ⚠️ `config.ini` 含有敏感密码，已加入 `.gitignore`，请勿提交到版本库。

### 2. 按需修改 SQL 查询文件

`queries/` 目录下有两个可自定义的 SQL 文件，请根据实际 Inceptor 表结构修改：

| 文件 | 说明 |
|------|------|
| `queries/account_query.sql` | 账户查询 SQL 模板 |
| `queries/transaction_query.sql` | 交易查询 SQL 模板 |

SQL 文件中的约定：
- `{field}` — Python 代码替换为白名单校验后的列名（如 `account_no`、`account_name`）
- `%s` — pyhive 参数占位符，对应实际查询值

---

## 方式一：直接用 Python 运行（有 Python 的机器）

### 环境要求

- Python 3.8+
- 系统 SASL 库（Linux 需 `apt install libsasl2-dev`，Windows 由 pip 自动安装）

### 启动

```bash
cd account_system
pip install -r requirements.txt
python app.py
```

启动后自动打开浏览器访问 `http://localhost:5000`。
局域网其他机器可通过 `http://<本机IP>:5000` 访问。

---

## 方式二：打包为独立 exe，拷贝到没有 Python 的内网电脑运行

### 打包步骤（在一台安装了 Python 的 Windows 机器上执行一次）

```bat
cd account_system
build_windows.bat
```

脚本会自动安装所有依赖和 PyInstaller，生成 `dist\query_system\` 文件夹。

### 分发

将整个 `dist\query_system\` 文件夹**完整拷贝**到目标内网电脑（无需安装 Python），
然后将 `config.ini` 放到 `query_system.exe` 同级目录。

可选：把自定义的 `queries\` 目录也放到 `query_system.exe` 同级，覆盖打包内置版本。

### 在目标电脑上运行

双击 `query_system.exe`，程序自动建立 SSH 隧道、连接 Inceptor 并打开浏览器。

### Linux / macOS 打包

```bash
cd account_system
bash build_linux.sh
# 产物位于 dist/query_system/query_system
```

---

## 架构说明

```
用户浏览器
    │  HTTP
    ▼
Flask 应用 (app.py)
    │  调用 query_db()，SQL 从 queries/*.sql 加载
    ▼
database.py
    │  pyhive.hive.Connection
    ▼
SSH 隧道 (sshtunnel) → 127.0.0.1:9999
    │  SSH 转发
    ▼
跳板机 (214.20.0.75)
    │  内网访问
    ▼
Inceptor 服务 (10.48.*.136:10002)
```

---

## 目录结构

```
account_system/
├── app.py                    # Flask 主程序（路由、下载）
├── database.py               # SSH 隧道 + pyhive 连接 + query_db() / load_query()
├── config.ini.example        # 连接配置模板（提交到 git）
├── config.ini                # 实际连接配置（含密码，不提交到 git）
├── queries/
│   ├── account_query.sql     # 账户查询 SQL 模板（可自定义）
│   └── transaction_query.sql # 交易查询 SQL 模板（可自定义）
├── query_system.spec         # PyInstaller 打包配置
├── build_windows.bat         # Windows 一键打包脚本
├── build_linux.sh            # Linux/macOS 一键打包脚本
├── requirements.txt          # Python 依赖
└── templates/
    ├── base.html             # 公共布局
    ├── index.html            # 首页
    ├── account_query.html    # 账户信息查询页
    └── transaction_query.html # 交易信息查询页
```

