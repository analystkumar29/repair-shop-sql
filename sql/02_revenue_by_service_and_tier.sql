-- 02. Revenue by service and price tier
--
-- Question: Which repairs bring in the most money, and how does each one's
-- revenue split across the Value, Recommended and Premium tiers?
--
-- Techniques: joins to lookup tables, conditional aggregation (a CASE inside
-- SUM) to turn the tiers into columns, SUM(SUM(...)) OVER () for each
-- service's share of all revenue.
--
-- Notes: The inner SUM is the per-service total from GROUP BY; the outer
-- SUM() OVER () adds those totals across every row of the result, which gives
-- the grand total without a second query.

WITH completed AS (
    SELECT
        s.device_type,
        s.service_name,
        t.tier_name,
        b.final_price
    FROM bookings AS b
    JOIN services AS s    ON s.service_id = b.service_id
    JOIN price_tiers AS t ON t.tier_id = b.tier_id
    WHERE b.status = 'completed'
)

SELECT
    device_type,
    service_name,
    COUNT(*)                                                             AS jobs,
    SUM(CASE WHEN tier_name = 'Value'       THEN final_price ELSE 0 END) AS value_revenue,
    SUM(CASE WHEN tier_name = 'Recommended' THEN final_price ELSE 0 END) AS recommended_revenue,
    SUM(CASE WHEN tier_name = 'Premium'     THEN final_price ELSE 0 END) AS premium_revenue,
    SUM(final_price)                                                     AS total_revenue,
    ROUND(100.0 * SUM(CASE WHEN tier_name = 'Premium' THEN final_price ELSE 0 END)
          / SUM(final_price), 1)                                         AS premium_share_pct,
    ROUND(100.0 * SUM(final_price) / SUM(SUM(final_price)) OVER (), 1)   AS share_of_all_revenue_pct
FROM completed
GROUP BY device_type, service_name
ORDER BY total_revenue DESC;
