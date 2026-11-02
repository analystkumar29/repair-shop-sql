-- 05. Repeat customers and monthly cohort retention
--
-- Question: What share of customers come back for another repair, and how
-- soon? Customers are grouped into cohorts by the month of their first
-- completed repair.
--
-- Techniques: chained CTEs, MIN() to find each customer's first and second
-- repair, a LEFT JOIN that keeps customers who never returned, conditional
-- counts, and a CASE that returns NULL when a cohort is too young to measure.
--
-- Notes: returned_so_far_pct is the plain repeat rate, so older cohorts score
-- higher simply because they've had longer. The fixed windows fix that: a
-- cohort's "within 90 days" figure only appears once every customer in it has
-- had 90 days to come back, and stays NULL until then rather than showing a
-- misleadingly low number. Duplicate customer records (query 10) make all of
-- these rates slightly understated.

WITH completed_jobs AS (
    SELECT
        customer_id,
        CAST(completed_at AS DATE) AS job_date
    FROM bookings
    WHERE status = 'completed'
),

first_job AS (
    SELECT customer_id, MIN(job_date) AS first_date
    FROM completed_jobs
    GROUP BY customer_id
),

second_job AS (
    SELECT f.customer_id, MIN(j.job_date) AS second_date
    FROM first_job AS f
    JOIN completed_jobs AS j
      ON j.customer_id = f.customer_id
     AND j.job_date > f.first_date
    GROUP BY f.customer_id
),

data_end AS (
    SELECT MAX(job_date) AS last_date
    FROM completed_jobs
),

customer_history AS (
    SELECT
        CAST(date_trunc('month', f.first_date) AS DATE) AS cohort_month,
        s.second_date - f.first_date                    AS days_to_return,  -- NULL if never returned
        d.last_date - f.first_date                      AS days_observed
    FROM first_job AS f
    LEFT JOIN second_job AS s ON s.customer_id = f.customer_id
    CROSS JOIN data_end AS d
)

SELECT
    cohort_month,
    COUNT(*)                                           AS new_customers,
    ROUND(100.0 * COUNT(days_to_return) / COUNT(*), 1) AS returned_so_far_pct,
    CASE WHEN MIN(days_observed) >= 90 THEN
        ROUND(100.0 * COUNT(CASE WHEN days_to_return <= 90 THEN 1 END) / COUNT(*), 1)
    END                                                AS back_within_90_days_pct,
    CASE WHEN MIN(days_observed) >= 180 THEN
        ROUND(100.0 * COUNT(CASE WHEN days_to_return <= 180 THEN 1 END) / COUNT(*), 1)
    END                                                AS back_within_180_days_pct,
    CASE WHEN MIN(days_observed) >= 365 THEN
        ROUND(100.0 * COUNT(CASE WHEN days_to_return <= 365 THEN 1 END) / COUNT(*), 1)
    END                                                AS back_within_365_days_pct
FROM customer_history
GROUP BY cohort_month
ORDER BY cohort_month;
