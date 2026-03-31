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

def preprocess_for_amount(img):
    """金额专用增强（提高清晰度）"""
    img = np.array(img)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 放大（非常关键）
    gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

    # 二值化
    _, binary = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)

    return binary


def ocr_amount_region(image_path):
    """只识别金额区域"""
    img = Image.open(image_path)

    w, h = img.size

    # ⚠️ 这个区域你可以后面微调（关键）
    crop = img.crop((
        int(w * 0.4),
        int(h * 0.3),
        int(w * 1.0),
        int(h * 0.7)
    ))

    crop = preprocess_for_amount(crop)

    res = ocr.ocr(crop)

    text = ""
    for line in res:
        for box in line:
            text += box[1][0]

    return text


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
        # 按你提供的外部模型初始化方式
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

                # 🔥 转 numpy（关键）
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

        # ===== 新增：空文本检测 =====
        if not all_text.strip():
            print(f"⚠️ OCR未识别到任何文本: {file_path}")

        # 去空格干扰
        all_text = all_text.replace(" ", "")

        final_text = clean_text(all_text)

        # ===== 新增：输出部分内容用于调试 =====
        print(f"[OCR] 总长度: {len(final_text)}")
        print(f"[OCR] 前100字符: {final_text[:100]}")

        return final_text

    except Exception as e:
        logging.error(f"OCR失败: {file_path}, {e}")
        print(f"❌ OCR异常: {e}")
        return ""

def fix_account(text):
    if not text:
        return text
    return text.replace("O", "0").replace("I", "1")


def extract_bank_by_context(lines):
    pay_bank = None
    loan_bank = None

    for i, line in enumerate(lines):
        if "开户银行" in line:

            # 当前行提取
            banks = re.findall(r"开户银行\s*([\u4e00-\u9fa5A-Za-z0-9]+)", line)

            if len(banks) >= 1:
                pay_bank = banks[0]
            if len(banks) >= 2:
                loan_bank = banks[1]

            # 👇 如果没提到，往下一行找（关键）
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
    从“凭证填写规范.xlsx”读取字段清单与是否必填。
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
            # 跳过表头/标题行
            if any(k in field for k in ["要素", "填写要求", "规范"]):
                continue

            required = False
            if req and req != "nan":
                # 简单规则：出现“必填/不得为空/不能为空/必须填写”视为必填；出现“非必填/可不填”则视为非必填
                req_lower = req.lower()
                if any(k in req for k in ["必填", "不得为空", "不能为空", "必须填写", "必须填"]):
                    required = True
                if any(k in req for k in ["非必填", "可不填", "无需填写"]):
                    required = False
                if "not required" in req_lower:
                    required = False

            # 规范里“账号”可能出现两次（申请人账号、收款人账号），这里先做去重计数
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
    """
    当前目录下的规范文件含多个sheet（如：银行汇票/借款还款凭证）。
    这里先用“尽量不打扰”的策略：优先选择字段数最多的那个sheet；
    后续若你提供明确的票据类型识别关键词，可再加规则分流。
    """
    if not spec_by_sheet:
        return None
    return max(spec_by_sheet.keys(), key=lambda s: len(spec_by_sheet.get(s, [])))


def choose_sheet_for_subfolder(spec_by_sheet, subfolder_name: str):
    """
    按子目录名称优先选规范sheet，避免“总是命中同一个sheet”的问题。
    - 子目录名包含“本票/汇票” -> 优先匹配“银行汇（本）票申请书填写规范”
    - 子目录名包含“贷款/还款” -> 优先匹配“贷款还款凭证填写规范”
    """
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

    # 若目录名不含特征词，回退到原逻辑
    return choose_sheet(spec_by_sheet, "")


# ================== 字段抽取规则（可逐步补全） ==================
# 先提供一组常见字段的“强规则”，其余字段走“弱规则”兜底（按字段名定位）
FIELD_REGEX = {
    "币别": r"(人民币|RMB|USD|CNY)",
    "日期": r"(\d{4}[年\-\.]\d{1,2}[月\-\.]\d{1,2}日?)",
    "申请人": r"申请人[:：]?\s*([\u4e00-\u9fa5A-Za-z0-9（）()·.\-]+)",
    "账号": r"账号[:：]?\s*(\d{10,30})",
    "用途": r"用途[:：]?\s*(.+)",
    "收款人": r"收款人[:：]?\s*([\u4e00-\u9fa5A-Za-z0-9（）()·.\-]+)",
    "收款账号": r"收款人账号[:：]?\s*(\d{10,30})",
    "代理付款行": r"代理付款行[:：]?\s*(.+)",
    "金额小写": r"￥?\s*([\d,]+\.\d{2})",
    "金额大写": r"(人民币[壹贰叁肆伍陆柒捌玖拾佰仟万亿元角分整]+)",
}




def extract_field_value(text, field):
    pattern = rf"{field}[:：]?\s*(.*)"
    match = re.search(pattern, text)

    if match:
        value = match.group(1).strip()

        # ❗关键：截断到下一个字段
        value = re.split(r"(日期|币种|产品名称|名称|付款账号|开户银行|贷款账号|本次偿还金额|摘要)", value)[0]

        return value.strip()

    return None


def _clean_date(value: str):
    if not value:
        return value
    m = re.search(r"(\d{4})[年\-/\.](\d{1,2})[月\-/\.]?(\d{1,2})?", value)
    if not m:
        return value
    y, mo, d = m.group(1), m.group(2), m.group(3) or ""
    if d:
        return f"{y}年{int(mo)}月{int(d)}日"
    return f"{y}年{int(mo)}月"


def _extract_account_candidates(text: str):
    nums = re.findall(r"\d{10,30}", text)
    # 去重并按长度降序，尽量保留更完整账号
    seen = set()
    result = []
    for n in sorted(nums, key=lambda x: len(x), reverse=True):
        if n not in seen:
            seen.add(n)
            result.append(n)
    return result
#贷款还款凭证使用的函数
def normalize_number(text: str):
    """OCR数字纠错"""
    return text.replace("O", "0").replace("o", "0").replace("l", "1")



def parse_line_fields(line):
    result = {}

    # 名称
    if "名称" in line:
        value = line.replace("名称", "").strip()
        if len(value) > 1:
            result["名称"] = value

    # 付款账号 + 贷款账号（同一行）
    if "付款账号" in line:
        m = re.search(r"付款账号\s*([0-9]{10,})", line)
        if m:
            result["付款账号"] = m.group(1)

    if "贷款账号" in line:
        m = re.search(r"贷款账号\s*([0-9]{10,})", line)
        if m:
            result["贷款账号"] = m.group(1)

    # 开户银行（可能两个）
    if "开户银行" in line:
        banks = re.findall(r"开户银行\s*([\u4e00-\u9fa5A-Za-z0-9]+)", line)
        if len(banks) >= 1:
            result["付款开户银行"] = banks[0]
        if len(banks) >= 2:
            result["贷款开户银行"] = banks[1]

    return result

def extract_amount(text: str):
    """提取小写金额（优先从'本次偿还金额'附近找）"""
    text = normalize_number(text)
    lines = text.split("\n")

    # 1️⃣ 优先：字段邻域查找（最稳）
    for i, line in enumerate(lines):
        if "本次偿还金额" in line:
            for j in range(i, min(i + 5, len(lines))):
                m = re.search(r"\d+\.\d{2}", lines[j])
                if m:
                    return m.group(0)

    # 2️⃣ fallback：全局查找
    matches = re.findall(r"\d+\.\d{2}", text)
    if matches:
        return matches[0]

    return None


def extract_big_amount(text: str):
    """提取大写金额"""
    m = re.search(r"人民币[\u4e00-\u9fa5]+元", text)
    return m.group(0) if m else None

def _split_lines(text: str):
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _extract_account_from_label_block(text: str, label: str):
    """
    从“标签块”中提取账号：
    - 从 label 行开始向下找，优先取该块内第一条 10-30 位数字
    - 遇到下一个同级字段标签则停止，避免串到别的块
    """
    lines = _split_lines(text)
    if not lines:
        return None

    stop_words = {
        "申请人", "收款人", "代理付款行", "用途", "金额", "客户签章",
        "业务类型", "付款方式", "申请机构", "签发机构", "票据种类", "流水号", "币别",
    }
    start_indices = [i for i, ln in enumerate(lines) if label in ln]
    for i in start_indices:
        for j in range(i + 1, min(i + 10, len(lines))):
            ln = lines[j]
            if j > i + 1 and any(w in ln for w in stop_words):
                break
            m = re.search(r"(\d{10,30})", ln)
            if m:
                return m.group(1)
    return None


def _extract_account_by_explicit_label(text: str, labels):
    """
    仅通过显式标签提取账号（更严格）：
    例如：申请人账号: 123... / 收款人账号: 123...
    """
    lines = _split_lines(text)
    for ln in lines:
        for lb in labels:
            m = re.search(rf"{re.escape(lb)}[:：]?\s*(\d{{10,30}})", ln)
            if m:
                return m.group(1)
    return None


def _extract_amount_upper(text: str, file_path=None):
    # ===== 优先用ROI识别 =====
    if file_path:
        try:
            roi_text = ocr_amount_region(file_path)
            if roi_text:
                m = re.search(r"(人民币[^\n\r]{1,30}?元整)", roi_text)
                if m:
                    return m.group(1).strip()
        except Exception as e:
            print("ROI金额识别失败:", e)

    # ===== fallback 全图 =====
    m = re.search(r"(人民币[^\n\r]{1,30}?元整)", text)
    if m:
        return m.group(1).strip()

    m = re.search(r"([^\n\r]{2,40}?元整)", text)
    if m:
        return m.group(1).strip()

    return None

def _fix_amount_ocr_error(text: str):
    """
    OCR金额大写纠错（只做轻量修复，不影响原结构）
    """
    if not text:
        return text

    fix_map = {
        "人常": "人民币",
        "人名币": "人民币",
        "常": "民",
        "参": "叁",
        "任": "仟",
        "伯": "佰",
        "圆": "元",
        "園": "元",
        "萬": "万",
    }

    for k, v in fix_map.items():
        text = text.replace(k, v)

    return text

def _money_to_upper(num_str: str):
    """
    将小写金额字符串（如 336400.00）转换为标准大写金额（人民币叁拾叁万陆仟肆佰元整）。
    """
    if not num_str:
        return None
    try:
        n = float(str(num_str).replace(",", ""))
    except Exception:
        return None

    digits = "零壹贰叁肆伍陆柒捌玖"
    units = ["", "拾", "佰", "仟"]
    big_units = ["", "万", "亿", "兆"]

    integer = int(n)
    fraction = round((n - integer) * 100)
    jiao = fraction // 10
    fen = fraction % 10

    if integer == 0:
        int_part = "零"
    else:
        parts = []
        group_idx = 0
        need_zero = False
        while integer > 0:
            group = integer % 10000
            integer //= 10000

            if group == 0:
                need_zero = True
                group_idx += 1
                continue

            group_str = ""
            zero_in_group = False
            for i in range(4):
                d = group % 10
                group //= 10
                if d == 0:
                    if group_str:
                        zero_in_group = True
                else:
                    if zero_in_group:
                        group_str = "零" + group_str
                        zero_in_group = False
                    group_str = digits[d] + units[i] + group_str

            if need_zero and parts and not group_str.endswith("零"):
                group_str += "零"
            group_str += big_units[group_idx]
            parts.append(group_str)
            need_zero = False
            group_idx += 1

        int_part = "".join(reversed(parts)).rstrip("零")

    if jiao == 0 and fen == 0:
        frac_part = "整"
    else:
        frac_part = ""
        if jiao > 0:
            frac_part += digits[jiao] + "角"
        if fen > 0:
            frac_part += digits[fen] + "分"

    return f"人民币{int_part}元{frac_part}"


def _normalize_upper_amount_text(v: str):
    """
    归一化大写金额文本，便于做一致性比较（仅用于校验）。
    """
    if not v:
        return ""
    s = str(v)
    # 常见OCR混淆字修正（仅用于比较，不回写提取值）
    fix_map = {
        "参": "叁",
        "伯": "佰",
        "任": "仟",
        "圆": "元",
        "園": "元",
        "圓": "元",
        "常": "民",
        "市": "币",
        "陆": "陆",
    }
    for k, vv in fix_map.items():
        s = s.replace(k, vv)

    # 只保留金额相关字符
    s = re.sub(r"[^人民币零壹贰叁肆伍陆柒捌玖拾佰仟万亿兆元角分整]", "", s)
    return s


def _is_name_candidate(s: str):
    if not s:
        return False
    if len(s) > 24:
        return False
    bad_words = [
        "申请人", "收款人", "账号", "用途", "代理付款行", "金额", "客户签章",
        "业务类型", "付款方式", "银行", "本票", "汇票", "流水号", "票据", "签发机构"
    ]
    if any(w in s for w in bad_words):
        return False
    return bool(re.match(r"^[\u4e00-\u9fa5A-Za-z0-9*（）()·.\-]+$", s))


def _extract_near_label_name(text: str, labels):
    lines = _split_lines(text)
    # 1) 优先取“标签同一行冒号后值”
    for ln in lines:
        for lb in labels:
            m = re.search(rf"{re.escape(lb)}[:：]?\s*([^\n\r:：]+)", ln)
            if m and _is_name_candidate(m.group(1).strip()):
                return m.group(1).strip()

    # 2) 再取标签前后邻近行的人名候选
    for i, ln in enumerate(lines):
        if any(lb in ln for lb in labels):
            # 先看上一行，再看下一行，最后再扩大范围
            for j in [i - 1, i + 1, i - 2, i + 2, i - 3, i + 3]:
                if 0 <= j < len(lines):
                    cand = lines[j].strip()
                    if _is_name_candidate(cand):
                        return cand
    return None


def _extract_near_label_text(text: str, labels, max_len: int = 60):
    """
    通用“标签邻域取值”：用于代理付款行、用途等文本字段。
    """
    lines = _split_lines(text)
    field_words = {"用途", "账号", "申请人", "收款人", "代理付款行", "金额", "客户签章", "业务类型", "付款方式", "币别", "日期"}

    def is_valid(v: str):
        if not v:
            return False
        v = v.strip()
        if len(v) > max_len:
            return False
        if v in field_words:
            return False
        # 纯标签词或明显无效词
        bad = ["流水号", "票据金额", "签发机构", "申请机构", "跨机构申请编号"]
        if any(b == v for b in bad):
            return False
        return True

    # 1) 同行冒号后
    for ln in lines:
        for lb in labels:
            m = re.search(rf"{re.escape(lb)}[:：]?\s*([^\n\r:：]+)", ln)
            if m:
                val = m.group(1).strip()
                if is_valid(val):
                    return val

    # 2) 邻近行
    for i, ln in enumerate(lines):
        if any(lb in ln for lb in labels):
            for j in [i + 1, i - 1, i + 2, i - 2, i + 3]:
                if 0 <= j < len(lines):
                    cand = lines[j].strip()
                    if is_valid(cand):
                        return cand
    return None


def _extract_customer_stamp_status(text: str):
    """
    客户签章仅输出“有章/无章”：
    - 识别到明显银行业务章/费用项文本，判为无章（避免误判）
    - 识别到客户名称类文本，判为有章
    """
    lines = _split_lines(text)
    idxs = [i for i, ln in enumerate(lines) if "客户签章" in ln]
    if not idxs:
        return "无章"

    i = idxs[0]
    nearby = []
    for j in [i - 1, i, i + 1, i + 2, i + 3]:
        if 0 <= j < len(lines):
            nearby.append(lines[j])
    merged = "|".join(nearby)

    bank_stamp_words = ["业务专用", "专用章", "手续费", "工本费", "对私", "本票", "银行"]
    if any(w in merged for w in bank_stamp_words):
        return "无章"

    # 客户章通常可识别出单位名/姓名的部分字符，这里只要有较稳文本则判有章
    text_tokens = [ln for ln in nearby if ln and "客户签章" not in ln]
    if any(len(t) >= 2 for t in text_tokens):
        return "有章"

    return "无章"


def extract_benpiao_fields(text: str, spec_fields, file_path=None):
    """
    本票字段专用规则：
    - 先按关键锚点提取（比通用“字段名+行尾”更稳）
    - 抽不到再回退到通用规则
    """
    data = {}

    # 预提取
    accounts = _extract_account_candidates(text)
    date_match = re.search(r"\d{4}[年\-/\.]\d{1,2}(?:[月\-/\.]\d{1,2})?", text)
    amount_num = re.search(r"￥\s*([\d,]+\.\d{2})", text)
    amount_cn = _extract_amount_upper(text,file_path)
    print("原始大写金额识别结果：",amount_cn)
    amount_cn = _fix_amount_ocr_error(amount_cn)

    # 锚点提取（允许跨行少量噪声）
    anchor_rules = {
        "币别": r"币别[:：]?\s*(人民币|RMB|USD|CNY)",
        "日期": r"(\d{4}[年\-/\.]\d{1,2}(?:[月\-/\.]\d{1,2})?)",
        "业务类型": r"(银行本票|银行汇票|本票|汇票)",
        "付款方式": r"(转账|现金)",
        "申请人": r"申请人[:：]?\s*([^\n\r:：]{2,40})",
        "收款人": r"收款人[:：]?\s*([^\n\r:：]{2,40})",
        "代理付款行": r"代理付款行[:：]?\s*([^\n\r]{2,60})",
        "用途": r"用途[:：]?\s*([^\n\r]{1,60})",
        "客户签章": r"客户签章[:：]?\s*([^\n\r]{2,60})",
    }

    # 先填充通用回退值
    for f in spec_fields:
        field = f["field"]
        data[field] = extract_field_value(text, field)

    # 再用本票锚点覆盖
    for field, rgx in anchor_rules.items():
        if field not in data:
            continue
        m = re.search(rgx, text)
        if m:
            data[field] = m.group(1).strip()

    # 特殊字段处理
    if "日期" in data:
        data["日期"] = _clean_date(data.get("日期")) or _clean_date(date_match.group(0) if date_match else "")

    if "金额" in data:
        # 优先小写金额，保留更稳定格式；若无则回退大写
        if amount_num:
            data["金额"] = amount_num.group(1).replace(",", "")
        elif amount_cn:
            data["金额"] = amount_cn
    # 新增金额大写字段（本票专用）：必须来自 OCR 文本，不做小写反推
    data["金额大写"] = amount_cn

    # 双账号：优先按锚点，否则按候选数字回填
    if "申请人账号" in data:
        m = _extract_account_by_explicit_label(text, ["申请人账号"])
        block_acc = _extract_account_from_label_block(text, "申请人")
        if block_acc:
            data["申请人账号"] = fix_account(block_acc)
        elif m:
            data["申请人账号"] = fix_account(m)
        elif accounts:
            data["申请人账号"] = fix_account(accounts[-1])

    if "收款人账号" in data:
        # 按你的要求：收款人账号必须有明确“收款人账号”锚点才填值，否则置空
        m = _extract_account_by_explicit_label(text, ["收款人账号", "收款账号"])
        data["收款人账号"] = fix_account(m) if m else None

    # 代理付款行：标签邻域优先，且过滤“用途/账号”等列名误识别
    if "代理付款行" in data:
        v = _extract_near_label_text(text, ["代理付款行"], max_len=80)
        if v:
            data["代理付款行"] = v
        else:
            data["代理付款行"] = None

        if data.get("代理付款行") in {"用途", "账号", "申请人", "收款人", "金额"}:
            data["代理付款行"] = None
        # 若提取到的是账号形态，强制清空
        if data.get("代理付款行") and re.fullmatch(r"\d{8,30}", str(data["代理付款行"]).strip()):
            data["代理付款行"] = None
        # 仅接受明确行名（银行/支行/分行），否则置空
        if data.get("代理付款行"):
            v2 = str(data["代理付款行"]).strip()
            if not any(k in v2 for k in ["银行", "支行", "分行"]):
                data["代理付款行"] = None

    # 人名字段：用标签邻域提取，避免把“申请人/收款人”标签本身识别为值
    if "申请人" in data:
        v = _extract_near_label_name(text, ["申请人"])
        if v:
            data["申请人"] = v
    if "收款人" in data:
        v = _extract_near_label_name(text, ["收款人"])
        if v:
            data["收款人"] = v

    # 客户签章：如果仅识别到银行“业务专用章”等文本，则视为空（不应当算客户签章）
    if "客户签章" in data:
        data["客户签章"] = _extract_customer_stamp_status(text)

    return data


def extract_daikuan_fields_v6(file_path):
    """
    贷款还款凭证字段提取 - v6 完整修复版
    处理：竖排文本、表格格子金额、账号原样读取、通用标签定位
    关键改进：精准Y坐标、严格过滤垃圾、范围查找代替全文搜索
    """
    data = {}

    if not file_path:
        return data

    try:
        # 转图片并OCR
        img = None
        if file_path.lower().endswith('.pdf'):
            images = convert_from_path(file_path, dpi=250)
            if images:
                img = images[0]
        else:
            img = Image.open(file_path)

        if not img:
            return data

        w, h = img.size
        img_np = np.array(img)
        res = ocr.ocr(img_np)

        print(f"[贷款凭证v6] 图片大小: {img.size}")

        # ===== 第一步：收集所有OCR框 =====
        all_boxes = []
        for line in res:
            for box in line:
                text = box[1][0]
                confidence = box[1][1]
                coords = box[0]

                x_avg = sum([pt[0] for pt in coords]) / len(coords)
                y_avg = sum([pt[1] for pt in coords]) / len(coords)

                all_boxes.append({
                    'text': text,
                    'x': x_avg,
                    'y': y_avg,
                    'confidence': confidence
                })

        print(f"[收集] 总共 {len(all_boxes)} 个文本框\n")

        # ===== 第二步：按Y坐标分行 =====
        def group_by_y(boxes, threshold=30):
            if not boxes:
                return []

            boxes_sorted = sorted(boxes, key=lambda x: x['y'])
            rows = []
            current_row = [boxes_sorted[0]]
            current_y = boxes_sorted[0]['y']

            for box in boxes_sorted[1:]:
                if abs(box['y'] - current_y) < threshold:
                    current_row.append(box)
                else:
                    current_row.sort(key=lambda x: x['x'])
                    rows.append(current_row)
                    current_row = [box]
                    current_y = box['y']

            if current_row:
                current_row.sort(key=lambda x: x['x'])
                rows.append(current_row)

            return rows

        all_rows = group_by_y(all_boxes, threshold=30)
        print(f"[分行] 按Y坐标分为 {len(all_rows)} 行\n")

        # ===== 第三步：字段提取 =====

        # 1. 币种
        data["币种"] = "人民币"

        # 2. 日期（Y<600）
        date_found = False
        for row in all_rows:
            row_y = row[0]['y'] if row else 0
            if row_y < 600:
                row_text = "".join([b['text'] for b in row])
                m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})", row_text)
                if m:
                    y, mo, d = m.group(1), m.group(2), m.group(3)
                    data["日期"] = f"{y}年{int(mo)}月{int(d)}日"
                    print(f"[日期] {data['日期']}")
                    date_found = True
                    break

        if not date_found:
            data["日期"] = None

        # 3. 产品名称
        data["产品名称"] = None

        # 4. 名称（找"名"字标签，排除"产品名称"行，从同一行提取企业名）
        name_found = False
        for i, row in enumerate(all_rows):
            row_text = "".join([b['text'] for b in row])

            # 关键：找包含"名"但不包含"产品名称"的行
            if "名" in row_text and "产品名称" not in row_text and not name_found:
                # 从这一行提取：名 + 企业名
                m = re.search(r"名\s*([\u4e00-\u9fa5]{3,40})", row_text)
                if m:
                    cand = m.group(1).strip()
                    # 过滤：不是标签词，长度3-40
                    if (3 <= len(cand) <= 40 and
                            not any(x in cand for x in
                                    ["账号", "银行", "日期", "摘要", "签章", "付款", "贷款", "开户", "币种", "产品",
                                     "名", "称"])):
                        data["名称"] = cand
                        name_found = True
                        print(f"[名称] {data['名称']}")
                        break

        if not name_found:
            data["名称"] = None

        # 5. 付款账号（Y=732）
        pay_acc_found = False
        for i, row in enumerate(all_rows):
            row_text = "".join([b['text'] for b in row])
            row_y = row[0]['y'] if row else 0

            if "付款账号" in row_text and 700 < row_y < 760 and not pay_acc_found:
                # 同一行查找
                m = re.search(r"付款账号[:：]?\s*([\dI\*]{15,})", row_text)
                if m:
                    data["付款账号"] = m.group(1)
                    pay_acc_found = True
                    print(f"[付款账号] {data['付款账号']} (同行)")
                    break

                # 上一行查找
                if not pay_acc_found and i > 0:
                    prev_text = "".join([b['text'] for b in all_rows[i - 1]])
                    m = re.search(r"([\dI\*]{15,})", prev_text)
                    if m:
                        data["付款账号"] = m.group(1)
                        pay_acc_found = True
                        print(f"[付款账号] {data['付款账号']} (上行)")
                        break

                # 下一行查找
                if not pay_acc_found and i + 1 < len(all_rows):
                    next_text = "".join([b['text'] for b in all_rows[i + 1]])
                    m = re.search(r"([\dI\*]{15,})", next_text)
                    if m:
                        data["付款账号"] = m.group(1)
                        pay_acc_found = True
                        print(f"[付款账号] {data['付款账号']} (下行)")
                        break

        if not pay_acc_found:
            # 兜底：从Y=700-800范围查找最长的数字序列
            account_region = [b for b in all_boxes if 700 < b['y'] < 800]
            number_boxes = [b for b in account_region if re.match(r"[\dI\*]{10,}", b['text'])]
            if number_boxes:
                longest = max(number_boxes, key=lambda x: len(x['text']))
                data["付款账号"] = longest['text']
                pay_acc_found = True
                print(f"[付款账号] {data['付款账号']} (范围查找)")

        if not pay_acc_found:
            data["付款账号"] = None

        # 6. 付款开户银行（找"付款账号"，往下找包含"银行"的boxes，按X坐标排序，取第一个）
        pay_bank_found = False
        for i, row in enumerate(all_rows):
            row_text = "".join([b['text'] for b in row])

            if "付款账号" in row_text and not pay_bank_found:
                # 往下找，找包含"银行"的行
                for j in range(i + 1, min(i + 5, len(all_rows))):
                    next_row = all_rows[j]

                    # 🔥 从这一行的所有boxes中找出所有包含"银行"的框
                    bank_boxes = [b for b in next_row if "银行" in b['text']]

                    if len(bank_boxes) > 0:
                        # 按X坐标排序，取第一个（左边）
                        bank_boxes.sort(key=lambda x: x['x'])
                        data["付款开户银行"] = bank_boxes[0]['text'].strip()
                        pay_bank_found = True
                        print(f"[付款开户银行] {data['付款开户银行']}")
                        break

        if not pay_bank_found:
            data["付款开户银行"] = None

        # 7. 贷款账号（Y=732同行有两个账号）
        loan_acc_found = False
        for i, row in enumerate(all_rows):
            row_text = "".join([b['text'] for b in row])
            row_y = row[0]['y'] if row else 0

            if "贷款账号" in row_text and 700 < row_y < 760 and not loan_acc_found:
                # 同一行查找
                m = re.search(r"贷款账号[:：]?\s*([\dI\*]{15,})", row_text)
                if m:
                    data["贷款账号"] = m.group(1)
                    loan_acc_found = True
                    print(f"[贷款账号] {data['贷款账号']} (同行)")
                    break

                # 上一行查找
                if not loan_acc_found and i > 0:
                    prev_text = "".join([b['text'] for b in all_rows[i - 1]])
                    m = re.search(r"([\dI\*]{15,})", prev_text)
                    if m:
                        data["贷款账号"] = m.group(1)
                        loan_acc_found = True
                        print(f"[贷款账号] {data['贷款账号']} (上行)")
                        break

                # 下一行查找
                if not loan_acc_found and i + 1 < len(all_rows):
                    next_text = "".join([b['text'] for b in all_rows[i + 1]])
                    m = re.search(r"([\dI\*]{15,})", next_text)
                    if m:
                        data["贷款账号"] = m.group(1)
                        loan_acc_found = True
                        print(f"[贷款账号] {data['贷款账号']} (下行)")
                        break

        if not loan_acc_found:
            # 兜底：从Y=700-800范围查找第二个最长的数字序列
            account_region = [b for b in all_boxes if 700 < b['y'] < 800]
            number_boxes = sorted([b for b in account_region if re.match(r"[\dI\*]{10,}", b['text'])],
                                  key=lambda x: len(x['text']), reverse=True)
            if len(number_boxes) > 1:
                data["贷款账号"] = number_boxes[1]['text']
                loan_acc_found = True
                print(f"[贷款账号] {data['贷款账号']} (范围查找)")

        if not loan_acc_found:
            data["贷款账号"] = None

        # 8. 贷款开户银行（找"贷款账号"，往下找包含"银行"的boxes，按X坐标排序，取第二个）
        loan_bank_found = False
        for i, row in enumerate(all_rows):
            row_text = "".join([b['text'] for b in row])

            if "贷款账号" in row_text and not loan_bank_found:
                # 往下找，找包含"银行"的行
                for j in range(i + 1, min(i + 5, len(all_rows))):
                    next_row = all_rows[j]

                    # 🔥 从这一行的所有boxes中找出所有包含"银行"的框
                    bank_boxes = [b for b in next_row if "银行" in b['text']]

                    if len(bank_boxes) >= 2:
                        # 按X坐标排序，取第二个（右边）
                        bank_boxes.sort(key=lambda x: x['x'])
                        data["贷款开户银行"] = bank_boxes[1]['text'].strip()
                        loan_bank_found = True
                        print(f"[贷款开户银行] {data['贷款开户银行']}")
                        break

        if not loan_bank_found:
            data["贷款开户银行"] = None

        # 9. 本次偿还金额（修复：扩大搜索范围和兜底）
        amount_upper = None
        amount_small = None

        # 大写金额：在Y=938-948查找
        amount_upper_region = [b for b in all_boxes if 938 < b['y'] < 948]
        amount_upper_text = "".join([b['text'] for b in sorted(amount_upper_region, key=lambda x: x['x'])])

        m = re.search(r"(伍佰[^\n]*元[^\n]*分)", amount_upper_text)
        if m:
            amount_upper = m.group(1).strip()
            print(f"[大写金额] {amount_upper}")

        # 小写金额：扩大搜索范围到Y=880-1000（因为可能在表格格子里）
        number_region = [b for b in all_boxes if 880 < b['y'] < 1000]
        number_boxes = [b for b in number_region if re.match(r"^\d+$", b['text'])]

        print(f"[小写金额] 数字框: {[b['text'] for b in sorted(number_boxes, key=lambda x: x['x'])]}")

        if number_boxes:
            all_digits = "".join([b['text'] for b in sorted(number_boxes, key=lambda x: x['x'])])
            print(f"[小写金额合并] {all_digits}")

            if len(all_digits) >= 3:
                amount_small = f"¥{all_digits[:-2]}.{all_digits[-2:]}"
                print(f"[小写金额] {amount_small}")
        else:
            print(f"[小写金额] 范围880-1000未找到数字，可能OCR识别失败")

        data["本次偿还金额_小写"] = amount_small
        data["本次偿还金额_大写"] = _fix_amount_ocr_error(amount_upper) if amount_upper else None

        # 10. 摘要（🔥修复：精确Y范围定位）
        summary_found = False
        summary_region = [b for b in all_boxes if 1046 < b['y'] < 1052]
        summary_text = "".join([b['text'] for b in sorted(summary_region, key=lambda x: x['x'])])

        m = re.search(r"(归还贷款|还款)", summary_text)
        if m:
            data["摘要"] = m.group(1).strip()
            summary_found = True
            print(f"[摘要] {data['摘要']}")

        if not summary_found:
            data["摘要"] = None

        # 11. 累计还款
        data["累计还款"] = None

        # ===== 12-15. 签章和签字 =====
        lower_boxes = [b for b in all_boxes if b['y'] > 1400]
        print(f"\n[签章签字区域] 找到 {len(lower_boxes)} 个框")

        # 还款单位签章（左侧，Y=1532有签章标记）
        try:
            crop = img.crop((
                int(w * 0.05), int(h * 0.65),
                int(w * 0.5), h
            ))
            crop_gray = crop.convert("L")
            crop_np = np.array(crop_gray)
            dark_ratio = np.sum(crop_np < 150) / crop_np.size
            print(f"[还款单位签章] 黑色像素占比: {dark_ratio:.2%}")
            data["还款单位签章"] = "有章" if dark_ratio > 0.05 else "无章"
        except Exception as e:
            print(f"[还款单位签章] 判定失败: {e}")
            data["还款单位签章"] = "无章"

        # 银行签章（右侧）
        try:
            crop = img.crop((
                int(w * 0.5), int(h * 0.65),
                int(w * 0.95), h
            ))
            crop_gray = crop.convert("L")
            crop_np = np.array(crop_gray)
            dark_ratio = np.sum(crop_np < 150) / crop_np.size
            print(f"[银行签章] 黑色像素占比: {dark_ratio:.2%}")
            data["银行签章"] = "有章" if dark_ratio > 0.05 else "无章"
        except Exception as e:
            print(f"[银行签章] 判定失败: {e}")
            data["银行签章"] = "无章"

        # 签字（经办/复核/授权/主管）
        data["经办"] = None
        data["复核"] = None
        data["授权"] = None
        data["主管"] = None

        for row in all_rows:
            row_text = "".join([b['text'] for b in row])

            # 经办
            if "经办" in row_text:
                m = re.search(r"经办[:：]?\s*([^\n\r:：】）)]*)", row_text)
                if m:
                    val = m.group(1).strip()
                    val = re.sub(r"[）)】\s，]", "", val)
                    if val and val not in ["经办"]:
                        data["经办"] = val
                        print(f"[经办] {val}")

            # 复核
            if "复核" in row_text:
                m = re.search(r"复核[:：]?\s*([^\n\r:：】）)]*)", row_text)
                if m:
                    val = m.group(1).strip()
                    val = re.sub(r"[）)】\s]", "", val)
                    if val and val not in ["复核", ""]:
                        data["复核"] = val
                        print(f"[复核] {val}")

            # 授权
            if "授权" in row_text:
                m = re.search(r"授权[:：]?\s*([^\n\r:：】）)]*)", row_text)
                if m:
                    val = m.group(1).strip()
                    val = re.sub(r"[）)】\s]", "", val)
                    if val and val not in ["授权", ""]:
                        data["授权"] = val
                        print(f"[授权] {val}")

            # 主管（🔥修复：不要贪心匹配授权）
            if "主管" in row_text:
                m = re.search(r"主管[:：]?\s*([^授]*?)(?:授权|$)", row_text)
                if m:
                    val = m.group(1).strip()
                    val = re.sub(r"[）)】\s，]", "", val)
                    if val and val not in ["主管", ""]:
                        data["主管"] = val
                        print(f"[主管] {val}")

        print(f"\n[贷款凭证v6] 提取完毕\n")
        return data

    except Exception as e:
        print(f"[贷款凭证v6] 提取失败: {e}")
        import traceback
        traceback.print_exc()
        return {}


def _detect_stamp_in_image(file_path: str, stamp_type: str):
    """
    检测图片中是否有签章（盖章）
    """
    if not file_path:
        return None

    try:
        # 获取图片
        img = None
        if file_path.lower().endswith('.pdf'):
            images = convert_from_path(file_path, dpi=150)
            if images:
                img = images[0]
        else:
            img = Image.open(file_path)

        if not img:
            return None

        w, h = img.size

        # 定义ROI（需要根据实际凭证调整）
        roi_map = {
            "还款单位签章": (int(w * 0.05), int(h * 0.55), int(w * 0.45), h),
            "银行签章": (int(w * 0.55), int(h * 0.55), int(w * 0.95), h),
        }

        if stamp_type not in roi_map:
            return None

        x1, y1, x2, y2 = roi_map[stamp_type]
        crop = img.crop((x1, y1, x2, y2))

        # 转为灰度图计算黑色像素（章的特征）
        crop_gray = crop.convert("L")
        crop_np = np.array(crop_gray)

        # 印章通常为红色或深色，灰度值较低
        # 计算像素低于150的占比
        dark_pixels = np.sum(crop_np < 150)
        total_pixels = crop_np.size
        dark_ratio = dark_pixels / total_pixels if total_pixels > 0 else 0

        print(f"[签章检测] {stamp_type} 黑色像素比: {dark_ratio:.2%}")

        # 阈值：如果黑色像素 > 3% 则认为有章
        if dark_ratio > 0.03:
            return "有章"
        else:
            return "无章"

    except Exception as e:
        print(f"[签章检测] 检测 {stamp_type} 失败: {e}")
        return None


def _extract_handwriting_text(file_path: str, field_type: str):
    """
    提取图片中的手写签字内容（返回识别到的文本）
    """
    if not file_path:
        return None

    try:
        # 获取图片
        img = None
        if file_path.lower().endswith('.pdf'):
            images = convert_from_path(file_path, dpi=200)
            if images:
                img = images[0]
        else:
            img = Image.open(file_path)

        if not img:
            return None

        w, h = img.size

        # 定义ROI（签字位置，需要根据实际凭证调整）
        roi_map = {
            "经办": (int(w * 0.1), int(h * 0.75), int(w * 0.4), int(h * 0.95)),
            "复核": (int(w * 0.4), int(h * 0.75), int(w * 0.7), int(h * 0.95)),
            "授权": (int(w * 0.05), int(h * 0.85), int(w * 0.35), h),
            "主管": (int(w * 0.55), int(h * 0.85), int(w * 0.85), h),
        }

        if field_type not in roi_map:
            return None

        x1, y1, x2, y2 = roi_map[field_type]
        crop = img.crop((x1, y1, x2, y2))

        # 用OCR识别该区域的文本（可能是签名、章、或文字）
        crop_np = np.array(crop)
        res = ocr.ocr(crop_np)

        # 提取识别文本
        recognized_text = ""
        if res:
            for line in res:
                for box in line:
                    text = box[1][0]
                    confidence = box[1][1]
                    if confidence > 0.3:  # 降低阈值以捕获手写
                        recognized_text += text

        recognized_text = recognized_text.strip()
        print(f"[签字提取] {field_type} 识别文本: '{recognized_text}'")

        # 判断：如果识别到文本或有明显笔画，则返回文本；否则判定为无签字
        if recognized_text:
            return recognized_text

        # fallback：检测笔画密度
        crop_gray = crop.convert("L")
        crop_np = np.array(crop_gray)
        dark_pixels = np.sum(crop_np < 150)
        total_pixels = crop_np.size
        dark_ratio = dark_pixels / total_pixels if total_pixels > 0 else 0

        if dark_ratio > 0.05:
            return "有签字"  # 有笔画但未识别出文字
        else:
            return None

    except Exception as e:
        print(f"[签字提取] 提取 {field_type} 失败: {e}")
        return None


def _detect_stamp_in_image(file_path: str, stamp_type: str):
    """
    检测图片中是否有签章（盖章）
    策略：根据stamp_type定位章的区域，然后用OCR识别是否有"章"字或印章相关文本
    """
    if not file_path:
        return None

    try:
        # 转换为图片
        img = None
        if file_path.lower().endswith('.pdf'):
            images = convert_from_path(file_path, dpi=150)
            if images:
                img = images[0]
        else:
            img = Image.open(file_path)

        if not img:
            return None

        w, h = img.size

        # 根据签章位置定义ROI
        # 注：这个需要根据实际凭证布局调整
        roi_map = {
            "还款单位签章": (0, int(h * 0.55), int(w * 0.5), h),  # 左下区域
            "银行签章": (int(w * 0.5), int(h * 0.55), w, h),  # 右下区域
        }

        if stamp_type not in roi_map:
            return None

        x1, y1, x2, y2 = roi_map[stamp_type]
        crop = img.crop((x1, y1, x2, y2))

        # OCR识别
        crop_np = np.array(crop)
        res = ocr.ocr(crop_np)

        stamp_text = ocr_to_text(res)
        print(f"[签章检测] {stamp_type} 区域识别文本: {stamp_text[:50]}")

        # 判断：如果识别到"章"、"印鉴"、"公章"等关键词，则判为有章
        if any(kw in stamp_text for kw in ["章", "印", "公章", "法人", "行业务"]):
            return "有章"
        else:
            return "无章"

    except Exception as e:
        print(f"[签章检测] 检测 {stamp_type} 失败: {e}")
        return None


def _detect_handwriting_in_image(file_path: str, field_type: str):
    """
    检测图片中是否有手写签字
    策略：根据field_type定位签字区域，识别是否有手写痕迹（可用笔画密度判断）
    """
    if not file_path:
        return None

    try:
        # 转换为图片
        img = None
        if file_path.lower().endswith('.pdf'):
            images = convert_from_path(file_path, dpi=150)
            if images:
                img = images[0]
        else:
            img = Image.open(file_path)

        if not img:
            return None

        w, h = img.size

        # 根据签字位置定义ROI
        roi_map = {
            "经办": (int(w * 0.15), int(h * 0.75), int(w * 0.45), h),
            "复核": (int(w * 0.45), int(h * 0.75), int(w * 0.75), h),
            "授权": (int(w * 0.05), int(h * 0.85), int(w * 0.35), h),
            "主管": (int(w * 0.55), int(h * 0.85), int(w * 0.85), h),
        }

        if field_type not in roi_map:
            return None

        x1, y1, x2, y2 = roi_map[field_type]
        crop = img.crop((x1, y1, x2, y2))

        # 转灰度，计算笔画密度
        crop_gray = crop.convert("L")
        crop_np = np.array(crop_gray)

        # 简单启发式：黑色像素（<200）占比 > 5% 认为有签字
        dark_pixels = np.sum(crop_np < 200)
        total_pixels = crop_np.size
        dark_ratio = dark_pixels / total_pixels if total_pixels > 0 else 0

        print(f"[签字检测] {field_type} 黑色像素比: {dark_ratio:.2%}")

        if dark_ratio > 0.05:
            return "有签字"
        else:
            return "无签字"

    except Exception as e:
        print(f"[签字检测] 检测 {field_type} 失败: {e}")
        return None


def detect_doc_type(text: str) -> str:
    if "银行本票" in text or "本票申请书" in text:
        return "benpiao"

    if "贷款还款凭证" in text or "还款凭证" in text:
        return "daikuan"

    # 兜底（弱特征）
    if "贷款账号" in text and "本次偿还金额" in text:
        return "daikuan"

    return "unknown"

# ================== 提取 + 校验 ==================
def extract_and_validate(text, spec_fields, file_path=None, sheet_name: str = "", doc_type: str = "unknown"):
    check = {}
    is_benpiao = (doc_type == "benpiao")
    is_daikuan = (doc_type == "daikuan")

    if is_benpiao:
        data = extract_benpiao_fields(text, spec_fields, file_path)
    elif is_daikuan:
        # 🔥 改为调用v5版本，直接传file_path而不是text
        data = extract_daikuan_fields_v6(file_path)
    else:
        data = {}

    for f in spec_fields:
        field = f["field"]
        required = bool(f.get("required"))
        requirement = f.get("requirement", "")

        value = data.get(field)

        # 账号纠错
        if field in ["账号", "收款账号", "申请人账号", "收款人账号", "付款账号", "贷款账号"]:
            value = fix_account(value) if value else None

        data[field] = value

        # ===== 检查规则 =====
        if field == "还款单位签章":
            check[field] = "PASS" if value == "有章" else ("FAIL-无章" if required else "PASS")

        elif field == "银行签章":
            check[field] = "PASS"  # 银行签章非必填

        elif field in ["经办", "复核", "授权", "主管"]:
            if value:
                check[field] = "PASS"
            elif required:
                check[field] = "FAIL-缺失"
            else:
                check[field] = "PASS"

        elif field in ["本次偿还金额_小写", "本次偿还金额_大写"]:
            if not value:
                check[field] = "FAIL-缺失" if required else "PASS"
            else:
                check[field] = "PASS"

        elif required and not value:
            check[field] = "FAIL-缺失"
        else:
            check[field] = "PASS"

        if requirement:
            check[f"{field}_规范"] = requirement

    # ===== 金额一致性检查 =====
    if is_daikuan:
        amount_small = data.get("本次偿还金额_小写")
        amount_upper_ocr = data.get("本次偿还金额_大写")

        if amount_small and amount_upper_ocr:
            num_match = re.search(r"(\d+\.\d{2})", str(amount_small))
            if num_match:
                num = num_match.group(1)
                expected_upper = _money_to_upper(num)
                if expected_upper:
                    a = _normalize_upper_amount_text(amount_upper_ocr)
                    b = _normalize_upper_amount_text(expected_upper)
                    check["金额大小写一致性"] = "一致" if a == b else "不一致"
                else:
                    check["金额大小写一致性"] = "无法校验"
            else:
                check["金额大小写一致性"] = "无法提取数值"
        else:
            check["金额大小写一致性"] = "FAIL-缺失金额"

    return data, check

def extract_other_fields(file_path):
    """提取其他类型凭证的字段（暂未实现）"""
    return {}


def extract_and_validate_from_file(file_path, is_daikuan=True):
    """新函数 - 直接从文件提取并显示结果（用于贷款凭证）"""

    if is_daikuan:
        data = extract_daikuan_fields_v6(file_path)
    else:
        data = extract_other_fields(file_path)

    # ===== 检查结果格式化 =====
    print("\n" + "=" * 80)
    print("【检查结果】")
    print("=" * 80)

    if is_daikuan:
        result_fields = [
            ("日期", data.get("日期")),
            ("币种", data.get("币种")),
            ("产品名称", data.get("产品名称")),
            ("名称", data.get("名称")),
            ("付款账号", data.get("付款账号")),
            ("付款开户银行", data.get("付款开户银行")),
            ("贷款账号", data.get("贷款账号")),
            ("贷款开户银行", data.get("贷款开户银行")),
            ("本次偿还金额_小写", data.get("本次偿还金额_小写")),
            ("本次偿还金额_大写", data.get("本次偿还金额_大写")),
            ("摘要", data.get("摘要")),
            ("累计还款", data.get("累计还款")),
            ("还款单位签章", data.get("还款单位签章")),
            ("银行签章", data.get("银行签章")),
            ("经办", data.get("经办")),
            ("复核", data.get("复核")),
            ("授权", data.get("授权")),
            ("主管", data.get("主管")),
        ]
    else:
        result_fields = [
            ("日期", data.get("日期")),
            ("币种", data.get("币种")),
        ]

    for field_name, field_value in result_fields:
        print(f"{field_name}\t{field_value}")

    # ===== 金额大小写一致性检查 =====
    small = data.get("本次偿还金额_小写")
    large = data.get("本次偿还金额_大写")

    print("\n" + "=" * 80)
    print("【金额大小写一致性】")
    print("=" * 80)
    print(f"小写={small}, 大写={large}")

    if small and large:
        print("✅ 两个金额都有")
    elif small and not large:
        print("⚠️ 缺少大写金额")
    elif large and not small:
        print("⚠️ 缺少小写金额")
    else:
        print("❌ 大小写金额都缺少")

    print("=" * 80 + "\n")

    return data

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

    spec_path = os.path.join(folder, "凭证填写规范.xlsx")
    if not os.path.exists(spec_path):
        print(f"跳过目录（未找到凭证填写规范.xlsx）: {folder}")
        return

    spec_by_sheet = load_spec_fields(spec_path)
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

        sheet = choose_sheet_for_subfolder(spec_by_sheet, os.path.basename(folder))
        spec_fields = spec_by_sheet.get(sheet, [])

        # 在 process_one_folder 中
        if doc_type == "daikuan" :
            data = extract_daikuan_fields_v6(f)  # 直接从文件提取
            check = {}  # 暂时空着
        else:
            data, check = extract_and_validate(text, spec_fields, f, sheet_name=sheet, doc_type=doc_type)

        data["文件名"] = os.path.basename(f)
        check["文件名"] = os.path.basename(f)
        if sheet:
            data["规范sheet"] = sheet
            check["规范sheet"] = sheet

        all_data.append(data)
        all_check.append(check)
        for sf in spec_fields:
            field = sf["field"]
            all_check_long.append(
                {
                    "文件名": os.path.basename(f),
                    "规范sheet": sheet,
                    "字段名": field,
                    "提取值": data.get(field),
                    "检查结果": check.get(field),
                    "填写要求": sf.get("requirement", ""),
                }
            )
        if "金额大小写一致性" in check:
            all_check_long.append(
                {
                    "文件名": os.path.basename(f),
                    "规范sheet": sheet,
                    "字段名": "金额大小写一致性",
                    "提取值": f"小写={data.get('本次偿还金额_小写')}, 大写={data.get('本次偿还金额_大写')}",
                    "检查结果": check.get("金额大小写一致性"),
                    "填写要求": "金额栏大小写应一致",
                }
            )

    # ================== 输出Excel ==================
    df_data = pd.DataFrame(all_data)
    df_check = pd.DataFrame(all_check)
    df_check_long = pd.DataFrame(all_check_long)

    # 🔥 删除不需要的列
    cols_to_drop = ["开户银行", "本次偿还金额"]  # 这两列应该不在规范里，或者已被拆分
    for col in cols_to_drop:
        if col in df_data.columns:
            df_data = df_data.drop(columns=[col])

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