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
b.cst_id 统一客户编号,
chn_nm 中文名称,
b.opnacc_dt 客户开户日期,
dpbkinno 开户机构,
opacinsnm 开户机构名称,
cst_stcd 客户状态,
cst_stdsc 客户状态描述,
csrt 客户评级,
adiv_cd 行政区划,
adiv_dsc 行政区划描述,
bb.cst_accno 客户账号,
bb.accno_nm 账户名称,
bb.opnacc_dt 账号开户日期,
acc_insid 账户机构,
acc_inst_nm 账户机构名称,
acc_tpcd 账户类型,
acc_tpds 账户类型描述,
acc_stcd 账户状态,
acc_stdsc 账户状态描述,
acchar_cd 账户性质,
acchar_dsc 账户性质描述


FROM bdmf.bdmf_detail_ip_cust_corp_info_h b LEFT JOIN bdmf.bdmf_detail_ar_deposit_corp_info_h bb
ON b.cst_id=bb.cst_id AND bb.start_date<=sysdate-1 AND bb.end_date>sysdate-1 AND bb.start_date>=substr(sysdate-1,1,8)||'01' 
WHERE  
 b.start_date<=sysdate-1 AND b.end_date>sysdate-1 AND b.start_date>=substr(sysdate-1,1,8)||'01'  
AND {field} like %s 

