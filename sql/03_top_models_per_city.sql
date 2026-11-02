-- 03. Top three device models in each city
--
-- Question: In each service area, which device models do we repair most
-- often? That decides which parts ride along in the van on a route day.
--
-- Techniques: GROUP BY, RANK() OVER (PARTITION BY ...) to rank models within
-- each city, a window SUM for the city's total, and filtering on the rank in
-- the outer query (WHERE runs before window functions, so it can't filter on
-- them in the same SELECT).
--
-- Notes: RANK() gives tied models the same rank, so a city can list more than
-- three models when there's a tie for third place. ROW_NUMBER() would always
-- keep exactly three and break the tie arbitrarily.

WITH jobs_by_city_and_model AS (
    SELECT
        c.city_name,
        m.model_name,
        COUNT(*) AS jobs
    FROM bookings AS b
    JOIN cities AS c        ON c.city_id = b.city_id
    JOIN device_models AS m ON m.model_id = b.model_id
    WHERE b.status = 'completed'
    GROUP BY c.city_name, m.model_name
),

ranked AS (
    SELECT
        city_name,
        model_name,
        jobs,
        SUM(jobs) OVER (PARTITION BY city_name)                    AS city_jobs,
        RANK()    OVER (PARTITION BY city_name ORDER BY jobs DESC) AS rank_in_city
    FROM jobs_by_city_and_model
)

SELECT
    city_name,
    rank_in_city,
    model_name,
    jobs,
    ROUND(100.0 * jobs / city_jobs, 1) AS share_of_city_jobs_pct
FROM ranked
WHERE rank_in_city <= 3
ORDER BY city_jobs DESC, city_name, rank_in_city, model_name;
