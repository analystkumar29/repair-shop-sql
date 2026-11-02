-- 06. Technician utilisation and jobs per working day
--
-- Question: How many jobs does each technician complete on a day they work,
-- how often do they have a day with no job at all, and what share of their
-- shift hours goes on hands-on repair work?
--
-- Techniques: a LEFT JOIN from the shifts table so days without a job still
-- count, join conditions kept in ON (not WHERE) so the LEFT JOIN isn't undone,
-- and aggregating in two steps: per shift, then per technician.
--
-- Notes: Hands-on time uses each service's typical duration. Travel between
-- jobs isn't tracked, so utilisation here means repair time only.

WITH jobs_per_shift AS (
    -- One row per technician per day worked, with the jobs finished that day (0 if none).
    SELECT
        sh.technician_id,
        sh.shift_date,
        sh.shift_hours,
        COUNT(b.booking_id)                  AS jobs,
        COALESCE(SUM(s.duration_minutes), 0) AS repair_minutes
    FROM technician_shifts AS sh
    LEFT JOIN bookings AS b
           ON b.technician_id = sh.technician_id
          AND b.status = 'completed'  -- in WHERE, this would drop the days with no job
          AND CAST(b.completed_at AS DATE) = sh.shift_date
    LEFT JOIN services AS s
           ON s.service_id = b.service_id
    GROUP BY sh.technician_id, sh.shift_date, sh.shift_hours
)

SELECT
    t.technician_name,
    t.employment_type,
    MIN(j.shift_date)                                                     AS first_shift,
    MAX(j.shift_date)                                                     AS last_shift,
    COUNT(*)                                                              AS days_worked,
    SUM(j.jobs)                                                           AS jobs,
    ROUND(1.0 * SUM(j.jobs) / COUNT(*), 2)                                AS jobs_per_day,
    ROUND(100.0 * COUNT(CASE WHEN j.jobs = 0 THEN 1 END) / COUNT(*), 1)   AS days_without_a_job_pct,
    ROUND(100.0 * SUM(j.repair_minutes) / (60.0 * SUM(j.shift_hours)), 1) AS utilisation_pct
FROM jobs_per_shift AS j
JOIN technicians AS t ON t.technician_id = j.technician_id
GROUP BY t.technician_id, t.technician_name, t.employment_type
ORDER BY jobs_per_day DESC, t.technician_name;
