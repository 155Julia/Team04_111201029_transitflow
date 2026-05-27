"""
TransitFlow — PostgreSQL / Relational Database Layer
=====================================================
This module handles all queries to PostgreSQL.

TWO ROLES ARE SERVED HERE:
  1. Relational  → dual-network transit (metro + national rail),
                   availability, fares, bookings, seat selection
  2. Vector      → policy document similarity search (pgvector)

STUDENT TASK
------------
Design your schema in databases/relational/schema.sql, seed it with
skeleton/seed_postgres.py, then implement the query functions below.

Functions prefixed with `query_`  are read-only lookups called by the agent.
Functions prefixed with `execute_` are write operations (booking/cancellation).

The vector functions (query_policy_vector_search, store_policy_document)
are already implemented — do not modify them.
"""

from __future__ import annotations

import json
import random
import string
from datetime import datetime, timezone
from typing import Optional

import psycopg2
import psycopg2.extras

from skeleton.config import PG_DSN, VECTOR_TOP_K, VECTOR_SIMILARITY_THRESHOLD


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

# TODO: Implement the query_ and execute_ functions below.
# ─────────────────────────────────────────────────────────────────────────────
Python
# =============================================================================
# TODO: Implement the query_ and execute_ functions below.
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
    """
    # 找出同時包含起訖站，且起點順序在終點之前的班次
    sql = """
        SELECT 
            schedule_id, line, service_type, direction, 
            origin_station_id, destination_station_id,
            first_train_time, last_train_time, frequency_min,
            stops_in_order, travel_time_from_origin_min, fare_classes
        FROM national_rail_schedules
        WHERE %s = ANY(stops_in_order) 
          AND %s = ANY(stops_in_order)
          AND array_position(stops_in_order, %s) < array_position(stops_in_order, %s);
    """
    
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (origin_id, destination_id, origin_id, destination_id))
            schedules = [dict(row) for row in cur.fetchall()]
            
            # 如果有提供日期，計算該日期該班次的已訂位人數
            for sched in schedules:
                if travel_date:
                    count_sql = """
                        SELECT COUNT(*) FROM bookings 
                        WHERE schedule_id = %s 
                          AND travel_date = %s 
                          AND status = 'completed';
                    """
                    cur.execute(count_sql, (sched["schedule_id"], travel_date))
                    sched["booked_seats_count"] = cur.fetchone()["count"]
                else:
                    sched["booked_seats_count"] = 0
            return schedules


def query_national_rail_fare(
    schedule_id: str,
    fare_class: str,
    stops_travelled: int,
) -> Optional[dict]:
    """
    Calculate the fare for a national rail journey.
    """
    sql = "SELECT fare_classes FROM national_rail_schedules WHERE schedule_id = %s;"
    
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (schedule_id,))
            row = cur.fetchone()
            if not row or not row["fare_classes"]:
                return None
            
            # 解析 JSONB 格式的費率
            fare_classes = row["fare_classes"]
            if isinstance(fare_classes, str):
                fare_classes = json.loads(fare_classes)
                
            class_info = fare_classes.get(fare_class)
            if not class_info:
                return None
                
            base_fare = float(class_info["base_fare_usd"])
            per_stop_rate = float(class_info["per_stop_rate_usd"])
            total_fare = base_fare + (stops_travelled * per_stop_rate)
            
            return {
                "fare_class": fare_class,
                "base_fare_usd": base_fare,
                "per_stop_rate_usd": per_stop_rate,
                "total_fare_usd": round(total_fare, 2)
            }


# ── METRO SCHEDULES & FARE ────────────────────────────────────────────────────

def query_metro_schedules(origin_id: str, destination_id: str) -> list[dict]:
    """
    Return metro schedules that serve both origin and destination in the correct order.
    """
    sql = """
        SELECT 
            schedule_id, line, direction, origin_station_id, destination_station_id,
            first_train_time, last_train_time, frequency_min,
            stops_in_order, travel_time_from_origin_min, base_fare_usd, per_stop_rate_usd
        FROM metro_schedules
        WHERE %s = ANY(stops_in_order) 
          AND %s = ANY(stops_in_order)
          AND array_position(stops_in_order, %s) < array_position(stops_in_order, %s);
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (origin_id, destination_id, origin_id, destination_id))
            return [dict(row) for row in cur.fetchall()]


def query_metro_fare(schedule_id: str, stops_travelled: int) -> Optional[dict]:
    """
    Calculate the metro fare for a single-ticket journey.
    """
    sql = "SELECT base_fare_usd, per_stop_rate_usd FROM metro_schedules WHERE schedule_id = %s;"
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (schedule_id,))
            row = cur.fetchone()
            if not row:
                return None
            
            base_fare = float(row["base_fare_usd"])
            per_stop_rate = float(row["per_stop_rate_usd"])
            total_fare = base_fare + (stops_travelled * per_stop_rate)
            
            return {
                "base_fare_usd": base_fare,
                "per_stop_rate_usd": per_stop_rate,
                "total_fare_usd": round(total_fare, 2)
            }


# ── SEAT SELECTION ────────────────────────────────────────────────────────────

def query_available_seats(
    schedule_id: str,
    travel_date: str,
    fare_class: str,
) -> list[dict]:
    """
    Return available seats for a national rail journey on a given date.
    """
    # 1. 先從座位配置表 (seat_layouts) 中查出該班次、該艙等的所有座位
    # 註：此處 SQL 語法假設你將 json 資料展開儲存在 layout 表中，或是使用 JSONB 查詢。
    # 這裡採用的邏輯是查詢 layouts 中對應 schedule_id 的艙等座位，並扣除 bookings 裡已被佔用的座位。
    layout_sql = """
        SELECT s.seat_id, s.coach, s.row, s.column
        FROM national_rail_seat_layouts l,
             jsonb_to_recordset(l.coaches) AS c(coach text, fare_class text, seats jsonb),
             jsonb_to_recordset(c.seats) AS s(seat_id text, row int, "column" text)
        WHERE l.schedule_id = %s AND c.fare_class = %s;
    """
    
    # 2. 查出當天已被預訂且狀態為 completed 的座位
    booked_sql = """
        SELECT seat_id FROM bookings
        WHERE schedule_id = %s AND travel_date = %s AND status = 'completed';
    """
    
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(layout_sql, (schedule_id, fare_class))
            all_seats = [dict(row) for row in cur.fetchall()]
            
            cur.execute(booked_sql, (schedule_id, travel_date))
            booked_seats = {row["seat_id"] for row in cur.fetchall()}
            
            # 過濾掉已被預訂的座位
            available = [s for s in all_seats if s["seat_id"] not in booked_seats]
            return available


# ── USER & BOOKING QUERIES ────────────────────────────────────────────────────

def query_user_profile(user_email: str) -> Optional[dict]:
    """Return a user's profile by email."""
    sql = """
        SELECT user_id, email, full_name, phone, date_of_birth, registered_at, is_active 
        FROM registered_users WHERE email = %s;
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (user_email,))
            row = cur.fetchone()
            return dict(row) if row else None


def query_user_bookings(user_email: str) -> dict:
    """
    Return a user's combined booking history (national rail + metro).
    """
    # 先找 user_id
    profile = query_user_profile(user_email)
    if not profile:
        return {"national_rail": [], "metro": []}
    
    user_id = profile["user_id"]
    
    nr_sql = "SELECT * FROM bookings WHERE user_id = %s ORDER BY travel_date DESC, departure_time DESC;"
    metro_sql = "SELECT * FROM metro_travel_history WHERE user_id = %s ORDER BY travel_date DESC, travelled_at DESC;"
    
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(nr_sql, (user_id,))
            nr_bookings = [dict(row) for row in cur.fetchall()]
            
            cur.execute(metro_sql, (user_id,))
            metro_trips = [dict(row) for row in cur.fetchall()]
            
            # 將 datetime 轉為字串避免 Gradio/JSON 序列化錯誤
            for b in nr_bookings:
                if isinstance(b.get("booked_at"), datetime):
                    b["booked_at"] = b["booked_at"].isoformat()
            for m in metro_trips:
                if isinstance(m.get("travelled_at"), datetime):
                    m["travelled_at"] = m["travelled_at"].isoformat()
                    
            return {"national_rail": nr_bookings, "metro": metro_trips}


def query_payment_info(booking_id: str) -> Optional[dict]:
    """Return payment record for a booking or metro trip."""
    sql = "SELECT * FROM payments WHERE booking_id = %s;"
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (booking_id,))
            row = cur.fetchone()
            if row and isinstance(row.get("paid_at"), datetime):
                row["paid_at"] = row["paid_at"].isoformat()
            return dict(row) if row else None


# ── TRANSACTIONAL OPERATIONS ──────────────────────────────────────────────────

def execute_booking(
    user_id: str,
    schedule_id: str,
    origin_station_id: str,
    destination_station_id: str,
    travel_date: str,
    fare_class: str,
    seat_id: str,
    ticket_type: str = "single",
) -> tuple[bool, dict | str]:
    """
    Create a national rail booking for a logged-in user.
    """
    conn = psycopg2.connect(PG_DSN) # 手動管理事務交易 (Transaction)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 1. 如果座位選擇 "any"，自動分配一個空位
            if seat_id == "any":
                # 調用前面寫好的查空位函式
                # 為了避免連線衝突，直接在同一個交易裡處理或透過原邏輯
                # 這裡簡單起見先查出所有可用座位
                available = query_available_seats(schedule_id, travel_date, fare_class)
                if not available:
                    return False, "No available seats for this class."
                seat_id = available[0]["seat_id"]
            else:
                # 檢查指定座位是否已被搶走
                check_seat_sql = """
                    SELECT COUNT(*) FROM bookings 
                    WHERE schedule_id = %s AND travel_date = %s AND seat_id = %s AND status = 'completed';
                """
                cur.execute(check_seat_sql, (schedule_id, travel_date, seat_id))
                if cur.fetchone()["count"] > 0:
                    return False, f"Seat {seat_id} is already booked."

            # 2. 計算車資
            # 計算停靠站數
            sched_sql = "SELECT stops_in_order, first_train_time FROM national_rail_schedules WHERE schedule_id = %s;"
            cur.execute(sched_sql, (schedule_id,))
            sched_row = cur.fetchone()
            if not sched_row:
                return False, "Schedule not found."
            
            stops = sched_row["stops_in_order"]
            try:
                p1 = stops.index(origin_station_id)
                p2 = stops.index(destination_station_id)
                stops_travelled = abs(p2 - p1)
            except ValueError:
                return False, "Invalid origin or destination station for this schedule."

            fare_dict = query_national_rail_fare(schedule_id, fare_class, stops_travelled)
            if not fare_dict:
                return False, "Failed to calculate fare."
            amount = fare_dict["total_fare_usd"]

            # 3. 獲取車廂編號 (Coach)
            # 從 layouts 中尋找該 seat_id 對應的 coach
            coach_sql = """
                SELECT c.coach FROM national_rail_seat_layouts l,
                     jsonb_to_recordset(l.coaches) AS c(coach text, fare_class text, seats jsonb),
                     jsonb_to_recordset(c.seats) AS s(seat_id text)
                WHERE l.schedule_id = %s AND s.seat_id = %s LIMIT 1;
            """
            cur.execute(coach_sql, (schedule_id, seat_id))
            coach_row = cur.fetchone()
            coach = coach_row["coach"] if coach_row else "B"

            # 4. 生成 ID 並寫入 bookings
            new_booking_id = _gen_booking_id()
            departure_time = sched_row["first_train_time"] # 簡化以發車時間代表
            
            insert_booking = """
                INSERT INTO bookings (
                    booking_id, user_id, schedule_id, origin_station_id, destination_station_id,
                    travel_date, departure_time, ticket_type, fare_class, coach, seat_id,
                    stops_travelled, amount_usd, status, booked_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'completed', NOW())
                RETURNING *;
            """
            cur.execute(insert_booking, (
                new_booking_id, user_id, schedule_id, origin_station_id, destination_station_id,
                travel_date, departure_time, ticket_type, fare_class, coach, seat_id,
                stops_travelled, amount, amount
            ))
            booking_record = dict(cur.fetchone())

            # 5. 寫入 payments 金流表
            new_payment_id = _gen_payment_id()
            insert_payment = """
                INSERT INTO payments (payment_id, booking_id, amount_usd, method, status, paid_at)
                VALUES (%s, %s, %s, 'credit_card', 'paid', NOW());
            """
            cur.execute(insert_payment, (new_payment_id, new_booking_id, amount))

            conn.commit()
            if isinstance(booking_record.get("booked_at"), datetime):
                booking_record["booked_at"] = booking_record["booked_at"].isoformat()
            return True, booking_record

    except Exception as e:
        conn.rollback()
        return False, f"Database error: {str(e)}"
    finally:
        conn.close()


def execute_cancellation(booking_id: str, user_id: str) -> tuple[bool, dict | str]:
    """
    Cancel a national rail booking owned by the given user and issue a refund.
    """
    conn = psycopg2.connect(PG_DSN)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 1. 檢查該預訂是否存在且屬於該使用者
            sql = """
                SELECT b.*, s.service_type 
                FROM bookings b
                JOIN national_rail_schedules s ON b.schedule_id = s.schedule_id
                WHERE b.booking_id = %s AND b.user_id = %s;
            """
            cur.execute(sql, (booking_id, user_id))
            booking = cur.fetchone()
            if not booking:
                return False, "Booking not found or access denied."
            if booking["status"] == "cancelled":
                return False, "Booking is already cancelled."

            # 2. 計算退款比例 (根據退款規則比對乘車時間)
            # 題目提示：Normal service -> RF001, Express service -> RF002
            # 這裡計算現在到開車時間差了幾小時
            try:
                dept_str = f"{booking['travel_date']} {booking['departure_time']}"
                dept_time = datetime.strptime(dept_str, "%Y-%m-%d %H:%M")
                # 假設系統皆以在地或統一時區比對
                hours_until_departure = (dept_time - datetime.now()).total_seconds() / 3600.0
            except Exception:
                hours_until_departure = 50.0 # 格式錯誤時的防呆預設

            service_type = booking["service_type"]
            refund_percent = 0
            policy_note = ""

            if service_type == "normal":
                if hours_until_departure >= 48:
                    refund_percent = 100
                    policy_note = "RF001_W1: Early cancellation (100% refund)"
                elif hours_until_departure >= 24:
                    refund_percent = 75
                    policy_note = "RF001_W2: Standard cancellation (75% refund)"
                elif hours_until_departure >= 2:
                    refund_percent = 50
                    policy_note = "RF001_W3: Late cancellation (50% refund)"
                else:
                    refund_percent = 0
                    policy_note = "RF001_W4: Too close to departure (0% refund)"
            else: # express 快車規則
                if hours_until_departure >= 48:
                    refund_percent = 100
                    policy_note = "RF002_W1: Express early cancellation (100% refund)"
                elif hours_until_departure >= 24:
                    refund_percent = 50
                    policy_note = "RF002_W2: Express standard cancellation (50% refund)"
                else:
                    refund_percent = 0
                    policy_note = "RF002_W3: Express late cancellation (0% refund)"

            amount_paid = float(booking["amount_usd"])
            refund_amount = round(amount_paid * (refund_percent / 100.0), 2)

            # 3. 更新訂單狀態為 cancelled
            update_sql = "UPDATE bookings SET status = 'cancelled' WHERE booking_id = %s;"
            cur.execute(update_sql, (booking_id,))

            # 4. 更新付款紀錄狀態或新增退款紀錄
            update_pay_sql = "UPDATE payments SET status = 'refunded' WHERE booking_id = %s;"
            cur.execute(update_pay_sql, (booking_id,))

            conn.commit()
            return True, {
                "booking_id": booking_id,
                "refund_amount_usd": refund_amount,
                "policy_note": policy_note
            }
    except Exception as e:
        conn.rollback()
        return False, f"Database error: {str(e)}"
    finally:
        conn.close()


import os
import hashlib
from datetime import datetime
from typing import Optional
import psycopg2
import psycopg2.extras

# ── 安全輔助函式：密碼加鹽雜湊 ───────────────────────────────────────

def _hash_password(password: str, salt: str = None) -> tuple[str, str]:
    """
    對密碼進行加鹽雜湊。
    如果是註冊：不傳入 salt，會自動隨機生成一個新的 salt。
    如果是登入：傳入資料庫取出的 salt，計算雜湊值用來比對。
    Returns:
        tuple[str, str]: (salt_hex, hash_hex)
    """
    if salt is None:
        # 隨機生成 32 位元組（64個字元）的鹽，確保全球唯一且不可預測
        salt_bytes = os.urandom(32)
        salt = salt_bytes.hex()
    else:
        salt_bytes = bytes.fromhex(salt)
        
    # 將明文密碼轉成 bytes
    password_bytes = password.encode('utf-8')
    
    # 使用 SHA-256 進行加鹽雜湊 (Salt + Password)
    hasher = hashlib.sha256()
    hasher.update(salt_bytes)
    hasher.update(password_bytes)
    password_hash = hasher.hexdigest()
    
    return salt, password_hash


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
    安全註冊新使用者：將密碼 Hash 與基本資料分開儲存於不同資料表。
    """
    check_sql = "SELECT COUNT(*) FROM registered_users WHERE email = %s;"
    
    # 使用專案原本的連線函式，手動管理 Transaction 確保資料完整性
    conn = _connect()
    try:
        with conn.cursor() as cur:
            # 1. 檢查信箱是否重複
            cur.execute(check_sql, (email,))
            if cur.fetchone()[0] > 0:
                return False, "Email is already registered."

            # 2. 生成新的 user_id (依 mock 資料格式如 RU20)
            cur.execute("SELECT COUNT(*) FROM registered_users;")
            next_num = cur.fetchone()[0] + 1
            new_user_id = f"RU{next_num:02d}"
            
            full_name = f"{first_name} {surname}"
            dob = f"{year_of_birth}-01-01"  # 簡易拼湊生日
            
            # 3. 計算密碼的 Salt 和 Hash
            salt, password_hash = _hash_password(password)
            
            # 4. 寫入第一張表：使用者基本資料（已移除原本的 password 欄位）
            insert_user_sql = """
                INSERT INTO registered_users (
                    user_id, full_name, email, phone, date_of_birth,
                    secret_question, secret_answer, registered_at, is_active
                ) VALUES (%s, %s, %s, '', %s, %s, %s, NOW(), TRUE);
            """
            cur.execute(insert_user_sql, (
                new_user_id, full_name, email, dob, secret_question, secret_answer
            ))
            
            # 5. 寫入第二張表：獨立的安全憑證表 (儲存 Salt 與 Hash)
            insert_cred_sql = """
                INSERT INTO user_credentials (user_id, password_salt, password_hash, updated_at)
                VALUES (%s, %s, %s, NOW());
            """
            cur.execute(insert_cred_sql, (new_user_id, salt, password_hash))
            
            conn.commit()  # 確認兩張表都寫入成功，正式提交
            return True, new_user_id

    except Exception as e:
        conn.rollback()  # 發生任何錯誤就全部倒帶
        return False, f"Database error: {str(e)}"
    finally:
        conn.close()


def login_user(email: str, password: str) -> Optional[dict]:
    """
    安全登入驗證：從憑證表取出 Salt 重新計算 Hash，與資料庫中的 Hash 比對。
    Returns a user dict on success or None on failure.
    """
    # 使用 JOIN 將基本資料與憑證表串起來，取出使用者的加密資訊
    sql = """
        SELECT u.*, c.password_salt, c.password_hash
        FROM registered_users u
        JOIN user_credentials c ON u.user_id = c.user_id
        WHERE u.email = %s AND u.is_active = TRUE;
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (email,))
            row = cur.fetchone()
            if not row:
                return None  # 找不到該信箱的使用者
                
            user_dict = dict(row)
            
            # 取出資料庫儲存的 Salt 與原本的 Hash，並將它們從回傳字典中移除
            stored_salt = user_dict.pop("password_salt")
            stored_hash = user_dict.pop("password_hash")
            
            # 使用相同的 Salt 對使用者輸入的明文密碼重新進行 Hash 計算
            _, computed_hash = _hash_password(password, salt=stored_salt)
            
            # 比對計算後的 Hash 是否與資料庫吻合
            if computed_hash != stored_hash:
                return None  # 密碼錯誤
            
            # 密碼正確，整理回傳的資料格式，切割出 first_name 與 surname 滿足 Spec 需求
            names = user_dict["full_name"].split(" ", 1)
            user_dict["first_name"] = names[0]
            user_dict["surname"] = names[1] if len(names) > 1 else ""
            
            if isinstance(user_dict.get("registered_at"), datetime):
                user_dict["registered_at"] = user_dict["registered_at"].isoformat()
            if user_dict.get("date_of_birth"):
                user_dict["date_of_birth"] = str(user_dict["date_of_birth"])
                
            return user_dict


def get_user_secret_question(email: str) -> Optional[str]:
    """Return the secret question for a registered email, or None if not found."""
    sql = "SELECT secret_question FROM registered_users WHERE email = %s;"
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (email,))
            row = cur.fetchone()
            return row[0] if row else None


def verify_secret_answer(email: str, answer: str) -> bool:
    """Return True if the provided answer matches the stored secret answer (case-insensitive)."""
    sql = "SELECT secret_answer FROM registered_users WHERE email = %s;"
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (email,))
            row = cur.fetchone()
            if not row or not row[0]:
                return False
            return row[0].strip().lower() == answer.strip().lower()


def update_password(email: str, new_password: str) -> bool:
    """
    安全更新密碼：重新生成隨機的 Salt 與新的 Hash，並更新至憑證表。
    Returns True if the row was updated.
    """
    # 1. 先透過 email 找出使用者的 user_id
    find_user_sql = "SELECT user_id FROM registered_users WHERE email = %s;"
    
    # 2. 更新憑證表
    update_cred_sql = """
        UPDATE user_credentials 
        SET password_salt = %s, password_hash = %s, updated_at = NOW() 
        WHERE user_id = %s;
    """
    
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(find_user_sql, (email,))
            row = cur.fetchone()
            if not row:
                return False
            user_id = row[0]
            
            # 3. 為新密碼產生一組全新的 Salt 和 Hash（避免重複使用舊 Salt）
            new_salt, new_hash = _hash_password(new_password)
            
            # 4. 更新到 user_credentials 表中
            cur.execute(update_cred_sql, (new_salt, new_hash, user_id))
            
            conn.commit()
            return cur.rowcount > 0
            
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()

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
        travel_date:     e.g. "2025-06-01" — used to count bookings; omit for general info
    """
    raise NotImplementedError("TODO: implement after designing your schema")


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
    raise NotImplementedError("TODO: implement after designing your schema")


# ── METRO SCHEDULES & FARE ────────────────────────────────────────────────────

def query_metro_schedules(origin_id: str, destination_id: str) -> list[dict]:
    """
    Return metro schedules that serve both origin and destination in the correct order.

    Args:
        origin_id:       e.g. "MS01"
        destination_id:  e.g. "MS09"
    """
    raise NotImplementedError("TODO: implement after designing your schema")


def query_metro_fare(schedule_id: str, stops_travelled: int) -> Optional[dict]:
    """
    Calculate the metro fare for a single-ticket journey.

    Args:
        schedule_id:     e.g. "MS_SCH01"
        stops_travelled: number of stops between origin and destination

    Returns:
        dict with base_fare_usd, per_stop_rate_usd, total_fare_usd
    """
    raise NotImplementedError("TODO: implement after designing your schema")


# ── SEAT SELECTION ────────────────────────────────────────────────────────────

def query_available_seats(
    schedule_id: str,
    travel_date: str,
    fare_class: str,
) -> list[dict]:
    """
    Return available seats for a national rail journey on a given date.

    Args:
        schedule_id:  e.g. "NR_SCH01"
        travel_date:  e.g. "2025-06-01"
        fare_class:   "standard" or "first"

    Returns:
        List of dicts: {seat_id, coach, row, column}
    """
    raise NotImplementedError("TODO: implement after designing your schema")


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
    raise NotImplementedError("TODO: implement after designing your schema")


def query_user_bookings(user_email: str) -> dict:
    """
    Return a user's combined booking history (national rail + metro).

    Returns:
        dict with keys 'national_rail' (list) and 'metro' (list)
    """
    raise NotImplementedError("TODO: implement after designing your schema")


def query_payment_info(booking_id: str) -> Optional[dict]:
    """Return payment record for a booking or metro trip."""
    raise NotImplementedError("TODO: implement after designing your schema")


# ── TRANSACTIONAL OPERATIONS ──────────────────────────────────────────────────

def execute_booking(
    user_id: str,
    schedule_id: str,
    origin_station_id: str,
    destination_station_id: str,
    travel_date: str,
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
        fare_class:             "standard" or "first"
        seat_id:                e.g. "B05" (or "any" to auto-assign)
        ticket_type:            "single" (default) or "return"

    Returns:
        (True, booking_dict)   on success
        (False, error_message) on failure
    """
    raise NotImplementedError("TODO: implement after designing your schema")


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
    raise NotImplementedError("TODO: implement after designing your schema")


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

    NOTE: passwords are stored as plain text here intentionally for teaching
    purposes. In production, replace with a salted hash (e.g. bcrypt).
    """
    raise NotImplementedError("TODO: implement after designing your schema")


def login_user(email: str, password: str) -> Optional[dict]:
    """
    Verify credentials. Returns a user dict on success or None on failure.
    Dict keys: user_id, email, full_name, first_name, surname, phone, date_of_birth, is_active.
    """
    raise NotImplementedError("TODO: implement after designing your schema")


def get_user_secret_question(email: str) -> Optional[str]:
    """Return the secret question for a registered email, or None if not found."""
    raise NotImplementedError("TODO: implement after designing your schema")


def verify_secret_answer(email: str, answer: str) -> bool:
    """Return True if the provided answer matches the stored secret answer (case-insensitive)."""
    raise NotImplementedError("TODO: implement after designing your schema")


def update_password(email: str, new_password: str) -> bool:
    """Update the password for a user. Returns True if the row was updated."""
    raise NotImplementedError("TODO: implement after designing your schema")


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
