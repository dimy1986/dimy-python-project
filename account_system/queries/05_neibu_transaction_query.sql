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

SELECT inracc_id 内部账编号,
inracc_blng_insid 内部账所属机构编号,
inracc_dtl_dt 内部账明细日期,
inracc_dtl_sn 内部账明细序号,
inracc_dtl_crwrtoff_id 内部账明细挂销账编号,
inracc_dtl_exrt 内部账明细汇率,
inracc_dtl_txn_inst_ecd 内部账明细交易机构编码,
inracc_dtl_txn_cgycd 内部账明细交易类别代码,
decode(inracc_dtl_dbtcrdrccd,'1','出账','2','入账',inracc_dtl_dbtcrdrccd) 内部账明细借贷方向代码,
inracc_dtl_bal 内部账明细余额,
inracc_dtl_amt 内部账明细金额,
inracc_dtl_dsc 内部账明细描述,
inracc_dtl_vchr_beg_no 内部账明细凭证起始号,
inracc_dtl_vchr_tmt_no 内部账明细凭证终止号,
inracc_dtl_vchr_ctcd 内部账明细凭证种类代码,
inracc_dtl_bal_dborcrtp_cd 内部账明细余额借贷别代码,
txn_itt_chnl_cgy 交易发起渠道类别,
txn_ctlg_ecd 交易种类编码,
ovrlsttn_ev_trck_no 全局事件跟踪号,
strd_sn 子交易序号,
cntrprt_txn_py_brno 对方交易支付行号,
cntrprt_txn_accno 对方交易账号,
cntrprt_txn_accno_nm 对方交易账号名称,
cntrprt_kpaccbnk_no 对方记账行号,
cntrprt_bookentr_accno 对方记账账号,
cntrprt_bookentr_accno_nm 对方记账账号名称 FROM bdmf.BDMF_F_EV_INRACC_DTL_a WHERE inracc_dtl_dt BETWEEN  %s AND  %s
AND {field} LIKE %s
ORDER BY inracc_dtl_dt

