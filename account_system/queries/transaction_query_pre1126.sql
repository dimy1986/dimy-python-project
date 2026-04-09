-- ============================================================
-- 交易查询（pre1126） SQL 模板
-- 说明：
--   无 {field} 占位符，查询条件固定，Python 通过 params_pattern
--   按序注入以下 10 个 %s 参数（参见 transaction_query_pre1126.json）：
--     第 1–2  个 %s → aa 表 partid 起止（YYYYMM）
--     第 3–5  个 %s → aa 表 cif_cust_no / cont_acct / sub_acct_no（精确匹配）
--     第 6–7  个 %s → bb 表 partid 起止（YYYYMM）
--     第 8–10 个 %s → bb 表 CIF_CUST_NO / TRAD_ACCT / TRAD_CHILD_ACCT（精确匹配）
--
-- 页面日期选择器输入 YYYY-MM-DD，_build_params 会自动截取为 YYYYMM。
-- 关键词输入客户号或账号，系统同时匹配两种字段，无需切换查询类型。
-- ============================================================

WITH aa AS (
    SELECT
        trad_date               交易日期,
        trad_seri_no            交易流水号,
        detail_trad_seri_no     明细交易流水号,
        subj                    科目号,
        org_no                  机构号,
        cif_cust_no             统一客户号,
        debit_credit_site       借贷标志,
        trad_code               交易代码,
        cont_acct               容器账户号,
        sub_acct_no             子账号,
        acct_org                账户机构,
        acct_name               账户名称,
        trad_advs_main_acct     交易对手主账户,
        trad_advs_cust_no       交易对手方客户号,
        trad_advs_acct_name     交易对手方户名,
        trad_advs_acct_no       交易对手账号,
        trad_advs_org_no        交易对手方机构,
        ccy                     币种,
        trad_amt                交易金额,
        cunt_no_bal             本次余额,
        trad_time               交易时间
    FROM cdm.cdm_td_vchr_seri_hs
    WHERE partid BETWEEN %s AND %s
      AND (cif_cust_no = %s OR cont_acct = %s OR sub_acct_no = %s)
),
bb AS (
    SELECT
        TRAD_DATE               交易日期,
        TRAD_TIME               交易时间,
        TRAD_SERI_NO            交易流水号,
        TRAD_SUMMY              交易摘要,
        CIF_CUST_NO             统一客户号,
        TRAD_ACCT               交易账号,
        TRAD_CHILD_ACCT         交易子账号
    FROM cdm.CDM_TD_TRAD_BASE_hs
    WHERE partid BETWEEN %s AND %s
      AND (CIF_CUST_NO = %s OR TRAD_ACCT = %s OR TRAD_CHILD_ACCT = %s)
)
SELECT aa.*, bb.交易摘要
FROM aa
LEFT JOIN bb
       ON aa.交易流水号 = bb.交易流水号
      AND aa.交易日期   = bb.交易日期
ORDER BY 容器账户号, 交易时间
