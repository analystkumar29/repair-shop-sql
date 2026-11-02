-- 07. Booking lead time by city
--
-- Question: How long do customers wait between booking and their appointment
-- in each area? The median shows the typical wait; the 90th percentile shows
-- the long tail that an average would hide.
--
-- Techniques: interval arithmetic, PERCENTILE_CONT(...) WITHIN GROUP (ORDER
-- BY ...), an ordered-set aggregate for medians and percentiles, and a
-- conditional count.
--
-- Notes: Uses confirmed bookings, whose scheduled_for is the agreed
-- appointment. The outer areas are only visited on route days (service_days),
-- which is why their waits are longer.

WITH lead_times AS (
    SELECT
        c.city_name,
        c.service_days,
        EXTRACT(EPOCH FROM (b.scheduled_for - b.created_at)) / 86400.0 AS lead_days
    FROM bookings AS b
    JOIN cities AS c ON c.city_id = b.city_id
    WHERE b.confirmed_at IS NOT NULL
)

SELECT
    city_name,
    service_days,
    COUNT(*) AS bookings,
    -- percentile_cont returns a double; the CAST lets ROUND(value, 1) work in PostgreSQL too
    ROUND(CAST(percentile_cont(0.5) WITHIN GROUP (ORDER BY lead_days) AS NUMERIC), 1) AS median_days,
    ROUND(CAST(percentile_cont(0.9) WITHIN GROUP (ORDER BY lead_days) AS NUMERIC), 1) AS p90_days,
    ROUND(100.0 * COUNT(CASE WHEN lead_days <= 1 THEN 1 END) / COUNT(*), 1)          AS within_24_hours_pct
FROM lead_times
GROUP BY city_name, service_days
ORDER BY median_days, city_name;
