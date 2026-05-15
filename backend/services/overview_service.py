from backend.services.query_utils import build_dimension_filters, fetch_all, fetch_one


LOCATION_EXPRESSION = "g.region_name"
PROGRAM_EXPRESSION = "p.program_name"



from backend.config import DEFAULT_YEAR

def _build_filters(year: list[int] | list[str] | None = None, region: list[str] | None = None, program: list[str] | None = None):
    return build_dimension_filters(
        year=year,
        region=region,
        program=program,
        year_expression="d.year_actual",
        location_expression=LOCATION_EXPRESSION,
        program_expression=PROGRAM_EXPRESSION,
    )



def get_overview_kpis(year: list[int] | list[str] | None = None, region: list[str] | None = None, program: list[str] | None = None):
    where_clause, params = _build_filters(year=year, region=region, program=program)

    # 1. Main session-based KPIs
    kpis_row = fetch_one(
        f"""
        SELECT
            COUNT(DISTINCT f.sk_user_id) AS total_instructors,
            COUNT(DISTINCT g.nk_region_id) AS total_states,
            COUNT(DISTINCT p.program_name) AS total_programs
        FROM dw.fact_session f
        LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN dw.dim_program p ON p.sk_program_id = f.sk_program_id
        {where_clause}
        """,
        params,
    )

    # 2. Driver-specific KPI from vehicle operations
    driver_row = fetch_one(
        f"""
        SELECT
            COUNT(DISTINCT f.sk_driver_id) AS total_drivers
        FROM dw.fact_vehicle_operations f
        LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN dw.dim_program p ON p.sk_program_id = f.sk_program_id
        {where_clause}
        """,
        params,
    )


    return {
        "total_instructors": int(kpis_row.get("total_instructors", 0) or 0),
        "total_drivers": int(driver_row.get("total_drivers", 0) or 0),
        "total_states": int(kpis_row.get("total_states", 0) or 0),
        "total_programs": int(kpis_row.get("total_programs", 0) or 0),
    }

def get_overview_trends(year: list[int] | list[str] | None = None, region: list[str] | None = None, program: list[str] | None = None):
    """Returns monthly historical trend data for sparklines."""
    where_clause, params = _build_filters(year=year, region=region, program=program)
    
    # We fetch monthly data for the last 12 periods based on filters
    # If years are selected, we show data for those years
    rows = fetch_all(f"""
        SELECT 
            d.year_actual,
            d.month_actual,
            MIN(d.full_date) as sort_key,
            COUNT(DISTINCT f.sk_user_id) as instructors,
            COUNT(DISTINCT g.nk_region_id) as states,
            COUNT(DISTINCT p.program_name) as programs
        FROM dw.fact_session f
        LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN dw.dim_program p ON p.sk_program_id = f.sk_program_id
        {where_clause}
        GROUP BY d.year_actual, d.month_actual
        ORDER BY sort_key
        LIMIT 24
    """, params)

    driver_rows = fetch_all(f"""
        SELECT 
            d.year_actual,
            d.month_actual,
            MIN(d.full_date) as sort_key,
            COUNT(DISTINCT f.sk_driver_id) as drivers
        FROM dw.fact_vehicle_operations f
        LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN dw.dim_program p ON p.sk_program_id = f.sk_program_id
        {where_clause}
        GROUP BY d.year_actual, d.month_actual
        ORDER BY sort_key
        LIMIT 24
    """, params)

    # Merge driver data into rows mapping
    driver_map = {(r["year_actual"], r["month_actual"]): r["drivers"] for r in driver_rows}
    
    trends = []
    for r in rows:
        key = (r["year_actual"], r["month_actual"])
        trends.append({
            "instructors": r["instructors"],
            "states": r["states"],
            "programs": r["programs"],
            "drivers": driver_map.get(key, 0)
        })
    
    return trends

def get_overview_charts(year: list[int] | list[str] | None = None, region: list[str] | None = None, program: list[str] | None = None):
    where_clause, params = _build_filters(year=year, region=region, program=program)
    
    # 1. Instructors per region
    instructors_rows = fetch_all(
        f"""
        SELECT
            COALESCE(g.region_name, 'Unknown') AS label,
            COUNT(DISTINCT f.sk_user_id) AS value
        FROM dw.fact_session f
        LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN dw.dim_program p ON p.sk_program_id = f.sk_program_id
        {where_clause} AND g.region_name IS NOT NULL
        GROUP BY g.region_name
        ORDER BY value DESC
        LIMIT 10
        """,
        params,
    )

    
    # 2. Programs per region
    programs_rows = fetch_all(
        f"""
        SELECT
            COALESCE(g.region_name, 'Unknown') AS label,
            COUNT(DISTINCT p.program_name) AS value
        FROM dw.fact_session f
        LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN dw.dim_program p ON p.sk_program_id = f.sk_program_id
        {where_clause} AND g.region_name IS NOT NULL
        GROUP BY g.region_name
        ORDER BY value DESC
        LIMIT 10
        """,
        params,
    )

    # 3. Drivers per region
    drivers_rows = fetch_all(
        f"""
        SELECT
            COALESCE(g.region_name, 'Unknown') AS label,
            COUNT(DISTINCT f.sk_user_id) AS value
        FROM dw.fact_vehicle_operations f
        JOIN dw.dim_user u ON f.sk_user_id = u.sk_user_id
        LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN dw.dim_program p ON p.sk_program_id = f.sk_program_id
        {where_clause} AND u.role_name = 'DRIVER' AND g.region_name IS NOT NULL
        GROUP BY g.region_name
        ORDER BY value DESC
        LIMIT 10
        """,
        params,
    )


    return {
        "instructors_by_region": [{"label": r["label"], "value": float(r["value"])} for r in instructors_rows],
        "drivers_by_region": [{"label": r["label"], "value": float(r["value"])} for r in drivers_rows],
        "programs_by_region": [{"label": r["label"], "value": float(r["value"])} for r in programs_rows]
    }


def get_program_targets(year: list[int] | list[str] | None = None, region: list[str] | None = None, program: list[str] | None = None, limit: int = 10, offset: int = 0):
    where_clause, params = _build_filters(year=year, region=region, program=program)
    
    total_count = fetch_one(
        f"""
        SELECT COUNT(*) FROM dw.dim_program
        """
    )["count"]


    rows = fetch_all(
        f"""
        SELECT
            p.sk_program_id,
            COALESCE(p.program_name, 'Unknown') AS label,
            COALESCE(p.donor_name, 'Unknown') AS donor,
            COALESCE(p.instructor_capacity, 0) AS target_sessions,
            COALESCE(COUNT(DISTINCT f.sk_fact_session_id), 0) AS completed_sessions,
            COALESCE(SUM(fa.total_exposure_count + f.community_men_count + f.community_women_count), 0) AS reached_students,
            p.end_date AS end_date
        FROM dw.dim_program p
        LEFT JOIN dw.fact_session f ON p.sk_program_id = f.sk_program_id
        LEFT JOIN dw.fact_attendance_exposure fa ON f.session_nk_id = fa.session_nk_id
        LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        {where_clause}
        GROUP BY p.sk_program_id
        ORDER BY completed_sessions DESC, label
        LIMIT %s OFFSET %s
        """,
        [*params, limit, offset],
    )


    items = []
    for row in rows:
        target_sessions = int(row.get("target_sessions", 0) or 0)
        completed_sessions = int(row.get("completed_sessions", 0) or 0)
        pct = round((completed_sessions / target_sessions) * 100) if target_sessions else 0
        if pct >= 80:
            status = "On track"
        elif pct >= 50:
            status = "At risk"
        else:
            status = "Behind"
        items.append(
            {
                "label": row.get("label") or "Unknown",
                "donor": row.get("donor") or "Unknown",
                "completed_sessions": completed_sessions,
                "target_sessions": target_sessions,
                        "students_target": int(row.get("target_students", 0) or 0),
                        "students_reached": int(row.get("reached_students", 0) or 0),
                "progress_pct": pct,
                "end_date": row["end_date"].strftime("%b %Y") if row.get("end_date") else "Unknown",
                "status": status,
            }
        )
    return {"table": items, "total_count": total_count}


def get_sessions_by_activity(year: list[int] | list[str] | None = None, region: list[str] | None = None, program: list[str] | None = None):
    where_clause, params = _build_filters(year=year, region=region, program=program)
    rows = fetch_all(
        f"""
        SELECT
            COALESCE(a.activity_name, 'Unknown') AS label,
            COALESCE(COUNT(DISTINCT f.sk_fact_session_id), 0) AS value
        FROM dw.fact_session f
        LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN dw.dim_program p ON p.sk_program_id = f.sk_program_id
        LEFT JOIN dw.dim_activity_type a ON a.sk_activity_type_id = f.sk_activity_type_id
        {where_clause}
        GROUP BY COALESCE(a.activity_name, 'Unknown')
        ORDER BY value DESC, label
        LIMIT 6
        """,
        params,
    )

    return [{"label": row["label"], "value": float(row["value"])} for row in rows]


def get_sessions_by_donor(year: list[int] | list[str] | None = None, region: list[str] | None = None, program: list[str] | None = None):
    where_clause, params = _build_filters(year=year, region=region, program=program)
    rows = fetch_all(
        f"""
        SELECT
            COALESCE(p.donor_name, 'Unknown') AS label,
            COALESCE(COUNT(DISTINCT f.sk_fact_session_id), 0) AS value
        FROM dw.fact_session f
        LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN dw.dim_program p ON p.sk_program_id = f.sk_program_id
        {where_clause}
        GROUP BY COALESCE(p.donor_name, 'Unknown')
        ORDER BY value DESC, label
        LIMIT 6
        """,
        params,
    )

    return [{"label": row["label"], "value": float(row["value"])} for row in rows]


def get_drilldown_data(
    region: str,
    year: list[int] | list[str] | None = None,
    program: list[str] | None = None,
):
    """
    Returns rich drill-down stats for a specific region click.
    Uses hardened matching to ensure data integrity.
    """
    # 1. Build base filters (default to 2026 if none provided)
    where_clause, params = _build_filters(year=year, program=program)
    
    # 2. Add hardened region filter
    region_norm = region.lower().replace("_", " ")
    region_filter = "REPLACE(LOWER(g.region_name), '_', ' ') = %s"
    
    if where_clause:
        where_clause += f" AND {region_filter}"
    else:
        where_clause = f"WHERE {region_filter}"
    params.append(region_norm)

    # 1. Extended summary stats
    summary_row = fetch_one(
        f"""
        SELECT
            COUNT(DISTINCT f.sk_fact_session_id)        AS total_sessions,
            COALESCE(SUM(fa.total_exposure_count + f.community_men_count + f.community_women_count), 0)   AS total_students,
            COUNT(DISTINCT f.sk_school_id)              AS total_schools
        FROM dw.fact_session f
        LEFT JOIN dw.dim_date d       ON d.date_id        = f.date_id
        LEFT JOIN dw.dim_geography g  ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN dw.dim_program p    ON p.sk_program_id   = f.sk_program_id
        LEFT JOIN dw.fact_attendance_exposure fa ON fa.session_nk_id = f.session_nk_id
        {where_clause}
        """,
        params,
    )

    # 2. Per-program breakdown table
    prog_rows = fetch_all(
        f"""
        SELECT
            COALESCE(p.program_name, 'Unknown')         AS program_name,
            COALESCE(p.donor_name, 'Unknown')           AS donor,
            COUNT(DISTINCT f.sk_fact_session_id)        AS sessions,
            COALESCE(SUM(fa.total_exposure_count + f.community_men_count + f.community_women_count), 0)   AS students_reached,
            COUNT(DISTINCT f.sk_school_id)              AS schools_visited,
            COUNT(DISTINCT f.sk_user_id)                AS instructors
        FROM dw.fact_session f
        LEFT JOIN dw.dim_date d       ON d.date_id        = f.date_id
        LEFT JOIN dw.dim_geography g  ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN dw.dim_program p    ON p.sk_program_id   = f.sk_program_id
        LEFT JOIN dw.fact_attendance_exposure fa ON fa.session_nk_id = f.session_nk_id
        {where_clause}
        GROUP BY p.program_name, p.donor_name
        ORDER BY sessions DESC
        LIMIT 2000
        """,
        params,
    )

    programs = [
        {
            "program": row.get("program_name") or "Unknown",
            "donor": row.get("donor") or "Unknown",
            "sessions": int(row.get("sessions", 0) or 0),
            "students_reached": int(row.get("students_reached", 0) or 0),
            "schools_visited": int(row.get("schools_visited", 0) or 0),
            "instructors": int(row.get("instructors", 0) or 0),
        }
        for row in prog_rows
    ]

    return {
        "region": region,
        "summary": {
            "total_sessions": int(summary_row.get("total_sessions", 0) or 0),
            "total_students": int(summary_row.get("total_students", 0) or 0),
            "total_schools": int(summary_row.get("total_schools", 0) or 0),
        },
        "programs": programs,
    }
