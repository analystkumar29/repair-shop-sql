-- 01. Monthly revenue, month-over-month change and running totals
--
-- Question: How much did completed repairs bring in each month, how did that
-- compare with the month before, and what is the running total for the year
-- and since the data starts?
--
-- Techniques: CTEs, LAG() to read the previous month's row, SUM() OVER with a
-- window frame for running totals, NULLIF so a zero month can't divide by zero.
--
-- Notes: Revenue is the final_price of completed bookings (it includes the
-- travel fee), counted in the month the job was completed.

WITH completed_jobs AS (
    SELECT
        CAST(date_trunc('month', completed_at) AS DATE) AS month,
        final_price
    FROM bookings
    WHERE status = 'completed'
),

monthly AS (
    SELECT
        month,
        COUNT(*)         AS jobs,
        SUM(final_price) AS revenue
    FROM completed_jobs
    GROUP BY month
),

with_previous AS (
    SELECT
        month,
        jobs,
        revenue,
        LAG(revenue) OVER (ORDER BY month) AS previous_revenue  -- NULL for the first month
    FROM monthly
)

SELECT
    month,
    jobs,
    revenue,
    previous_revenue,
    ROUND(100.0 * (revenue - previous_revenue) / NULLIF(previous_revenue, 0), 1) AS mom_change_pct,
    SUM(revenue) OVER (
        PARTITION BY EXTRACT(YEAR FROM month)  -- restart the total each January
        ORDER BY month
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS year_to_date_revenue,
    SUM(revenue) OVER (
        ORDER BY month
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total_revenue
FROM with_previous
ORDER BY month;
