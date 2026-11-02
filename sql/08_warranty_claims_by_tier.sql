-- 08. Warranty claim rate by price tier
--
-- Question: Do cheaper tiers come back under warranty more often, and how does
-- that compare with what each tier costs?
--
-- Techniques: CTEs, a LEFT JOIN so jobs without a claim still count, and a
-- fixed observation window so every tier is compared on the same terms.
--
-- Notes: Warranty length differs by tier (3, 6 or 12 months), so simply
-- counting all claims would compare different amounts of time. Instead this
-- counts claims made within 90 days of the repair, and only for jobs completed
-- at least 90 days before the data ends, so every job had the full 90 days.

WITH data_end AS (
    SELECT MAX(created_at) AS as_of
    FROM bookings
),

eligible_jobs AS (
    SELECT b.booking_id, b.tier_id, b.completed_at, b.final_price
    FROM bookings AS b
    CROSS JOIN data_end AS d
    WHERE b.status = 'completed'
      AND b.completed_at <= d.as_of - INTERVAL '90 days'
),

claimed_within_90_days AS (
    SELECT DISTINCT j.booking_id  -- a job with two claims still counts once
    FROM eligible_jobs AS j
    JOIN warranty_claims AS w ON w.booking_id = j.booking_id
    WHERE w.claimed_at <= j.completed_at + INTERVAL '90 days'
)

SELECT
    t.tier_name,
    t.warranty_months,
    COUNT(*)                                         AS jobs,
    ROUND(AVG(j.final_price), 2)                     AS avg_price,
    COUNT(c.booking_id)                              AS jobs_with_a_claim,
    ROUND(100.0 * COUNT(c.booking_id) / COUNT(*), 1) AS claim_rate_pct
FROM eligible_jobs AS j
JOIN price_tiers AS t ON t.tier_id = j.tier_id
LEFT JOIN claimed_within_90_days AS c ON c.booking_id = j.booking_id
GROUP BY t.tier_id, t.tier_name, t.warranty_months
ORDER BY t.tier_id;
