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
    trans_date,
    trans_time,
    account_no,
    account_name,
    customer_no,
    trans_type,
    amount,
    direction,
    balance_after,
    channel,
    remark
FROM transactions
WHERE trans_date BETWEEN %s AND %s
  AND {field} LIKE %s
ORDER BY trans_date DESC, trans_time DESC
