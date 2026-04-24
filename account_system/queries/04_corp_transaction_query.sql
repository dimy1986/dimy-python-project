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

SELECT 
--a.cmpt_trcno 组件流水号,
a.data_date 数据日期,
a.cst_accno 客户账号,
b.accno_nm 账户名,
a.txn_dt 交易日期,
a.cst_id 客户编号,
a.txn_rmrk 交易备注,
a.smy_cd 摘要代码,
c.cd_dsc 摘要,
a.txn_lcl_dt 交易本地日期,
a.txn_lcl_tm 交易本地时间,
a.dep_dhamt 存款借方发生额,
a.dep_cr_hpnam 存款贷方发生额,
a.dep_txnamt 存款交易金额,
a.dep_acba 存款账户余额,
a.txn_fnds_use_cd 交易资金用途代码,
a.txn_fnds_use_rmrk 交易资金用途备注,
a.cntrprtbookentr_accno 对方记账账号,
a.cntrprtbookentracnonm 对方记账账号名称,
a.cntrprt_kpaccbnk_no 对方记账行号,
a.cntrprt_txn_accno 对方交易账号,
a.cntrprt_txn_accno_nm 对方交易账号名称,
a.cntrprt_txn_py_brno 对方交易支付行号,
a.cntrprt_trdbrh_nm 对方交易行名

 FROM bdmf.bdmf_f_ev_corp_dmddep_acc_tndtl_a a LEFT JOIN bdmf.bdmf_detail_ar_deposit_corp_info_h b  
 ON a.cst_accno=b.cst_accno  AND a.ccycd=b.ccy  AND b.start_date<=sysdate-1 AND b.end_date>sysdate-1 AND b.start_date>=substr(sysdate-1,1,8)||'01' 
 LEFT JOIN  bdmf.bdmf_f_cm_pblc_dct_inf c ON a.smy_cd=c.cd_val AND c.dct_id ='11479'
  
 WHERE a.txn_dt BETWEEN  %s AND  %s
AND {field} LIKE %s
ORDER BY a.txn_lcl_dt||a.txn_lcl_tm 

