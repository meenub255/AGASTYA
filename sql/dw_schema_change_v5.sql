-- ==========================================
-- KIMBALL DATA WAREHOUSE SCHEMA
-- ==========================================

-- 1. Dimensions
CREATE TABLE IF NOT EXISTS dw.dim_date (
    date_id INT PRIMARY KEY,
    full_date DATE,
    day_of_week INT,
    day_name TEXT,
    day_of_month INT,
    month_name TEXT,
    month_actual INT,
    quarter_actual INT,
    year_actual INT,
    is_weekend BOOLEAN
);

CREATE TABLE IF NOT EXISTS dw.dim_geography (
    sk_geography_id SERIAL PRIMARY KEY,
    nk_area_id BIGINT,
    nk_region_id BIGINT,
    area_name TEXT,
    region_name TEXT,
    area_code TEXT,
    region_code TEXT,
    is_deleted BOOLEAN,
    dw_inserted_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dw.dim_user (
    sk_user_id SERIAL PRIMARY KEY,
    nk_user_id BIGINT,
    user_name TEXT,
    user_code TEXT,
    email TEXT,
    role_name TEXT,
    manager_name TEXT,
    joining_date TIMESTAMP,
    has_b_ed BOOLEAN,
    has_d_ed BOOLEAN,
    pg_degree TEXT,
    ug_degree TEXT,
    is_active BOOLEAN,
    dw_inserted_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dw.dim_school (
    sk_school_id SERIAL PRIMARY KEY,
    nk_school_id BIGINT,
    school_name TEXT,
    school_code TEXT,
    udise_code DOUBLE PRECISION,
    address TEXT,
    pincode DOUBLE PRECISION,
    school_type_name TEXT,
    school_category_id DOUBLE PRECISION,
    state_management_id DOUBLE PRECISION,
    is_deleted BOOLEAN,
    dw_inserted_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dw.dim_program (
    sk_program_id SERIAL PRIMARY KEY,
    nk_program_id BIGINT,
    program_name TEXT,
    donor_name TEXT,
    donor_code TEXT,
    start_date TIMESTAMP,
    end_date TIMESTAMP,
    instructor_capacity BIGINT,
    periodicity TEXT,
    is_deleted BOOLEAN,
    dw_inserted_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dw.dim_activity_type (
    sk_activity_type_id SERIAL PRIMARY KEY,
    nk_activity_type_id BIGINT,
    activity_code TEXT,
    activity_name TEXT,
    is_adhoc BOOLEAN,
    dw_inserted_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dw.dim_subject_topic (
    sk_subject_topic_id SERIAL PRIMARY KEY,
    nk_topic_id BIGINT,
    topic_description TEXT,
    subject_name TEXT,
    subject_code TEXT,
    dw_inserted_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Facts
CREATE TABLE IF NOT EXISTS dw.fact_session (
    sk_fact_session_id SERIAL PRIMARY KEY,
    date_id INT REFERENCES dw.dim_date(date_id),
    sk_user_id INT REFERENCES dw.dim_user(sk_user_id),
    sk_school_id INT REFERENCES dw.dim_school(sk_school_id),
    sk_program_id INT REFERENCES dw.dim_program(sk_program_id),
    sk_activity_type_id INT REFERENCES dw.dim_activity_type(sk_activity_type_id),
    sk_subject_topic_id INT REFERENCES dw.dim_subject_topic(sk_subject_topic_id),
    sk_geography_id INT REFERENCES dw.dim_geography(sk_geography_id),
    session_nk_id BIGINT,
    demo_session_count INT,
    hands_on_session_count INT,
    session_duration_minutes INT,
    no_of_teachers_participated INT,
    no_of_models_displayed INT,
    community_men_count INT,
    community_women_count INT,
    is_overdue BOOLEAN,
    dw_inserted_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dw.fact_attendance_exposure (
    sk_fact_attendance_exposure_id SERIAL PRIMARY KEY,
    date_id INT REFERENCES dw.dim_date(date_id),
    sk_user_id INT REFERENCES dw.dim_user(sk_user_id),
    sk_school_id INT REFERENCES dw.dim_school(sk_school_id),
    sk_program_id INT REFERENCES dw.dim_program(sk_program_id),
    sk_geography_id INT REFERENCES dw.dim_geography(sk_geography_id),
    session_nk_id BIGINT,
    class_name TEXT,
    section_name TEXT,
    boys_count INT,
    girls_count INT,
    total_exposure_count INT,
    dw_inserted_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dw.fact_vehicle_operations (
    sk_fact_vehicle_operations_id SERIAL PRIMARY KEY,
    date_id INT REFERENCES dw.dim_date(date_id),
    sk_user_id INT REFERENCES dw.dim_user(sk_user_id),
    sk_instructor_id INT REFERENCES dw.dim_user(sk_user_id),
    sk_driver_id INT REFERENCES dw.dim_user(sk_user_id),
    sk_program_id INT REFERENCES dw.dim_program(sk_program_id),
    sk_geography_id INT REFERENCES dw.dim_geography(sk_geography_id),
    vehicle_nk_id BIGINT,
    distance_travelled DOUBLE PRECISION,
    fuel_quantity DOUBLE PRECISION,
    fuel_cost DOUBLE PRECISION,
    was_vehicle_used BOOLEAN,
    dw_inserted_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
