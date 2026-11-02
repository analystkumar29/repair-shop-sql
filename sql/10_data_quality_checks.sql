-- 10. Data-quality checks
--
-- Question: Can the numbers in the other nine queries be trusted? Each row is
-- one check, and issues_found should be 0.
--
-- Techniques: UNION ALL to stack independent checks into one result, NOT
-- EXISTS anti-joins to find rows with no match, and COUNT(*) minus COUNT(
-- DISTINCT ...) to count duplicates.
--
-- Notes: The data generator plants two realistic problems on purpose, so this
-- query has something to find: returning customers who registered again with
-- the same email in different letter case, and cash jobs that were never
-- entered as payments. Comparisons with NULL are never true, so check 4 skips
-- missing timestamps; check 5 is the one that catches those.

WITH checks AS (
    SELECT
        1                                        AS check_id,
        'Completed job with no payment recorded' AS check_name,
        COUNT(*)                                 AS issues_found
    FROM bookings AS b
    WHERE b.status = 'completed'
      AND NOT EXISTS (SELECT 1 FROM payments AS p WHERE p.booking_id = b.booking_id)

    UNION ALL

    SELECT 2, 'Payments that do not add up to the final price', COUNT(*)
    FROM (
        SELECT b.booking_id
        FROM bookings AS b
        JOIN payments AS p ON p.booking_id = b.booking_id
        GROUP BY b.booking_id, b.final_price
        HAVING SUM(p.amount) <> b.final_price
    ) AS mismatched

    UNION ALL

    SELECT 3, 'Duplicate customer records (same email, ignoring case)',
           COUNT(*) - COUNT(DISTINCT LOWER(TRIM(email)))
    FROM customers

    UNION ALL

    SELECT 4, 'Booking milestones out of order', COUNT(*)
    FROM bookings
    WHERE confirmed_at  < created_at
       OR scheduled_for < created_at
       OR confirmed_at  > scheduled_for
       OR completed_at  < scheduled_for
       OR cancelled_at  < created_at

    UNION ALL

    SELECT 5, 'Status does not match the milestone timestamps', COUNT(*)
    FROM bookings
    WHERE NOT (
           (status = 'requested' AND confirmed_at IS NULL AND technician_id IS NULL
                                 AND completed_at IS NULL AND cancelled_at IS NULL)
        OR (status = 'confirmed' AND confirmed_at IS NOT NULL AND technician_id IS NOT NULL
                                 AND completed_at IS NULL AND cancelled_at IS NULL)
        OR (status = 'completed' AND completed_at IS NOT NULL AND technician_id IS NOT NULL
                                 AND final_price IS NOT NULL AND cancelled_at IS NULL)
        OR (status = 'cancelled' AND cancelled_at IS NOT NULL AND completed_at IS NULL)
    )

    UNION ALL

    SELECT 6, 'Service booked for the wrong kind of device', COUNT(*)
    FROM bookings AS b
    JOIN services AS s      ON s.service_id = b.service_id
    JOIN device_models AS m ON m.model_id = b.model_id
    WHERE s.device_type <> m.device_type

    UNION ALL

    SELECT 7, 'Completed job on a day the technician did not work', COUNT(*)
    FROM bookings AS b
    WHERE b.status = 'completed'
      AND NOT EXISTS (
          SELECT 1
          FROM technician_shifts AS sh
          WHERE sh.technician_id = b.technician_id
            AND sh.shift_date = CAST(b.completed_at AS DATE)
      )

    UNION ALL

    SELECT 8, 'Payment, review or claim on a job not completed (or dated before it)', COUNT(*)
    FROM (
        SELECT booking_id, paid_at AS happened_at FROM payments
        UNION ALL
        SELECT booking_id, reviewed_at FROM reviews
        UNION ALL
        SELECT booking_id, claimed_at FROM warranty_claims
    ) AS follow_ups
    JOIN bookings AS b ON b.booking_id = follow_ups.booking_id
    WHERE b.status <> 'completed'
       OR follow_ups.happened_at < b.completed_at
)

SELECT
    check_id,
    check_name,
    issues_found,
    CASE WHEN issues_found = 0 THEN 'pass' ELSE 'investigate' END AS result
FROM checks
ORDER BY check_id;
