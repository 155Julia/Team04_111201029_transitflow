# TASK 6 EXTENSION — Loyalty Points System

## Overview

This extension adds a passenger loyalty-points system to TransitFlow.
Every completed national-rail booking earns 10 points per USD spent.
Users can query their balance and full earn history.

---

## Files Modified or Added

### `databases/relational/schema.sql`
- **New table:** `loyalty_points`
  - Columns: `id` (SERIAL PK), `user_id` (FK → registered_users), `source_booking_id` (FK → national_rail_bookings), `points_earned` (NUMERIC), `description` (TEXT), `earned_at` (TIMESTAMPTZ)
  - Indexes: `idx_loyalty_user_id` (balance/history lookup), `idx_loyalty_booking_unique` (prevents double-crediting)
  - Marker: `# TASK 6 EXTENSION` appears near the top of the file and beside the loyalty schema block.

### `databases/relational/queries.py`
- **New function:** `query_loyalty_balance(user_id)` — returns total points and transaction count
- **New function:** `query_loyalty_history(user_id)` — returns full earn history with booking context
- **New function:** `execute_earn_loyalty_points(booking_id)` — atomic INSERT into loyalty_points; earn rate 10 pts/USD
  - Marker: `# TASK 6 EXTENSION` appears near the top of the module and before the loyalty query section.

### `skeleton/seed_postgres.py`
- **New function:** `seed_loyalty_points(cur)` — seeds points for all completed national_rail_bookings in mock data
  - Marker: `# TASK 6 EXTENSION` appears near the top of the file and on the seeding call.

---

## Earn Rate

| Ticket type | Earn rate |
|---|---|
| National rail (any fare class) | 10 points per USD |
| Metro | Not eligible (metro trips are not tracked in national_rail_bookings table) |

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
JOIN national_rail_bookings b ON b.booking_id = lp.source_booking_id
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

Use the queries above in pgAdmin after running `skeleton/seed_postgres.py`.
The expected checks are:

- `SELECT COUNT(*) FROM loyalty_points;` returns a positive count after seeding.
- Re-running `skeleton/seed_postgres.py` leaves the count unchanged because `source_booking_id` is unique and inserts use `ON CONFLICT DO NOTHING`.
- `query_loyalty_balance('RU01')` returns one row with `user_id`, `total_points`, and `transaction_count`.
- `execute_earn_loyalty_points(<confirmed booking id>)` inserts exactly one ledger row and returns `(True, result_dict)`.
- Calling `execute_earn_loyalty_points()` again for the same booking returns `(False, message)` and does not duplicate points.

---

## Design Document Section 7

The official Section 7 write-up is included in `DESIGN_DOCUMENT.md` under:

```text
Section 7 — Optional Extension: Loyalty Points System
```

It covers the required motivation, schema changes, SQL examples, expected output, and testing evidence.
