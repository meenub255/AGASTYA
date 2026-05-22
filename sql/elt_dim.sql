-- [ELT] elt_dim.sql
-- Description: Dimension loading logic (SCD Type 1).
-- Includes Date Dimension generation and transformation logic.

SET search_path TO dw, source;

--------------------------------------------------------------------------------
-- 1. DIM_DATE (Calendar Generation)
--------------------------------------------------------------------------------
TRUNCATE TABLE dw.dim_date CASCADE;
INSERT INTO dw.dim_date (date_id, full_date, day_of_week, day_name, day_of_month, month_name, month_actual, quarter_actual, year_actual, is_weekend)
SELECT 
    CAST(TO_CHAR(datum, 'YYYYMMDD') AS INT) AS date_id,
    datum AS full_date,
    EXTRACT(DOW FROM datum) + 1 AS day_of_week,
    TO_CHAR(datum, 'Day') AS day_name,
    EXTRACT(DAY FROM datum) AS day_of_month,
    TO_CHAR(datum, 'Month') AS month_name,
    EXTRACT(MONTH FROM datum) AS month_actual,
    EXTRACT(QUARTER FROM datum) AS quarter_actual,
    EXTRACT(YEAR FROM datum) AS year_actual,
    CASE WHEN EXTRACT(DOW FROM datum) IN (0, 6) THEN TRUE ELSE FALSE END AS is_weekend
FROM generate_series('2010-01-01'::DATE, '2030-12-31'::DATE, '1 day'::INTERVAL) AS datum;

--------------------------------------------------------------------------------
-- 2. DIM_GEOGRAPHY (Area + Region)
--------------------------------------------------------------------------------
TRUNCATE TABLE dw.dim_geography CASCADE;
INSERT INTO dw.dim_geography (nk_area_id, nk_region_id, area_name, region_name, area_code, region_code, is_deleted)
SELECT 
    CASE WHEN a.mst_area_id ~ '^[0-9]+$' THEN a.mst_area_id::BIGINT ELSE NULL END as nk_area_id,
    CASE WHEN r.mst_region_id ~ '^[0-9]+$' THEN r.mst_region_id::BIGINT ELSE NULL END as nk_region_id,
    a.name as area_name,
    r.name as region_name,
    a.code as area_code,
    r.code as region_code,
    COALESCE(CASE WHEN a.is_deleted ~ '^[0-9]+$' THEN a.is_deleted::INT ELSE 0 END = 1, false) OR 
    COALESCE(CASE WHEN r.is_deleted ~ '^[0-9]+$' THEN r.is_deleted::INT ELSE 0 END = 1, false)
FROM source.mst_area a
JOIN source.mst_region r ON (CASE WHEN a.region_id ~ '^[0-9]+$' THEN a.region_id::BIGINT ELSE NULL END) = (CASE WHEN r.mst_region_id ~ '^[0-9]+$' THEN r.mst_region_id::BIGINT ELSE NULL END);

--------------------------------------------------------------------------------
-- 3. DIM_USER (SCD Type 1)
--------------------------------------------------------------------------------
TRUNCATE TABLE dw.dim_user CASCADE;
INSERT INTO dw.dim_user (nk_user_id, user_name, user_code, email, role_name, manager_name, joining_date, has_b_ed, has_d_ed, pg_degree, ug_degree, is_active)
SELECT 
    CASE WHEN u.mst_user_id ~ '^[0-9]+$' THEN u.mst_user_id::BIGINT ELSE NULL END as nk_user_id,
    u.name as user_name,
    u.code as user_code,
    u.email,
    r.name as role_name,
    m.name as manager_name,
    CASE WHEN u.joining_date ~ '^[12][0-9]{3}-[01][0-9]-[0-3][0-9]' THEN u.joining_date::TIMESTAMP ELSE NULL END,
    CASE WHEN u.has_b_ed_degree ~ '^[0-9]+$' THEN u.has_b_ed_degree::INT ELSE 0 END = 1,
    CASE WHEN u.has_d_ed_degree ~ '^[0-9]+$' THEN u.has_d_ed_degree::INT ELSE 0 END = 1,
    u.pg_degree,
    u.ug_degree,
    CASE WHEN u.is_deleted ~ '^[0-9]+$' THEN u.is_deleted::INT ELSE 1 END = 0 as is_active
FROM source.mst_user u
LEFT JOIN source.mst_role r ON (CASE WHEN u.role_id ~ '^[0-9]+$' THEN u.role_id::BIGINT ELSE NULL END) = (CASE WHEN r.mst_role_id ~ '^[0-9]+$' THEN r.mst_role_id::BIGINT ELSE NULL END)
LEFT JOIN source.mst_user m ON (CASE WHEN u.report_id ~ '^[0-9]+$' THEN u.report_id::BIGINT ELSE NULL END) = (CASE WHEN m.mst_user_id ~ '^[0-9]+$' THEN m.mst_user_id::BIGINT ELSE NULL END);

--------------------------------------------------------------------------------
-- 4. DIM_SCHOOL
--------------------------------------------------------------------------------
TRUNCATE TABLE dw.dim_school CASCADE;
INSERT INTO dw.dim_school (nk_school_id, school_name, school_code, udise_code, address, pincode, school_type_name, school_category_id, state_management_id, is_deleted)
SELECT 
    CASE WHEN s.mst_school_id ~ '^[0-9]+$' THEN s.mst_school_id::BIGINT ELSE NULL END as nk_school_id,
    s.name as school_name,
    s.code as school_code,
    CASE WHEN s.udise_code ~ '^[0-9\.]+$' THEN s.udise_code::DOUBLE PRECISION ELSE 0 END,
    s.address,
    CASE WHEN s.pincode ~ '^[0-9\.]+$' THEN s.pincode::DOUBLE PRECISION ELSE 0 END,
    st.name as school_type_name,
    CASE WHEN s.school_category ~ '^[0-9\.]+$' THEN s.school_category::DOUBLE PRECISION ELSE 0 END as school_category_id,
    CASE WHEN s.state_management ~ '^[0-9\.]+$' THEN s.state_management::DOUBLE PRECISION ELSE 0 END as state_management_id,
    CASE WHEN s.is_deleted ~ '^[0-9]+$' THEN s.is_deleted::INT ELSE 0 END = 1
FROM source.mst_school s
LEFT JOIN source.mst_school_type st ON (CASE WHEN s.school_type ~ '^[0-9]+$' THEN s.school_type::BIGINT ELSE NULL END) = (CASE WHEN st.mst_school_type_id ~ '^[0-9]+$' THEN st.mst_school_type_id::BIGINT ELSE NULL END);

-- 4b. Add Pseudo Schools from adhoc villages that don't match any real school
INSERT INTO dw.dim_school (nk_school_id, school_name, school_code, is_deleted)
SELECT 
    (9000000 + row_number() over ()) as nk_school_id,
    v.village as school_name,
    'VIRTUAL' as school_code,
    false as is_deleted
FROM (
    SELECT DISTINCT village 
    FROM source.rpt_adhoc_feedback 
    WHERE village IS NOT NULL AND village != ''
    AND LOWER(TRIM(village)) NOT IN (SELECT LOWER(TRIM(name)) FROM source.mst_school WHERE name IS NOT NULL)
) v;

--------------------------------------------------------------------------------
-- 5. DIM_PROGRAM
--------------------------------------------------------------------------------
TRUNCATE TABLE dw.dim_program CASCADE;
INSERT INTO dw.dim_program (nk_program_id, program_name, donor_name, donor_code, start_date, end_date, instructor_capacity, periodicity, is_deleted)
SELECT 
    CASE WHEN p.txn_program_id ~ '^[0-9]+$' THEN p.txn_program_id::BIGINT ELSE NULL END as nk_program_id,
    p.name as program_name,
    d.name as donor_name,
    d.code as donor_code,
    CASE WHEN p.start_date ~ '^[12][0-9]{3}-[01][0-9]-[0-3][0-9]' THEN p.start_date::TIMESTAMP ELSE NULL END,
    CASE WHEN p.end_date ~ '^[12][0-9]{3}-[01][0-9]-[0-3][0-9]' THEN p.end_date::TIMESTAMP ELSE NULL END,
    CASE WHEN p.instructor_capacity ~ '^[0-9]+$' THEN p.instructor_capacity::BIGINT ELSE 0 END,
    CAST(p.periodicity_id AS TEXT), 
    CASE WHEN p.is_deleted ~ '^[0-9]+$' THEN p.is_deleted::INT ELSE 0 END = 1
FROM source.txn_program p
LEFT JOIN source.mst_donor d ON (CASE WHEN p.donor_id ~ '^[0-9]+$' THEN p.donor_id::BIGINT ELSE NULL END) = (CASE WHEN d.mst_donor_id ~ '^[0-9]+$' THEN d.mst_donor_id::BIGINT ELSE NULL END);

--------------------------------------------------------------------------------
-- 6. DIM_ACTIVITY_TYPE
--------------------------------------------------------------------------------
TRUNCATE TABLE dw.dim_activity_type CASCADE;
INSERT INTO dw.dim_activity_type (nk_activity_type_id, activity_code, activity_name, is_adhoc)
SELECT 
    CASE WHEN mst_activity_type_id ~ '^[0-9]+$' THEN mst_activity_type_id::BIGINT ELSE NULL END as nk_activity_type_id,
    code as activity_code,
    name as activity_name,
    CASE WHEN is_adhoc ~ '^[0-9]+$' THEN is_adhoc::INT ELSE 0 END = 1
FROM source.mst_activity_type;

--------------------------------------------------------------------------------
-- 7. DIM_SUBJECT_TOPIC
--------------------------------------------------------------------------------
TRUNCATE TABLE dw.dim_subject_topic CASCADE;
INSERT INTO dw.dim_subject_topic (nk_topic_id, topic_description, subject_name, subject_code)
SELECT 
    CASE WHEN t.mst_topic_id ~ '^[0-9]+$' THEN t.mst_topic_id::BIGINT ELSE NULL END as nk_topic_id,
    t.description as topic_description,
    s.name as subject_name,
    s.code as subject_code
FROM source.mst_topic t
LEFT JOIN source.mst_subject s ON (CASE WHEN t.subject_id ~ '^[0-9]+$' THEN t.subject_id::BIGINT ELSE NULL END) = (CASE WHEN s.mst_subject_id ~ '^[0-9]+$' THEN s.mst_subject_id::BIGINT ELSE NULL END);
