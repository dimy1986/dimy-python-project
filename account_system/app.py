#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
账户与交易查询系统 — Flask 主程序
运行: python app.py
访问: http://localhost:5000 (内网可通过 http://<本机IP>:5000 访问)

数据库连接参数由 config.ini 提供，不在代码中硬编码。
SQL 查询语句由 queries/*.sql 文件提供，不在代码中写死。
每个查询页面的元信息由对应的 queries/*.json 文件描述。
新增查询只需在 queries/ 目录下放入 <name>.sql 和 <name>.json，
无需修改本文件。
"""
from database import _tunnel_cleanup_worker
import atexit
import datetime
import decimal
import json
import os
import sys
import tempfile
import threading
_download_semaphore = threading.Semaphore(5)
import webbrowser
from flask import Response
import csv
import io
import tempfile, os
import xlsxwriter
from flask import (
    Flask,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

from database import (
    add_user,
    change_password,
    delete_user,
    get_db,
    get_queries_dir,
    init_users_db,
    iter_query_db,
    list_users,
    load_query,
    query_db,
    start_tunnel,
    stop_tunnel,
    user_count,
    verify_user,
)


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
app.secret_key = os.urandom(24)


def _json_safe(value):
    """Convert a single DB value to a JSON-serializable type."""
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (datetime.date, datetime.datetime)):
        return str(value)
    if value is None:
        return ""
    return value


def _serialize_rows(rows: list) -> list:
    """Convert DB result rows to JSON-safe dicts."""
    return [{k: _json_safe(v) for k, v in row.items()} for row in rows]


_PAGE_LIMIT = 100  # 单次页面展示的最大行数


# ──────────────────────────── 查询配置加载 ────────────────────────────

def _load_all_query_configs() -> dict:
    """
    扫描 queries/ 目录，按文件名顺序加载所有 *.json 配置文件。
    文件名（不含扩展名）同时作为查询 ID 和路由端点名称。
    """
    configs: dict = {}
    d = get_queries_dir()
    if not os.path.isdir(d):
        return configs
    for fname in sorted(os.listdir(d)):
        if fname.endswith(".json"):
            qid = fname[:-5]
            with open(os.path.join(d, fname), encoding="utf-8") as f:
                configs[qid] = json.load(f)
    return configs


_query_configs = _load_all_query_configs()


@app.context_processor
def _inject_query_configs():
    """将所有查询配置注入到每个模板的上下文，供导航栏、首页等公共模板使用。"""
    return {"query_configs": _query_configs}


# ──────────────────────────── 数据库连接管理 ────────────────────────────

def get_connection(inceptor: str = "inceptor"):
    """
    返回当前请求中指定 Inceptor 节点的数据库连接（懒建立，请求内复用）。
    所有连接统一存储在 g._db_connections 字典中，由 teardown 统一关闭。
    """
    if not hasattr(g, "_db_connections"):
        g._db_connections = {}
    if inceptor not in g._db_connections:
        g._db_connections[inceptor] = get_db(inceptor)
    return g._db_connections[inceptor]


@app.teardown_appcontext
def close_connection(exception):
    connections = g.pop("_db_connections", None)
    if connections:
        for db in connections.values():
            db.close()


# ──────────────────────────── 用户认证 ────────────────────────────

# 启动时初始化用户数据库，自动从 config.ini [auth] 迁移历史用户（如有）
try:
    init_users_db(migrate_from_config=True)
except Exception as _e:
    print(f"[警告] 用户数据库初始化失败: {_e}")


def _auth_enabled() -> bool:
    """当用户数据库中存在至少一个用户时启用认证。"""
    try:
        return user_count() > 0
    except Exception:
        return False


@app.before_request
def _require_login():
    """所有路由（除登录页、登出页和静态资源外）必须先登录。"""
    if not _auth_enabled():
        return
    if request.endpoint in ("login", "logout", "static"):
        return
    if not session.get("logged_in"):
        return redirect(url_for("login", next=request.path))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if verify_user(username, password):
            session["logged_in"] = True
            session["username"] = username
            # 只允许跳转到本站内部路径，防止开放重定向攻击
            raw_next = request.form.get("next", "")
            from urllib.parse import urlparse
            parsed = urlparse(raw_next)
            # 仅接受相对路径（无 scheme 和 netloc）
            if raw_next and not parsed.scheme and not parsed.netloc:
                next_url = raw_next
            else:
                next_url = url_for("index")
            return redirect(next_url)
        error = "用户名或密码错误，请重试。"
    return render_template("login.html", error=error,
                           next=request.args.get("next", ""))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ──────────────────────────── 用户管理（管理员）────────────────────────────

@app.route("/admin/users")
def admin_users():
    users = list_users()
    return render_template("admin_users.html", users=users)


@app.route("/admin/users/add", methods=["POST"])
def admin_users_add():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    is_admin = bool(request.form.get("is_admin"))
    error = ""
    if not username or not password:
        error = "用户名和密码不能为空。"
    else:
        try:
            add_user(username, password, is_admin=is_admin)
        except ValueError as exc:
            error = str(exc)
    users = list_users()
    return render_template("admin_users.html", users=users, error=error)


@app.route("/admin/users/delete", methods=["POST"])
def admin_users_delete():
    username = request.form.get("username", "").strip()
    current = session.get("username", "")
    error = ""
    if username == current:
        error = "不能删除当前登录的用户。"
    elif username:
        delete_user(username)
    users = list_users()
    return render_template("admin_users.html", users=users, error=error)


@app.route("/admin/users/change_password", methods=["POST"])
def admin_change_password():
    username = request.form.get("username", "").strip()
    new_password = request.form.get("new_password", "")
    error = ""
    if not username or not new_password:
        error = "用户名和新密码不能为空。"
    else:
        change_password(username, new_password)
    users = list_users()
    return render_template("admin_users.html", users=users, error=error,
                           pw_changed=username if not error else "")


# ──────────────────────────── 首页 ────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ──────────────────────────── 动态路由注册 ────────────────────────────

def _build_params(cfg: dict, keyword: str, date_from: str, date_to: str) -> tuple:
    """根据查询配置组装 SQL 参数元组。"""
    pattern = cfg.get("params_pattern")
    if pattern:
        if cfg.get("date_format") == "yyyymm":
            date_from = date_from[:7].replace("-", "")
            date_to   = date_to[:7].replace("-", "")
        mapping = {"date_from": date_from, "date_to": date_to, "keyword": keyword}
        return tuple(mapping[k] for k in pattern)
    if cfg.get("date_range"):
        return (date_from, date_to, f"%{keyword}%")
    return (f"%{keyword}%",)


def _make_query_view(query_id: str, cfg: dict):
    """为指定查询 ID 生成 GET / POST 路由处理函数。"""
    allowlist = {sf["value"] for sf in cfg["search_fields"]}
    default_field = cfg["search_fields"][0]["value"]
    inceptor = cfg.get("inceptor", "inceptor")

    def view():
        results = []
        keyword = ""
        search_type = default_field
        date_from = ""
        date_to = ""
        searched = False
        error = ""

        if request.method == "POST":
            keyword = request.form.get("keyword", "").strip()
            search_type = request.form.get("search_type", default_field)
            searched = True

            if cfg.get("date_range"):
                date_from = request.form.get("date_from", "").strip()
                date_to = request.form.get("date_to", "").strip()
                if not date_from or not date_to:
                    error = "请填写查询起止日期。"
                elif date_from > date_to:
                    error = "开始日期不能晚于结束日期。"
                elif not keyword:
                    error = "请输入关键词。"

            if not error and keyword:
                field = search_type if search_type in allowlist else default_field
                try:
                    sql = load_query(query_id).format(field=field)
                    results = query_db(
                        get_connection(inceptor), sql,
                        _build_params(cfg, keyword, date_from, date_to),
                    )
                    # 保存本次查询参数，以便切换页面后返回时自动恢复
                    session[query_id] = {
                        "keyword": keyword,
                        "search_type": search_type,
                        "date_from": date_from,
                        "date_to": date_to,
                    }
                except Exception as exc:
                    error = f"查询失败：{exc}"

        else:
            # GET 请求：从 session 恢复表单输入值（结果由客户端 sessionStorage 恢复）
            saved = session.get(query_id)
            if saved:
                keyword = saved.get("keyword", "")
                search_type = saved.get("search_type", default_field)
                date_from = saved.get("date_from", "")
                date_to = saved.get("date_to", "")

        total_count = len(results)
        display_results = results[:_PAGE_LIMIT]

        return render_template(
            "query.html",
            cfg=cfg,
            query_id=query_id,
            results=display_results,
            total_count=total_count,
            page_limit=_PAGE_LIMIT,
            keyword=keyword,
            search_type=search_type,
            date_from=date_from,
            date_to=date_to,
            searched=searched,
            error=error,
        )

    view.__name__ = query_id
    return view


def _make_download_view(query_id: str, cfg: dict):
    """为指定查询 ID 生成 Excel 下载路由处理函数。

    使用 xlsxwriter constant_memory 模式 + 磁盘临时文件流式写入，
    避免几十万行数据一次性载入内存或缓存在 BytesIO 中导致 OOM / 卡死。
    """
    allowlist = {sf["value"] for sf in cfg["search_fields"]}
    default_field = cfg["search_fields"][0]["value"]
    inceptor = cfg.get("inceptor", "inceptor")

    def download():
        keyword = request.form.get("keyword", "").strip()
        search_type = request.form.get("search_type", default_field)
        date_from = request.form.get("date_from", "").strip()
        date_to = request.form.get("date_to", "").strip()

        field = search_type if search_type in allowlist else default_field
        sql = load_query(query_id).format(field=field)

        sheet = cfg.get("sheet_name", "查询结果")

        # 写到磁盘临时文件，避免整个 workbook 缓存在内存中
        tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        tmp_path = tmp.name
        tmp.close()

        try:
            workbook = xlsxwriter.Workbook(tmp_path, {"constant_memory": True})
            worksheet = workbook.add_worksheet(sheet[:31])  # Excel 表名最长 31 字符

            headers_written = False
            row_idx = 0
            for record in iter_query_db(
                get_connection(inceptor), sql,
                _build_params(cfg, keyword, date_from, date_to),
            ):
                if not headers_written:
                    for col_idx, key in enumerate(record.keys()):
                        worksheet.write(0, col_idx, key)
                    headers_written = True
                    row_idx = 1

                for col_idx, value in enumerate(record.values()):
                    v = _json_safe(value)
                    worksheet.write(row_idx, col_idx, v)
                row_idx += 1

            workbook.close()

            response = send_file(
                tmp_path,
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                as_attachment=True,
                download_name=f"{sheet}.xlsx",
            )

            @response.call_on_close
            def _cleanup():
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

            return response

        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    download.__name__ = f"{query_id}_download"
    return download

def _make_download_view_stream(query_id: str, cfg: dict):


    allowlist = {sf["value"] for sf in cfg["search_fields"]}
    default_field = cfg["search_fields"][0]["value"]
    inceptor = cfg.get("inceptor", "inceptor")

    def download():
        with _download_semaphore:

            keyword = request.form.get("keyword", "").strip()
            search_type = request.form.get("search_type", default_field)
            date_from = request.form.get("date_from", "").strip()
            date_to = request.form.get("date_to", "").strip()
            file_format = request.form.get("format", "csv").lower()

            field = search_type if search_type in allowlist else default_field
            sql = load_query(query_id).format(field=field)
            params = _build_params(cfg, keyword, date_from, date_to)

            # ==========================================================
            # ✅ CSV（保持你原逻辑）
            # ==========================================================
            if file_format == "csv":

                conn = get_db(inceptor)

                def generate():
                    output = io.StringIO()
                    writer = csv.writer(output)

                    yield "\ufeff"

                    first = True
                    row_count = 0
                    buffer_limit = 100

                    try:
                        for record in iter_query_db(conn, sql, params):
                            if first:
                                writer.writerow(record.keys())
                                first = False

                            row = ["" if v is None else str(v) for v in record.values()]
                            writer.writerow(row)
                            row_count += 1

                            if row_count % buffer_limit == 0:
                                yield output.getvalue()
                                output.seek(0)
                                output.truncate(0)

                        if output.tell() > 0:
                            yield output.getvalue()

                        if row_count == 0:
                            writer.writerow(["无数据"])
                            yield output.getvalue()

                    except Exception as e:
                        import traceback
                        print("下载异常:", e)
                        traceback.print_exc()

                    finally:
                        conn.close()   # ✅ 正确位置（generator 内）

                return Response(
                    generate(),
                    mimetype="text/csv; charset=utf-8",
                    headers={
                        "Content-Disposition": f"attachment; filename={query_id}.csv",
                        "Cache-Control": "no-cache, no-store, must-revalidate",
                        "Pragma": "no-cache",
                        "Expires": "0"
                    }
                )

            # ==========================================================
            # 🔥 Excel（已替换为高性能版本）
            # ==========================================================
            elif file_format == "xlsx":



                sheet = cfg.get("sheet_name", "查询结果")

                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
                tmp_path = tmp.name
                tmp.close()

                conn = get_db(inceptor)

                try:
                    workbook = xlsxwriter.Workbook(tmp_path, {"constant_memory": True})
                    worksheet = workbook.add_worksheet(sheet[:31])

                    headers_written = False
                    row_idx = 0

                    for record in iter_query_db(conn, sql, params):

                        if not headers_written:
                            for col_idx, key in enumerate(record.keys()):
                                worksheet.write(0, col_idx, key)
                            headers_written = True
                            row_idx = 1

                        for col_idx, value in enumerate(record.values()):
                            worksheet.write(
                                row_idx,
                                col_idx,
                                "" if value is None else str(value)
                            )

                        row_idx += 1

                    if not headers_written:
                        worksheet.write(0, 0, "无数据")

                    workbook.close()

                    response = send_file(
                        tmp_path,
                        as_attachment=True,
                        download_name=f"{query_id}.xlsx"
                    )

                    @response.call_on_close
                    def cleanup():
                        try:
                            os.unlink(tmp_path)
                        except:
                            pass

                    return response

                except Exception as e:
                    import traceback
                    print("Excel下载异常:", e)
                    traceback.print_exc()
                    return "导出失败", 500

                finally:
                    conn.close()   # ✅ 必须在外层 finally

            # ==========================================================
            # ❌ 不支持格式
            # ==========================================================
            else:
                return "不支持的格式", 400

    download.__name__ = f"{query_id}_download_stream"
    return download

def _make_api_view(query_id: str, cfg: dict):
    """为指定查询 ID 生成 AJAX JSON API 路由处理函数（POST）。"""
    allowlist = {sf["value"] for sf in cfg["search_fields"]}
    default_field = cfg["search_fields"][0]["value"]
    inceptor = cfg.get("inceptor", "inceptor")

    def api():
        keyword = request.form.get("keyword", "").strip()
        search_type = request.form.get("search_type", default_field)
        date_from = request.form.get("date_from", "").strip()
        date_to = request.form.get("date_to", "").strip()

        error = ""
        if cfg.get("date_range"):
            if not date_from or not date_to:
                error = "请填写查询起止日期。"
            elif date_from > date_to:
                error = "开始日期不能晚于结束日期。"
            elif not keyword:
                error = "请输入关键词。"

        rows = []
        if not error and keyword:
            field = search_type if search_type in allowlist else default_field
            try:
                sql = load_query(query_id).format(field=field)
                rows = query_db(
                    get_connection(inceptor), sql,
                    _build_params(cfg, keyword, date_from, date_to),
                )
                session[query_id] = {
                    "keyword": keyword,
                    "search_type": search_type,
                    "date_from": date_from,
                    "date_to": date_to,
                }
            except Exception as exc:
                app.logger.error("API query error [%s]: %s", query_id, exc)
                error = "查询失败，请联系管理员。"
        serialized = _serialize_rows(rows)
        return jsonify({
            "rows": serialized[:_PAGE_LIMIT],
            "total_count": len(serialized),
            "keyword": keyword,
            "search_type": search_type,
            "date_from": date_from,
            "date_to": date_to,
            "error": error,
        })

    api.__name__ = f"{query_id}_api"
    return api


# 遍历所有已加载的查询配置，自动注册查询路由、下载路由和 API 路由
for _qid, _cfg in _query_configs.items():
    app.add_url_rule(
        f"/{_qid}",
        endpoint=_qid,
        view_func=_make_query_view(_qid, _cfg),
        methods=["GET", "POST"],
    )
    app.add_url_rule(
        f"/{_qid}/download",
        endpoint=f"{_qid}_download",
        view_func=_make_download_view_stream(_qid, _cfg),
        methods=["POST"],
    )
    app.add_url_rule(
        f"/api/{_qid}",
        endpoint=f"{_qid}_api",
        view_func=_make_api_view(_qid, _cfg),
        methods=["POST"],
    )


# ──────────────────────────── 入口 ────────────────────────────

if __name__ == "__main__":
    # 启动 SSH 隧道（失败时给出清晰提示后退出）
    # try:
    #     local_port = start_tunnel()
    #     print(f"SSH 隧道已建立，本地端口: {local_port}")
    # except Exception as exc:
    #     print(f"[错误] SSH 隧道启动失败: {exc}")
    #     sys.exit(1)

    # 启动隧道清理线程（空闲 3 分钟后自动关闭）


    cleanup_thread = threading.Thread(target=_tunnel_cleanup_worker, daemon=True)
    cleanup_thread.start()
    # ✅ 改这里：不在启动时强制建立隧道
    print("程序启动，不预先建立 SSH 隧道")

    # 注册退出时关闭隧道
    atexit.register(stop_tunnel)

    port = 5000
    url = f"http://localhost:{port}"

    # 在后台守护线程中启动 Flask（主线程留给托盘图标）
    flask_thread = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False),
        daemon=True,
    )
    flask_thread.start()

    # 延迟 1.2 秒后自动打开默认浏览器（给 Flask 启动时间）
    def _open_browser():
        import time
        time.sleep(1.2)
        webbrowser.open(url)

    threading.Thread(target=_open_browser, daemon=True).start()

    # 尝试以系统托盘图标形式运行（打包 exe 时隐藏到右下角通知区域）
    try:
        import pystray
        from PIL import Image, ImageDraw

        def _make_tray_image():
            """创建一个简单的蓝色正方形托盘图标。"""
            size = 64
            img = Image.new("RGB", (size, size), "#1a478a")
            draw = ImageDraw.Draw(img)
            # 中心白色小方块，模拟"查"字
            m = size // 4
            draw.rectangle([m, m, size - m, size - m], fill="white")
            return img

        def _on_open_browser(icon, item):
            webbrowser.open(url)

        def _on_quit(icon, item):
            icon.stop()
            stop_tunnel()
            os._exit(0)

        tray_menu = pystray.Menu(
            pystray.MenuItem("打开浏览器", _on_open_browser, default=True),
            pystray.MenuItem("退出", _on_quit),
        )
        tray_icon = pystray.Icon(
            "query_system",
            _make_tray_image(),
            "账户与交易查询系统",
            tray_menu,
        )
        # 阻塞运行托盘，直到用户通过菜单「退出」
        tray_icon.run()
    except ImportError:
        # pystray 不可用时（纯命令行/开发环境），保持阻塞直到手动终止
        print(f"启动成功，请在浏览器访问: {url}")
        print("按 Ctrl+C 退出程序")
        flask_thread.join()
