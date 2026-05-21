-- ============================================================
--  TransitFlow PostgreSQL Schema
--  Seed data is loaded separately by: python skeleton/seed_postgres.py
-- ============================================================

-- ============================================================
--  STUDENT TASK — Design and create your relational tables here
-- ============================================================

-- 1. 地鐵車站表
CREATE TABLE IF NOT EXISTS metro_stations (
    station_id VARCHAR(10) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    lines TEXT[] NOT NULL, -- 儲存該站所屬的多條地鐵線，例: {'M1', 'M2'}
    is_interchange_metro BOOLEAN DEFAULT FALSE,
    is_interchange_national_rail BOOLEAN DEFAULT FALSE,
    interchange_national_rail_station_id VARCHAR(10),
    adjacent_stations TEXT[] -- 鄰近車站代碼陣列
);

-- 2. 國鐵車站表
CREATE TABLE IF NOT EXISTS national_rail_stations (
    station_id VARCHAR(10) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    lines TEXT[] NOT NULL -- 儲存所屬國鐵線，例: {'NR1'}
);

-- 3. 地鐵時刻表
CREATE TABLE IF NOT EXISTS metro_schedules (
    schedule_id VARCHAR(10) PRIMARY KEY,
    line VARCHAR(10) NOT NULL, -- M1, M2, M3, M4 (配合 json 欄位名)
    direction VARCHAR(50) NOT NULL,
    origin_station_id VARCHAR(10) REFERENCES metro_stations(station_id),
    destination_station_id VARCHAR(10) REFERENCES metro_stations(station_id),
    stops_in_order TEXT[] NOT NULL,
    first_train_time TIME NOT NULL,
    last_train_time TIME NOT NULL,
    travel_time_from_origin_min JSONB NOT NULL, -- 各站距離起點的分鐘數
    base_fare_usd NUMERIC(5, 2) DEFAULT 0.80,
    per_stop_rate_usd NUMERIC(5, 2) DEFAULT 0.30,
    frequency_min INT NOT NULL,
    operates_on TEXT[] NOT NULL
);

-- 4. 國鐵時刻表
CREATE TABLE IF NOT EXISTS national_rail_schedules (
    schedule_id VARCHAR(10) PRIMARY KEY,
    line VARCHAR(10) NOT NULL,
    service_type VARCHAR(20) NOT NULL CHECK (service_type IN ('normal', 'express')),
    direction VARCHAR(50) NOT NULL,
    origin_station_id VARCHAR(10) REFERENCES national_rail_stations(station_id),
    destination_station_id VARCHAR(10) REFERENCES national_rail_stations(station_id),
    frequency_min INT NOT NULL,
    first_train_time TIME NOT NULL,
    last_train_time TIME NOT NULL,
    operates_on TEXT[] NOT NULL,
    stops_in_order TEXT[] NOT NULL,
    passed_through_stations TEXT[], -- 快車經過但不停靠的車站
    travel_time_from_origin_min JSONB NOT NULL,
    standard_base_fare NUMERIC(5, 2) DEFAULT 2.50,
    standard_per_stop_rate NUMERIC(5, 2) DEFAULT 1.50,
    first_base_fare NUMERIC(5, 2) DEFAULT 4.00,
    first_per_stop_rate NUMERIC(5, 2) DEFAULT 2.50,
    is_express_premium BOOLEAN DEFAULT FALSE
);

-- 5. 國鐵座位配置表 (僅適用於普通車次 SL01-SL04)
CREATE TABLE IF NOT EXISTS national_rail_seat_layouts (
    layout_id VARCHAR(10) NOT NULL,
    schedule_id VARCHAR(10) REFERENCES national_rail_schedules(schedule_id),
    coach VARCHAR(5) NOT NULL CHECK (coach IN ('A', 'B')), -- Coach A (First), Coach B (Standard)
    fare_class VARCHAR(20) NOT NULL CHECK (fare_class IN ('standard', 'first')),
    seat_id VARCHAR(5) NOT NULL, -- A01-A06, B01-B12
    "row" INT NOT NULL,
    "column" VARCHAR(2) NOT NULL,
    PRIMARY KEY (schedule_id, coach, seat_id)
);

-- 6. 註冊用戶表
CREATE TABLE IF NOT EXISTS registered_users (
    user_id VARCHAR(10) PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    first_name VARCHAR(50),
    surname VARCHAR(50),
    email VARCHAR(150) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    phone VARCHAR(30),
    date_of_birth DATE,
    secret_question VARCHAR(255),
    secret_answer VARCHAR(255),
    registered_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

-- 7. 國鐵訂票表
CREATE TABLE IF NOT EXISTS bookings (
    booking_id VARCHAR(10) PRIMARY KEY,
    user_id VARCHAR(10) REFERENCES registered_users(user_id),
    schedule_id VARCHAR(10) REFERENCES national_rail_schedules(schedule_id),
    origin_station_id VARCHAR(10) REFERENCES national_rail_stations(station_id),
    destination_station_id VARCHAR(10) REFERENCES national_rail_stations(station_id),
    travel_date DATE NOT NULL,
    departure_time TIME NOT NULL,
    ticket_type VARCHAR(20) NOT NULL CHECK (ticket_type IN ('single', 'return')),
    fare_class VARCHAR(20) NOT NULL CHECK (fare_class IN ('standard', 'first')),
    coach VARCHAR(5),
    seat_id VARCHAR(5),
    stops_travelled INT NOT NULL,
    amount_usd NUMERIC(6, 2) NOT NULL,
    status VARCHAR(20) NOT NULL CHECK (status IN ('completed', 'confirmed', 'cancelled')),
    booked_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    travelled_at TIMESTAMP WITH TIME ZONE
);

-- 8. 地鐵乘車紀錄表
CREATE TABLE IF NOT EXISTS metro_travel_history (
    trip_id VARCHAR(10) PRIMARY KEY,
    user_id VARCHAR(10) REFERENCES registered_users(user_id),
    schedule_id VARCHAR(10) REFERENCES metro_schedules(schedule_id),
    origin_station_id VARCHAR(10) REFERENCES metro_stations(station_id),
    destination_station_id VARCHAR(10) REFERENCES metro_stations(station_id),
    travel_date DATE NOT NULL,
    ticket_type VARCHAR(20) NOT NULL CHECK (ticket_type IN ('single', 'day_pass')),
    day_pass_ref VARCHAR(10) REFERENCES metro_travel_history(trip_id), -- 指向第一次買日票的紀錄
    stops_travelled INT,
    amount_usd NUMERIC(5, 2) NOT NULL DEFAULT 0.00,
    status VARCHAR(20) NOT NULL CHECK (status IN ('completed', 'in_progress', 'cancelled')),
    purchased_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    travelled_at TIMESTAMP WITH TIME ZONE
);

-- 9. 付款資料表 (多型關聯：booking_id 不設實體 FK 約束，允許填入 BK... 或 MT...)
CREATE TABLE IF NOT EXISTS payments (
    payment_id VARCHAR(10) PRIMARY KEY,
    booking_id VARCHAR(10) NOT NULL, 
    amount_usd NUMERIC(6, 2) NOT NULL,
    method VARCHAR(20) NOT NULL CHECK (method IN ('credit_card', 'debit_card', 'ewallet')),
    status VARCHAR(20) NOT NULL CHECK (status IN ('paid', 'refunded')),
    paid_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 10. 評價資料表 (多型關聯：booking_id 不設實體 FK 約束)
CREATE TABLE IF NOT EXISTS feedback (
    feedback_id VARCHAR(10) PRIMARY KEY,
    booking_id VARCHAR(10) NOT NULL, 
    user_id VARCHAR(10) REFERENCES registered_users(user_id),
    rating INT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment TEXT,
    submitted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 效能優化：常用索引
CREATE INDEX IF NOT EXISTS idx_users_email ON registered_users(email);
CREATE INDEX IF NOT EXISTS idx_bookings_user_date ON bookings(user_id, travel_date);
CREATE INDEX IF NOT EXISTS idx_bookings_status ON bookings(status);
CREATE INDEX IF NOT EXISTS idx_metro_travel_user_date ON metro_travel_history(user_id, travel_date);
CREATE INDEX IF NOT EXISTS idx_payments_booking_id ON payments(booking_id);
CREATE INDEX IF NOT EXISTS idx_feedback_booking_id ON feedback(booking_id);


-- ============================================================
--  VECTOR SCHEMA  (RAG / Help Desk) — do not modify
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS policy_documents (
    id          SERIAL       PRIMARY KEY,
    title       VARCHAR(200) NOT NULL,
    category    VARCHAR(50)  NOT NULL,  -- 'refund', 'booking', 'conduct'
    content     TEXT         NOT NULL,
    embedding   vector(768),
    source_file VARCHAR(200),
    created_at  TIMESTAMPTZ  DEFAULT NOW()
);

-- 修正版：明確指定索引名稱 idx_policy_embedding，避免 PostgreSQL 語法報錯
CREATE INDEX IF NOT EXISTS idx_policy_embedding ON policy_documents USING hnsw (embedding vector_cosine_ops);
