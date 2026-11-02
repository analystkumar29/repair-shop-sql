-- 09. Average rating by technician (at least 30 reviews)
--
-- Question: Which technicians get the best reviews? A technician only makes
-- the table with 30 or more reviews, so a handful of five-star reviews can't
-- put someone at the top.
--
-- Techniques: joins across three tables, GROUP BY with HAVING to filter whole
-- groups, and RANK() over an aggregate.
--
-- Notes: WHERE filters rows before grouping; HAVING filters the groups after
-- it. Window functions run after HAVING, so the rank only compares the
-- technicians who qualify.

SELECT
    RANK() OVER (ORDER BY ROUND(AVG(r.rating), 2) DESC)                    AS rating_rank,
    t.technician_name,
    COUNT(*)                                                               AS reviews,
    ROUND(AVG(r.rating), 2)                                                AS avg_rating,
    ROUND(100.0 * COUNT(CASE WHEN r.rating = 5 THEN 1 END) / COUNT(*), 1)  AS five_star_pct,
    ROUND(100.0 * COUNT(CASE WHEN r.rating <= 2 THEN 1 END) / COUNT(*), 1) AS one_or_two_star_pct
FROM reviews AS r
JOIN bookings AS b    ON b.booking_id = r.booking_id
JOIN technicians AS t ON t.technician_id = b.technician_id
GROUP BY t.technician_id, t.technician_name
HAVING COUNT(*) >= 30
ORDER BY rating_rank, t.technician_name;
