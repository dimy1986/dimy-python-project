#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys

# ── 早期崩溃日志：在任何重量级 import 之前建立，确保错误信息能写到磁盘 ──────
def _write_crash(msg: str):
    """将崩溃信息写入与 exe（或脚本）同级的 crash.log，并同时尝试输出到 stderr。"""
    try:
        base = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__))
        crash_path = os.path.join(base, 'crash.log')
        with open(crash_path, 'a', encoding='utf-8', errors='replace') as f:
            f.write(msg + '\n')
    except Exception:
        pass
    try:
        print(msg, file=sys.stderr)
    except Exception:
        pass

# ── Paddle 在部分 Windows CPU 环境会触发 oneDNN/MKLDNN 相关报错 ──────────────
# 必须在 import paddle/paddleocr 之前设置，否则 paddle 初始化时已读取过环境变量
os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("FLAGS_use_onednn", "0")
os.environ.setdefault("FLAGS_enable_pir_api", "0")
os.environ.setdefault("FLAGS_use_pir_executor", "0")

# ── 抑制 paddle/glog 的 stderr/console 输出 ───────────────────────────────────
# console=False 只抑制 Python 的 console；paddle 底层使用 glog，若不设置，
# glog 会在 Windows 上触发新建 console 窗口（即"黑框"闪现）。
os.environ.setdefault("GLOG_logtostderr", "0")        # 不写 stderr
os.environ.setdefault("GLOG_minloglevel", "3")        # 只输出 FATAL（3），屏蔽 INFO/WARNING/ERROR
os.environ.setdefault("GLOG_v", "0")                  # 关闭 verbose logging
os.environ.setdefault("FLAGS_call_stack_level", "0")  # 不打印 paddle 调用栈

# ── 修复 paddleocr 的相对导入问题 ─────────────────────────────────────────────
try:
    import paddleocr as paddle_module
    paddle_path = os.path.dirname(paddle_module.__file__)
    if paddle_path not in sys.path:
        sys.path.insert(0, paddle_path)
except Exception as _e:
    import traceback as _tb
    _msg = (
        "=" * 60 + "\n"
        "[FATAL] import paddleocr 失败，程序无法启动。\n"
        f"错误类型: {type(_e).__name__}\n"
        f"错误信息: {_e}\n"
        f"Python 版本: {sys.version}\n"
        f"sys.path:\n" + "\n".join(f"  {p}" for p in sys.path) + "\n"
        "Traceback:\n" + _tb.format_exc() +
        "=" * 60
    )
    _write_crash(_msg)
    # 在 GUI 模式下用 tkinter 弹窗展示错误（console=False 时无命令行输出）
    try:
        import tkinter as _tk
        import tkinter.messagebox as _mb
        _root = _tk.Tk()
        _root.withdraw()
        _mb.showerror(
            "启动失败 — 请查看 crash.log",
            f"import paddleocr 失败，程序无法启动。\n\n"
            f"错误: {type(_e).__name__}: {_e}\n\n"
            "完整信息已写入 crash.log，请将该文件发给技术支持。"
        )
        _root.destroy()
    except Exception:
        pass
    sys.exit(1)

import re
import logging
import importlib
import string
from datetime import datetime
import pandas as pd
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox
import threading
from pathlib import Path

from PIL import Image
import numpy as np
import cv2

# ================== 日志 ==================
# 在 Windows GBK 控制台下确保 stdout/stderr 能输出 UTF-8（如 ✓ ✗ 等字符）
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, 'reconfigure'):
        try:
            _s.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

# ── 日志初始化 ─────────────────────────────────────────────────────────────────
# paddle 在 import 时已经向 root logger 添加了 handler，导致 basicConfig() 是
# no-op（Python 文档：root logger 已有 handler 时 basicConfig 什么都不做）。
# 用 force=True 强制重置，并直接操作 root logger 以确保 FileHandler 生效。
_log_file = os.path.join(
    os.path.dirname(sys.executable) if getattr(sys, 'frozen', False)
    else os.path.dirname(os.path.abspath(__file__)),
    'ocr_app.log'
)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(_log_file, encoding='utf-8'),
        logging.StreamHandler(),
    ],
    force=True,   # 强制清除 paddle 已添加的 handler，确保 FileHandler 生效
)


# ================== OCR初始化 ==================
# 获取 ocr_read 目录的相对路径
def get_ocr_base():
    """获取 OCR 模型基础目录"""
    if getattr(sys, 'frozen', False):
        # 如果是 exe 环境
        base_dir = os.path.dirname(sys.executable)
    else:
        # 如果是 Python 直接运行
        # main.py 在 dimy-python-project 下，需要向上一级找到 ocr_read 目录
        main_dir = os.path.dirname(os.path.abspath(__file__))
        base_dir = os.path.dirname(main_dir)  # D:\python_projects\ocr_read
        return base_dir

    return base_dir


EXTERNAL_OCR_BASE = get_ocr_base()
ocr = None


def _get_short_path(path: str) -> str:
    """将含非 ASCII 字符的路径转换为 Windows 8.3 短路径。

    PaddlePaddle 的 C++ 推理引擎使用 ANSI 文件 API，在非中文 locale 的 Windows
    上无法打开含中文字符的路径（analysis_predictor.cc fin.is_open() == false）。
    转为全 ASCII 的 8.3 短路径可绕过该限制。非 Windows 平台直接返回原路径。
    """
    if sys.platform != 'win32':
        return path
    if all(ord(c) < 128 for c in path):
        return path  # 纯 ASCII，无需转换
    try:
        import ctypes
        buf_size = ctypes.windll.kernel32.GetShortPathNameW(path, None, 0)
        if buf_size > 0:
            buf = ctypes.create_unicode_buffer(buf_size)
            ctypes.windll.kernel32.GetShortPathNameW(path, buf, buf_size)
            short = buf.value
            if short:
                logging.info(f"短路径转换: {path} -> {short}")
                return short
    except Exception as e:
        logging.warning(f"短路径转换失败（{e}），使用原路径: {path}")
    return path


def _init_ocr():
    """初始化OCR，使用外部模型"""
    global ocr

    # 第一步：导入PaddleOCR
    logging.info("尝试导入PaddleOCR...")
    try:
        import paddleocr
        logging.info(f"paddleocr模块位置: {paddleocr.__file__}")

        if not hasattr(paddleocr, 'PaddleOCR'):
            raise ImportError("paddleocr模块中找不到PaddleOCR类")

        PaddleOCR = paddleocr.PaddleOCR
        if PaddleOCR is None:
            raise ImportError("PaddleOCR类为None")

        logging.info("✓ PaddleOCR导入成功")
    except Exception as e:
        logging.error(f"✗ PaddleOCR导入失败: {e}")
        logging.error(traceback.format_exc())
        raise

    # 第二步：构建模型路径
    logging.info(f"OCR基础目录: {EXTERNAL_OCR_BASE}")
    model_base = os.path.join(EXTERNAL_OCR_BASE, "ocr_models")
    det_model = os.path.join(model_base, "ch_PP-OCRv4_det_infer")
    rec_model = os.path.join(model_base, "ch_PP-OCRv4_rec_infer")
    cls_model = os.path.join(model_base, "ch_ppocr_mobile_v2.0_cls_infer")

    # 验证模型目录
    models = {"det": det_model, "rec": rec_model, "cls": cls_model}
    for name, path in models.items():
        exists = os.path.isdir(path)
        logging.info(f"  {name}: {path} -> {'✓' if exists else '✗'}")
        if not exists:
            raise FileNotFoundError(f"模型目录不存在: {path}")

    # 将路径转为 8.3 短路径，避免 PaddlePaddle C++ 层在非中文 locale Windows
    # 上因 ANSI API 无法处理中文字符而报 "Cannot open file" 错误
    det_model = _get_short_path(det_model)
    rec_model = _get_short_path(rec_model)
    cls_model = _get_short_path(cls_model)

    # 第三步：初始化OCR
    try:
        logging.info("初始化PaddleOCR（外部模型）...")
        ocr = PaddleOCR(
            det_model_dir=det_model,
            rec_model_dir=rec_model,
            cls_model_dir=cls_model,
            use_angle_cls=True,
            lang="ch",
        )
        logging.info("✓ OCR初始化成功")
    except Exception as e:
        logging.error(f"✗ OCR初始化失败: {e}")
        logging.error(traceback.format_exc())
        raise


# 应用启动时调用
try:
    _init_ocr()
except Exception as e:
    import traceback as _tb2
    _msg2 = (
        "=" * 60 + "\n"
        "[FATAL] OCR初始化失败，程序无法启动。\n"
        f"错误类型: {type(e).__name__}\n"
        f"错误信息: {e}\n"
        f"OCR基础目录: {EXTERNAL_OCR_BASE}\n"
        "Traceback:\n" + _tb2.format_exc() +
        "=" * 60
    )
    logging.error(_msg2)
    _write_crash(_msg2)
    try:
        import tkinter as _tk2
        import tkinter.messagebox as _mb2
        _root2 = _tk2.Tk()
        _root2.withdraw()
        _mb2.showerror(
            "启动失败 — 请查看 crash.log",
            f"OCR初始化失败，程序无法启动。\n\n"
            f"错误: {type(e).__name__}: {e}\n\n"
            "完整信息已写入 crash.log，请将该文件发给技术支持。"
        )
        _root2.destroy()
    except Exception:
        pass
    sys.exit(1)

# ================== 注入OCR实例到提取模块 ==================
import voucher_extractor
voucher_extractor.set_ocr(ocr)

from voucher_extractor import BENPIAO_RULES, DAIKUAN_RULES, fix_account
from voucher_validator import extract_and_validate

# ================== 工具函数 ==================
def get_files(folder):
    files = []
    for root, _, filenames in os.walk(folder):
        for f in filenames:
            if f.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg')):
                files.append(os.path.join(root, f))
    return files

def clean_text(text):
    if not text:
        return ""
    return "\n".join([line.strip() for line in text.split("\n") if line.strip()])

def ocr_to_text(res):
    """完全按原始脚本的方式"""
    lines = []
    for line in res:
        for box in line:
            text = box[1][0]
            x, y = box[0][0]
            lines.append((y, x, text))
    lines.sort()
    return "\n".join([t[2] for t in lines])

def process_file(file_path):
    """完全按原始脚本的方式"""
    all_text = ""

    try:
        print(f"\n[OCR] 开始处理: {file_path}")

        if file_path.lower().endswith(".pdf"):
            import fitz
            from PIL import Image
            import io

            doc = fitz.open(file_path)

            for page in doc:
                print(f"[OCR] 处理PDF第 {page.number + 1} 页")
                pix = page.get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                img = img.convert("L")
                img = np.array(img)
                print("图像shape:", img.shape)

                try:
                    res = ocr.ocr(img)
                    text_part = ocr_to_text(res)
                    print(f"[OCR] 本页识别长度: {len(text_part)}")
                    all_text += text_part + "\n"
                except Exception as e:
                    print("❌ OCR内部错误:", repr(e))

        else:
            print("[OCR] 图片文件识别")
            # ✅ 修复：直接使用 ocr，不需要判断 _resolved_mode
            res = ocr.ocr(file_path)
            all_text = ocr_to_text(res)

        if not all_text.strip():
            print(f"⚠️ OCR未识别到任何文本: {file_path}")

        all_text = all_text.replace(" ", "")
        final_text = clean_text(all_text)

        print(f"[OCR] 总长度: {len(final_text)}")
        print(f"[OCR] 前100字符: {final_text[:100]}")

        return final_text

    except Exception as e:
        logging.error(f"OCR失败: {file_path}, {e}")
        print(f"❌ OCR异常: {e}")
        return ""

def detect_doc_type(text: str) -> str:
    """完全按原始脚本的方式"""
    if "银行本票" in text or "本票申请书" in text:
        return "benpiao"
    if "贷款还款凭证" in text or "还款凭证" in text:
        return "daikuan"
    if "贷款账号" in text and "本次偿还金额" in text:
        return "daikuan"
    return "unknown"

def save_excel_with_fallback(df: pd.DataFrame, output_path: str):
    try:
        df.to_excel(output_path, index=False)
        return output_path
    except PermissionError:
        base, ext = os.path.splitext(output_path)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fallback = f"{base}_{ts}{ext}"
        df.to_excel(fallback, index=False)
        print(f"文件被占用，已输出到新文件: {fallback}")
        return fallback

def process_one_folder(folder: str, progress_callback=None):
    """处理单个子目录（完全按原始脚本逻辑）"""
    print(f"\n========== 开始处理目录: {folder} ==========")
    if progress_callback:
        progress_callback(f"处理目录: {folder}")

    files = get_files(folder)
    if not files:
        print(f"目录下未找到待识别 pdf/图片: {folder}")
        if progress_callback:
            progress_callback(f"  ⚠️ 无文件")
        return

    all_data = []
    all_check = []
    all_check_long = []

    for f in files:
        print(f"\n===== 处理文件: {f} =====")
        if progress_callback:
            progress_callback(f"  📄 {os.path.basename(f)}")

        text = process_file(f)
        doc_type = detect_doc_type(text)
        print(f"识别类型: {doc_type}")

        data, check = extract_and_validate(text, [], f, sheet_name="", doc_type=doc_type)

        data["文件名"] = os.path.basename(f)
        check["文件名"] = os.path.basename(f)

        all_data.append(data)
        all_check.append(check)

        if doc_type == "benpiao":
            fields = list(BENPIAO_RULES.keys())
            amount_field = "金额大小写一致性"
        elif doc_type == "daikuan":
            fields = list(DAIKUAN_RULES.keys())
            amount_field = "金额一致性"
        else:
            fields = []
            amount_field = None

        for field in fields:
            all_check_long.append({
                "文件名": os.path.basename(f),
                "字段名": field,
                "提取值": data.get(field),
                "检查结果": check.get(field),
            })

        if amount_field and amount_field in check:
            if doc_type == "benpiao":
                amount_value = f"小写={data.get('金额小写')}, 大写={data.get('金额大写')}"
            else:
                amount_value = f"小写={data.get('本次偿还金额_小写')}, 大写={data.get('本次偿还金额_大写')}"

            all_check_long.append({
                "文件名": os.path.basename(f),
                "字段名": amount_field,
                "提取值": amount_value,
                "检查结果": check.get(amount_field),
            })

        if progress_callback:
            progress_callback(f"     ✅ 完成")

    df_data = pd.DataFrame(all_data)
    df_check = pd.DataFrame(all_check)
    df_check_long = pd.DataFrame(all_check_long)

    output_data = os.path.join(folder, "提取结果.xlsx")
    output_check = os.path.join(folder, "检查结果.xlsx")
    real_data = save_excel_with_fallback(df_data, output_data)
    real_check = save_excel_with_fallback(df_check_long if len(df_check_long) else df_check, output_check)
    print(f"\n已输出提取结果: {real_data}")
    print(f"已输出检查结果: {real_check}")

    if progress_callback:
        progress_callback(f"  ✅ 提取结果: {os.path.basename(real_data)}")
        progress_callback(f"  ✅ 检查结果: {os.path.basename(real_check)}\n")

def process_folder_with_subdirs(root: str, progress_callback=None):
    """遍历子目录处理（完全按原始脚本逻辑）"""
    if not os.path.exists(root):
        return False, f"❌ 目录不存在: {root}"

    subdirs = [
        os.path.join(root, d)
        for d in os.listdir(root)
        if os.path.isdir(os.path.join(root, d))
    ]

    if not subdirs:
        print(f"未发现子目录，直接按单目录模式处理: {root}")
        if progress_callback:
            progress_callback(f"未发现子目录，直接处理: {root}")
        process_one_folder(root, progress_callback)
        return True, "✅ 处理完成"

    for folder in subdirs:
        process_one_folder(folder, progress_callback)

    return True, "✅ 全部处理完成"


class VoucherExtractorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("凭证提取工具 v1.0.0")
        self.root.geometry("800x700")
        self.root.resizable(True, True)

        # 标题
        title = tk.Label(root, text="凭证提取工具", font=("微软雅黑", 20, "bold"), fg="#2196F3")
        title.pack(pady=15)

        # 说明
        info = tk.Label(root, text="选择包含凭证子文件夹的父目录", font=("微软雅黑", 11), fg="#666")
        info.pack(pady=5)

        # 文件夹选择
        select_frame = tk.Frame(root)
        select_frame.pack(pady=10, padx=30, fill="x")

        tk.Label(select_frame, text="选择文件夹:", font=("微软雅黑", 11)).pack(anchor="w", pady=(0, 5))

        folder_input_frame = tk.Frame(select_frame)
        folder_input_frame.pack(fill="x", pady=(0, 10))

        self.folder_path = tk.StringVar()
        folder_entry = tk.Entry(folder_input_frame, textvariable=self.folder_path, font=("微软雅黑", 10))
        folder_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        browse_btn = tk.Button(folder_input_frame, text="浏览...", command=self.select_folder, width=12, font=("微软雅黑", 11))
        browse_btn.pack(side="left")

        # ========== 日志区 ==========
        log_label = tk.Label(root, text="处理日志:", font=("微软雅黑", 11))
        log_label.pack(anchor="w", padx=30, pady=(5, 3))

        log_frame = tk.Frame(root)
        log_frame.pack(padx=30, pady=(0, 10), fill="both", expand=False)

        self.output_text = tk.Text(log_frame, height=8, font=("Courier New", 9), bg="#f5f5f5", relief="sunken",
                                   bd=1)
        self.output_text.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(log_frame, command=self.output_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.output_text.config(yscrollcommand=scrollbar.set)

        # 按钮
        button_frame = tk.Frame(root)
        button_frame.pack(pady=15, fill="x")

        btn_container = tk.Frame(button_frame)
        btn_container.pack()

        self.start_btn = tk.Button(
            btn_container,
            text="▶ 开始处理",
            command=self.start_process,
            width=16,
            height=2,
            bg="#4CAF50",
            fg="white",
            font=("微软雅黑", 12, "bold"),
            relief="raised"
        )
        self.start_btn.pack(side="left", padx=10)

        self.clear_btn = tk.Button(
            btn_container,
            text="🗑 清空日志",
            command=self.clear_log,
            width=16,
            height=2,
            font=("微软雅黑", 12, "bold"),
            relief="raised"
        )
        self.clear_btn.pack(side="left", padx=10)

        self.exit_btn = tk.Button(
            btn_container,
            text="❌ 退出",
            command=root.quit,
            width=16,
            height=2,
            font=("微软雅黑", 12, "bold"),
            relief="raised"
        )
        self.exit_btn.pack(side="left", padx=10)

    def select_folder(self):
        folder = filedialog.askdirectory(title="选择包含凭证子文件夹的父目录")
        if folder:
            self.folder_path.set(folder)
            self.log(f"📁 已选择: {folder}")

    def log(self, message):
        self.output_text.insert("end", message + "\n")
        self.output_text.see("end")
        self.root.update()

    def clear_log(self):
        self.output_text.delete("1.0", "end")

    def start_process(self):
        folder = self.folder_path.get()

        if not folder:
            messagebox.showerror("错误", "请先选择文件夹")
            return

        if not Path(folder).exists():
            messagebox.showerror("错误", "文件夹不存在")
            return

        self.start_btn.config(state="disabled")
        self.clear_log()

        thread = threading.Thread(target=self._process_thread, args=(folder,))
        thread.daemon = True
        thread.start()

    def _process_thread(self, folder):
        try:
            success, message = process_folder_with_subdirs(folder, self.log)
            if success:
                messagebox.showinfo("完成", message)
            else:
                messagebox.showerror("错误", message)
        except Exception as e:
            messagebox.showerror("错误", f"处理失败: {str(e)}")
            import traceback
            traceback.print_exc()
        finally:
            self.start_btn.config(state="normal")


if __name__ == "__main__":
    root = tk.Tk()
    app = VoucherExtractorGUI(root)
    root.mainloop()