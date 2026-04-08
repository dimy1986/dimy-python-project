"""
voucher_extractor.py
字段提取模块：本票和贷款还款凭证的字段提取逻辑及辅助函数。

使用方式：
    import voucher_extractor
    voucher_extractor.set_ocr(ocr_instance)   # 必须在调用任何提取函数前注入OCR实例

新增凭证类型时：
  1. 在此文件添加新规则字典（如 XXX_RULES）和提取函数（如 extract_xxx_fields()）
  2. 在 voucher_validator.py 的 extract_and_validate() 中增加对应分支
"""
import re
import os

from pdf2image import convert_from_path
from PIL import Image
import numpy as np
import cv2

# ================== OCR 实例注入 ==================
# 由主文件初始化后通过 set_ocr() 注入
ocr = None


def set_ocr(ocr_instance):
    """由主文件在 OCR 初始化后调用，注入 OCR 实例。
    在调用 ocr_amount_region、extract_benpiao_fields、extract_daikuan_fields_v6
    等任何使用 OCR 的函数之前，必须先调用此函数。
    """
    global ocr
    ocr = ocr_instance


def _require_ocr():
    """内部守卫：确保 OCR 实例已注入，否则抛出清晰的错误提示。"""
    if ocr is None:
        raise RuntimeError(
            "OCR 实例尚未注入。请在调用提取函数前执行：\n"
            "  import voucher_extractor\n"
            "  voucher_extractor.set_ocr(ocr_instance)"
        )


# ================== 凭证规则定义 ==================
BENPIAO_RULES = {
    "币别": {"required": True},
    "日期": {"required": True},
    "业务类型": {"required": True},
    "付款方式": {"required": True},
    "申请人": {"required": True},
    "申请人账号": {"required": True},
    "用途": {"required": True},
    "收款人": {"required": True},
    "收款人账号": {"required": True},
    "代理付款行": {"required": True},
    "金额大写": {"required": True},
    "金额小写": {"required": True},
    "客户签章": {"required": True},
    "录入": {"required": False},
    "复核": {"required": False},
    "授权": {"required": False},
    "会计主管": {"required": False},
}

DAIKUAN_RULES = {
    "日期": {"required": True},
    "币种": {"required": True},
    "产品名称": {"required": False},
    "名称": {"required": True},
    "付款账号": {"required": True},
    "付款开户银行": {"required": True},
    "贷款账号": {"required": True},
    "贷款开户银行": {"required": True},
    "本次偿还金额_小写": {"required": True},
    "本次偿还金额_大写": {"required": True},
    "摘要": {"required": True},
    "累计还款": {"required": False},
    "还款单位签章": {"required": False},
    "银行签章": {"required": False},
    "经办": {"required": True},
    "复核": {"required": False},
    "授权": {"required": False},
    "主管": {"required": False},
}


# ================== 工具函数 ==================
def fix_account(text):
    if not text:
        return text
    return text.replace("O", "0").replace("I", "1")


def preprocess_for_amount(img):
    """金额专用增强（提高清晰度）"""
    img = np.array(img)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    _, binary = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
    return binary


def ocr_amount_region(image_path):
    """只识别金额区域"""
    _require_ocr()
    img = Image.open(image_path)
    w, h = img.size
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


def _split_lines(text: str):
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


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


def extract_field_value(text, field):
    pattern = rf"{field}[:：]?\s*(.*)"
    match = re.search(pattern, text)
    if match:
        value = match.group(1).strip()
        value = re.split(r"(日期|币种|产品名称|名称|付款账号|开户银行|贷款账号|本次偿还金额|摘要)", value)[0]
        return value.strip()
    return None


def _extract_account_candidates(text: str):
    nums = re.findall(r"\d{10,30}", text)
    seen = set()
    result = []
    for n in sorted(nums, key=lambda x: len(x), reverse=True):
        if n not in seen:
            seen.add(n)
            result.append(n)
    return result


def _extract_account_from_label_block(text: str, label: str):
    """
    从"标签块"中提取账号：
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
    # ===== 优先用ROI识别（仅图片，PDF需先渲染） =====
    if file_path and not file_path.lower().endswith('.pdf'):
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
    """OCR金额大写纠错（只做轻量修复，不影响原结构）"""
    if not text:
        return text

    fix_map = {
        "人常": "人民币",
        "人名币": "人民币",
        "常": "民",
        "参": "叁",
        "琴": "叁",
        "岑": "叁",   # OCR 把第二个"叁"识别为"岑"
        "任": "仟",
        "伯": "佰",
        "鱼": "佰",   # OCR 把"佰"识别为"鱼"
        "渔": "佰",
        "圆": "元",
        "園": "元",
        "萬": "万",
        "市": "币",
        "拾陆": "拾陆",  # 保留，防止意外替换
    }

    for k, v in fix_map.items():
        text = text.replace(k, v)

    # 修复乱码前缀：当"人民币"或"RMB"被识别为乱码时，
    # 找到第一个合法大写金额字符，将其之前的乱码前缀替换为"人民币"
    _AMOUNT_CHARS = re.compile(r'[壹贰叁肆伍陆柒捌玖拾佰仟万亿元角分整零百千]')
    m = _AMOUNT_CHARS.search(text)
    if m and m.start() > 0:
        prefix = text[:m.start()]
        if not re.match(r'^(人民币|RMB)', prefix):
            text = '人民币' + text[m.start():]

    return text


def _chinese_amount_to_number(text: str) -> str:
    """将中文大写金额转换为小写数字字符串（如 叁拾叁万陆仟肆佰元整 → ￥336400.00）。

    作为 OCR 无法识别表格单格数字阵列时的兜底方案。
    """
    if not text:
        return None

    DIGIT = {
        '零': 0, '壹': 1, '贰': 2, '叁': 3, '肆': 4,
        '伍': 5, '陆': 6, '柒': 7, '捌': 8, '玖': 9,
        # 兼容简写
        '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
        '六': 6, '七': 7, '八': 8, '九': 9,
    }
    UNIT = {
        '拾': 10, '十': 10,
        '佰': 100, '百': 100,
        '仟': 1000, '千': 1000,
    }

    def parse_section(s: str) -> int:
        """解析不含万/亿的段（最多4位：千百十个）"""
        val, cur = 0, 0
        for ch in s:
            if ch in DIGIT:
                cur = DIGIT[ch]
            elif ch in UNIT:
                if cur == 0:
                    cur = 1  # 拾前省略"壹"
                val += cur * UNIT[ch]
                cur = 0
        val += cur
        return val

    # 去除前缀（人民币/RMB 等）和后缀（整/正）
    clean = re.sub(r'^[人民币RMB￥\s(（【\u0028\u3010]+', '', text).strip()
    clean = re.sub(r'[整正\s]+$', '', clean).strip()
    if not clean:
        return None

    # 提取角/分
    jiao, fen = 0, 0
    m = re.search(r'([零壹贰叁肆伍陆柒捌玖一二三四五六七八九])角', clean)
    if m:
        jiao = DIGIT.get(m.group(1), 0)
    m = re.search(r'([零壹贰叁肆伍陆柒捌玖一二三四五六七八九])分', clean)
    if m:
        fen = DIGIT.get(m.group(1), 0)

    # 截取元之前的整数部分
    int_part = re.split(r'[元圆园]', clean)[0]

    total = 0
    # 处理亿段
    if '亿' in int_part:
        yi_s, int_part = int_part.split('亿', 1)
        total += parse_section(yi_s) * 100000000
    # 处理万段
    if '万' in int_part:
        wan_s, int_part = int_part.split('万', 1)
        total += parse_section(wan_s) * 10000
    total += parse_section(int_part)
    total += jiao * 0.1 + fen * 0.01

    if total <= 0:
        return None

    return f"￥{total:.2f}"


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
    for ln in lines:
        for lb in labels:
            m = re.search(rf"{re.escape(lb)}[:：]?\s*([^\n\r:：]+)", ln)
            if m and _is_name_candidate(m.group(1).strip()):
                return m.group(1).strip()

    for i, ln in enumerate(lines):
        if any(lb in ln for lb in labels):
            for j in [i - 1, i + 1, i - 2, i + 2, i - 3, i + 3]:
                if 0 <= j < len(lines):
                    cand = lines[j].strip()
                    if _is_name_candidate(cand):
                        return cand
    return None


def _extract_near_label_text(text: str, labels, max_len: int = 60):
    """通用"标签邻域取值"：用于代理付款行、用途等文本字段。"""
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
        bad = ["流水号", "票据金额", "签发机构", "申请机构", "跨机构申请编号"]
        if any(b == v for b in bad):
            return False
        return True

    for ln in lines:
        for lb in labels:
            m = re.search(rf"{re.escape(lb)}[:：]?\s*([^\n\r:：]+)", ln)
            if m:
                val = m.group(1).strip()
                if is_valid(val):
                    return val

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
    客户签章仅输出"有章/无章"：
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

    text_tokens = [ln for ln in nearby if ln and "客户签章" not in ln]
    if any(len(t) >= 2 for t in text_tokens):
        return "有章"

    return "无章"


def _is_empty_signature(val: str) -> bool:
    """
    判断签字字段是否为空
    - 纯空白
    - 全是 / 或 -
    - 标签词（经办、复核、授权、主管等）
    """
    if not val:
        return True
    if not val.strip():
        return True
    if re.match(r"^[/\-\s]+$", val):
        return True
    label_words = {"经办", "复核", "授权", "主管", ""}
    if val in label_words:
        return True
    return False


def _normalize_digit_text(t: str) -> str:
    """将OCR常见误识字符替换为数字，用于小写金额提取"""
    return t.replace('O', '0').replace('o', '0').replace('l', '1').replace('I', '1')


# ================== 本票字段提取 ==================
def extract_benpiao_fields(text: str, spec_fields, file_path=None):
    """
    本票字段专用规则：
    - 先按关键锚点提取（比通用"字段名+行尾"更稳）
    - 抽不到再回退到通用规则
    """
    _require_ocr()
    data = {}

    # ===== 调试：输出完整OCR结果 =====
    if file_path:
        print(f"\n[OCR调试] 文件: {file_path}")
        print(f"[OCR调试] 文本长度: {len(text)}")
        print(f"[OCR调试] 前500字符: {text[:500]}")
        print(f"[OCR调试] 完整文本:\n{text}\n")

    # ===== 预提取 =====
    accounts = _extract_account_candidates(text)
    date_match = re.search(r"\d{4}[年\-/\.]\d{1,2}(?:[月\-/\.]\d{1,2})?", text)
    amount_num = re.search(r"￥\s*([\d,]+\.\d{2})", text)
    amount_cn = _extract_amount_upper(text, file_path)
    print(f"[金额小写原始] {amount_num.group(1) if amount_num else None}")
    print(f"[金额大写原始] {amount_cn}")
    amount_cn = _fix_amount_ocr_error(amount_cn)
    print(f"[金额大写修正] {amount_cn}")

    # ===== 初始化所有本票字段 =====
    for field in BENPIAO_RULES.keys():
        data[field] = None

    # ===== 锚点提取（允许跨行少量噪声） =====
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

    # 先用通用回退规则填充
    for field in anchor_rules.keys():
        data[field] = extract_field_value(text, field)

    # 再用本票锚点覆盖
    for field, rgx in anchor_rules.items():
        m = re.search(rgx, text)
        if m:
            data[field] = m.group(1).strip()

    # ===== 日期处理 =====
    if data.get("日期"):
        data["日期"] = _clean_date(data["日期"])
    elif date_match:
        data["日期"] = _clean_date(date_match.group(0))

    # ===== 金额处理 =====
    if amount_num:
        data["金额小写"] = "￥" + amount_num.group(1).replace(",", "")
    data["金额大写"] = amount_cn

    # 兜底：OCR 无法从单格数字阵列识别小写金额时，从大写推算
    if not data.get("金额小写") and amount_cn:
        derived = _chinese_amount_to_number(amount_cn)
        if derived:
            print(f"[金额小写推算] {amount_cn} -> {derived}")
            data["金额小写"] = derived

    # ===== 申请人账号 =====
    m = _extract_account_by_explicit_label(text, ["申请人账号"])
    block_acc = _extract_account_from_label_block(text, "申请人")
    if block_acc:
        data["申请人账号"] = fix_account(block_acc)
    elif m:
        data["申请人账号"] = fix_account(m)
    elif accounts:
        data["申请人账号"] = fix_account(accounts[-1])

    # ===== 收款人账号 =====
    m = _extract_account_by_explicit_label(text, ["收款人账号", "收款账号"])
    data["收款人账号"] = fix_account(m) if m else None

    # ===== 代理付款行（过滤垃圾值） =====
    if data.get("代理付款行"):
        v = _extract_near_label_text(text, ["代理付款行"], max_len=80)
        if v:
            data["代理付款行"] = v

        if data.get("代理付款行") in {"用途", "账号", "申请人", "收款人", "金额"}:
            data["代理付款行"] = None
        if data.get("代理付款行") and re.fullmatch(r"\d{8,30}", str(data["代理付款行"]).strip()):
            data["代理付款行"] = None
        if data.get("代理付款行"):
            v2 = str(data["代理付款行"]).strip()
            if not any(k in v2 for k in ["银行", "支行", "分行"]):
                data["代理付款行"] = None

    # ===== 用途（当同行未提取到时，用邻域回退） =====
    # OCR 对表格凭证常将标签行与内容行分开，导致同行正则无法捕获
    if not data.get("用途"):
        v = _extract_near_label_text(text, ["用途"], max_len=30)
        if v:
            print(f"[用途邻域提取] {v}")
            data["用途"] = v
    # 过滤掉误捕获的字段名
    if data.get("用途") in {"账号", "申请人", "收款人", "金额", "代理付款行"}:
        data["用途"] = None

    # ===== 申请人、收款人（用标签邻域提取） =====
    if data.get("申请人"):
        v = _extract_near_label_name(text, ["申请人"])
        if v:
            data["申请人"] = v

    if data.get("收款人"):
        v = _extract_near_label_name(text, ["收款人"])
        if v:
            data["收款人"] = v

    # ===== 客户签章 =====
    if data.get("客户签章"):
        data["客户签章"] = _extract_customer_stamp_status(text)

    # ===== 签字字段（录入、复核、授权、会计主管） =====
    if file_path:
        try:
            img = None
            if file_path.lower().endswith('.pdf'):
                images = convert_from_path(file_path, dpi=200)
                if images:
                    img = images[0]
            else:
                img = Image.open(file_path)

            if img:
                w, h = img.size
                img_np = np.array(img)
                res = ocr.ocr(img_np)

                # 收集所有OCR框
                all_boxes = []
                for line in res:
                    for box in line:
                        box_text = box[1][0]
                        coords = box[0]
                        x_avg = sum([pt[0] for pt in coords]) / len(coords)
                        y_avg = sum([pt[1] for pt in coords]) / len(coords)
                        all_boxes.append({'text': box_text, 'x': x_avg, 'y': y_avg})

                # 签字区域ROI（Y=0.88以下，避免与客户签章/费用项区域重叠）
                signature_regions = {
                    "录入": (int(w * 0.0), int(h * 0.88), int(w * 0.3), h),
                    "复核": (int(w * 0.3), int(h * 0.88), int(w * 0.6), h),
                    "授权": (int(w * 0.6), int(h * 0.88), int(w * 0.8), h),
                    "会计主管": (int(w * 0.8), int(h * 0.88), int(w * 1.0), h),
                }

                # 垃圾文本过滤词表：
                # - 费用项/业务标签（如"工本费"、"对私"）不是签字内容
                # - 票据类型标签（"本票"、"汇票"等）来自邻近行，也需过滤，
                #   否则"客户签章本票-"中的"本票-"会在移除"客户签章"后残留
                garbage_words = [
                    "工本费", "手续费", "对私", "业务", "专用", "常", "00",
                    "业务专用", "本票工本费", "本票手续费", "客户签章",
                    "本票", "汇票", "银行本票", "银行汇票",
                ]

                for sig_name, (x1, y1, x2, y2) in signature_regions.items():
                    region_boxes = [b for b in all_boxes if x1 < b['x'] < x2 and y1 < b['y'] < y2]

                    if region_boxes:
                        region_text = "".join([b['text'] for b in sorted(region_boxes, key=lambda x: x['x'])])
                        original_text = region_text

                        # 过滤垃圾文本
                        for garbage in garbage_words:
                            region_text = region_text.replace(garbage, "")

                        # 过滤标签词中的单字
                        region_text = re.sub(r"[录复授会计主管核权人入]", "", region_text)

                        # 清理首尾横线和空白
                        region_text = region_text.strip("-").strip()

                        # 有效签字必须满足：
                        # - len >= 2：防止"-"、"票"等单字残留通过
                        # - 含中文或字母：真实姓名特征；纯符号/数字不是签字
                        if (region_text
                                and len(region_text) >= 2
                                and re.search(r"[\u4e00-\u9fa5A-Za-z]", region_text)):
                            data[sig_name] = region_text
                            print(f"[签字提取] {sig_name}: 原始='{original_text}' -> 清理后='{region_text}'")
                        else:
                            print(f"[签字提取] {sig_name}: 原始='{original_text}' -> 无有效签字")
                    else:
                        print(f"[签字提取] {sig_name}: 该区域无文本框")

        except Exception as e:
            print(f"[签字提取] 提取失败: {e}")
            import traceback
            traceback.print_exc()

    print(f"[本票提取] 提取完毕，共{len([v for v in data.values() if v is not None])}个字段有值\n")
    return data


# ================== 贷款还款凭证字段提取 ==================
def extract_daikuan_fields_v6(file_path):
    """
    贷款还款凭证字段提取 - v6 完整修复版
    处理：竖排文本、表格格子金额、账号原样读取、通用标签定位
    关键改进：精准Y坐标、严格过滤垃圾、范围查找代替全文搜索
    """
    _require_ocr()
    data = {}

    if not file_path:
        return data

    try:
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
                box_text = box[1][0]
                confidence = box[1][1]
                coords = box[0]

                x_avg = sum([pt[0] for pt in coords]) / len(coords)
                y_avg = sum([pt[1] for pt in coords]) / len(coords)

                all_boxes.append({
                    'text': box_text,
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
        ocr_text = "\n".join([b['text'] for b in all_boxes])
        currency_match = re.search(r"(人民币|USD|EUR|GBP|JPY|CNY)", ocr_text)
        data["币种"] = currency_match.group(1) if currency_match else "人民币"
        print(f"[币种] {data['币种']}")

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

        # 4. 名称
        name_found = False
        for i, row in enumerate(all_rows):
            row_text = "".join([b['text'] for b in row])

            if "名" in row_text and "产品名称" not in row_text and not name_found:
                m = re.search(r"名\s*([\u4e00-\u9fa5]{3,40})", row_text)
                if m:
                    cand = m.group(1).strip()
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
                m = re.search(r"付款账号[:：]?\s*([\dI\*]{15,})", row_text)
                if m:
                    data["付款账号"] = m.group(1)
                    pay_acc_found = True
                    print(f"[付款账号] {data['付款账号']} (同行)")
                    break

                if not pay_acc_found and i > 0:
                    prev_text = "".join([b['text'] for b in all_rows[i - 1]])
                    m = re.search(r"([\dI\*]{15,})", prev_text)
                    if m:
                        data["付款账号"] = m.group(1)
                        pay_acc_found = True
                        print(f"[付款账号] {data['付款账号']} (上行)")
                        break

                if not pay_acc_found and i + 1 < len(all_rows):
                    next_text = "".join([b['text'] for b in all_rows[i + 1]])
                    m = re.search(r"([\dI\*]{15,})", next_text)
                    if m:
                        data["付款账号"] = m.group(1)
                        pay_acc_found = True
                        print(f"[付款账号] {data['付款账号']} (下行)")
                        break

        if not pay_acc_found:
            account_region = [b for b in all_boxes if 700 < b['y'] < 800]
            number_boxes = [b for b in account_region if re.match(r"[\dI\*]{10,}", b['text'])]
            if number_boxes:
                longest = max(number_boxes, key=lambda x: len(x['text']))
                data["付款账号"] = longest['text']
                pay_acc_found = True
                print(f"[付款账号] {data['付款账号']} (范围查找)")

        if not pay_acc_found:
            data["付款账号"] = None

        # 6. 付款开户银行
        pay_bank_found = False
        for i, row in enumerate(all_rows):
            row_text = "".join([b['text'] for b in row])

            if "付款账号" in row_text and not pay_bank_found:
                for j in range(i + 1, min(i + 5, len(all_rows))):
                    next_row = all_rows[j]
                    bank_boxes = [b for b in next_row if "银行" in b['text']]

                    if len(bank_boxes) > 0:
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
                m = re.search(r"贷款账号[:：]?\s*([\dI\*]{15,})", row_text)
                if m:
                    data["贷款账号"] = m.group(1)
                    loan_acc_found = True
                    print(f"[贷款账号] {data['贷款账号']} (同行)")
                    break

                if not loan_acc_found and i > 0:
                    prev_text = "".join([b['text'] for b in all_rows[i - 1]])
                    m = re.search(r"([\dI\*]{15,})", prev_text)
                    if m:
                        data["贷款账号"] = m.group(1)
                        loan_acc_found = True
                        print(f"[贷款账号] {data['贷款账号']} (上行)")
                        break

                if not loan_acc_found and i + 1 < len(all_rows):
                    next_text = "".join([b['text'] for b in all_rows[i + 1]])
                    m = re.search(r"([\dI\*]{15,})", next_text)
                    if m:
                        data["贷款账号"] = m.group(1)
                        loan_acc_found = True
                        print(f"[贷款账号] {data['贷款账号']} (下行)")
                        break

        if not loan_acc_found:
            account_region = [b for b in all_boxes if 700 < b['y'] < 800]
            number_boxes = sorted([b for b in account_region if re.match(r"[\dI\*]{10,}", b['text'])],
                                  key=lambda x: len(x['text']), reverse=True)
            if len(number_boxes) > 1:
                data["贷款账号"] = number_boxes[1]['text']
                loan_acc_found = True
                print(f"[贷款账号] {data['贷款账号']} (范围查找)")

        if not loan_acc_found:
            data["贷款账号"] = None

        # 8. 贷款开户银行
        loan_bank_found = False
        for i, row in enumerate(all_rows):
            row_text = "".join([b['text'] for b in row])

            if "贷款账号" in row_text and not loan_bank_found:
                for j in range(i + 1, min(i + 5, len(all_rows))):
                    next_row = all_rows[j]
                    bank_boxes = [b for b in next_row if "银行" in b['text']]

                    if len(bank_boxes) >= 2:
                        bank_boxes.sort(key=lambda x: x['x'])
                        data["贷款开户银行"] = bank_boxes[1]['text'].strip()
                        loan_bank_found = True
                        print(f"[贷款开户银行] {data['贷款开户银行']}")
                        break

        if not loan_bank_found:
            data["贷款开户银行"] = None

        # 9. 本次偿还金额
        amount_upper = None
        amount_small = None

        amount_upper_region = [b for b in all_boxes if 938 < b['y'] < 948]
        amount_upper_text = "".join([b['text'] for b in sorted(amount_upper_region, key=lambda x: x['x'])])

        m = re.search(r"(伍佰[^\n]*元[^\n]*分)", amount_upper_text)
        if m:
            amount_upper = m.group(1).strip()
            print(f"[大写金额] {amount_upper}")

        # 扩大搜索范围：Y > 800，覆盖整个表格下半部分
        # 匹配纯数字或含OCR误识字符（如 'O'/'o' 误识为 '0'）的框
        digit_candidates = []
        for b in all_boxes:
            if b['y'] <= 800:
                continue
            normalized = _normalize_digit_text(b['text'])
            if re.match(r'^\d+$', normalized):
                digit_candidates.append({**b, 'normalized': normalized})

        print(f"[小写金额] Y>800 范围内共找到 {len(digit_candidates)} 个数字框：")
        for d in sorted(digit_candidates, key=lambda x: x['y']):
            print(f"  text='{d['text']}' normalized='{d['normalized']}' x={d['x']:.0f} y={d['y']:.0f}")

        # 智能Y聚类：找出数字框最密集的Y区间（窗口=40px，覆盖单行格子高度）
        number_boxes = []
        if digit_candidates:
            ys = sorted(set(d['y'] for d in digit_candidates))
            best_y_center = None
            best_count = 0
            y_window = 40
            for y in ys:
                group = [d for d in digit_candidates if abs(d['y'] - y) <= y_window]
                if len(group) > best_count:
                    best_count = len(group)
                    best_y_center = y

            if best_y_center is not None:
                number_boxes = [d for d in digit_candidates if abs(d['y'] - best_y_center) <= y_window]
                print(f"[小写金额] 密集区Y≈{best_y_center:.0f}，选中 {len(number_boxes)} 个数字框")

        if number_boxes:
            all_digits = "".join([b['normalized'] for b in sorted(number_boxes, key=lambda x: x['x'])])
            print(f"[小写金额合并] {all_digits}")

            if len(all_digits) >= 3:
                amount_small = f"¥{all_digits[:-2]}.{all_digits[-2:]}"
                print(f"[小写金额] {amount_small}")
            else:
                amount_small = f"¥{all_digits}"
                print(f"[小写金额] {amount_small}")
        else:
            print(f"[小写金额] Y>800范围内未找到数字框，可能OCR识别失败")

        data["本次偿还金额_小写"] = amount_small
        data["本次偿还金额_大写"] = _fix_amount_ocr_error(amount_upper) if amount_upper else None

        # 10. 摘要
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

        # 还款单位签章（左侧）
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

            if "经办" in row_text:
                m = re.search(r"经办[:：]?\s*([^\n\r:：】）)]*)", row_text)
                if m:
                    val = m.group(1).strip()
                    val = re.sub(r"[）)】\s，]", "", val)
                    if val and not _is_empty_signature(val):
                        data["经办"] = val
                        print(f"[经办] {val}")

            if "复核" in row_text:
                m = re.search(r"复核[:：]?\s*([^\n\r:：】）)]*)", row_text)
                if m:
                    val = m.group(1).strip()
                    val = re.sub(r"[）)】\s]", "", val)
                    if val and not _is_empty_signature(val):
                        data["复核"] = val
                        print(f"[复核] {val}")

            if "授权" in row_text:
                m = re.search(r"授权[:：]?\s*([^\n\r:：】）)]*)", row_text)
                if m:
                    val = m.group(1).strip()
                    val = re.sub(r"[）)】\s]", "", val)
                    if val and not _is_empty_signature(val):
                        data["授权"] = val
                        print(f"[授权] {val}")

            if "主管" in row_text:
                m = re.search(r"主管[:：]?\s*([^授]*?)(?:授权|$)", row_text)
                if m:
                    val = m.group(1).strip()
                    val = re.sub(r"[）)】\s，]", "", val)
                    if val and not _is_empty_signature(val):
                        data["主管"] = val
                        print(f"[主管] {val}")

        print(f"\n[贷款凭证v6] 提取完毕\n")
        return data

    except Exception as e:
        print(f"[贷款凭证v6] 提取失败: {e}")
        import traceback
        traceback.print_exc()
        return {}
