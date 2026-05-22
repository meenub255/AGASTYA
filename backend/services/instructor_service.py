from backend.services.query_utils import build_dimension_filters, fetch_all, fetch_one
from backend.config import DATAMART_SCHEMA_NAME

def _build_filters(years=None, region=None, program=None, instructor=None):
    return build_dimension_filters(
        year=years,
        region=region,
        program=program,
        year_expression="d.year_actual",
        location_expression="g.region_name",
        program_expression="p.program_name",
        instructor=instructor,
        instructor_expression="u.role_name",
    )

def get_unified_instructor_data(years=None, region=None, program=None, instructor=None):
    """Unified data for Instructor Dashboard."""
    kpis = get_instructor_kpis(years, region, program, instructor)
    type_breakdown = get_sessions_by_instructor_type(years, region, program, instructor)
    multi_program = get_multi_program_instructors(years, region, program, instructor)
    productivity = get_instructor_productivity(years, region, program, instructor)
    monthly = get_monthly_instructor_activity(years, region, program, instructor)
    
    return {
        "kpis": kpis,
        "type_breakdown": type_breakdown,
        "multi_program": multi_program,
        "productivity": productivity,
        "monthly_activity": monthly
    }

def get_instructor_kpis(years=None, region=None, program=None, instructor=None) -> dict:
    where_clause, params = _build_filters(years, region, program, instructor)

    row = fetch_one(
        f"""
        SELECT
            COUNT(DISTINCT f.sk_user_id) AS total_instructors,
            COUNT(f.sk_fact_session_id) AS sessions_conducted,
            COALESCE(
                COUNT(f.sk_fact_session_id)::numeric / NULLIF(COUNT(DISTINCT f.sk_user_id), 0),
                0
            ) AS avg_sessions_per_instructor,
            COALESCE(
                COUNT(CASE WHEN f.is_overdue THEN 1 END),
                0
            ) AS unprocessed_sessions
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON d.date_id = f.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON p.sk_program_id = f.sk_program_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_user u ON u.sk_user_id = f.sk_user_id
        {where_clause}
        """,
        params,
    )

    top_region_row = fetch_one(
        f"""
        SELECT
            COALESCE(g.region_name, 'Unknown') AS top_region,
            COUNT(f.sk_fact_session_id) AS top_region_sessions
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON d.date_id = f.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_user u ON u.sk_user_id = f.sk_user_id
        {where_clause}
        GROUP BY g.region_name
        ORDER BY top_region_sessions DESC, top_region
        LIMIT 1
        """,
        params,
    )

    return {
        "total_instructors": int(row.get("total_instructors", 0) or 0),
        "avg_sessions_per_instructor": round(float(row.get("avg_sessions_per_instructor", 0) or 0), 1),
        "top_region": top_region_row.get("top_region", "-") or "-",
        "top_region_sessions": int(top_region_row.get("top_region_sessions", 0) or 0),
        "unprocessed_sessions": int(row.get("unprocessed_sessions", 0) or 0),
    }

def get_instructor_session_log(years=None, region=None, program=None, instructor=None, limit=10, offset=0, dt_params=None) -> dict:
    from backend.services.query_utils import get_datatables_sql
    where_clause, params = _build_filters(years, region, program, instructor)

    search_sql = "TRUE"
    search_params = []
    sort_sql = "ORDER BY sessions DESC, students DESC, name"
    
    if dt_params:
        searchable_cols = ["COALESCE(u.user_name, 'Unknown')", "u.role_name", "g.region_name"]
        sortable_cols = ["name", "type", "region", "sessions", "activity_types", "students", "last_session"]
        inner_search_sql, inner_search_params, inner_sort_sql = get_datatables_sql(dt_params, searchable_cols, sortable_cols)
        search_sql = inner_search_sql
        search_params = inner_search_params
        if inner_sort_sql:
            sort_sql = inner_sort_sql

    rows = fetch_all(
        f"""
        SELECT
            COALESCE(u.user_name, 'Unknown') AS name,
            COALESCE(u.role_name, 'Unknown') AS type,
            COALESCE(g.region_name, 'Unknown') AS region,
            COUNT(f.sk_fact_session_id) AS sessions,
            STRING_AGG(DISTINCT COALESCE(act.activity_name, 'NA'), ', ') AS activity_types,
            (SELECT COALESCE(SUM(total_exposure_count), 0) FROM {DATAMART_SCHEMA_NAME}.fact_attendance_exposure fae 
             JOIN {DATAMART_SCHEMA_NAME}.fact_session fs ON fae.session_nk_id = fs.session_nk_id 
             WHERE fs.sk_user_id = u.sk_user_id) AS students,
            TO_CHAR(MAX(d.full_date), 'Mon DD') AS last_session
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON d.date_id = f.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_user u ON u.sk_user_id = f.sk_user_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_activity_type act ON f.sk_activity_type_id = act.sk_activity_type_id
        {where_clause} AND {search_sql}
        GROUP BY u.sk_user_id, u.user_name, u.role_name, g.region_name
        {sort_sql}
        LIMIT %s OFFSET %s
        """,
        [*params, *search_params, limit, offset],
    )

    total_count_row = fetch_one(
        f"""
        SELECT COUNT(*) FROM (
            SELECT u.sk_user_id
            FROM {DATAMART_SCHEMA_NAME}.fact_session f
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON d.date_id = f.date_id
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON g.sk_geography_id = f.sk_geography_id
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_user u ON u.sk_user_id = f.sk_user_id
            {where_clause} AND {search_sql}
            GROUP BY u.sk_user_id
        ) as sub
        """,
        params + search_params,
    )
    total_count = total_count_row.get("count", 0) if total_count_row else 0

    return {
        "table": [
            {
                "name": row["name"],
                "type": row["type"],
                "region": row["region"],
                "sessions": int(row["sessions"] or 0),
                "activity_types": row["activity_types"],
                "students": int(row["students"] or 0),
                "last_session": row.get("last_session") or "-",
            }
            for row in rows
        ],
        "total_count": total_count
    }

def get_multi_program_instructors(years=None, region=None, program=None, instructor=None, limit=5) -> list[dict]:
    where_clause, params = _build_filters(years, region, program, instructor)

    rows = fetch_all(
        f"""
        SELECT
            COALESCE(u.user_name, 'Unknown') AS name,
            COALESCE(u.role_name, 'Unknown') AS instructor_type,
            COALESCE(g.region_name, 'Unknown') AS region,
            COUNT(DISTINCT f.sk_program_id) AS programs,
            COUNT(f.sk_fact_session_id) AS sessions
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON d.date_id = f.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_user u ON u.sk_user_id = f.sk_user_id
        {where_clause}
        GROUP BY u.sk_user_id, u.user_name, u.role_name, g.region_name
        HAVING COUNT(DISTINCT f.sk_program_id) > 1
        ORDER BY programs DESC, sessions DESC, name
        LIMIT %s
        """,
        [*params, limit],
    )

    return [
        {
            "name": row["name"],
            "type": row["instructor_type"],
            "region": row["region"],
            "programs": int(row["programs"] or 0),
            "sessions": int(row["sessions"] or 0),
            "initials": "".join(part[0] for part in str(row["name"]).split()[:2]).upper() or "NA",
        }
        for row in rows
    ]

def get_sessions_by_instructor_type(years=None, region=None, program=None, instructor=None) -> list[dict]:
    where_clause, params = _build_filters(years, region, program, instructor)
    rows = fetch_all(
        f"""
        SELECT
            COALESCE(u.role_name, 'Unknown') AS label,
            COUNT(f.sk_fact_session_id) AS value
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON d.date_id = f.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_user u ON u.sk_user_id = f.sk_user_id
        {where_clause}
        GROUP BY u.role_name
        ORDER BY value DESC
        """,
        params,
    )
    return [{"label": row["label"], "value": float(row["value"] or 0)} for row in rows]

def get_instructor_productivity(years=None, region=None, program=None, instructor=None, limit=20) -> list[dict]:
    data = get_instructor_session_log(years=years, region=region, program=program, instructor=instructor, limit=limit)
    return [{"label": row["name"], "value": float(row["sessions"])} for row in data["table"]]

def get_monthly_instructor_activity(years=None, region=None, program=None, instructor=None) -> list[dict]:
    where_clause, params = _build_filters(years, region, program, instructor)
    rows = fetch_all(
        f"""
        SELECT
            TO_CHAR(d.full_date, 'Mon') AS label,
            COUNT(f.sk_fact_session_id) AS value,
            EXTRACT(MONTH FROM d.full_date) AS sort_key
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON d.date_id = f.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        {where_clause}
        GROUP BY TO_CHAR(d.full_date, 'Mon'), EXTRACT(MONTH FROM d.full_date)
        ORDER BY sort_key
        """,
        params,
    )
    return [{"label": row["label"], "value": float(row["value"])} for row in rows]
