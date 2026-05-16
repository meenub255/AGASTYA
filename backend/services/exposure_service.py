from backend.services.query_utils import build_dimension_filters, fetch_all, fetch_one
from backend.config import DATAMART_SCHEMA_NAME

def _base_where(years=None, region=None, program=None):
    return build_dimension_filters(
        year=years,
        region=region,
        program=program,
        year_expression="d.year_actual",
        location_expression="g.region_name",
        program_expression="p.program_name",
    )

def get_unified_exposure_data(years=None, region=None, program=None):
    where_clause, params = _base_where(years, region, program)
    
    # 1. KPIs
    kpi_sql = f"""
        SELECT
            (
                (SELECT COALESCE(SUM(total_exposure_count), 0) FROM {DATAMART_SCHEMA_NAME}.fact_attendance_exposure fae 
                 LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON d.date_id = fae.date_id 
                 LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON g.sk_geography_id = fae.sk_geography_id 
                 LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON p.sk_program_id = fae.sk_program_id {where_clause})
            ) AS total_students,
            (
                SELECT COALESCE(SUM(f.community_men_count + f.community_women_count), 0) FROM {DATAMART_SCHEMA_NAME}.fact_session f
                 LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON d.date_id = f.date_id 
                 LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON g.sk_geography_id = f.sk_geography_id 
                 LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON p.sk_program_id = f.sk_program_id {where_clause}
            ) AS total_community,
            (
                SELECT COALESCE(SUM(f.community_girls_count), 0) FROM {DATAMART_SCHEMA_NAME}.fact_session f
                 LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON d.date_id = f.date_id 
                 LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON g.sk_geography_id = f.sk_geography_id 
                 LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON p.sk_program_id = f.sk_program_id {where_clause}
            ) AS girls_count,
            (
                SELECT COALESCE(SUM(f.community_boys_count), 0) FROM {DATAMART_SCHEMA_NAME}.fact_session f
                 LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON d.date_id = f.date_id 
                 LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON g.sk_geography_id = f.sk_geography_id 
                 LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON p.sk_program_id = f.sk_program_id {where_clause}
            ) AS boys_count,
            (
                SELECT COALESCE(SUM(f.community_men_count), 0) FROM {DATAMART_SCHEMA_NAME}.fact_session f
                 LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON d.date_id = f.date_id 
                 LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON g.sk_geography_id = f.sk_geography_id 
                 LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON p.sk_program_id = f.sk_program_id {where_clause}
            ) AS men_count,
            (
                SELECT COALESCE(SUM(f.community_women_count), 0) FROM {DATAMART_SCHEMA_NAME}.fact_session f
                 LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON d.date_id = f.date_id 
                 LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON g.sk_geography_id = f.sk_geography_id 
                 LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON p.sk_program_id = f.sk_program_id {where_clause}
            ) AS women_count,
            COALESCE(SUM(f.no_of_teachers_participated), 0) AS total_teachers,
            (SELECT COALESCE(AVG(total_exposure_count), 0) FROM {DATAMART_SCHEMA_NAME}.fact_attendance_exposure fae 
             LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON d.date_id = fae.date_id 
             LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON g.sk_geography_id = fae.sk_geography_id 
             LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON p.sk_program_id = fae.sk_program_id {where_clause}) AS average_exposure
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON d.date_id = f.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
        {where_clause}
    """
    kpi_res = fetch_one(kpi_sql, params * 7 + params)
    
    # 2. Top Schools
    top_schools = fetch_all(f"""
        SELECT COALESCE(s.school_name, 'Unknown') as name,
               SUM(COALESCE(e.total_exposure_count, 0)) as students
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_school s ON f.sk_school_id = s.sk_school_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
        {where_clause}
        GROUP BY s.school_name
        ORDER BY students DESC
        LIMIT 5
    """, params)

    # 3. Cohort Breakdown
    cohorts = fetch_all(f"""
        SELECT COALESCE(e.class_name, 'N/A') as type,
               SUM(COALESCE(e.total_exposure_count, 0)) as students
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        LEFT JOIN {DATAMART_SCHEMA_NAME}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
        {where_clause}
        GROUP BY e.class_name
        ORDER BY students DESC
    """, params)

    return {
        "kpis": {
            "total_students": int(kpi_res.get("total_students") or 0),
            "total_community": int(kpi_res.get("total_community") or 0),
            "total_teachers": int(kpi_res.get("total_teachers") or 0),
            "average_exposure": round(float(kpi_res.get("average_exposure") or 0), 1),
            "girls": int(kpi_res.get("girls_count") or 0),
            "boys": int(kpi_res.get("boys_count") or 0),
            "men": int(kpi_res.get("men_count") or 0),
            "women": int(kpi_res.get("women_count") or 0)
        },
        "top_schools": top_schools,
        "cohort_breakdown": cohorts
    }

def get_program_options():
    rows = fetch_all(f"SELECT DISTINCT program_name FROM {DATAMART_SCHEMA_NAME}.dim_program ORDER BY program_name")
    return [r["program_name"] for r in rows]
