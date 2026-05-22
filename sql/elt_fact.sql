-- [ELT] elt_fact.sql
-- Description: Fact table loading logic.
-- Populates measures and lookups surrogate keys from dimensions.

SET search_path TO dw, source;

--------------------------------------------------------------------------------
-- 1. FACT_SESSION (Measures from TXN_SESSION + RPT_FEEDBACK + RPT_ADHOC_FEEDBACK)
--------------------------------------------------------------------------------
TRUNCATE TABLE dw.fact_session CASCADE;

-- A. Sessions from TXN_SESSION
INSERT INTO dw.fact_session (
    date_id, sk_user_id, sk_school_id, sk_program_id, sk_activity_type_id, 
    sk_subject_topic_id, sk_geography_id, session_nk_id, 
    demo_session_count, hands_on_session_count, session_duration_minutes, 
    no_of_teachers_participated, no_of_models_displayed, 
    community_men_count, community_women_count, is_overdue
)
SELECT 
    d.date_id, 
    u.sk_user_id, 
    COALESCE(s.sk_school_id, s_direct.sk_school_id) as sk_school_id, 
    COALESCE(p.sk_program_id, pi.sk_program_id) as sk_program_id,
    at.sk_activity_type_id,
    st.sk_subject_topic_id,
    COALESCE(gs.sk_geography_id, gi.sk_geography_id) as sk_geography_id,
    CASE WHEN ts.txn_session_id ~ '^[0-9]+$' THEN ts.txn_session_id::BIGINT ELSE NULL END as session_nk_id,
    COALESCE(CASE WHEN rf.demo_session ~ '^[0-9\.]+$' THEN rf.demo_session::DOUBLE PRECISION::INT ELSE NULL END, 0) as demo_session_count,
    COALESCE(CASE WHEN rf.hands_on_session ~ '^[0-9\.]+$' THEN rf.hands_on_session::DOUBLE PRECISION::INT ELSE NULL END, 0) as hands_on_session_count,
    COALESCE(CASE WHEN rf.session_duration ~ '^[0-9\.]+$' THEN rf.session_duration::DOUBLE PRECISION::INT ELSE NULL END, 0) as session_duration_minutes,
    COALESCE(CASE WHEN rf.no_of_teachers ~ '^[0-9\.]+$' THEN rf.no_of_teachers::DOUBLE PRECISION::INT ELSE NULL END, 0) as no_of_teachers_participated,
    COALESCE(CASE WHEN rf.no_of_model_displayed ~ '^[0-9\.]+$' THEN rf.no_of_model_displayed::DOUBLE PRECISION::INT ELSE NULL END, 0) as no_of_models_displayed,
    COALESCE(CASE WHEN rf.no_of_men ~ '^[0-9\.]+$' THEN rf.no_of_men::DOUBLE PRECISION::INT ELSE NULL END, 0) as community_men_count,
    COALESCE(CASE WHEN rf.no_of_women ~ '^[0-9\.]+$' THEN rf.no_of_women::DOUBLE PRECISION::INT ELSE NULL END, 0) as community_women_count,
    COALESCE(NULLIF(ts.is_overdue, ''), '0')::INT = 1
FROM source.txn_session ts
LEFT JOIN dw.dim_date d ON COALESCE(
    CASE WHEN ts.date ~ '^[12][0-9]{3}-[01][0-9]-(0[1-9]|[12][0-9]|3[01])' THEN ts.date::DATE ELSE NULL END, 
    CASE WHEN ts.created_on ~ '^[12][0-9]{3}-[01][0-9]-(0[1-9]|[12][0-9]|3[01])' THEN ts.created_on::DATE ELSE NULL END
)::DATE = d.full_date
LEFT JOIN dw.dim_user u ON (CASE WHEN ts.instructor_id ~ '^[0-9]+$' THEN ts.instructor_id::BIGINT ELSE NULL END) = u.nk_user_id
LEFT JOIN source.conf_program_school_mapping cpsm ON (CASE WHEN ts.program_school_mapped_id ~ '^[0-9]+$' THEN ts.program_school_mapped_id::BIGINT ELSE NULL END) = (CASE WHEN cpsm.conf_program_school_mapping_id ~ '^[0-9]+$' THEN cpsm.conf_program_school_mapping_id::BIGINT ELSE NULL END)
LEFT JOIN dw.dim_school s ON (CASE WHEN cpsm.school_id ~ '^[0-9]+$' THEN cpsm.school_id::BIGINT ELSE NULL END) = s.nk_school_id
LEFT JOIN dw.dim_school s_direct ON (CASE WHEN ts.program_school_mapped_id ~ '^[0-9]+$' THEN ts.program_school_mapped_id::BIGINT ELSE NULL END) = s_direct.nk_school_id
LEFT JOIN dw.dim_program p ON (CASE WHEN cpsm.program_id ~ '^[0-9]+$' THEN cpsm.program_id::BIGINT ELSE NULL END) = p.nk_program_id
LEFT JOIN dw.dim_activity_type at ON (CASE WHEN cpsm.activity_type_id ~ '^[0-9]+$' THEN cpsm.activity_type_id::BIGINT ELSE NULL END) = at.nk_activity_type_id
LEFT JOIN source.rpt_feedback rf ON (CASE WHEN ts.txn_session_id ~ '^[0-9]+$' THEN ts.txn_session_id::BIGINT ELSE NULL END) = (CASE WHEN rf.session_id ~ '^[0-9]+$' THEN rf.session_id::BIGINT ELSE NULL END)
LEFT JOIN dw.dim_subject_topic st ON (CASE WHEN rf.topic_id ~ '^[0-9]+$' THEN rf.topic_id::BIGINT ELSE NULL END) = st.nk_topic_id
LEFT JOIN source.mst_school ms ON COALESCE((CASE WHEN cpsm.school_id ~ '^[0-9]+$' THEN cpsm.school_id::BIGINT ELSE NULL END), (CASE WHEN ts.program_school_mapped_id ~ '^[0-9]+$' THEN ts.program_school_mapped_id::BIGINT ELSE NULL END)) = (CASE WHEN ms.mst_school_id ~ '^[0-9]+$' THEN ms.mst_school_id::BIGINT ELSE NULL END)
LEFT JOIN dw.dim_geography gs ON (CASE WHEN ms.area_id ~ '^[0-9]+$' THEN ms.area_id::BIGINT ELSE NULL END) = gs.nk_area_id
LEFT JOIN source.mst_user mu ON (CASE WHEN ts.instructor_id ~ '^[0-9]+$' THEN ts.instructor_id::BIGINT ELSE NULL END) = (CASE WHEN mu.mst_user_id ~ '^[0-9]+$' THEN mu.mst_user_id::BIGINT ELSE NULL END)
LEFT JOIN dw.dim_geography gi ON (CASE WHEN mu.area_id ~ '^[0-9]+$' THEN mu.area_id::BIGINT ELSE NULL END) = gi.nk_area_id
LEFT JOIN dw.dim_program pi ON (CASE WHEN mu.base_program_id ~ '^[0-9]+$' THEN mu.base_program_id::BIGINT ELSE NULL END) = pi.nk_program_id;

-- B. Sessions from RPT_ADHOC_FEEDBACK (Primary source for historical 4-year data)
INSERT INTO dw.fact_session (
    date_id, sk_user_id, sk_school_id, sk_program_id, sk_activity_type_id, 
    sk_subject_topic_id, sk_geography_id, session_nk_id, 
    demo_session_count, hands_on_session_count, session_duration_minutes, 
    no_of_teachers_participated, no_of_models_displayed, 
    community_men_count, community_women_count, is_overdue
)
SELECT 
    d.date_id,
    u.sk_user_id,
    COALESCE(s_loc.sk_school_id, s_village.sk_school_id) as sk_school_id, 
    COALESCE(p.sk_program_id, pi.sk_program_id) as sk_program_id,
    at.sk_activity_type_id,
    st.sk_subject_topic_id,
    COALESCE(s_loc_geo.sk_geography_id, s_village_geo.sk_geography_id, gi.sk_geography_id) as sk_geography_id,
    (CASE WHEN ra.adhoc_id ~ '^[0-9]+$' THEN ra.adhoc_id::BIGINT ELSE NULL END) + 1000000 as session_nk_id, 
    COALESCE(CASE WHEN ra.no_of_model_demonstrated ~ '^[0-9\.]+$' THEN ra.no_of_model_demonstrated::DOUBLE PRECISION::INT ELSE NULL END, 0) as demo_session_count,
    0 as hands_on_session_count,
    COALESCE(CASE WHEN ra.session_duration_id ~ '^[0-9\.]+$' THEN ra.session_duration_id::DOUBLE PRECISION::INT ELSE NULL END, 0) as session_duration_minutes,
    0 as no_of_teachers_participated,
    COALESCE(CASE WHEN ra.no_of_model_demonstrated ~ '^[0-9\.]+$' THEN ra.no_of_model_demonstrated::DOUBLE PRECISION::INT ELSE NULL END, 0) as no_of_models_displayed,
    COALESCE(CASE WHEN ra.no_of_men ~ '^[0-9\.]+$' THEN ra.no_of_men::DOUBLE PRECISION::INT ELSE NULL END, 0) as community_men_count,
    COALESCE(CASE WHEN ra.no_of_women ~ '^[0-9\.]+$' THEN ra.no_of_women::DOUBLE PRECISION::INT ELSE NULL END, 0) as community_women_count,
    false as is_overdue
FROM source.rpt_adhoc_feedback ra
JOIN dw.dim_date d ON (CASE WHEN ra.date ~ '^[12][0-9]{3}-[01][0-9]-(0[1-9]|[12][0-9]|3[01])' THEN ra.date::DATE ELSE NULL END) = d.full_date
LEFT JOIN dw.dim_user u ON (CASE WHEN ra.instructor_id ~ '^[0-9]+$' THEN ra.instructor_id::BIGINT ELSE NULL END) = u.nk_user_id
LEFT JOIN dw.dim_program p ON (CASE WHEN ra.program_id ~ '^[0-9]+$' THEN ra.program_id::BIGINT ELSE NULL END) = p.nk_program_id
LEFT JOIN dw.dim_activity_type at ON (CASE WHEN ra.activity_type_id ~ '^[0-9]+$' THEN ra.activity_type_id::BIGINT ELSE NULL END) = at.nk_activity_type_id
LEFT JOIN dw.dim_subject_topic st ON (CASE WHEN ra.topic_id ~ '^[0-9]+$' THEN ra.topic_id::BIGINT ELSE NULL END) = st.nk_topic_id
LEFT JOIN dw.dim_school s_loc ON (CASE WHEN ra.location_id ~ '^[0-9]+$' THEN ra.location_id::BIGINT ELSE NULL END) = s_loc.nk_school_id
LEFT JOIN source.mst_school ms_loc ON (CASE WHEN ra.location_id ~ '^[0-9]+$' THEN ra.location_id::BIGINT ELSE NULL END) = (CASE WHEN ms_loc.mst_school_id ~ '^[0-9]+$' THEN ms_loc.mst_school_id::BIGINT ELSE NULL END)
LEFT JOIN dw.dim_geography s_loc_geo ON (CASE WHEN ms_loc.area_id ~ '^[0-9]+$' THEN ms_loc.area_id::BIGINT ELSE NULL END) = s_loc_geo.nk_area_id
LEFT JOIN (SELECT DISTINCT ON (LOWER(TRIM(school_name))) sk_school_id, school_name, nk_school_id FROM dw.dim_school) s_village ON LOWER(TRIM(ra.village)) = LOWER(TRIM(s_village.school_name))
LEFT JOIN source.mst_school ms_village ON s_village.nk_school_id = (CASE WHEN ms_village.mst_school_id ~ '^[0-9]+$' THEN ms_village.mst_school_id::BIGINT ELSE NULL END)
LEFT JOIN dw.dim_geography s_village_geo ON (CASE WHEN ms_village.area_id ~ '^[0-9]+$' THEN ms_village.area_id::BIGINT ELSE NULL END) = s_village_geo.nk_area_id
LEFT JOIN source.mst_user mu ON (CASE WHEN ra.instructor_id ~ '^[0-9]+$' THEN ra.instructor_id::BIGINT ELSE NULL END) = (CASE WHEN mu.mst_user_id ~ '^[0-9]+$' THEN mu.mst_user_id::BIGINT ELSE NULL END)
LEFT JOIN dw.dim_geography gi ON (CASE WHEN mu.area_id ~ '^[0-9]+$' THEN mu.area_id::BIGINT ELSE NULL END) = gi.nk_area_id
LEFT JOIN dw.dim_program pi ON (CASE WHEN mu.base_program_id ~ '^[0-9]+$' THEN mu.base_program_id::BIGINT ELSE NULL END) = pi.nk_program_id
WHERE ra.adhoc_id ~ '^[0-9]+$';

--------------------------------------------------------------------------------
-- 2. FACT_ATTENDANCE_EXPOSURE
--------------------------------------------------------------------------------
TRUNCATE TABLE dw.fact_attendance_exposure CASCADE;
INSERT INTO dw.fact_attendance_exposure (
    date_id, sk_user_id, sk_school_id, sk_program_id, sk_geography_id, 
    session_nk_id, class_name, section_name, boys_count, girls_count, total_exposure_count
)
SELECT 
    d.date_id,
    u.sk_user_id,
    COALESCE(s.sk_school_id, s_direct.sk_school_id) as sk_school_id,
    COALESCE(p.sk_program_id, pi.sk_program_id) as sk_program_id,
    COALESCE(gs.sk_geography_id, gi.sk_geography_id) as sk_geography_id,
    CASE WHEN tfe.session_id ~ '^[0-9]+$' THEN tfe.session_id::BIGINT ELSE NULL END as session_nk_id,
    mc.name as class_name,
    tfe.section as section_name,
    COALESCE(CASE WHEN tfe.boys ~ '^[0-9]+$' THEN tfe.boys::INT ELSE NULL END, 0) as boys_count,
    COALESCE(CASE WHEN tfe.girls ~ '^[0-9]+$' THEN tfe.girls::INT ELSE NULL END, 0) as girls_count,
    COALESCE(CASE WHEN tfe.boys ~ '^[0-9]+$' THEN tfe.boys::INT ELSE NULL END, 0) + COALESCE(CASE WHEN tfe.girls ~ '^[0-9]+$' THEN tfe.girls::INT ELSE NULL END, 0) as total_exposure_count
FROM source.txn_feedback_exposure tfe
JOIN source.txn_session ts ON (CASE WHEN tfe.session_id ~ '^[0-9]+$' THEN tfe.session_id::BIGINT ELSE NULL END) = (CASE WHEN ts.txn_session_id ~ '^[0-9]+$' THEN ts.txn_session_id::BIGINT ELSE NULL END)
LEFT JOIN dw.dim_date d ON COALESCE(
    CASE WHEN ts.date ~ '^[12][0-9]{3}-[01][0-9]-(0[1-9]|[12][0-9]|3[01])' THEN ts.date::DATE ELSE NULL END, 
    CASE WHEN ts.created_on ~ '^[12][0-9]{3}-[01][0-9]-(0[1-9]|[12][0-9]|3[01])' THEN ts.created_on::DATE ELSE NULL END
)::DATE = d.full_date
LEFT JOIN dw.dim_user u ON (CASE WHEN ts.instructor_id ~ '^[0-9]+$' THEN ts.instructor_id::BIGINT ELSE NULL END) = u.nk_user_id
LEFT JOIN source.conf_program_school_mapping cpsm ON (CASE WHEN ts.program_school_mapped_id ~ '^[0-9]+$' THEN ts.program_school_mapped_id::BIGINT ELSE NULL END) = (CASE WHEN cpsm.conf_program_school_mapping_id ~ '^[0-9]+$' THEN cpsm.conf_program_school_mapping_id::BIGINT ELSE NULL END)
LEFT JOIN dw.dim_school s ON (CASE WHEN cpsm.school_id ~ '^[0-9]+$' THEN cpsm.school_id::BIGINT ELSE NULL END) = s.nk_school_id
LEFT JOIN dw.dim_school s_direct ON (CASE WHEN ts.program_school_mapped_id ~ '^[0-9]+$' THEN ts.program_school_mapped_id::BIGINT ELSE NULL END) = s_direct.nk_school_id
LEFT JOIN dw.dim_program p ON (CASE WHEN cpsm.program_id ~ '^[0-9]+$' THEN cpsm.program_id::BIGINT ELSE NULL END) = p.nk_program_id
LEFT JOIN source.mst_user mu ON (CASE WHEN ts.instructor_id ~ '^[0-9]+$' THEN ts.instructor_id::BIGINT ELSE NULL END) = (CASE WHEN mu.mst_user_id ~ '^[0-9]+$' THEN mu.mst_user_id::BIGINT ELSE NULL END)
LEFT JOIN source.mst_school ms ON COALESCE((CASE WHEN cpsm.school_id ~ '^[0-9]+$' THEN cpsm.school_id::BIGINT ELSE NULL END), (CASE WHEN ts.program_school_mapped_id ~ '^[0-9]+$' THEN ts.program_school_mapped_id::BIGINT ELSE NULL END)) = (CASE WHEN ms.mst_school_id ~ '^[0-9]+$' THEN ms.mst_school_id::BIGINT ELSE NULL END)
LEFT JOIN dw.dim_geography gs ON (CASE WHEN ms.area_id ~ '^[0-9]+$' THEN ms.area_id::BIGINT ELSE NULL END) = gs.nk_area_id
LEFT JOIN dw.dim_geography gi ON (CASE WHEN mu.area_id ~ '^[0-9]+$' THEN mu.area_id::BIGINT ELSE NULL END) = gi.nk_area_id
LEFT JOIN dw.dim_program pi ON (CASE WHEN mu.base_program_id ~ '^[0-9]+$' THEN mu.base_program_id::BIGINT ELSE NULL END) = pi.nk_program_id
LEFT JOIN source.mst_class mc ON (CASE WHEN tfe.class_id ~ '^[0-9]+$' THEN tfe.class_id::BIGINT ELSE NULL END) = (CASE WHEN mc.mst_class_id ~ '^[0-9]+$' THEN mc.mst_class_id::BIGINT ELSE NULL END);

-- B. Exposure from RPT_ADHOC_FEEDBACK
INSERT INTO dw.fact_attendance_exposure (
    date_id, sk_user_id, sk_school_id, sk_program_id, sk_geography_id, 
    session_nk_id, class_name, section_name, boys_count, girls_count, total_exposure_count
)
SELECT 
    d.date_id,
    u.sk_user_id,
    COALESCE(s_loc.sk_school_id, s_village.sk_school_id) as sk_school_id,
    COALESCE(p.sk_program_id, pi.sk_program_id) as sk_program_id,
    COALESCE(s_loc_geo.sk_geography_id, s_village_geo.sk_geography_id, gi.sk_geography_id) as sk_geography_id,
    (CASE WHEN ra.adhoc_id ~ '^[0-9]+$' THEN ra.adhoc_id::BIGINT ELSE NULL END) + 1000000 as session_nk_id,
    'ADHOC' as class_name,
    'N/A' as section_name,
    COALESCE(CASE WHEN ra.no_of_boys ~ '^[0-9]+$' THEN ra.no_of_boys::INT ELSE NULL END, 0) as boys_count,
    COALESCE(CASE WHEN ra.no_of_girls ~ '^[0-9]+$' THEN ra.no_of_girls::INT ELSE NULL END, 0) as girls_count,
    COALESCE(CASE WHEN ra.no_of_boys ~ '^[0-9]+$' THEN ra.no_of_boys::INT ELSE NULL END, 0) + COALESCE(CASE WHEN ra.no_of_girls ~ '^[0-9]+$' THEN ra.no_of_girls::INT ELSE NULL END, 0) as total_exposure_count
FROM source.rpt_adhoc_feedback ra
JOIN dw.dim_date d ON (CASE WHEN ra.date ~ '^[12][0-9]{3}-[01][0-9]-(0[1-9]|[12][0-9]|3[01])' THEN ra.date::DATE ELSE NULL END) = d.full_date
LEFT JOIN dw.dim_user u ON (CASE WHEN ra.instructor_id ~ '^[0-9]+$' THEN ra.instructor_id::BIGINT ELSE NULL END) = u.nk_user_id
LEFT JOIN dw.dim_school s_loc ON (CASE WHEN ra.location_id ~ '^[0-9]+$' THEN ra.location_id::BIGINT ELSE NULL END) = s_loc.nk_school_id
LEFT JOIN source.mst_school ms_loc ON (CASE WHEN ra.location_id ~ '^[0-9]+$' THEN ra.location_id::BIGINT ELSE NULL END) = (CASE WHEN ms_loc.mst_school_id ~ '^[0-9]+$' THEN ms_loc.mst_school_id::BIGINT ELSE NULL END)
LEFT JOIN dw.dim_geography s_loc_geo ON (CASE WHEN ms_loc.area_id ~ '^[0-9]+$' THEN ms_loc.area_id::BIGINT ELSE NULL END) = s_loc_geo.nk_area_id
LEFT JOIN (SELECT DISTINCT ON (LOWER(TRIM(school_name))) sk_school_id, school_name, nk_school_id FROM dw.dim_school) s_village ON LOWER(TRIM(ra.village)) = LOWER(TRIM(s_village.school_name))
LEFT JOIN source.mst_school ms_village ON s_village.nk_school_id = (CASE WHEN ms_village.mst_school_id ~ '^[0-9]+$' THEN ms_village.mst_school_id::BIGINT ELSE NULL END)
LEFT JOIN dw.dim_geography s_village_geo ON (CASE WHEN ms_village.area_id ~ '^[0-9]+$' THEN ms_village.area_id::BIGINT ELSE NULL END) = s_village_geo.nk_area_id
LEFT JOIN dw.dim_program p ON (CASE WHEN ra.program_id ~ '^[0-9]+$' THEN ra.program_id::BIGINT ELSE NULL END) = p.nk_program_id
LEFT JOIN source.mst_user mu ON (CASE WHEN ra.instructor_id ~ '^[0-9]+$' THEN ra.instructor_id::BIGINT ELSE NULL END) = (CASE WHEN mu.mst_user_id ~ '^[0-9]+$' THEN mu.mst_user_id::BIGINT ELSE NULL END)
LEFT JOIN dw.dim_geography gi ON (CASE WHEN mu.area_id ~ '^[0-9]+$' THEN mu.area_id::BIGINT ELSE NULL END) = gi.nk_area_id
LEFT JOIN dw.dim_program pi ON (CASE WHEN mu.base_program_id ~ '^[0-9]+$' THEN mu.base_program_id::BIGINT ELSE NULL END) = pi.nk_program_id
WHERE ra.adhoc_id ~ '^[0-9]+$';

--------------------------------------------------------------------------------
-- 3. FACT_VEHICLE_OPERATIONS
--------------------------------------------------------------------------------
TRUNCATE TABLE dw.fact_vehicle_operations CASCADE;
INSERT INTO dw.fact_vehicle_operations (
    date_id, sk_user_id, sk_instructor_id, sk_driver_id, sk_program_id, sk_geography_id, 
    vehicle_nk_id, distance_travelled, fuel_quantity, fuel_cost, was_vehicle_used
)
SELECT 
    d.date_id,
    ui.sk_user_id as sk_user_id,
    ui.sk_user_id as sk_instructor_id,
    ud.sk_user_id as sk_driver_id,
    p.sk_program_id,
    g.sk_geography_id,
    CASE WHEN tvl.vehicle_id ~ '^[0-9]+$' THEN tvl.vehicle_id::BIGINT ELSE NULL END as vehicle_nk_id,
    COALESCE(CASE WHEN tvl.closed_reading ~ '^[0-9\.]+$' THEN tvl.closed_reading::DOUBLE PRECISION ELSE 0 END - CASE WHEN tvl.open_reading ~ '^[0-9\.]+$' THEN tvl.open_reading::DOUBLE PRECISION ELSE 0 END, 0) as distance_travelled,
    COALESCE(CASE WHEN tvl.fuel_quantity ~ '^[0-9\.]+$' THEN tvl.fuel_quantity::DOUBLE PRECISION ELSE 0 END, 0),
    COALESCE(CASE WHEN tvl.fuel_quantity ~ '^[0-9\.]+$' THEN tvl.fuel_quantity::DOUBLE PRECISION ELSE 0 END * CASE WHEN tvl.fuel_price ~ '^[0-9\.]+$' THEN tvl.fuel_price::DOUBLE PRECISION ELSE 0 END, 0) as fuel_cost,
    COALESCE(NULLIF(tvl.vehicle_used_flag, ''), '0')::INT = 1
FROM source.txn_vehicle_log tvl
LEFT JOIN dw.dim_date d ON COALESCE(
    CASE WHEN tvl.date ~ '^[12][0-9]{3}-[01][0-9]-(0[1-9]|[12][0-9]|3[01])' THEN tvl.date::DATE ELSE NULL END, 
    CASE WHEN tvl.created_on ~ '^[12][0-9]{3}-[01][0-9]-(0[1-9]|[12][0-9]|3[01])' THEN tvl.created_on::DATE ELSE NULL END
)::DATE = d.full_date
LEFT JOIN dw.dim_user ui ON (CASE WHEN tvl.instructor_id ~ '^[0-9]+$' THEN tvl.instructor_id::BIGINT ELSE NULL END) = ui.nk_user_id
LEFT JOIN dw.dim_user ud ON (CASE WHEN tvl.driver_id ~ '^[0-9]+$' THEN tvl.driver_id::BIGINT ELSE NULL END) = ud.nk_user_id
LEFT JOIN dw.dim_program p ON (CASE WHEN tvl.program_id ~ '^[0-9]+$' THEN tvl.program_id::BIGINT ELSE NULL END) = p.nk_program_id
LEFT JOIN source.txn_program sp ON (CASE WHEN tvl.program_id ~ '^[0-9]+$' THEN tvl.program_id::BIGINT ELSE NULL END) = (CASE WHEN sp.txn_program_id ~ '^[0-9]+$' THEN sp.txn_program_id::BIGINT ELSE NULL END)
LEFT JOIN dw.dim_geography g ON (CASE WHEN sp.area_id ~ '^[0-9]+$' THEN sp.area_id::BIGINT ELSE NULL END) = g.nk_area_id;

-- B. Operations from TXN_DAILY_DATA
INSERT INTO dw.fact_vehicle_operations (
    date_id, sk_user_id, sk_instructor_id, sk_driver_id, sk_program_id, sk_geography_id, 
    vehicle_nk_id, distance_travelled, fuel_quantity, fuel_cost, was_vehicle_used
)
SELECT 
    d.date_id,
    ui.sk_user_id,
    ui.sk_user_id as sk_instructor_id,
    NULL as sk_driver_id,
    pi.sk_program_id,
    gi.sk_geography_id,
    CASE WHEN tdd.vehicle_id ~ '^[0-9]+$' THEN tdd.vehicle_id::BIGINT ELSE NULL END as vehicle_nk_id,
    COALESCE(CASE WHEN tdd.closed_reading ~ '^[0-9\.]+$' THEN tdd.closed_reading::DOUBLE PRECISION ELSE 0 END - CASE WHEN tdd.open_reading ~ '^[0-9\.]+$' THEN tdd.open_reading::DOUBLE PRECISION ELSE 0 END, 0) as distance_travelled,
    COALESCE(CASE WHEN tdd.fuel_quantity ~ '^[0-9\.]+$' THEN tdd.fuel_quantity::DOUBLE PRECISION ELSE 0 END, 0),
    COALESCE(CASE WHEN tdd.fuel_quantity ~ '^[0-9\.]+$' THEN tdd.fuel_quantity::DOUBLE PRECISION ELSE 0 END * CASE WHEN tdd.fuel_price ~ '^[0-9\.]+$' THEN tdd.fuel_price::DOUBLE PRECISION ELSE 0 END, 0) as fuel_cost,
    COALESCE(NULLIF(tdd.vehicle_used_flag, ''), '0')::INT = 1
FROM source.txn_daily_data tdd
JOIN dw.dim_date d ON (CASE WHEN tdd.date ~ '^[12][0-9]{3}-[01][0-9]-(0[1-9]|[12][0-9]|3[01])' THEN tdd.date::DATE ELSE NULL END) = d.full_date
LEFT JOIN dw.dim_user ui ON (CASE WHEN tdd.instructor_id ~ '^[0-9]+$' THEN tdd.instructor_id::BIGINT ELSE NULL END) = ui.nk_user_id
LEFT JOIN source.mst_user mu ON (CASE WHEN tdd.instructor_id ~ '^[0-9]+$' THEN tdd.instructor_id::BIGINT ELSE NULL END) = (CASE WHEN mu.mst_user_id ~ '^[0-9]+$' THEN mu.mst_user_id::BIGINT ELSE NULL END)
LEFT JOIN dw.dim_geography gi ON (CASE WHEN mu.area_id ~ '^[0-9]+$' THEN mu.area_id::BIGINT ELSE NULL END) = gi.nk_area_id
LEFT JOIN dw.dim_program pi ON (CASE WHEN mu.base_program_id ~ '^[0-9]+$' THEN mu.base_program_id::BIGINT ELSE NULL END) = pi.nk_program_id;
