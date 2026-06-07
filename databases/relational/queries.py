"""
TransitFlow — PostgreSQL / Relational Database Layer
=====================================================
This module handles all queries to PostgreSQL.

TWO ROLES ARE SERVED HERE:
  1. Relational  → dual-network transit (metro + national rail),
                   availability, fares, national_rail_bookings, seat selection
  2. Vector      → policy document similarity search (pgvector)

STUDENT TASK
------------
Design your schema in databases/relational/schema.sql, seed it with
skeleton/seed_postgres.py, then implement the query functions below.

Functions prefixed with `query_`  are read-only lookups called by the agent.
Functions prefixed with `execute_` are write operations (booking/cancellation).

The vector functions (query_policy_vector_search, store_policy_document)
are already implemented — do not modify them.

TASK 6 EXTENSION: this file also implements loyalty-points ledger queries.
"""

from __future__ import annotations

import random
import string
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

import bcrypt
import psycopg2
import psycopg2.extras

from skeleton.config import PG_DSN, VECTOR_TOP_K, VECTOR_SIMILARITY_THRESHOLD


# TASK 6 EXTENSION: loyalty-points ledger queries live near the end of this file.


# ── Password helpers ──────────────────────────────────────────────────────────

def _hash_password(plain: str) -> tuple[str, str]:
    """
    # TASK 6 EXTENSION: Bcrypt Integration with Table Decoupling
    Used during registration: Hashes a plain-text password using bcrypt 
    and separates the generated salt from the final hash string.
    
    Returns:
        tuple[str, str]: (salt_str, hash_str) mapped to the user_credentials table.
    """
    password_bytes = plain.encode('utf-8')
    
    # 1. Generate a random bcrypt salt (12 rounds of key stretching for high brute-force resistance)
    salt_bytes = bcrypt.gensalt(rounds=12)
    salt_str = salt_bytes.decode('utf-8')
    
    # 2. Compute the final cryptographic hash
    hash_bytes = bcrypt.hashpw(password_bytes, salt_bytes)
    hash_str = hash_bytes.decode('utf-8')
    
    return salt_str, hash_str


def _check_password(plain: str, stored_salt: str, stored_hash: str) -> bool:
    """
    Used during login verification: Compares the user-input plain password 
    against the stored salt and hash retrieved from the user_credentials table.
    
    Returns:
        bool: True if the password matches the hash, False otherwise.
    """
    # 1. Encode the database-retrieved salt and hash back to bytes
    salt_bytes = stored_salt.encode('utf-8')
    hash_bytes = stored_hash.encode('utf-8')
    
    # 2. Re-hash the provided plain-text password using the original extracted salt
    current_hash_bytes = bcrypt.hashpw(plain.encode('utf-8'), salt_bytes)
    
    # 3. Perform a strict comparison between the computed hash and the stored hash
    return current_hash_bytes == hash_bytes


def _connect():
    """Return a new psycopg2 connection with autocommit enabled."""
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = True
    return conn


def _gen_booking_id() -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"BK-{suffix}"


def _gen_payment_id() -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"PM-{suffix}"


# ── Example ───────────────────────────────────────────────────────────────────
# The block below shows the query pattern: open a cursor, run SQL, return rows.
# Use _connect() for read-only queries; for write operations use a manual
# connection with conn.commit() / conn.rollback() (see execute_booking below).

def example_query() -> dict:
    """Example: returns the name of the connected database."""
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT current_database() AS db;")
            return dict(cur.fetchone())

def _money(value: Decimal | float | int) -> Decimal:
    """Round a numeric value to two decimal places for storage."""
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _time_text(value) -> str:
    """Return HH:MM for PostgreSQL time values or user-provided time strings."""
    if hasattr(value, "strftime"):
        return value.strftime("%H:%M")
    parsed = datetime.strptime(str(value).strip()[:5], "%H:%M")
    return parsed.strftime("%H:%M")


def _generated_departure_times(first_train_time, last_train_time, frequency_min: int) -> list[str]:
    """Expand a frequency-based schedule into selectable departure times."""
    first = datetime.strptime(_time_text(first_train_time), "%H:%M")
    last = datetime.strptime(_time_text(last_train_time), "%H:%M")
    times: list[str] = []
    current = first
    while current <= last:
        times.append(current.strftime("%H:%M"))
        current += timedelta(minutes=int(frequency_min))
    return times


def _new_user_id(cur) -> str:
    """Return the next RU-style user id."""
    cur.execute(
        """
        SELECT COALESCE(MAX(NULLIF(regexp_replace(user_id, '\\D', '', 'g'), '')::int), 0) + 1
            AS next_num
        FROM registered_users
        """
    )
    return f"RU{cur.fetchone()['next_num']:02d}"


# Query and transaction functions below follow the schema in schema.sql.
# ─────────────────────────────────────────────────────────────────────────────


# ── NATIONAL RAIL AVAILABILITY ────────────────────────────────────────────────

def query_national_rail_availability(
    origin_id: str,
    destination_id: str,
    travel_date: Optional[str] = None,
) -> list[dict]:
    """
    Return national rail schedules that serve both origin and destination stations
    in the correct order, along with seat occupancy for the requested travel date.

    Args:
        origin_id:       e.g. "NR01"
        destination_id:  e.g. "NR05"
        travel_date:     e.g. "2025-06-01" — used to count national_rail_bookings; omit for general info
    """
    sql = """
        WITH matching AS (
            SELECT
                s.*,
                os.stop_order AS origin_pos,
                ds.stop_order AS destination_pos,
                os.travel_time_from_origin_min AS origin_time_min,
                ds.travel_time_from_origin_min AS destination_time_min,
                array_agg(ss.station_id ORDER BY ss.stop_order) AS stops_in_order
            FROM national_rail_schedules s
            JOIN national_rail_schedule_stops os
              ON os.schedule_id = s.schedule_id
             AND os.station_id = %s
            JOIN national_rail_schedule_stops ds
              ON ds.schedule_id = s.schedule_id
             AND ds.station_id = %s
            JOIN national_rail_schedule_stops ss
              ON ss.schedule_id = s.schedule_id
            WHERE os.stop_order < ds.stop_order
              AND (%s::date IS NULL OR lower(to_char(%s::date, 'dy')) = ANY(s.operates_on))
            GROUP BY s.schedule_id, os.stop_order, ds.stop_order,
                     os.travel_time_from_origin_min, ds.travel_time_from_origin_min
        )
        SELECT
            m.schedule_id,
            m.line,
            m.service_type,
            m.direction,
            m.origin_station_id AS schedule_origin_station_id,
            m.destination_station_id AS schedule_destination_station_id,
            orig.name AS origin_name,
            dest.name AS destination_name,
            m.first_train_time::text,
            m.last_train_time::text,
            m.frequency_min,
            m.operates_on,
            m.stops_in_order,
            m.passed_through_stations,
            m.destination_pos - m.origin_pos AS stops_travelled,
            (m.destination_time_min - m.origin_time_min) AS travel_time_min,
            m.standard_base_fare,
            m.standard_per_stop_rate,
            m.first_base_fare,
            m.first_per_stop_rate,
            COALESCE(seats.total_seats, 0) AS total_seats,
            COALESCE(booked.booked_seats_by_departure, '{}'::jsonb) AS booked_seats_by_departure
        FROM matching m
        JOIN national_rail_stations orig ON orig.station_id = %s
        JOIN national_rail_stations dest ON dest.station_id = %s
        LEFT JOIN (
            SELECT schedule_id, COUNT(*) AS total_seats
            FROM national_rail_seat_layouts
            GROUP BY schedule_id
        ) seats ON seats.schedule_id = m.schedule_id
        LEFT JOIN (
            SELECT
                schedule_id,
                jsonb_object_agg(to_char(departure_time, 'HH24:MI'), booked_seats)
                    AS booked_seats_by_departure
            FROM (
                SELECT
                    schedule_id,
                    departure_time,
                    COUNT(DISTINCT coach || ':' || seat_id) AS booked_seats
                FROM national_rail_bookings
                WHERE %s::date IS NOT NULL
                  AND travel_date = %s::date
                  AND status <> 'cancelled'
                  AND seat_id IS NOT NULL
                GROUP BY schedule_id, departure_time
            ) counts
            GROUP BY schedule_id
        ) booked ON booked.schedule_id = m.schedule_id
        ORDER BY m.first_train_time, m.schedule_id
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                sql,
                (
                    origin_id,
                    destination_id,
                    travel_date,
                    travel_date,
                    origin_id,
                    destination_id,
                    travel_date,
                    travel_date,
                ),
            )
            rows = [dict(row) for row in cur.fetchall()]
            for row in rows:
                row["departure_times"] = _generated_departure_times(
                    row["first_train_time"],
                    row["last_train_time"],
                    row["frequency_min"],
                )
                booked_by_departure = row.pop("booked_seats_by_departure", {}) or {}
                total_seats = int(row.get("total_seats") or 0)
                row["availability_by_departure"] = [
                    {
                        "departure_time": departure_time,
                        "booked_seats": int(booked_by_departure.get(departure_time, 0)),
                        "available_seats": max(
                            total_seats - int(booked_by_departure.get(departure_time, 0)),
                            0,
                        ),
                    }
                    for departure_time in row["departure_times"]
                ]
            return rows


def query_national_rail_fare(
    schedule_id: str,
    fare_class: str,
    stops_travelled: int,
) -> Optional[dict]:
    """
    Calculate the fare for a national rail journey.

    Args:
        schedule_id:     e.g. "NR_SCH01"
        fare_class:      "standard" or "first"
        stops_travelled: number of stops between origin and destination (inclusive)

    Returns:
        dict with fare_class, base_fare_usd, per_stop_rate_usd, total_fare_usd
    """
    fare_class = fare_class.lower().strip()
    if fare_class not in {"standard", "first"}:
        return None

    base_col = "standard_base_fare" if fare_class == "standard" else "first_base_fare"
    rate_col = "standard_per_stop_rate" if fare_class == "standard" else "first_per_stop_rate"
    sql = f"""
        SELECT
            %s AS fare_class,
            {base_col} AS base_fare_usd,
            {rate_col} AS per_stop_rate_usd,
            ({base_col} + {rate_col} * %s) AS total_fare_usd
        FROM national_rail_schedules
        WHERE schedule_id = %s
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (fare_class, stops_travelled, schedule_id))
            row = cur.fetchone()
            return dict(row) if row else None


# ── METRO SCHEDULES & FARE ────────────────────────────────────────────────────

def query_metro_schedules(origin_id: str, destination_id: str) -> list[dict]:
    """
    Return metro schedules that serve both origin and destination in the correct order.

    Args:
        origin_id:       e.g. "MS01"
        destination_id:  e.g. "MS09"
    """
    sql = """
        WITH matching AS (
            SELECT
                s.*,
                os.stop_order AS origin_pos,
                ds.stop_order AS destination_pos,
                os.travel_time_from_origin_min AS origin_time_min,
                ds.travel_time_from_origin_min AS destination_time_min,
                array_agg(ss.station_id ORDER BY ss.stop_order) AS stops_in_order
            FROM metro_schedules s
            JOIN metro_schedule_stops os
              ON os.schedule_id = s.schedule_id
             AND os.station_id = %s
            JOIN metro_schedule_stops ds
              ON ds.schedule_id = s.schedule_id
             AND ds.station_id = %s
            JOIN metro_schedule_stops ss
              ON ss.schedule_id = s.schedule_id
            WHERE os.stop_order < ds.stop_order
            GROUP BY s.schedule_id, os.stop_order, ds.stop_order,
                     os.travel_time_from_origin_min, ds.travel_time_from_origin_min
        )
        SELECT
            m.schedule_id,
            m.line,
            m.direction,
            m.origin_station_id AS schedule_origin_station_id,
            m.destination_station_id AS schedule_destination_station_id,
            orig.name AS origin_name,
            dest.name AS destination_name,
            m.first_train_time::text,
            m.last_train_time::text,
            m.frequency_min,
            m.operates_on,
            m.stops_in_order,
            m.destination_pos - m.origin_pos AS stops_travelled,
            (m.destination_time_min - m.origin_time_min) AS travel_time_min,
            m.base_fare_usd,
            m.per_stop_rate_usd
        FROM matching m
        JOIN metro_stations orig ON orig.station_id = %s
        JOIN metro_stations dest ON dest.station_id = %s
        ORDER BY m.first_train_time, m.schedule_id
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                sql,
                (
                    origin_id,
                    destination_id,
                    origin_id,
                    destination_id,
                ),
            )
            return [dict(row) for row in cur.fetchall()]


def query_metro_fare(schedule_id: str, stops_travelled: int) -> Optional[dict]:
    """
    Calculate the metro fare for a single-ticket journey.

    Args:
        schedule_id:     e.g. "MS_SCH01"
        stops_travelled: number of stops between origin and destination

    Returns:
        dict with base_fare_usd, per_stop_rate_usd, total_fare_usd
    """
    sql = """
        SELECT
            base_fare_usd,
            per_stop_rate_usd,
            (base_fare_usd + per_stop_rate_usd * %s) AS total_fare_usd
        FROM metro_schedules
        WHERE schedule_id = %s
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (stops_travelled, schedule_id))
            row = cur.fetchone()
            return dict(row) if row else None


# ── SEAT SELECTION ────────────────────────────────────────────────────────────

def query_available_seats(
    schedule_id: str,
    travel_date: str,
    departure_time: str,
    fare_class: str,
) -> list[dict]:
    """
    Return available seats for a national rail journey on a given date.

    Args:
        schedule_id:     e.g. "NR_SCH01"
        travel_date:     e.g. "2025-06-01"
        departure_time:  e.g. "07:00"
        fare_class:      "standard" or "first"

    Returns:
        List of dicts: {seat_id, coach, row, column}
    """
    sql = """
        SELECT
            l.seat_id,
            l.coach,
            l."row",
            l."column",
            l.fare_class
        FROM national_rail_seat_layouts l
        WHERE l.schedule_id = %s
          AND l.fare_class = %s
          AND NOT EXISTS (
              SELECT 1
              FROM national_rail_bookings b
              WHERE b.schedule_id = l.schedule_id
                AND b.travel_date = %s::date
                AND b.departure_time = %s::time
                AND b.coach = l.coach
                AND b.seat_id = l.seat_id
                AND b.status <> 'cancelled'
          )
        ORDER BY l.coach, l."row", l."column", l.seat_id
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                sql,
                (schedule_id, fare_class.lower().strip(), travel_date, _time_text(departure_time)),
            )
            return [dict(row) for row in cur.fetchall()]


def auto_select_adjacent_seats(available_seats: list[dict], count: int) -> list[str]:
    """
    Select `count` seats that are as close together as possible (same row preferred,
    then adjacent rows). Returns a list of seat_ids.

    Args:
        available_seats: output of query_available_seats()
        count:           number of seats needed
    """
    if not available_seats or count <= 0:
        return []
    if count >= len(available_seats):
        return [s["seat_id"] for s in available_seats[:count]]

    from collections import defaultdict
    rows: dict[int, list[dict]] = defaultdict(list)
    for seat in available_seats:
        rows[seat["row"]].append(seat)

    for row_seats in sorted(rows.values(), key=lambda s: s[0]["row"]):
        if len(row_seats) >= count:
            return [s["seat_id"] for s in row_seats[:count]]

    sorted_seats = sorted(available_seats, key=lambda s: (s["row"], s["column"]))
    return [s["seat_id"] for s in sorted_seats[:count]]


# ── USER & BOOKING QUERIES ────────────────────────────────────────────────────

def query_user_profile(user_email: str) -> Optional[dict]:
    """Return a user's profile by email."""
    sql = """
        SELECT
            user_id,
            email,
            full_name,
            first_name,
            surname,
            phone,
            date_of_birth,
            EXTRACT(YEAR FROM date_of_birth)::int AS year_of_birth,
            is_active,
            registered_at
        FROM registered_users
        WHERE lower(email) = lower(%s)
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (user_email,))
            row = cur.fetchone()
            return dict(row) if row else None


def query_user_bookings(user_email: str) -> dict:
    """
    Return a user's combined booking history (national rail + metro).

    Returns:
        dict with keys 'national_rail' (list) and 'metro' (list)
    """
    rail_sql = """
        SELECT
            b.booking_id,
            b.schedule_id,
            s.line,
            s.service_type,
            b.travel_date,
            b.departure_time::text,
            b.ticket_type,
            b.fare_class,
            b.coach,
            b.seat_id,
            b.stops_travelled,
            b.amount_usd,
            b.status,
            b.booked_at,
            b.travelled_at,
            orig.station_id AS origin_station_id,
            orig.name AS origin_name,
            dest.station_id AS destination_station_id,
            dest.name AS destination_name,
            p.payment_id,
            p.status AS payment_status
        FROM national_rail_bookings b
        JOIN registered_users u ON u.user_id = b.user_id
        JOIN national_rail_schedules s ON s.schedule_id = b.schedule_id
        JOIN national_rail_stations orig ON orig.station_id = b.origin_station_id
        JOIN national_rail_stations dest ON dest.station_id = b.destination_station_id
        LEFT JOIN payments p ON p.national_rail_booking_id = b.booking_id
        WHERE lower(u.email) = lower(%s)
        ORDER BY b.travel_date DESC, b.departure_time DESC, b.booking_id DESC
    """
    metro_sql = """
        SELECT
            t.trip_id,
            t.schedule_id,
            s.line,
            t.travel_date,
            t.ticket_type,
            t.day_pass_ref,
            t.stops_travelled,
            t.amount_usd,
            t.status,
            t.purchased_at,
            t.travelled_at,
            orig.station_id AS origin_station_id,
            orig.name AS origin_name,
            dest.station_id AS destination_station_id,
            dest.name AS destination_name,
            p.payment_id,
            p.status AS payment_status
        FROM metro_travel_history t
        JOIN registered_users u ON u.user_id = t.user_id
        JOIN metro_schedules s ON s.schedule_id = t.schedule_id
        JOIN metro_stations orig ON orig.station_id = t.origin_station_id
        JOIN metro_stations dest ON dest.station_id = t.destination_station_id
        LEFT JOIN payments p ON p.metro_trip_id = t.trip_id
        WHERE lower(u.email) = lower(%s)
        ORDER BY t.travel_date DESC, t.purchased_at DESC, t.trip_id DESC
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(rail_sql, (user_email,))
            rail = [dict(row) for row in cur.fetchall()]
            cur.execute(metro_sql, (user_email,))
            metro = [dict(row) for row in cur.fetchall()]
            return {"national_rail": rail, "metro": metro}


def query_payment_info(booking_id: str) -> Optional[dict]:
    """Return payment record for a booking or metro trip."""
    sql = """
        SELECT
            payment_id,
            COALESCE(national_rail_booking_id, metro_trip_id) AS booking_id,
            national_rail_booking_id,
            metro_trip_id,
            amount_usd,
            method,
            status,
            paid_at
        FROM payments
        WHERE national_rail_booking_id = %s
           OR metro_trip_id = %s
        ORDER BY paid_at DESC
        LIMIT 1
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (booking_id, booking_id))
            row = cur.fetchone()
            return dict(row) if row else None


# ── TRANSACTIONAL OPERATIONS ──────────────────────────────────────────────────

def execute_booking(
    user_id: str,
    schedule_id: str,
    origin_station_id: str,
    destination_station_id: str,
    travel_date: str,
    departure_time: str,
    fare_class: str,
    seat_id: str,
    ticket_type: str = "single",
) -> tuple[bool, dict | str]:
    """
    Create a national rail booking for a logged-in user.

    Args:
        user_id:                e.g. "RU01" — must match the logged-in user
        schedule_id:            e.g. "NR_SCH01"
        origin_station_id:      e.g. "NR01"
        destination_station_id: e.g. "NR05"
        travel_date:            e.g. "2025-06-01"
        departure_time:         e.g. "07:00"
        fare_class:             "standard" or "first"
        seat_id:                e.g. "B05" (or "any" to auto-assign)
        ticket_type:            "single" (default) or "return"

    Returns:
        (True, booking_dict)   on success
        (False, error_message) on failure
    """
    fare_class = fare_class.lower().strip()
    ticket_type = ticket_type.lower().strip()
    if fare_class not in {"standard", "first"}:
        return False, "fare_class must be 'standard' or 'first'."
    if ticket_type not in {"single", "return"}:
        return False, "ticket_type must be 'single' or 'return'."
    try:
        departure_time = _time_text(departure_time)
    except ValueError:
        return False, "departure_time must be in HH:MM format."

    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT user_id, is_active FROM registered_users WHERE user_id = %s",
                (user_id,),
            )
            user = cur.fetchone()
            if not user or not user["is_active"]:
                conn.rollback()
                return False, "User account not found or inactive."

            cur.execute(
                """
                SELECT
                    s.*,
                    os.stop_order AS origin_pos,
                    ds.stop_order AS destination_pos
                FROM national_rail_schedules s
                JOIN national_rail_schedule_stops os
                  ON os.schedule_id = s.schedule_id
                 AND os.station_id = %s
                JOIN national_rail_schedule_stops ds
                  ON ds.schedule_id = s.schedule_id
                 AND ds.station_id = %s
                WHERE s.schedule_id = %s
                  AND os.stop_order < ds.stop_order
                """,
                (origin_station_id, destination_station_id, schedule_id),
            )
            schedule = cur.fetchone()
            if not schedule:
                conn.rollback()
                return False, "Schedule not found or does not serve the requested stations in order."
            valid_departure_times = _generated_departure_times(
                schedule["first_train_time"],
                schedule["last_train_time"],
                schedule["frequency_min"],
            )
            if departure_time not in valid_departure_times:
                conn.rollback()
                return (
                    False,
                    "departure_time must match this schedule's generated timetable "
                    f"({', '.join(valid_departure_times[:6])}"
                    f"{'...' if len(valid_departure_times) > 6 else ''}).",
                )

            stops_travelled = schedule["destination_pos"] - schedule["origin_pos"]
            base = (
                schedule["standard_base_fare"]
                if fare_class == "standard"
                else schedule["first_base_fare"]
            )
            rate = (
                schedule["standard_per_stop_rate"]
                if fare_class == "standard"
                else schedule["first_per_stop_rate"]
            )
            amount = _money(base + rate * stops_travelled)

            if seat_id.lower().strip() == "any":
                cur.execute(
                    """
                    SELECT l.seat_id, l.coach, l."row", l."column"
                    FROM national_rail_seat_layouts l
                    WHERE l.schedule_id = %s
                      AND l.fare_class = %s
                      AND NOT EXISTS (
                          SELECT 1
                          FROM national_rail_bookings b
                          WHERE b.schedule_id = l.schedule_id
                            AND b.travel_date = %s::date
                            AND b.departure_time = %s::time
                            AND b.coach = l.coach
                            AND b.seat_id = l.seat_id
                            AND b.status <> 'cancelled'
                      )
                    ORDER BY l.coach, l."row", l."column", l.seat_id
                    LIMIT 1
                    """,
                    (schedule_id, fare_class, travel_date, departure_time),
                )
                seat = cur.fetchone()
                if not seat:
                    conn.rollback()
                    return False, "No seats available for this service/date/fare class."
            else:
                cur.execute(
                    """
                    SELECT seat_id, coach, "row", "column"
                    FROM national_rail_seat_layouts
                    WHERE schedule_id = %s
                      AND fare_class = %s
                      AND lower(seat_id) = lower(%s)
                    """,
                    (schedule_id, fare_class, seat_id),
                )
                seat = cur.fetchone()
                if not seat:
                    conn.rollback()
                    return False, "Requested seat does not exist for this service/fare class."

                cur.execute(
                    """
                    SELECT 1
                    FROM national_rail_bookings
                    WHERE schedule_id = %s
                      AND travel_date = %s::date
                      AND departure_time = %s::time
                      AND coach = %s
                      AND seat_id = %s
                      AND status <> 'cancelled'
                    LIMIT 1
                    """,
                    (schedule_id, travel_date, departure_time, seat["coach"], seat["seat_id"]),
                )
                if cur.fetchone():
                    conn.rollback()
                    return False, "Requested seat is already booked."

            for _ in range(10):
                booking_id = _gen_booking_id()
                cur.execute("SELECT 1 FROM national_rail_bookings WHERE booking_id = %s", (booking_id,))
                if not cur.fetchone():
                    break
            else:
                conn.rollback()
                return False, "Could not generate a unique booking id."

            for _ in range(10):
                payment_id = _gen_payment_id()
                cur.execute("SELECT 1 FROM payments WHERE payment_id = %s", (payment_id,))
                if not cur.fetchone():
                    break
            else:
                conn.rollback()
                return False, "Could not generate a unique payment id."

            cur.execute(
                """
                INSERT INTO national_rail_bookings (
                    booking_id, user_id, schedule_id, origin_station_id,
                    destination_station_id, travel_date, departure_time,
                    ticket_type, fare_class, coach, seat_id, stops_travelled,
                    amount_usd, status
                )
                VALUES (%s, %s, %s, %s, %s, %s::date, %s, %s, %s, %s, %s, %s, %s, 'confirmed')
                RETURNING *
                """,
                (
                    booking_id,
                    user_id,
                    schedule_id,
                    origin_station_id,
                    destination_station_id,
                    travel_date,
                    departure_time,
                    ticket_type,
                    fare_class,
                    seat["coach"],
                    seat["seat_id"],
                    stops_travelled,
                    amount,
                ),
            )
            booking = dict(cur.fetchone())

            cur.execute(
                """
                INSERT INTO payments (payment_id, national_rail_booking_id, amount_usd, method, status)
                VALUES (%s, %s, %s, 'credit_card', 'paid')
                RETURNING payment_id, status
                """,
                (payment_id, booking_id, amount),
            )
            payment = dict(cur.fetchone())
            conn.commit()
            booking["payment_id"] = payment["payment_id"]
            booking["payment_status"] = payment["status"]
            return True, booking
    except Exception as exc:
        conn.rollback()
        return False, str(exc)
    finally:
        conn.close()


def execute_cancellation(booking_id: str, user_id: str) -> tuple[bool, dict | str]:
    """
    Cancel a national rail booking owned by the given user.

    Calculates the refund amount according to the booking's service type:
      - Normal service: RF001 windows (100% / 75% / 50% / 0%)
      - Express service: RF002 windows (100% / 50% / 0%)

    Args:
        booking_id: e.g. "BK001"
        user_id:    must match the booking's user_id

    Returns:
        (True, result_dict)  with refund_amount_usd and policy note
        (False, error_msg)
    """
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    b.*,
                    s.service_type,
                    p.payment_id,
                    p.status AS payment_status
                FROM national_rail_bookings b
                JOIN national_rail_schedules s ON s.schedule_id = b.schedule_id
                LEFT JOIN payments p ON p.national_rail_booking_id = b.booking_id
                WHERE b.booking_id = %s
                  AND b.user_id = %s
                FOR UPDATE OF b
                """,
                (booking_id, user_id),
            )
            booking = cur.fetchone()
            if not booking:
                conn.rollback()
                return False, "Booking not found for this user."
            if booking["status"] == "cancelled":
                conn.rollback()
                return False, "Booking is already cancelled."
            if booking["status"] == "completed" and booking["travelled_at"] is not None:
                conn.rollback()
                return False, "Completed journeys cannot be cancelled."

            departure_dt = datetime.combine(
                booking["travel_date"], booking["departure_time"]
            ).replace(tzinfo=timezone.utc)
            hours_before = (departure_dt - datetime.now(timezone.utc)).total_seconds() / 3600

            service_type = booking["service_type"]
            if service_type == "express":
                policy_id = "RF002"
                if hours_before >= 48:
                    refund_percent, admin_fee, label = Decimal("100"), Decimal("1.00"), "Early cancellation"
                elif hours_before >= 24:
                    refund_percent, admin_fee, label = Decimal("50"), Decimal("1.00"), "Late cancellation"
                else:
                    refund_percent, admin_fee, label = Decimal("0"), Decimal("0.00"), "No refund"
            else:
                policy_id = "RF001"
                if hours_before >= 48:
                    refund_percent, admin_fee, label = Decimal("100"), Decimal("0.00"), "Early cancellation"
                elif hours_before >= 24:
                    refund_percent, admin_fee, label = Decimal("75"), Decimal("0.50"), "Standard cancellation"
                elif hours_before >= 2:
                    refund_percent, admin_fee, label = Decimal("50"), Decimal("0.50"), "Late cancellation"
                else:
                    refund_percent, admin_fee, label = Decimal("0"), Decimal("0.00"), "No refund"

            refund = _money((booking["amount_usd"] * refund_percent / Decimal("100")) - admin_fee)
            if refund < 0:
                refund = Decimal("0.00")

            cur.execute(
                """
                UPDATE national_rail_bookings
                SET status = 'cancelled'
                WHERE booking_id = %s
                RETURNING booking_id, status
                """,
                (booking_id,),
            )
            updated = dict(cur.fetchone())

            if booking["payment_id"]:
                cur.execute(
                    """
                    UPDATE payments
                    SET status = 'refunded'
                    WHERE payment_id = %s
                    """,
                    (booking["payment_id"],),
                )

            conn.commit()
            return True, {
                **updated,
                "refund_amount": refund,
                "refund_amount_usd": refund,
                "refund_percent": refund_percent,
                "admin_fee_usd": admin_fee,
                "policy_id": policy_id,
                "policy_window": label,
                "hours_before_departure": round(hours_before, 2),
            }
    except Exception as exc:
        conn.rollback()
        return False, str(exc)
    finally:
        conn.close()


# ── AUTHENTICATION QUERIES ────────────────────────────────────────────────────

def register_user(
    email: str,
    first_name: str,
    surname: str,
    year_of_birth: int,
    password: str,
    secret_question: str,
    secret_answer: str,
) -> tuple[bool, str]:
    """
    Register a new user.
    Returns (True, user_id) on success or (False, error_message) on failure.

    Profile goes to registered_users; bcrypt salt+hash and secret Q&A go to
    user_credentials (Defense in Depth — credentials never mixed with profile).
    """
    email = email.strip().lower()
    first_name = first_name.strip()
    surname = surname.strip()
    if not email or not first_name or not surname or not password:
        return False, "Email, name, and password are required."

    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT 1 FROM registered_users WHERE lower(email) = lower(%s)", (email,))
            if cur.fetchone():
                conn.rollback()
                return False, "An account with this email already exists."

            user_id = _new_user_id(cur)
            full_name = f"{first_name} {surname}"
            date_of_birth = f"{int(year_of_birth):04d}-01-01"

            # Insert profile (no password here)
            cur.execute(
                """
                INSERT INTO registered_users (
                    user_id, full_name, first_name, surname, email,
                    date_of_birth, is_active
                )
                VALUES (%s, %s, %s, %s, %s, %s::date, TRUE)
                RETURNING user_id
                """,
                (user_id, full_name, first_name, surname, email, date_of_birth),
            )
            new_user_id = cur.fetchone()["user_id"]

            # Hash password and insert into isolated user_credentials table
            salt_str, hash_str = _hash_password(password)
            cur.execute(
                """
                INSERT INTO user_credentials (user_id, salt_str, password_hash, secret_question, secret_answer)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (new_user_id, salt_str, hash_str, secret_question, secret_answer),
            )
            conn.commit()
            return True, new_user_id
    except Exception as exc:
        conn.rollback()
        return False, str(exc)
    finally:
        conn.close()


def login_user(email: str, password: str) -> Optional[dict]:
    """
    Verify credentials using bcrypt against user_credentials table.
    Returns a user dict on success or None on failure.
    Dict keys: user_id, email, full_name, first_name, surname, phone, date_of_birth, is_active.
    """
    sql = """
        SELECT u.user_id, u.email, u.full_name, u.first_name, u.surname,
               u.phone, u.date_of_birth,
               EXTRACT(YEAR FROM u.date_of_birth)::int AS year_of_birth,
               u.is_active,
               c.salt_str, c.password_hash
        FROM registered_users u
        JOIN user_credentials c ON c.user_id = u.user_id
        WHERE lower(u.email) = lower(%s)
          AND u.is_active = TRUE
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (email.strip(),))
            row = cur.fetchone()
            if not row:
                return None
            if not _check_password(password, row["salt_str"], row["password_hash"]):
                return None
            result = dict(row)
            result.pop("salt_str", None)
            result.pop("password_hash", None)
            return result


def get_user_secret_question(email: str) -> Optional[str]:
    """Return the secret question for a registered email, or None if not found."""
    sql = """
        SELECT c.secret_question
        FROM registered_users u
        JOIN user_credentials c ON c.user_id = u.user_id
        WHERE lower(u.email) = lower(%s)
          AND u.is_active = TRUE
    """
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (email.strip(),))
            row = cur.fetchone()
            return row[0] if row else None


def verify_secret_answer(email: str, answer: str) -> bool:
    """Return True if the provided answer matches the stored secret answer (case-insensitive)."""
    sql = """
        SELECT 1
        FROM registered_users u
        JOIN user_credentials c ON c.user_id = u.user_id
        WHERE lower(u.email) = lower(%s)
          AND lower(trim(c.secret_answer)) = lower(trim(%s))
          AND u.is_active = TRUE
    """
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (email.strip(), answer.strip()))
            return cur.fetchone() is not None


def update_password(email: str, new_password: str) -> bool:
    """Update the password hash in user_credentials. Returns True if updated."""
    salt_str, hash_str = _hash_password(new_password)
    sql = """
        UPDATE user_credentials
        SET salt_str = %s, password_hash = %s
        WHERE user_id = (
            SELECT user_id FROM registered_users
            WHERE lower(email) = lower(%s) AND is_active = TRUE
        )
    """
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (salt_str, hash_str, email.strip()))
            return cur.rowcount > 0


# TASK 6 EXTENSION: Loyalty Points System
# ── LOYALTY POINTS QUERIES ────────────────────────────────────────────────────

def query_loyalty_balance(user_id: str) -> dict:
    """
    Return the total loyalty points balance for a user.

    Points are earned at a rate of 10 per USD spent on completed
    national-rail national_rail_bookings.  This function sums all rows in the
    loyalty_points ledger for the given user.

    Args:
        user_id: e.g. "RU01"

    Returns:
        dict with user_id, total_points (Decimal), and transaction_count (int).
        Returns zero balance (not None) when the user has no points.
    """
    sql = """
        SELECT
            %s                              AS user_id,
            COALESCE(SUM(points_earned), 0) AS total_points,
            COUNT(*)                        AS transaction_count
        FROM loyalty_points
        WHERE user_id = %s
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # TASK 6 EXTENSION: read the loyalty ledger for one user and aggregate
            # every earn row into a dashboard-ready balance.
            cur.execute(sql, (user_id, user_id))
            return dict(cur.fetchone())


def query_loyalty_history(user_id: str) -> list[dict]:
    """
    Return the full loyalty-points earn history for a user, newest first.

    Joins to national_rail_bookings so the caller can display the route and travel date
    alongside the points earned.

    Args:
        user_id: e.g. "RU01"

    Returns:
        List of dicts ordered by earned_at DESC.  Empty list for unknown user.
    """
    sql = """
        SELECT
            lp.id,
            lp.user_id,
            lp.source_booking_id,
            lp.points_earned,
            lp.description,
            lp.earned_at,
            b.travel_date,
            b.amount_usd          AS booking_amount_usd,
            b.fare_class,
            orig.name             AS origin_name,
            dest.name             AS destination_name
        FROM loyalty_points lp
        JOIN national_rail_bookings b
            ON b.booking_id = lp.source_booking_id
        JOIN national_rail_stations orig
            ON orig.station_id = b.origin_station_id
        JOIN national_rail_stations dest
            ON dest.station_id = b.destination_station_id
        WHERE lp.user_id = %s
        ORDER BY lp.earned_at DESC
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # TASK 6 EXTENSION: join loyalty rows back to bookings and stations so
            # every credited point transaction remains auditable to its journey.
            cur.execute(sql, (user_id,))
            return [dict(row) for row in cur.fetchall()]


def execute_earn_loyalty_points(booking_id: str) -> tuple[bool, dict | str]:
    """
    Credit loyalty points for a completed booking.

    Earn rate: 10 points per USD of the booking amount, rounded to 2 dp.
    The unique index on source_booking_id prevents double-crediting if
    this function is called more than once for the same booking.

    This is an atomic write: the INSERT either succeeds fully or rolls back.

    Args:
        booking_id: e.g. "BK001" — must exist and have status 'completed' or 'confirmed'.

    Returns:
        (True, result_dict)  with user_id, points_earned, total_points
        (False, error_msg)   if booking not found, already credited, or wrong status
    """
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # TASK 6 EXTENSION: lock the earn operation to an existing rail booking;
            # loyalty points are never created without a real source booking.
            cur.execute(
                "SELECT booking_id, user_id, amount_usd, status FROM national_rail_bookings WHERE booking_id = %s",
                (booking_id,),
            )
            booking = cur.fetchone()
            if not booking:
                conn.rollback()
                return False, f"Booking {booking_id} not found."
            if booking["status"] == "cancelled":
                conn.rollback()
                return False, "Cancelled national_rail_bookings do not earn loyalty points."

            # TASK 6 EXTENSION: pre-check the unique ledger key so duplicate earn
            # attempts return a friendly message instead of double-crediting points.
            cur.execute(
                "SELECT 1 FROM loyalty_points WHERE source_booking_id = %s",
                (booking_id,),
            )
            if cur.fetchone():
                conn.rollback()
                return False, f"Points already credited for booking {booking_id}."

            # Calculate points: 10 per USD, rounded to 2 decimal places
            points = _money(Decimal(str(booking["amount_usd"])) * 10)

            # TASK 6 EXTENSION: write one auditable ledger row for this booking.
            # The transaction commits only after the insert and balance read succeed.
            cur.execute(
                """
                INSERT INTO loyalty_points
                    (user_id, source_booking_id, points_earned, description)
                VALUES (%s, %s, %s, %s)
                RETURNING id, user_id, points_earned, earned_at
                """,
                (
                    booking["user_id"],
                    booking_id,
                    points,
                    f"Points earned for booking {booking_id}",
                ),
            )
            row = dict(cur.fetchone())

            # TASK 6 EXTENSION: re-read the user's aggregate balance after the earn
            # insert so the caller can immediately display the updated total.
            cur.execute(
                "SELECT COALESCE(SUM(points_earned), 0) AS total FROM loyalty_points WHERE user_id = %s",
                (booking["user_id"],),
            )
            total = cur.fetchone()["total"]
            conn.commit()
            return True, {**row, "total_points": total}
    except Exception as exc:
        conn.rollback()
        return False, str(exc)
    finally:
        conn.close()


# ── VECTOR / RAG QUERIES — do not modify ─────────────────────────────────────

def query_policy_vector_search(embedding: list[float], top_k: int = VECTOR_TOP_K) -> list[dict]:
    """
    Find the most relevant policy documents for a given query embedding.

    Args:
        embedding: Query vector from llm.embed(user_question)
        top_k:     Number of results to return

    Returns:
        List of dicts with title, category, content, and similarity score
    """
    sql = """
        SELECT
            title,
            category,
            content,
            1 - (embedding <=> %s::vector) AS similarity
        FROM policy_documents
        WHERE 1 - (embedding <=> %s::vector) > %s
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (vec_str, vec_str, VECTOR_SIMILARITY_THRESHOLD, vec_str, top_k))
            return [dict(row) for row in cur.fetchall()]


def store_policy_document(
    title: str,
    category: str,
    content: str,
    embedding: list[float],
    source_file: str = "",
) -> int:
    """
    Insert a policy document with its embedding into the database.
    Used by skeleton/seed_vectors.py — students don't need to call this directly.

    Returns:
        The new document's id
    """
    sql = """
        INSERT INTO policy_documents (title, category, content, embedding, source_file)
        VALUES (%s, %s, %s, %s::vector, %s)
        RETURNING id
    """
    vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (title, category, content, vec_str, source_file))
            return cur.fetchone()[0]
