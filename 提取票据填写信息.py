import os
import re
import logging
import importlib
import string
from datetime import datetime
import pandas as pd
from pdf2image import convert_from_path
import tempfile


# Paddle 在部分 Windows CPU 环境会触发 oneDNN/MKLDNN 相关报错；
# 这里先禁用以提升稳定性（不影响正确性，只可能稍降速度）。
os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("FLAGS_use_onednn", "0")
os.environ.setdefault("FLAGS_enable_pir_api", "0")
os.environ.setdefault("FLAGS_use_pir_executor", "0")

PaddleOCR = None

from PIL import Image
import numpy as np
import cv2

def load_pdf2image_convert():
    """
    延迟导入 pdf2image，避免 IDE 在未安装依赖时提示 unresolved reference。
    """
    try:
        module = importlib.import_module("pdf2image")
        return getattr(module, "convert_from_path", None)
    except Exception:
        return None

# ================== 日志 ==================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ================== OCR初始化（自动选择最优方案） ==================
# 优先级：Python版 PaddleOCR（准确率/可控性更好） > PaddleOCR-json（如果你有exe）
OCR_MODE = "auto"  # auto | paddleocr | paddleocr_json
PADDLEOCR_JSON_EXE = r""  # 可选：例如 D:\tools\PaddleOCR-json\PaddleOCR_json.exe
PADDLEOCR_JSON_MODELS = r""  # 可选：例如 D:\tools\PaddleOCR-json\models
EXTERNAL_OCR_BASE = r"D:\ocr_read"  # 外部OCR目录，优先使用其下 ocr_models

ocr = None  # Python PaddleOCR
ppocr = None  # PaddleOCR-json


def find_ocr_read_folder():
    # 先用显式路径
    if EXTERNAL_OCR_BASE and os.path.isdir(EXTERNAL_OCR_BASE):
        return EXTERNAL_OCR_BASE
    # 再扫盘符
    for drive in string.ascii_uppercase:
        path = f"{drive}:\\ocr_read"
        if os.path.isdir(path):
            return path
    return None


def get_external_model_dirs():
    base = find_ocr_read_folder()
    if not base:
        return None, None, None
    model_base_path = os.path.join(base, "ocr_models")
    det_model_dir = os.path.join(model_base_path, "ch_PP-OCRv4_det_infer")
    rec_model_dir = os.path.join(model_base_path, "PP-OCRv4_server_rec_infer")
    cls_model_dir = os.path.join(model_base_path, "ch_ppocr_mobile_v2.0_cls_infer")
    if all(os.path.isdir(p) for p in [det_model_dir, rec_model_dir, cls_model_dir]):
        return det_model_dir, rec_model_dir, cls_model_dir
    return None, None, None


_resolved_mode = None
if OCR_MODE in ("auto", "paddleocr"):
    try:
        from paddleocr import PaddleOCR as _PaddleOCR
    except Exception:
        _PaddleOCR = None

    PaddleOCR = _PaddleOCR

if OCR_MODE in ("auto", "paddleocr") and PaddleOCR is not None:
    _resolved_mode = "paddleocr"
    det_model_dir, rec_model_dir, cls_model_dir = get_external_model_dirs()
    if det_model_dir and rec_model_dir and cls_model_dir:
        logging.info(
            "使用外部OCR模型: det=%s rec=%s cls=%s",
            det_model_dir, rec_model_dir, cls_model_dir
        )
        ocr = PaddleOCR(
            det_model_dir=det_model_dir,
            rec_model_dir=rec_model_dir,
            cls_model_dir=cls_model_dir,
            use_angle_cls=True,
            lang="ch",
        )
    else:
        logging.info("未找到外部OCR模型目录，回退到默认PaddleOCR模型。")
        # PaddleOCR 3.x：use_angle_cls 已弃用，改用 use_textline_orientation
        ocr = PaddleOCR(use_textline_orientation=True, lang="ch")
elif OCR_MODE in ("auto", "paddleocr_json"):
    if PADDLEOCR_JSON_EXE:
        from PPOCR_api import GetOcrApi

        _resolved_mode = "paddleocr_json"
        ppocr = GetOcrApi(PADDLEOCR_JSON_EXE, modelsPath=PADDLEOCR_JSON_MODELS or None, ipcMode="pipe")

if _resolved_mode is None:
    raise RuntimeError(
        "未找到可用OCR引擎。\n"
        "- 建议：在当前项目环境安装 Python 版 PaddleOCR：pip install paddleocr\n"
        "- 或：配置 PADDLEOCR_JSON_EXE 使用 PaddleOCR-json。"
    )

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
    lines = []
    for line in res:
        for box in line:
            text = box[1][0]
            x, y = box[0][0]
            lines.append((y, x, text))
    lines.sort()
    return "\n".join([t[2] for t in lines])


def process_file(file_path):
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

            if _resolved_mode == "paddleocr":
                res = ocr.ocr(file_path)
                all_text = ocr_to_text(res)
            else:
                res = ppocr.run(file_path)
                if res.get("code") != 100:
                    raise RuntimeError(f"OCR失败 code={res.get('code')}")
                all_text = "\n".join([
                    x.get("text", "") for x in res.get("data", [])
                    if x.get("text")
                ])

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


def extract_bank_by_context(lines):
    pay_bank = None
    loan_bank = None

    for i, line in enumerate(lines):
        if "开户银行" in line:

            banks = re.findall(r"开户银行\s*([\u4e00-\u9fa5A-Za-z0-9]+)", line)

            if len(banks) >= 1:
                pay_bank = banks[0]
            if len(banks) >= 2:
                loan_bank = banks[1]

            if not pay_bank and i + 1 < len(lines):
                if "银行" in lines[i + 1]:
                    pay_bank = lines[i + 1]

            if not loan_bank and i + 2 < len(lines):
                if "银行" in lines[i + 2]:
                    loan_bank = lines[i + 2]

    return pay_bank, loan_bank

# ================== 规范读取（凭证填写规范.xlsx 驱动） ==================
def load_spec_fields(spec_path: str):
    """
    从"凭证填写规范.xlsx"读取字段清单与是否必填。
    规范表结构目前是：两列（要素名称、填写要求），且每个 sheet 都是同样结构。
    """
    if not os.path.exists(spec_path):
        raise FileNotFoundError(f"未找到填写规范: {spec_path}")

    xls = pd.ExcelFile(spec_path)
    spec = {}
    for sheet in xls.sheet_names:
        df = pd.read_excel(spec_path, sheet_name=sheet)
        if df.shape[1] < 2:
            continue

        name_col = df.columns[0]
        req_col = df.columns[1]

        fields = []
        duplicate_counter = {}
        for _, row in df.iterrows():
            field = str(row.get(name_col, "")).strip()
            req = str(row.get(req_col, "")).strip()

            if not field or field == "nan":
                continue
            if any(k in field for k in ["要素", "填写要求", "规范"]):
                continue

            required = False
            if req and req != "nan":
                req_lower = req.lower()
                if any(k in req for k in ["必填", "不得为空", "不能为空", "必须填写", "必须填"]):
                    required = True
                if any(k in req for k in ["非必填", "可不填", "无需填写"]):
                    required = False
                if "not required" in req_lower:
                    required = False

            duplicate_counter[field] = duplicate_counter.get(field, 0) + 1
            norm_field = field
            if field == "账号" and duplicate_counter[field] == 1:
                norm_field = "申请人账号"
            elif field == "账号" and duplicate_counter[field] == 2:
                norm_field = "收款人账号"

            fields.append({"field": norm_field, "required": required, "requirement": req if req != "nan" else ""})

        spec[sheet] = fields

    return spec


def choose_sheet(spec_by_sheet, text: str):
    if not spec_by_sheet:
        return None
    return max(spec_by_sheet.keys(), key=lambda s: len(spec_by_sheet.get(s, [])))


def choose_sheet_for_subfolder(spec_by_sheet, subfolder_name: str):
    if not spec_by_sheet:
        return None

    name = subfolder_name or ""
    keys = list(spec_by_sheet.keys())

    if any(k in name for k in ["本票", "汇票"]):
        for s in keys:
            if any(w in s for w in ["本票", "汇票"]):
                return s
    if any(k in name for k in ["贷款", "还款"]):
        for s in keys:
            if any(w in s for w in ["贷款", "还款"]):
                return s

    return choose_sheet(spec_by_sheet, "")


def detect_doc_type(text: str) -> str:
    if "银行本票" in text or "本票申请书" in text:
        return "benpiao"

    if "贷款还款凭证" in text or "还款凭证" in text:
        return "daikuan"

    if "贷款账号" in text and "本次偿还金额" in text:
        return "daikuan"

    return "unknown"


# ================== 主程序 ==================
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


def process_one_folder(folder: str):
    print(f"\n========== 开始处理目录: {folder} ==========")

    files = get_files(folder)
    if not files:
        print(f"目录下未找到待识别 pdf/图片: {folder}")
        return

    all_data = []
    all_check = []
    all_check_long = []

    for f in files:
        print(f"\n===== 处理文件: {f} =====")

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
            all_check_long.append(
                {
                    "文件名": os.path.basename(f),
                    "字段名": field,
                    "提取值": data.get(field),
                    "检查结果": check.get(field),
                }
            )

        if amount_field and amount_field in check:
            if doc_type == "benpiao":
                amount_value = f"小写={data.get('金额小写')}, 大写={data.get('金额大写')}"
            else:
                amount_value = f"小写={data.get('本次偿还金额_小写')}, 大写={data.get('本次偿还金额_大写')}"

            all_check_long.append(
                {
                    "文件名": os.path.basename(f),
                    "字段名": amount_field,
                    "提取值": amount_value,
                    "检查结果": check.get(amount_field),
                }
            )

    df_data = pd.DataFrame(all_data)
    df_check = pd.DataFrame(all_check)
    df_check_long = pd.DataFrame(all_check_long)

    output_data = os.path.join(folder, "提取结果.xlsx")
    output_check = os.path.join(folder, "检查结果.xlsx")
    real_data = save_excel_with_fallback(df_data, output_data)
    real_check = save_excel_with_fallback(df_check_long if len(df_check_long) else df_check, output_check)
    print(f"\n已输出提取结果: {real_data}")
    print(f"已输出检查结果: {real_check}")


def main():
    root = r"D:\本票文件夹"
    if not os.path.exists(root):
        raise FileNotFoundError(f"目录不存在: {root}")

    subdirs = [
        os.path.join(root, d)
        for d in os.listdir(root)
        if os.path.isdir(os.path.join(root, d))
    ]

    if not subdirs:
        print(f"未发现子目录，直接按单目录模式处理: {root}")
        process_one_folder(root)
        return

    for folder in subdirs:
        process_one_folder(folder)


# ================== 入口 ==================
if __name__ == "__main__":
    main()
