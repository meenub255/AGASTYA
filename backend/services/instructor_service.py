from backend.services.query_utils import build_dimension_filters, fetch_all, fetch_one


def _type_expression() -> str:
    return "COALESCE(NULLIF(INITCAP(TRIM(u.role_name)), ''), 'Unknown')"


def _region_expression() -> str:
    return "COALESCE(NULLIF(g.region_name, ''), 'Unknown')"



def get_instructor_kpis(
    start: int | list[int] | None = None,
    end: int | list[int] | None = None,
    year: int | list[int] | None = None,
    region: str | list[str] | None = None,
    program: str | list[str] | None = None,
    instructor: str | list[str] | None = None,
) -> dict[str, int | float | str]:
    where_clause, params = build_dimension_filters(
        start=start,
        end=end,
        year=year,
        region=region,
        program=program,
        year_expression="d.year_actual",
        location_expression="g.region_name",
        program_expression="p.program_name",
        instructor=instructor,
        instructor_expression="u.role_name",
    )

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
        FROM dw.fact_session f
        LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN dw.dim_program p ON p.sk_program_id = f.sk_program_id
        LEFT JOIN dw.dim_user u ON u.sk_user_id = f.sk_user_id
        {where_clause}
        """,
        params,
    )

    top_region = fetch_one(
        f"""
        SELECT
            COALESCE(g.region_name, 'Unknown') AS top_region,
            COUNT(f.sk_fact_session_id) AS top_region_sessions
        FROM dw.fact_session f
        LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN dw.dim_user u ON u.sk_user_id = f.sk_user_id
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
        "top_region": top_region.get("top_region", "-") or "-",
        "top_region_sessions": int(top_region.get("top_region_sessions", 0) or 0),
        "unprocessed_sessions": int(row.get("unprocessed_sessions", 0) or 0),
    }


def get_instructor_session_log(
    start: int | list[int] | None = None,
    end: int | list[int] | None = None,
    year: int | list[int] | None = None,
    region: str | list[str] | None = None,
    program: str | list[str] | None = None,
    instructor: str | list[str] | None = None,
    limit: int = 10,
    offset: int = 0,
    dt_params: dict | None = None,
) -> dict:
    from backend.services.query_utils import get_datatables_sql
    where_clause, params = build_dimension_filters(
        start=start,
        end=end,
        year=year,
        region=region,
        program=program,
        year_expression="d.year_actual",
        location_expression="g.region_name",
        program_expression="p.program_name",
        instructor=instructor,
        instructor_expression="u.role_name",
    )

    # DataTable Logic
    search_sql = "TRUE"
    search_params = []
    sort_sql = "ORDER BY sessions DESC, students DESC, name"
    
    if dt_params:
        searchable_cols = ["COALESCE(u.user_name, 'Unknown')", "u.role_name", "g.region_name"]
        sortable_cols = ["name", "type", "region", "sessions", "students", "last_session"]
        
        inner_search_sql, inner_search_params, inner_sort_sql = get_datatables_sql(dt_params, searchable_cols, sortable_cols)
        search_sql = inner_search_sql
        search_params = inner_search_params
        if inner_sort_sql:
            # Map aliases to DB expressions for sorting
            mapping = {
                "name": "u.user_name",
                "type": _type_expression(),
                "region": _region_expression(),
                "sessions": "COUNT(f.sk_fact_session_id)",
                "students": "(SELECT COALESCE(SUM(total_exposure_count), 0) FROM dw.fact_attendance_exposure fae JOIN dw.fact_session fs ON fae.session_nk_id = fs.session_nk_id WHERE fs.sk_user_id = u.sk_user_id)",
                "last_session": "MAX(d.full_date)"
            }
            for alias, db_col in mapping.items():
                inner_sort_sql = inner_sort_sql.replace(alias, db_col)
            sort_sql = inner_sort_sql

    rows = fetch_all(
        f"""
        SELECT
            COALESCE(u.user_name, 'Unknown') AS name,
            {_type_expression()} AS instructor_type,
            {_region_expression()} AS region,
            COUNT(f.sk_fact_session_id) AS sessions,
            STRING_AGG(DISTINCT COALESCE(act.activity_name, 'NA'), ', ') AS activity_types,
            (SELECT COALESCE(SUM(total_exposure_count), 0) FROM dw.fact_attendance_exposure fae 
             JOIN dw.fact_session fs ON fae.session_nk_id = fs.session_nk_id 
             WHERE fs.sk_user_id = u.sk_user_id) AS students,
            TO_CHAR(MAX(d.full_date), 'Mon DD') AS last_session
        FROM dw.fact_session f
        LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN dw.dim_user u ON u.sk_user_id = f.sk_user_id
        LEFT JOIN dw.dim_activity_type act ON f.sk_activity_type_id = act.sk_activity_type_id
        {where_clause} AND {search_sql}
        GROUP BY u.sk_user_id, u.user_name, u.role_name, g.region_name
        {sort_sql}
        LIMIT %s OFFSET %s
        """,
        [*params, *search_params, limit, offset],
    )

    total_count = fetch_one(
        f"""
        SELECT COUNT(*) FROM (
            SELECT u.sk_user_id
            FROM dw.fact_session f
            LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
            LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
            LEFT JOIN dw.dim_user u ON u.sk_user_id = f.sk_user_id
            LEFT JOIN dw.dim_activity_type act ON f.sk_activity_type_id = act.sk_activity_type_id
            {where_clause} AND {search_sql}
            GROUP BY u.sk_user_id
        ) as sub
        """,
        params + search_params,
    ).get("count", 0)

    return {
        "table": [
            {
                "name": row["name"],
                "type": row["instructor_type"],
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


def get_multi_program_instructors(
    start: int | list[int] | None = None,
    end: int | list[int] | None = None,
    year: int | list[int] | None = None,
    region: str | list[str] | None = None,
    program: str | list[str] | None = None,
    instructor: str | list[str] | None = None,
    limit: int = 5,
) -> list[dict]:
    where_clause, params = build_dimension_filters(
        start=start,
        end=end,
        year=year,
        region=region,
        program=program,
        year_expression="d.year_actual",
        location_expression="g.region_name",
        program_expression="p.program_name",
        instructor=instructor,
        instructor_expression="u.role_name",
    )

    rows = fetch_all(
        f"""
        SELECT
            COALESCE(u.user_name, 'Unknown') AS name,
            {_type_expression()} AS instructor_type,
            {_region_expression()} AS region,
            COUNT(DISTINCT f.sk_program_id) AS programs,
            COUNT(f.sk_fact_session_id) AS sessions
        FROM dw.fact_session f
        LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN dw.dim_user u ON u.sk_user_id = f.sk_user_id
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


def get_sessions_by_instructor_type(
    start: int | list[int] | None = None,
    end: int | list[int] | None = None,
    year: int | list[int] | None = None,
    region: str | list[str] | None = None,
    program: str | list[str] | None = None,
    instructor: str | list[str] | None = None,
) -> list[dict]:
    where_clause, params = build_dimension_filters(
        start=start,
        end=end,
        year=year,
        region=region,
        program=program,
        year_expression="d.year_actual",
        location_expression="g.region_name",
        program_expression="p.program_name",
        instructor=instructor,
        instructor_expression="u.role_name",
    )

    # Comparison Logic: If multiple regions are selected, group by region
    compare_region = isinstance(region, list) and len([v for v in region if v]) > 1
    
    group_sql = ""
    group_select = ""
    if compare_region:
        group_sql = ", g.region_name"
        group_select = ", COALESCE(g.region_name, 'Unknown') AS group"

    rows = fetch_all(
        f"""
        SELECT
            {_type_expression()} AS label,
            COUNT(f.sk_fact_session_id) AS value
            {group_select}
        FROM dw.fact_session f
        LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN dw.dim_user u ON u.sk_user_id = f.sk_user_id
        {where_clause}
        GROUP BY u.role_name {group_sql}
        ORDER BY value DESC, label
        """,
        params,
    )
    return [{
        "label": row["label"], 
        "value": float(row["value"] or 0),
        **({"group": row["group"]} if "group" in row else {})
    } for row in rows]



def get_instructor_type_options() -> list[str]:
    rows = fetch_all(
        """
        SELECT DISTINCT role_name as name
        FROM dw.dim_user
        WHERE role_name IS NOT NULL
        ORDER BY role_name
        """
    )
    return [str(row["name"]) for row in rows if row.get("name")]



def get_instructor_productivity(
    start: int | list[int] | None = None,
    end: int | list[int] | None = None,
    year: int | list[int] | None = None,
    region: str | list[str] | None = None,
    program: str | list[str] | None = None,
    instructor: str | list[str] | None = None,
    limit: int = 20,
) -> list[dict]:
    rows = get_instructor_session_log(start=start, end=end, year=year, region=region, program=program, instructor=instructor, limit=limit)
    return [{"label": row["name"], "value": float(row["sessions"])} for row in rows]


def get_monthly_instructor_activity(
    start: int | list[int] | None = None,
    end: int | list[int] | None = None,
    year: int | list[int] | None = None,
    region: str | list[str] | None = None,
    program: str | list[str] | None = None,
    instructor: str | list[str] | None = None,
) -> list[dict]:
    where_clause, params = build_dimension_filters(
        start=start,
        end=end,
        year=year,
        region=region,
        program=program,
        year_expression="d.year_actual",
        location_expression="g.region_name",
        program_expression="p.program_name",
        instructor=instructor,
        instructor_expression="u.role_name",
    )

    # Comparison Logic: If multiple years are selected, group by year
    # 'start' is the 'year' filter in instructor.html
    compare_year = isinstance(start, list) and len([v for v in start if v]) > 1
    
    group_select = ""
    if compare_year:
        group_select = ", d.year_actual::text AS group"

    rows = fetch_all(
        f"""
        SELECT
            TO_CHAR(d.full_date, 'Mon') AS label,
            COUNT(f.sk_fact_session_id) AS value,
            EXTRACT(MONTH FROM d.full_date) AS sort_key
            {group_select}
        FROM dw.fact_session f
        LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        {where_clause}
        GROUP BY TO_CHAR(d.full_date, 'Mon'), EXTRACT(MONTH FROM d.full_date) {", d.year_actual" if compare_year else ""}
        ORDER BY sort_key
        """,
        params,
    )
    return [{
        "label": row["label"], 
        "value": float(row["value"]),
        **({"group": row["group"]} if "group" in row else {})
    } for row in rows]

