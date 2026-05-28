# TASK 6 EXTENSION — Loyalty Points System

## Overview

This extension adds a passenger loyalty-points system to TransitFlow.
Every completed national-rail booking earns 10 points per USD spent.
Users can query their balance and full earn history.

---

## Files Modified or Added

### `databases/relational/schema.sql`
- **New table:** `loyalty_points`
  - Columns: `id` (SERIAL PK), `user_id` (FK → registered_users), `source_booking_id` (FK → bookings), `points_earned` (NUMERIC), `description` (TEXT), `earned_at` (TIMESTAMPTZ)
  - Indexes: `idx_loyalty_user_id` (balance/history lookup), `idx_loyalty_booking_unique` (prevents double-crediting)

### `databases/relational/queries.py`
- **New function:** `query_loyalty_balance(user_id)` — returns total points and transaction count
- **New function:** `query_loyalty_history(user_id)` — returns full earn history with booking context
- **New function:** `execute_earn_loyalty_points(booking_id)` — atomic INSERT into loyalty_points; earn rate 10 pts/USD

### `skeleton/seed_postgres.py`
- **New function:** `seed_loyalty_points(cur)` — seeds points for all completed bookings in mock data

---

## Earn Rate

| Ticket type | Earn rate |
|---|---|
| National rail (any fare class) | 10 points per USD |
| Metro | Not eligible (metro trips are not tracked in bookings table) |

---

## Example Queries (run in pgAdmin after seeding)

```sql
-- 1. Check balance for user RU01
SELECT user_id, SUM(points_earned) AS total_points
FROM loyalty_points
WHERE user_id = 'RU01'
GROUP BY user_id;

-- 2. Full earn history for RU01 with route details
SELECT lp.points_earned, lp.earned_at,
       b.travel_date, b.amount_usd,
       orig.name AS from_station, dest.name AS to_station
FROM loyalty_points lp
JOIN bookings b ON b.booking_id = lp.source_booking_id
JOIN national_rail_stations orig ON orig.station_id = b.origin_station_id
JOIN national_rail_stations dest ON dest.station_id = b.destination_station_id
WHERE lp.user_id = 'RU01'
ORDER BY lp.earned_at DESC;

-- 3. Top 5 users by points balance
SELECT user_id, SUM(points_earned) AS total_points
FROM loyalty_points
GROUP BY user_id
ORDER BY total_points DESC
LIMIT 5;

-- 4. Verify idempotency — re-running seed should not add duplicates
SELECT COUNT(*) FROM loyalty_points;  -- should stay the same after re-seed
```

---

## Testing Evidence

See Section 7 of the design document for screenshots of the above queries
executed in pgAdmin, showing correct point totals and history records.
