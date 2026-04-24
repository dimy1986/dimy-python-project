-- ============================================================
-- 账户信息查询 SQL 模板
-- 说明：
--   {field}  由 Python 代码在执行前替换为实际列名（来自白名单校验）
--   %s       为 pyhive 参数占位符，对应查询关键词（含通配符，例如 %张三%）
--
-- 如需修改查询的表名或列名，请直接编辑本文件。
-- 请确保 {field} 替换后的列名在 Inceptor 表中实际存在。
-- ============================================================

SELECT DISTINCT 
a.cst_id 统一客户编号,
b.crdt_no 证件号码,
chn_nm 中文名称,
fam_adr 家庭地址,
mblph_no 移动电话,
a.opnacc_dt 客户开户日期,
a.opnacc_inst 客户开户机构,
a.opnacc_inst_nm 客户开户机构名称,
a.opnacc_inst_blng_br 客户开户机构所属分行,
a.opnacc_inst_blng_br_nm 客户开户机构所属分行名称,
c.cardno 卡表借记卡卡号,
c.opncrd_dt 开卡日期,cnccrd_dt 销卡日期,
d.dbcrd_cardno 帐户表借记卡卡号,
d.cst_accno 客户账号,
d.ccy 币种,
d.ccycddsc 币种描述,
d.cshex_cd 钞汇代码,
d.trm_depseqno 定期笔号,
d.acct_ins 账户机构,
d.acct_ins_nm 账户机构名称,
d.fxdm_ind 定活标志,
d.fxdm_ind_nm 定活标志描述,
d.sbj_no 科目号,
d.sbj_nm 科目名称,
d.pd_id 产品号,
d.pd_nm 产品名称,
d.opnacc_dt 开户日期,
d.opacins 开户机构,
d.opacins_nm 开户机构名称,
d.opnacc_chnl 开户渠道,
d.opnacc_chnldsc 开户渠道描述,
d.cnclacct_dt 销户日期,
d.cnclacct_ins 销户机构,
d.bal 余额,
d.dcny_bal 折人民币余额

FROM bdmf.bdmf_detail_ip_cust_per_info_h a LEFT JOIN bdmf.bdmf_detail_ip_cust_per_snstv_info_h b ON a.cst_id=b.cst_id AND 
 b.start_date<=sysdate-1 AND b.end_date>sysdate-1 AND b.start_date>=substr(sysdate-1,1,8)||'01' 
LEFT JOIN bdmf.bdmf_detail_ar_deposit_per_info_h d ON a.cst_id=d.cst_id AND d.start_date<=sysdate-1 AND d.end_date>sysdate-1 AND d.start_date>=substr(sysdate-1,1,8)||'01'  
LEFT JOIN bdmf.bdmf_detail_pd_card_base_info_h c ON d.dbcrd_cardno=c.cardno AND c.start_date<=sysdate-1 AND c.end_date>sysdate-1 AND c.start_date>=substr(sysdate-1,1,8)||'01' 
WHERE a.start_date<=sysdate-1 AND a.end_date>sysdate-1 AND a.start_date>=substr(sysdate-1,1,8)||'01'
AND {field} like %s 
order by 统一客户编号,客户账号

