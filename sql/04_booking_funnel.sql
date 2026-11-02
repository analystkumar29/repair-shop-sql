-- 04. Booking funnel by month
--
-- Question: Of the repairs requested each month, how many were confirmed and
-- how many were completed? Where do bookings drop out?
--
-- Techniques: COUNT(column) only counts non-NULL values, so counting each
-- milestone timestamp gives every step of the funnel in one pass; conversion
-- rates with NULLIF.
--
-- Notes: Bookings are grouped by the month they were requested, so each row
-- follows one month's requests through to the end. The newest month still has
-- open bookings (appointments after the data ends), so its completion rate
-- will rise as those jobs happen.

WITH requests AS (
    SELECT
        CAST(date_trunc('month', created_at) AS DATE) AS month,
        status,
        confirmed_at,
        completed_at,
        cancelled_at
    FROM bookings
),

monthly AS (
    SELECT
        month,
        COUNT(*)                                                         AS requested,
        COUNT(confirmed_at)                                              AS confirmed,
        COUNT(completed_at)                                              AS completed,
        COUNT(cancelled_at)                                              AS cancelled,
        COUNT(CASE WHEN status IN ('requested', 'confirmed') THEN 1 END) AS still_open
    FROM requests
    GROUP BY month
)

SELECT
    month,
    requested,
    confirmed,
    completed,
    cancelled,
    still_open,
    ROUND(100.0 * confirmed / requested, 1)            AS confirm_rate_pct,
    ROUND(100.0 * completed / NULLIF(confirmed, 0), 1) AS confirmed_to_completed_pct,
    ROUND(100.0 * completed / requested, 1)            AS overall_conversion_pct
FROM monthly
ORDER BY month;
