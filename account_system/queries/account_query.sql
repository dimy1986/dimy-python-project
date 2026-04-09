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
c.dbcrd_cardno 借记卡卡号,
chn_nm 中文名称,
fam_adr 家庭地址,
mblph_no 移动电话,
opnacc_dt 开户日期,
opnacc_inst 开户机构,
opnacc_inst_nm 开户机构名称,
opnacc_inst_blng_br 开户机构所属分行,
opnacc_inst_blng_br_nm 开户机构所属分行名称
FROM bdmf.bdmf_detail_ip_cust_per_info_h a JOIN bdmf.bdmf_detail_ip_cust_per_snstv_info_h b ON a.cst_id=b.cst_id AND 
 b.start_date<=sysdate-1 AND b.end_date>sysdate-1 AND b.start_date>=substr(sysdate-1,1,8)||'01' 
JOIN bdmf.bdmf_f_ar_dbcrd_crd_inf_h c ON a.cst_id=c.cst_id AND c.start_date<=sysdate-1 AND c.end_date>sysdate-1 AND c.start_date>=substr(sysdate-1,1,8)||'01'  
WHERE a.start_date<=sysdate-1 AND a.end_date>sysdate-1 AND a.start_date>=substr(sysdate-1,1,8)||'01'
AND {field} like %s 

