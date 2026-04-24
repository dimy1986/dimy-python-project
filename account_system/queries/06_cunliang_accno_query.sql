-- ============================================================
-- 交易信息查询 SQL 模板
-- 说明：
--   {field}  由 Python 代码在执行前替换为实际列名（来自白名单校验）
--   %s       为 pyhive 参数占位符，按顺序对应：
--              第 1 个 %s → 开始日期 (date_from)
--              第 2 个 %s → 结束日期 (date_to)
--              第 3 个 %s → 查询关键词（含通配符，例如 %6222%）
--
-- 如需修改查询的表名或列名，请直接编辑本文件。
-- 请确保 {field} 替换后的列名在 Inceptor 表中实际存在。
-- ============================================================

--1 银行账号	2 银行卡号/企业账号	3 银行卡归属地区	4 证件号码/企业统一代码	
--5 姓名/企业名称	6 电话号码	7 开户时间	8 开户网点名称
--9 卡类型	10 批次号	11 法人身份证号	12 法人姓名	13 法人手机号	14 风险模型名称
SELECT cst_accno 银行账号,
cst_accno "银行卡号/企业账号",
'' 银行卡归属地区,
bb.unn_soc_cr_no "证件号码/企业统一代码",	
bb.cst_nm "姓名/企业名称",
bb.ctc_tel 电话号码,
aa.opnacc_dt 开户时间,
aa.opacins_nm 开户网点名称,
'' 卡类型,
'' 批次号,
bb.lgl_rprs_crdt_no  法人身份证号,
bb.lgl_rprs_nm 法人姓名,
bb.lglrprsfixtel_ctc_tel  法人手机号,
'' 风险模型名称
FROM bdmf.bdmf_detail_ar_deposit_corp_info_h aa LEFT JOIN 
bdmf.bdmf_tp01_corp_cst_bsc_inf_w bb ON aa.cst_id=bb.cst_id
AND bb.data_date=to_char(sysdate-1,'YYYYMMDD')
WHERE aa.start_date<=sysdate-1 AND aa.end_date>sysdate-1 AND aa.start_date>=substr(sysdate-1,1,8)||'01'


