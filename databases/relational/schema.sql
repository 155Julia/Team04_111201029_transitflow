-- ============================================================
--  TransitFlow PostgreSQL Schema
--  Seed data is loaded separately by: python skeleton/seed_postgres.py
-- # TASK 6 EXTENSION: This schema includes the loyalty_points ledger.
--
--  DELETE STRATEGY (applied consistently throughout):
--    Hard delete is used for all tables EXCEPT registered_users.
--    registered_users uses SOFT DELETE via the is_active flag —
--    user records are never physically removed so booking history
--    and audit trails remain intact after account deactivation.
--
--  PK DESIGN:
--    Human-readable VARCHAR IDs (e.g. "NR01", "BK001") are used
--    throughout because the mock data already defines them and they
--    appear in the UI. A UUID or SERIAL would add no benefit here
--    and would make debugging harder during development.
-- ============================================================

-- ============================================================
--  STUDENT TASK — Relational tables
-- ============================================================

-- 1. National rail station master data
CREATE TABLE IF NOT EXISTS national_rail_stations (
    -- VARCHAR chosen to match source IDs like "NR01"
    station_id VARCHAR(10)  PRIMARY KEY,
    name       VARCHAR(100) NOT NULL,
    lines      TEXT[]       NOT NULL
);

-- 2. Metro station master data
--    adjacent_stations stores neighbour IDs for reference;
--    the live route graph lives in Neo4j (METRO_LINK edges).
CREATE TABLE IF NOT EXISTS metro_stations (
    -- VARCHAR chosen to match source IDs like "MS01"
    station_id                           VARCHAR(10)  PRIMARY KEY,
    name                                 VARCHAR(100) NOT NULL,
    lines                                TEXT[]       NOT NULL,
    is_interchange_metro                 BOOLEAN      NOT NULL DEFAULT FALSE,
    is_interchange_national_rail         BOOLEAN      NOT NULL DEFAULT FALSE,
    -- NULL when the station has no national-rail interchange
    interchange_national_rail_station_id VARCHAR(10)
        REFERENCES national_rail_stations(station_id) ON DELETE SET NULL ON UPDATE CASCADE,
    adjacent_stations                    TEXT[]       -- neighbour station IDs (informational)
);

-- 3. Metro schedule — one row per line/direction
CREATE TABLE IF NOT EXISTS metro_schedules (
    schedule_id                  VARCHAR(20)    PRIMARY KEY,
    line                         VARCHAR(10)    NOT NULL,
    direction                    VARCHAR(50)    NOT NULL,
    origin_station_id            VARCHAR(10)    NOT NULL
        REFERENCES metro_stations(station_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    destination_station_id       VARCHAR(10)    NOT NULL
        REFERENCES metro_stations(station_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    first_train_time             TIME           NOT NULL,
    last_train_time              TIME           NOT NULL,
    base_fare_usd                NUMERIC(5,2)   NOT NULL DEFAULT 0.80,
    per_stop_rate_usd            NUMERIC(5,2)   NOT NULL DEFAULT 0.30,
    frequency_min                INT            NOT NULL,
    operates_on                  TEXT[]         NOT NULL
);

-- 4. National rail schedule — normal and express services
CREATE TABLE IF NOT EXISTS national_rail_schedules (
    schedule_id                  VARCHAR(20)    PRIMARY KEY,
    line                         VARCHAR(10)    NOT NULL,
    -- 'normal' or 'express'; express has higher fares and fewer stops
    service_type                 VARCHAR(20)    NOT NULL CHECK (service_type IN ('normal','express')),
    direction                    VARCHAR(50)    NOT NULL,
    origin_station_id            VARCHAR(10)    NOT NULL
        REFERENCES national_rail_stations(station_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    destination_station_id       VARCHAR(10)    NOT NULL
        REFERENCES national_rail_stations(station_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    frequency_min                INT            NOT NULL,
    first_train_time             TIME           NOT NULL,
    last_train_time              TIME           NOT NULL,
    operates_on                  TEXT[]         NOT NULL,
    -- Express trains pass through stations without stopping
    passed_through_stations      TEXT[],
    -- Fare rates stored per class to avoid a separate fare table
    standard_base_fare           NUMERIC(5,2)   NOT NULL DEFAULT 2.50,
    standard_per_stop_rate       NUMERIC(5,2)   NOT NULL DEFAULT 1.50,
    first_base_fare              NUMERIC(5,2)   NOT NULL DEFAULT 4.00,
    first_per_stop_rate          NUMERIC(5,2)   NOT NULL DEFAULT 2.50,
    is_express_premium           BOOLEAN        NOT NULL DEFAULT FALSE
);

-- 5. Metro schedule stops — one row per scheduled stop.
--    This junction table keeps stop sequence in 1NF/3NF instead of
--    storing ordered station IDs in an array column.
CREATE TABLE IF NOT EXISTS metro_schedule_stops (
    schedule_id                 VARCHAR(20) NOT NULL
        REFERENCES metro_schedules(schedule_id) ON DELETE CASCADE ON UPDATE CASCADE,
    station_id                  VARCHAR(10) NOT NULL
        REFERENCES metro_stations(station_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    stop_order                  INT         NOT NULL CHECK (stop_order > 0),
    travel_time_from_origin_min INT         NOT NULL CHECK (travel_time_from_origin_min >= 0),
    PRIMARY KEY (schedule_id, stop_order),
    UNIQUE (schedule_id, station_id)
);

CREATE INDEX IF NOT EXISTS idx_metro_schedule_stops_station
    ON metro_schedule_stops(station_id, schedule_id, stop_order);

-- 6. National rail schedule stops — one row per scheduled stop.
--    Normalising stop order makes origin/destination order checks relational
--    and avoids array-position logic in the schema.
CREATE TABLE IF NOT EXISTS national_rail_schedule_stops (
    schedule_id                 VARCHAR(20) NOT NULL
        REFERENCES national_rail_schedules(schedule_id) ON DELETE CASCADE ON UPDATE CASCADE,
    station_id                  VARCHAR(10) NOT NULL
        REFERENCES national_rail_stations(station_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    stop_order                  INT         NOT NULL CHECK (stop_order > 0),
    travel_time_from_origin_min INT         NOT NULL CHECK (travel_time_from_origin_min >= 0),
    PRIMARY KEY (schedule_id, stop_order),
    UNIQUE (schedule_id, station_id)
);

CREATE INDEX IF NOT EXISTS idx_nr_schedule_stops_station
    ON national_rail_schedule_stops(station_id, schedule_id, stop_order);

-- 7. Seat layout — one row per physical seat per schedule
--    Only normal services (SL01-SL04) have assigned seating.
CREATE TABLE IF NOT EXISTS national_rail_seat_layouts (
    layout_id   VARCHAR(10)  NOT NULL,
    schedule_id VARCHAR(20)  NOT NULL
        REFERENCES national_rail_schedules(schedule_id) ON DELETE CASCADE ON UPDATE CASCADE,
    coach       VARCHAR(5)   NOT NULL CHECK (coach IN ('A','B')),
    fare_class  VARCHAR(20)  NOT NULL CHECK (fare_class IN ('standard','first')),
    seat_id     VARCHAR(5)   NOT NULL,
    "row"       INT          NOT NULL,
    "column"    VARCHAR(2)   NOT NULL,
    PRIMARY KEY (schedule_id, coach, seat_id)
);

-- 8. Registered users
--    SOFT DELETE: is_active = FALSE deactivates the account without
--    removing the row, preserving booking history and audit trails.
--    Password is stored as a bcrypt hash (never plain text).
CREATE TABLE IF NOT EXISTS registered_users (
    -- VARCHAR(20) to match source IDs like "RU01"; new users get RU<nn>
    user_id         VARCHAR(20)  PRIMARY KEY,
    full_name       VARCHAR(100) NOT NULL,
    first_name      VARCHAR(50),
    surname         VARCHAR(50),
    email           VARCHAR(150) NOT NULL UNIQUE,
    -- bcrypt hash (60 chars); plain text is never stored
    password        VARCHAR(255) NOT NULL,
    phone           VARCHAR(30),
    date_of_birth   DATE,
    secret_question VARCHAR(255),
    secret_answer   VARCHAR(255),
    registered_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    -- Soft-delete flag: FALSE = deactivated, TRUE = active
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE
);

-- 9. National rail bookings
CREATE TABLE IF NOT EXISTS national_rail_bookings (
    -- BK-XXXXXX format generated at runtime; VARCHAR(20) gives headroom
    booking_id              VARCHAR(20)  PRIMARY KEY,
    user_id                 VARCHAR(20)  NOT NULL
        REFERENCES registered_users(user_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    schedule_id             VARCHAR(20)  NOT NULL
        REFERENCES national_rail_schedules(schedule_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    origin_station_id       VARCHAR(10)  NOT NULL
        REFERENCES national_rail_stations(station_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    destination_station_id  VARCHAR(10)  NOT NULL
        REFERENCES national_rail_stations(station_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    travel_date             DATE         NOT NULL,
    departure_time          TIME         NOT NULL,
    ticket_type             VARCHAR(20)  NOT NULL CHECK (ticket_type IN ('single','return')),
    fare_class              VARCHAR(20)  NOT NULL CHECK (fare_class IN ('standard','first')),
    coach                   VARCHAR(5),
    seat_id                 VARCHAR(5),
    stops_travelled         INT          NOT NULL,
    amount_usd              NUMERIC(6,2) NOT NULL,
    status                  VARCHAR(20)  NOT NULL CHECK (status IN ('completed','confirmed','cancelled')),
    booked_at               TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    travelled_at            TIMESTAMPTZ
);

-- 10. Metro travel history (single tickets and day passes)
CREATE TABLE IF NOT EXISTS metro_travel_history (
    trip_id                 VARCHAR(20)  PRIMARY KEY,
    user_id                 VARCHAR(20)  NOT NULL
        REFERENCES registered_users(user_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    schedule_id             VARCHAR(20)  NOT NULL
        REFERENCES metro_schedules(schedule_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    origin_station_id       VARCHAR(10)  NOT NULL
        REFERENCES metro_stations(station_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    destination_station_id  VARCHAR(10)  NOT NULL
        REFERENCES metro_stations(station_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    travel_date             DATE         NOT NULL,
    ticket_type             VARCHAR(20)  NOT NULL CHECK (ticket_type IN ('single','day_pass')),
    -- For day-pass child trips, points back to the original purchase row
    day_pass_ref            VARCHAR(20)
        REFERENCES metro_travel_history(trip_id) ON DELETE SET NULL ON UPDATE CASCADE,
    stops_travelled         INT,
    amount_usd              NUMERIC(5,2) NOT NULL DEFAULT 0.00,
    status                  VARCHAR(20)  NOT NULL CHECK (status IN ('completed','in_progress','cancelled')),
    purchased_at            TIMESTAMPTZ,
    travelled_at            TIMESTAMPTZ
);

-- 11. Payments
--    Exactly one journey reference must be present.  Splitting the
--    references keeps both paths protected by real foreign keys.
CREATE TABLE IF NOT EXISTS payments (
    payment_id               VARCHAR(20)  PRIMARY KEY,
    national_rail_booking_id VARCHAR(20)
        REFERENCES national_rail_bookings(booking_id) ON DELETE CASCADE ON UPDATE CASCADE,
    metro_trip_id            VARCHAR(20)
        REFERENCES metro_travel_history(trip_id) ON DELETE CASCADE ON UPDATE CASCADE,
    amount_usd               NUMERIC(6,2) NOT NULL,
    method                   VARCHAR(20)  NOT NULL CHECK (method IN ('credit_card','debit_card','ewallet')),
    status                   VARCHAR(20)  NOT NULL CHECK (status IN ('paid','refunded')),
    paid_at                  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CHECK (num_nonnulls(national_rail_booking_id, metro_trip_id) = 1)
);

-- 12. Feedback
--     Same explicit-reference pattern as payments.
CREATE TABLE IF NOT EXISTS feedback (
    feedback_id              VARCHAR(20)  PRIMARY KEY,
    national_rail_booking_id VARCHAR(20)
        REFERENCES national_rail_bookings(booking_id) ON DELETE CASCADE ON UPDATE CASCADE,
    metro_trip_id            VARCHAR(20)
        REFERENCES metro_travel_history(trip_id) ON DELETE CASCADE ON UPDATE CASCADE,
    user_id                  VARCHAR(20)
        REFERENCES registered_users(user_id) ON DELETE SET NULL ON UPDATE CASCADE,
    rating                   INT          NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment                  TEXT,
    submitted_at             TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CHECK (num_nonnulls(national_rail_booking_id, metro_trip_id) = 1)
);

-- ── Indexes ──────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_users_email
    ON registered_users(lower(email));

CREATE INDEX IF NOT EXISTS idx_bookings_user_date
    ON national_rail_bookings(user_id, travel_date DESC);

CREATE INDEX IF NOT EXISTS idx_bookings_schedule_date
    ON national_rail_bookings(schedule_id, travel_date)
    WHERE status <> 'cancelled';

-- Prevents two active bookings from claiming the same physical seat
-- on the same service date, even under concurrent booking attempts.
CREATE UNIQUE INDEX IF NOT EXISTS idx_nr_active_seat_booking_unique
    ON national_rail_bookings(schedule_id, travel_date, coach, seat_id)
    WHERE status <> 'cancelled' AND seat_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_metro_travel_user_date
    ON metro_travel_history(user_id, travel_date DESC);

CREATE INDEX IF NOT EXISTS idx_payments_nr_booking_id
    ON payments(national_rail_booking_id);

CREATE INDEX IF NOT EXISTS idx_payments_metro_trip_id
    ON payments(metro_trip_id);

CREATE INDEX IF NOT EXISTS idx_feedback_nr_booking_id
    ON feedback(national_rail_booking_id);

CREATE INDEX IF NOT EXISTS idx_feedback_metro_trip_id
    ON feedback(metro_trip_id);

-- ============================================================
--  TASK 6 EXTENSION: Loyalty Points System
--
--  Motivation: reward passengers for completed journeys and
--  encourage repeat national_rail_bookings.  Every $1 spent on a confirmed
--  national-rail booking earns 10 points.  Points can be
--  queried per user and are recorded per booking so the history
--  is fully auditable.
--
--  Design decisions:
--    * Separate table (not a column on national_rail_bookings) so the points
--      ledger can grow independently and supports future
--      redemption rows with negative amounts.
--    * source_booking_id is NOT NULL — every row must trace back
--      to a real booking for auditability.
--    * NUMERIC(10,2) for points_earned allows fractional points
--      if the earn rate changes in future.
--    * Index on user_id covers the most common query pattern
--      (balance lookup and history for a single user).
-- ============================================================

-- 11. Loyalty points ledger
--     One row per booking that earns points.
--     Earn rate: 10 points per USD spent on completed national_rail_bookings.
CREATE TABLE IF NOT EXISTS loyalty_points (
    -- SERIAL PK: no natural key exists for a ledger entry
    id                  SERIAL        PRIMARY KEY,
    -- The user who earned the points
    user_id             VARCHAR(20)   NOT NULL
        REFERENCES registered_users(user_id) ON DELETE CASCADE ON UPDATE CASCADE,
    -- The booking that triggered the earn event
    source_booking_id   VARCHAR(20)   NOT NULL
        REFERENCES national_rail_bookings(booking_id) ON DELETE CASCADE ON UPDATE CASCADE,
    -- Points earned for this booking (amount_usd * 10, rounded to 2dp)
    points_earned       NUMERIC(10,2) NOT NULL CHECK (points_earned >= 0),
    -- Human-readable reason stored for display and debugging
    description         TEXT          NOT NULL DEFAULT 'Journey completed',
    -- When the points were credited
    earned_at           TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

-- Index: balance and history queries always filter by user_id
CREATE INDEX IF NOT EXISTS idx_loyalty_user_id
    ON loyalty_points(user_id);

-- Unique constraint: one earn row per booking prevents double-crediting
CREATE UNIQUE INDEX IF NOT EXISTS idx_loyalty_booking_unique
    ON loyalty_points(source_booking_id);

-- ============================================================
--  VECTOR SCHEMA  (RAG / Help Desk) — do not modify
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS policy_documents (
    id          SERIAL       PRIMARY KEY,
    title       VARCHAR(200) NOT NULL,
    category    VARCHAR(50)  NOT NULL,
    content     TEXT         NOT NULL,
    embedding   vector(768),
    source_file VARCHAR(200),
    created_at  TIMESTAMPTZ  DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_policy_embedding
    ON policy_documents USING hnsw (embedding vector_cosine_ops);
