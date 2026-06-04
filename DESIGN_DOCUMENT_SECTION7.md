## Section 7 — Optional Extension: Loyalty Points System

### 7.1 Motivation

TransitFlow’s optional extension is a loyalty points system for National Rail bookings. The purpose of this feature is to model a realistic customer retention mechanism on top of the booking and payment workflow. When a registered user completes an eligible National Rail booking, the system records earned points that can later be queried as part of the user’s travel profile.

This extension is useful for the project because it adds a business-facing feature that depends on the existing relational database design instead of existing as an isolated table. The loyalty records are connected to registered users and National Rail bookings, so the feature demonstrates referential integrity, transactional booking data, and analytical queries over user activity.

The design focuses on three goals:

- Keep loyalty data normalized and traceable to the original booking.
- Prevent duplicate loyalty awards for the same booking.
- Support simple reporting queries for user balance and loyalty history.

### 7.2 Database Changes

The extension adds a new relational table named `loyalty_points`. Each row represents one loyalty points transaction for a registered user. The row is linked to both the user and the National Rail booking that generated the points.

```sql
CREATE TABLE loyalty_points (
    loyalty_id SERIAL PRIMARY KEY,
    user_id VARCHAR(10) NOT NULL REFERENCES registered_users(user_id) ON DELETE CASCADE,
    national_rail_booking_id VARCHAR(20) NOT NULL REFERENCES national_rail_bookings(booking_id) ON DELETE CASCADE,
    points_earned DECIMAL(10, 2) NOT NULL CHECK (points_earned >= 0),
    transaction_type VARCHAR(20) NOT NULL DEFAULT 'EARNED',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_loyalty_booking UNIQUE (national_rail_booking_id)
);
```

The main integrity rules are:

- `user_id` must reference an existing registered user.
- `national_rail_booking_id` must reference an existing National Rail booking.
- `points_earned` cannot be negative.
- `unique_loyalty_booking` prevents the same booking from earning points more than once.

Seed data is inserted after National Rail bookings have been created. This preserves the foreign key dependency order and makes the initialization process repeatable.

### 7.3 Example Queries

The project implements two loyalty-related PostgreSQL query functions in `databases/relational/queries.py`.

The first query returns a user’s total loyalty balance:

```python
query_loyalty_balance("RU01")
```

Expected result shape:

```text
{
    "user_id": "RU01",
    "total_points": 85.00,
    "transaction_count": 1
}
```

This query is useful for a customer profile page or an account dashboard because it summarizes all loyalty transactions for one user.

The second query returns the user’s loyalty transaction history:

```python
query_loyalty_history("RU01")
```

Expected result shape:

```text
[
    {
        "loyalty_id": 1,
        "booking_id": "NRB001",
        "points_earned": 85.00,
        "transaction_type": "EARNED",
        "created_at": "...",
        "origin_station": "London Euston",
        "destination_station": "Manchester Piccadilly",
        "total_amount": 85.00
    }
]
```

This query joins loyalty records with National Rail bookings and schedules, so the output explains where the points came from instead of only showing a number.

### 7.4 Testing Evidence

The extension was tested during the live database initialization workflow.

PostgreSQL seeding successfully inserted loyalty records:

```text
loyalty_points: 14 rows
```

The loyalty balance query was tested with user `RU01`:

```text
query_loyalty_balance("RU01")
=> total_points: 85.00
=> transaction_count: 1
```

The loyalty history query was tested with user `RU01` and returned a booking-linked loyalty transaction, including the booking id, points earned, route information, and booking amount.

The following files support the feature:

- `databases/relational/schema.sql`: defines the `loyalty_points` table and constraints.
- `skeleton/seed_postgres.py`: inserts loyalty seed data after users and bookings.
- `databases/relational/queries.py`: implements loyalty balance and history queries.
- `TASK6.md`: summarizes the optional extension implementation.

This satisfies the Task 6 bonus requirement by adding an extra database-backed feature, documenting the motivation and schema changes, providing example queries, and verifying the feature with seeded live data.
