"""
voucher_validator.py
验证规则模块：金额校验、一致性检查及 extract_and_validate() 入口。
新增凭证类型时：
  1. 在 voucher_extractor.py 添加新规则字典和提取函数
  2. 在此文件的 extract_and_validate() 中增加对应分支
"""
import re

from voucher_extractor import (
    BENPIAO_RULES,
    DAIKUAN_RULES,
    extract_benpiao_fields,
    extract_daikuan_fields_v6,
    fix_account,
)


# ================== 金额工具 ==================
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
    s = re.sub(r"[^人民币零壹贰叁肆伍陆柒捌玖拾佰仟万亿兆元角分整]", "", s)
    return s


# ================== 提取 + 校验入口 ==================
def extract_and_validate(text, spec_fields, file_path=None, sheet_name: str = "", doc_type: str = "unknown"):
    check = {}
    is_benpiao = (doc_type == "benpiao")
    is_daikuan = (doc_type == "daikuan")

    # ===== 第一步：提取数据 =====
    if is_benpiao:
        data = extract_benpiao_fields(text, spec_fields, file_path)
        for field in BENPIAO_RULES.keys():
            if field not in data:
                data[field] = None
    elif is_daikuan:
        data = extract_daikuan_fields_v6(file_path)
        for field in DAIKUAN_RULES.keys():
            if field not in data:
                data[field] = None
    else:
        data = {}

    # ===== 第二步：选择规则 =====
    if is_benpiao:
        rules = BENPIAO_RULES
    elif is_daikuan:
        rules = DAIKUAN_RULES
    else:
        rules = {}

    # ===== 第三步：根据规则检查每个字段 =====
    for field_name, rule in rules.items():
        value = data.get(field_name)
        required = rule.get("required", False)

        # 账号纠错
        if field_name in ["账号", "收款账号", "申请人账号", "收款人账号", "付款账号", "贷款账号"]:
            value = fix_account(value) if value else None
            data[field_name] = value

        if not value:
            if required:
                check[field_name] = "FAIL-缺失"
            else:
                check[field_name] = "PASS"
        else:
            check[field_name] = "PASS"

    # ===== 第四步：特殊检查 =====
    # 本票：金额大小写一致性
    if is_benpiao:
        amount_small = data.get("金额小写")
        amount_large = data.get("金额大写")

        if amount_small and amount_large:
            try:
                num_match = re.search(r"(\d+\.\d{2})", str(amount_small))
                if num_match:
                    num = num_match.group(1)
                    expected_upper = _money_to_upper(num)
                    if expected_upper:
                        a = _normalize_upper_amount_text(amount_large)
                        b = _normalize_upper_amount_text(expected_upper)
                        check["金额大小写一致性"] = "一致" if a == b else "不一致"
                    else:
                        check["金额大小写一致性"] = "无法校验"
                else:
                    check["金额大小写一致性"] = "无法提取数值"
            except Exception as e:
                check["金额大小写一致性"] = f"校验失败: {e}"
        else:
            check["金额大小写一致性"] = "FAIL-缺失金额"

    # 贷款凭证：金额大小写一致性
    if is_daikuan:
        amount_small = data.get("本次偿还金额_小写")
        amount_large = data.get("本次偿还金额_大写")

        if amount_small and amount_large:
            try:
                num_match = re.search(r"(\d+\.\d{2})", str(amount_small))
                if num_match:
                    num = num_match.group(1)
                    expected_upper = _money_to_upper(num)
                    if expected_upper:
                        a = _normalize_upper_amount_text(amount_large)
                        b = _normalize_upper_amount_text(expected_upper)
                        check["金额一致性"] = "一致" if a == b else "不一致"
                    else:
                        check["金额一致性"] = "无法校验"
                else:
                    check["金额一致性"] = "无法提取数值"
            except Exception as e:
                check["金额一致性"] = f"校验失败: {e}"
        else:
            check["金额一致性"] = "FAIL-缺失金额"

    return data, check
