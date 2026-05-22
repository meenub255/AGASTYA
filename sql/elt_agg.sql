-- [ELT] elt_agg.sql
-- Description: Precomputed aggregate tables for performance.
-- Summary: Rollups of metrics by month, region, and instructor.

SET search_path TO dw;

--------------------------------------------------------------------------------
-- 1. AGG_INSTRUCTOR_MONTHLY_SUMMARY
--------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dw.agg_instructor_monthly_summary (
    sk_user_id INT REFERENCES dw.dim_user(sk_user_id),
    year_actual INTEGER,
    month_actual INTEGER,
    total_sessions INTEGER DEFAULT 0,
    total_exposures BIGINT DEFAULT 0,
    total_distance_travelled DOUBLE PRECISION DEFAULT 0,
    is_deleted BOOLEAN DEFAULT FALSE,
    last_updated TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

TRUNCATE TABLE dw.agg_instructor_monthly_summary;
INSERT INTO dw.agg_instructor_monthly_summary (sk_user_id, year_actual, month_actual, total_sessions, total_exposures, total_distance_travelled)
SELECT 
    f.sk_user_id,
    d.year_actual,
    d.month_actual,
    COUNT(DISTINCT f.sk_fact_session_id) as total_sessions,
    SUM(COALESCE(fa.total_exposure_count, 0)) as total_exposures,
    SUM(COALESCE(fv.distance_travelled, 0)) as total_distance_travelled
FROM dw.fact_session f
JOIN dw.dim_date d ON f.date_id = d.date_id
LEFT JOIN dw.fact_attendance_exposure fa ON f.session_nk_id = fa.session_nk_id
LEFT JOIN dw.fact_vehicle_operations fv ON f.sk_user_id = fv.sk_user_id AND f.date_id = fv.date_id
GROUP BY f.sk_user_id, d.year_actual, d.month_actual;

--------------------------------------------------------------------------------
-- 2. AGG_GEOGRAPHY_DAILY_METRICS
--------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dw.agg_geography_daily_metrics (
    sk_geography_id INT REFERENCES dw.dim_geography(sk_geography_id),
    date_id INTEGER REFERENCES dw.dim_date(date_id),
    session_count INTEGER DEFAULT 0,
    exposure_count BIGINT DEFAULT 0,
    instructor_count INTEGER DEFAULT 0,
    school_count INTEGER DEFAULT 0,
    last_updated TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

TRUNCATE TABLE dw.agg_geography_daily_metrics;
INSERT INTO dw.agg_geography_daily_metrics (sk_geography_id, date_id, session_count, exposure_count, instructor_count, school_count)
SELECT 
    f.sk_geography_id,
    f.date_id,
    COUNT(DISTINCT f.sk_fact_session_id) as session_count,
    SUM(COALESCE(fa.total_exposure_count, 0)) as exposure_count,
    COUNT(DISTINCT f.sk_user_id) as instructor_count,
    COUNT(DISTINCT f.sk_school_id) as school_count
FROM dw.fact_session f
LEFT JOIN dw.fact_attendance_exposure fa ON f.session_nk_id = fa.session_nk_id
GROUP BY f.sk_geography_id, f.date_id;

--------------------------------------------------------------------------------
-- 3. AGG_PROGRAM_PERFORMANCE
--------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dw.agg_program_performance (
    sk_program_id INT REFERENCES dw.dim_program(sk_program_id),
    total_sessions_completed INTEGER DEFAULT 0,
    total_exposures_achieved BIGINT DEFAULT 0,
    active_instructors INTEGER DEFAULT 0,
    participating_schools INTEGER DEFAULT 0,
    last_updated TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

TRUNCATE TABLE dw.agg_program_performance;
INSERT INTO dw.agg_program_performance (sk_program_id, total_sessions_completed, total_exposures_achieved, active_instructors, participating_schools)
SELECT 
    f.sk_program_id,
    COUNT(DISTINCT f.sk_fact_session_id) as total_sessions_completed,
    SUM(COALESCE(fa.total_exposure_count, 0)) as total_exposures_achieved,
    COUNT(DISTINCT f.sk_user_id) as active_instructors,
    COUNT(DISTINCT f.sk_school_id) as participating_schools
FROM dw.fact_session f
LEFT JOIN dw.fact_attendance_exposure fa ON f.session_nk_id = fa.session_nk_id
GROUP BY f.sk_program_id;
