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
a.data_date 数据日期,
a.ovrlsttn_ev_trck_no 全局事件跟踪号,
a.cst_accno 客户账号,
b.opnacc_dt 开户日期,
b.dbcrd_cardno 借记卡卡号,
b.cst_nm 客户姓名,
a.txn_dt 交易日期,
a.cst_id 客户编号,
a.stm_dt 系统日期,
a.txn_lcl_tm 交易本地时间,
a.txn_lcl_dt 交易本地日期,
a.ccycd 币种代码,
c.cd_dsc 交易渠道,
CASE WHEN a.dep_dhamt=0 AND a.dep_cr_hpnam>0 THEN '10'  WHEN a.dep_dhamt>0 AND a.dep_cr_hpnam=0  THEN '11' END AS 借贷方向代码,
a.dep_txnamt 存款交易金额,
a.dep_dhamt 存款借方发生额,
a.dep_cr_hpnam 存款贷方发生额,
a.dep_acba 变更后账户余额,
a.txn_rmrk 交易备注,
a.smy_cd 摘要代码,
d.cd_dsc 摘要,
a.cntrprtbookentr_accno 对方记账账号,
a.cntrprtbookentracnonm 对方记账账号名称,
a.cntrprt_kpaccbnk_no 对方记账行号,
a.cntrprt_txn_accno 对方交易账号,
a.cntrprt_txn_accno_nm 对方交易账号名称,
a.cntrprt_trdbrh_nm 对方交易行名,
a.cntrprt_txn_py_brno 对方交易支付行号
 from bdmf.BDMF_F_EV_PRVT_DMDDEP_ACC_TNDTL_a a LEFT JOIN bdmf.BDMF_DETAIL_AR_DEPOSIT_PER_INFO_h b
 ON a.cst_accno =b.cst_accno  AND a.ccycd=b.ccy AND start_date<=sysdate-1 AND end_date>sysdate-1 AND start_date>=substr(sysdate-1,1,8)||'01' 
 LEFT JOIN bdmf.bdmf_f_cm_pblc_dct_inf  c ON a.txn_itt_chnl_tpcd=c.cd_val AND c.dct_id='11476'
  LEFT JOIN  bdmf.bdmf_f_cm_pblc_dct_inf d ON a.smy_cd=d.cd_val AND d.dct_id ='11479'
 WHERE a.txn_dt BETWEEN  %s AND  %s
AND {field} LIKE %s
ORDER BY a.txn_lcl_dt||a.txn_lcl_tm 

