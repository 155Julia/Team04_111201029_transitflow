"""
Seed PostgreSQL with all TransitFlow mock data from train-mock-data/.

Usage:
    python skeleton/seed_postgres.py

Run AFTER docker-compose up -d.
You must first design and create your tables in databases/relational/schema.sql.
Safe to re-run: implement your inserts with ON CONFLICT DO NOTHING.
TASK 6 EXTENSION: seeds loyalty_points from completed national rail bookings.
"""

import json
import os
import sys

import bcrypt
import psycopg2
from psycopg2.extras import execute_values

# ── resolve paths ────────────────────────────────────────────────────────────
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR    = os.path.join(PROJECT_DIR, "train-mock-data")

sys.path.insert(0, PROJECT_DIR)
from skeleton import config as cfg


# TASK 6 EXTENSION: seed_loyalty_points loads the loyalty_points ledger.


def load(filename):
    with open(os.path.join(DATA_DIR, filename), encoding="utf-8") as f:
        return json.load(f)


def connect():
    return psycopg2.connect(
        host=cfg.PG_HOST,
        port=cfg.PG_PORT,
        dbname=cfg.PG_DB,
        user=cfg.PG_USER,
        password=cfg.PG_PASSWORD,
    )


def insert_many(cur, table, columns, rows):
    """Bulk insert with ON CONFLICT DO NOTHING. Returns row count inserted."""
    if not rows:
        return 0
    sql = (
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES %s "
        f"ON CONFLICT DO NOTHING"
    )
    execute_values(cur, sql, rows)
    return cur.rowcount


# ── seeders ──────────────────────────────────────────────────────────────────

def seed_metro_stations(cur):
    data = load("metro_stations.json")
    rows = [
        (
            station["station_id"],
            station["name"],
            station["lines"],
            station.get("is_interchange_metro", False),
            station.get("is_interchange_national_rail", False),
            station.get("interchange_national_rail_station_id"),
            [adj["station_id"] for adj in station.get("adjacent_stations", [])],
        )
        for station in data
    ]
    n = insert_many(
        cur,
        "metro_stations",
        [
            "station_id",
            "name",
            "lines",
            "is_interchange_metro",
            "is_interchange_national_rail",
            "interchange_national_rail_station_id",
            "adjacent_stations",
        ],
        rows,
    )
    print(f"  metro_stations: {n} rows")


def seed_national_rail_stations(cur):
    data = load("national_rail_stations.json")
    rows = [
        (
            station["station_id"],
            station["name"],
            station["lines"],
        )
        for station in data
    ]
    n = insert_many(
        cur,
        "national_rail_stations",
        ["station_id", "name", "lines"],
        rows,
    )
    print(f"  national_rail_stations: {n} rows")


def seed_metro_schedules(cur):
    data = load("metro_schedules.json")
    rows = [
        (
            schedule["schedule_id"],
            schedule["line"],
            schedule["direction"],
            schedule["origin_station_id"],
            schedule["destination_station_id"],
            schedule["first_train_time"],
            schedule["last_train_time"],
            schedule["base_fare_usd"],
            schedule["per_stop_rate_usd"],
            schedule["frequency_min"],
            schedule["operates_on"],
        )
        for schedule in data
    ]
    n = insert_many(
        cur,
        "metro_schedules",
        [
            "schedule_id",
            "line",
            "direction",
            "origin_station_id",
            "destination_station_id",
            "first_train_time",
            "last_train_time",
            "base_fare_usd",
            "per_stop_rate_usd",
            "frequency_min",
            "operates_on",
        ],
        rows,
    )
    print(f"  metro_schedules: {n} rows")


def seed_national_rail_schedules(cur):
    data = load("national_rail_schedules.json")
    rows = []
    for schedule in data:
        fare_classes = schedule["fare_classes"]
        standard = fare_classes["standard"]
        first = fare_classes["first"]
        rows.append(
            (
                schedule["schedule_id"],
                schedule["line"],
                schedule["service_type"],
                schedule["direction"],
                schedule["origin_station_id"],
                schedule["destination_station_id"],
                schedule["frequency_min"],
                schedule["first_train_time"],
                schedule["last_train_time"],
                schedule["operates_on"],
                schedule.get("passed_through_stations"),
                standard["base_fare_usd"],
                standard["per_stop_rate_usd"],
                first["base_fare_usd"],
                first["per_stop_rate_usd"],
                schedule["service_type"] == "express",
            )
        )
    n = insert_many(
        cur,
        "national_rail_schedules",
        [
            "schedule_id",
            "line",
            "service_type",
            "direction",
            "origin_station_id",
            "destination_station_id",
            "frequency_min",
            "first_train_time",
            "last_train_time",
            "operates_on",
            "passed_through_stations",
            "standard_base_fare",
            "standard_per_stop_rate",
            "first_base_fare",
            "first_per_stop_rate",
            "is_express_premium",
        ],
        rows,
    )
    print(f"  national_rail_schedules: {n} rows")


def seed_metro_schedule_stops(cur):
    """Seed normalised metro stop sequences with one row per schedule stop."""
    data = load("metro_schedules.json")
    rows = []
    for schedule in data:
        travel_times = schedule["travel_time_from_origin_min"]
        for idx, station_id in enumerate(schedule["stops_in_order"], start=1):
            rows.append((
                schedule["schedule_id"],
                station_id,
                idx,
                travel_times[station_id],
            ))
    n = insert_many(
        cur,
        "metro_schedule_stops",
        ["schedule_id", "station_id", "stop_order", "travel_time_from_origin_min"],
        rows,
    )
    print(f"  metro_schedule_stops: {n} rows")


def seed_national_rail_schedule_stops(cur):
    """Seed normalised national rail stop sequences with one row per schedule stop."""
    data = load("national_rail_schedules.json")
    rows = []
    for schedule in data:
        travel_times = schedule["travel_time_from_origin_min"]
        for idx, station_id in enumerate(schedule["stops_in_order"], start=1):
            rows.append((
                schedule["schedule_id"],
                station_id,
                idx,
                travel_times[station_id],
            ))
    n = insert_many(
        cur,
        "national_rail_schedule_stops",
        ["schedule_id", "station_id", "stop_order", "travel_time_from_origin_min"],
        rows,
    )
    print(f"  national_rail_schedule_stops: {n} rows")


def seed_seat_layouts(cur):
    data = load("national_rail_seat_layouts.json")
    rows = []
    for layout in data:
        for coach in layout["coaches"]:
            for seat in coach["seats"]:
                rows.append(
                    (
                        layout["layout_id"],
                        layout["schedule_id"],
                        coach["coach"],
                        coach["fare_class"],
                        seat["seat_id"],
                        seat["row"],
                        seat["column"],
                    )
                )
    n = insert_many(
        cur,
        "national_rail_seat_layouts",
        ["layout_id", "schedule_id", "coach", "fare_class", "seat_id", '"row"', '"column"'],
        rows,
    )
    print(f"  national_rail_seat_layouts: {n} rows")


def seed_users(cur):
    data = load("registered_users.json")
    rows = []
    for user in data:
        name_parts = user["full_name"].split(maxsplit=1)
        first_name = name_parts[0]
        surname = name_parts[1] if len(name_parts) > 1 else ""
        # Hash the plain-text password from mock data using bcrypt
        # so the database never stores plain text, matching register_user()
        hashed_pw = bcrypt.hashpw(
            user["password"].encode(), bcrypt.gensalt()
        ).decode()
        rows.append(
            (
                user["user_id"],
                user["full_name"],
                first_name,
                surname,
                user["email"],
                hashed_pw,
                user.get("phone"),
                user.get("date_of_birth"),
                user.get("secret_question"),
                user.get("secret_answer"),
                user.get("registered_at"),
                user.get("is_active", True),
            )
        )
    n = insert_many(
        cur,
        "registered_users",
        [
            "user_id",
            "full_name",
            "first_name",
            "surname",
            "email",
            "password",
            "phone",
            "date_of_birth",
            "secret_question",
            "secret_answer",
            "registered_at",
            "is_active",
        ],
        rows,
    )
    print(f"  registered_users: {n} rows")


def seed_national_rail_bookings(cur):
    data = load("bookings.json")
    rows = [
        (
            booking["booking_id"],
            booking["user_id"],
            booking["schedule_id"],
            booking["origin_station_id"],
            booking["destination_station_id"],
            booking["travel_date"],
            booking["departure_time"],
            booking["ticket_type"],
            booking["fare_class"],
            booking.get("coach"),
            booking.get("seat_id"),
            booking["stops_travelled"],
            booking["amount_usd"],
            booking["status"],
            booking.get("booked_at"),
            booking.get("travelled_at"),
        )
        for booking in data
    ]
    n = insert_many(
        cur,
        "national_rail_bookings",
        [
            "booking_id",
            "user_id",
            "schedule_id",
            "origin_station_id",
            "destination_station_id",
            "travel_date",
            "departure_time",
            "ticket_type",
            "fare_class",
            "coach",
            "seat_id",
            "stops_travelled",
            "amount_usd",
            "status",
            "booked_at",
            "travelled_at",
        ],
        rows,
    )
    print(f"  national_rail_bookings: {n} rows")


def seed_metro_travels(cur):
    data = load("metro_travel_history.json")
    rows = [
        (
            trip["trip_id"],
            trip["user_id"],
            trip["schedule_id"],
            trip["origin_station_id"],
            trip["destination_station_id"],
            trip["travel_date"],
            trip["ticket_type"],
            trip.get("day_pass_ref"),
            trip.get("stops_travelled"),
            trip["amount_usd"],
            trip["status"],
            trip.get("purchased_at"),
            trip.get("travelled_at"),
        )
        for trip in data
    ]
    n = insert_many(
        cur,
        "metro_travel_history",
        [
            "trip_id",
            "user_id",
            "schedule_id",
            "origin_station_id",
            "destination_station_id",
            "travel_date",
            "ticket_type",
            "day_pass_ref",
            "stops_travelled",
            "amount_usd",
            "status",
            "purchased_at",
            "travelled_at",
        ],
        rows,
    )
    print(f"  metro_travel_history: {n} rows")


def seed_payments(cur):
    data = load("payments.json")
    rows = [
        (
            payment["payment_id"],
            payment["booking_id"] if payment["booking_id"].startswith("BK") else None,
            payment["booking_id"] if payment["booking_id"].startswith("MT") else None,
            payment["amount_usd"],
            payment["method"],
            payment["status"],
            payment.get("paid_at"),
        )
        for payment in data
    ]
    n = insert_many(
        cur,
        "payments",
        [
            "payment_id",
            "national_rail_booking_id",
            "metro_trip_id",
            "amount_usd",
            "method",
            "status",
            "paid_at",
        ],
        rows,
    )
    print(f"  payments: {n} rows")


def seed_feedback(cur):
    data = load("feedback.json")
    rows = [
        (
            feedback["feedback_id"],
            feedback["booking_id"] if feedback["booking_id"].startswith("BK") else None,
            feedback["booking_id"] if feedback["booking_id"].startswith("MT") else None,
            feedback["user_id"],
            feedback["rating"],
            feedback.get("comment"),
            feedback.get("submitted_at"),
        )
        for feedback in data
    ]
    n = insert_many(
        cur,
        "feedback",
        [
            "feedback_id",
            "national_rail_booking_id",
            "metro_trip_id",
            "user_id",
            "rating",
            "comment",
            "submitted_at",
        ],
        rows,
    )
    print(f"  feedback: {n} rows")


# TASK 6 EXTENSION: Loyalty Points System
def seed_loyalty_points(cur):
    """
    Seed initial loyalty points for all completed national_rail_bookings in the mock data.

    Earn rate: 10 points per USD spent.  Only 'completed' national_rail_bookings are
    seeded — confirmed and cancelled national_rail_bookings do not earn points at seed
    time.  ON CONFLICT DO NOTHING on the unique index (source_booking_id)
    makes this safe to re-run without creating duplicate ledger entries.
    """
    data = load("bookings.json")
    rows = []
    for booking in data:
        if booking["status"] != "completed":
            continue
        points = round(float(booking["amount_usd"]) * 10, 2)
        rows.append((
            booking["user_id"],
            booking["booking_id"],
            points,
            f"Points earned for booking {booking['booking_id']}",
        ))
    n = insert_many(
        cur,
        "loyalty_points",
        ["user_id", "source_booking_id", "points_earned", "description"],
        rows,
    )
    print(f"  loyalty_points: {n} rows")


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print("Connecting to PostgreSQL...")
    conn = connect()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        print("Seeding tables (dependency order):")
        seed_national_rail_stations(cur)
        seed_metro_stations(cur)
        seed_metro_schedules(cur)
        seed_national_rail_schedules(cur)
        seed_metro_schedule_stops(cur)
        seed_national_rail_schedule_stops(cur)
        seed_seat_layouts(cur)
        seed_users(cur)
        seed_national_rail_bookings(cur)
        seed_metro_travels(cur)
        seed_payments(cur)
        seed_feedback(cur)
        seed_loyalty_points(cur)  # TASK 6 EXTENSION
        conn.commit()
        print("\nAll done. Database seeded successfully.")
    except Exception as e:
        conn.rollback()
        print(f"\nError: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
