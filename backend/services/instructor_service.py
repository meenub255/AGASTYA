from backend.services.query_utils import fetch_all, fetch_one
from backend.config import DATAMART_SCHEMA_NAME

def _build_filters(years=None, region=None, program=None, instructor=None, month=None, quarter=None):
    from backend.services.query_utils import build_standard_filters
    where_sql, params, max_month = build_standard_filters(
        years=years,
        region=region,
        program=program,
        month=month,
        quarter=quarter,
        region_expr="g.region_name",
        program_expr="p.program_name"
    )
    if instructor:
        from backend.services.query_utils import get_list_filter_clause
        c, p = get_list_filter_clause("u.role_name", instructor)
        if c != "TRUE":
            if where_sql != "TRUE":
                where_sql += f" AND {c}"
            else:
                where_sql = c
            params.extend(p)
    return where_sql, params

def get_unified_instructor_data(years=None, region=None, program=None, instructor=None, month=None, quarter=None):
    """Unified data for Instructor Dashboard."""
    kpis = get_instructor_kpis(years, region, program, instructor, month, quarter)
    type_breakdown = get_sessions_by_instructor_type(years, region, program, instructor, month, quarter)
    multi_program = get_multi_program_instructors(years, region, program, instructor, month, quarter)
    productivity = get_instructor_productivity(years, region, program, instructor, month, quarter)
    monthly = get_monthly_instructor_activity(years, region, program, instructor, month, quarter)
    
    return {
        "kpis": kpis["kpis"],
        "sparklines": kpis["sparklines"],
        "metrics": kpis["metrics"],
        "type_breakdown": type_breakdown,
        "multi_program": multi_program,
        "productivity": productivity,
        "monthly_activity": monthly
    }

def get_instructor_kpis(years=None, region=None, program=None, instructor=None, month=None, quarter=None) -> dict:
    from backend.services.query_utils import build_standard_filters, get_kpi_insight, calc_trend
    from backend.config import DEFAULT_YEAR
    
    where_sql, params, max_month = build_standard_filters(
        years=years,
        region=region,
        program=program,
        month=month,
        quarter=quarter,
        region_expr="g.region_name",
        program_expr="p.program_name"
    )
    
    effective_years = years
    if effective_years is None or (isinstance(effective_years, list) and len(effective_years) == 0):
        effective_years = [DEFAULT_YEAR]
        
    resolved_years = []
    for y in effective_years:
        try:
            resolved_years.append(int(y))
        except (ValueError, TypeError):
            pass
    if not resolved_years:
        resolved_years = [DEFAULT_YEAR]
        
    prev_year_vals = [y - 1 for y in resolved_years]
    
    prev_where_sql, prev_params, _ = build_standard_filters(
        years=prev_year_vals,
        region=region,
        program=program,
        month=month,
        quarter=quarter,
        region_expr="g.region_name",
        program_expr="p.program_name"
    )
    
    if instructor:
        from backend.services.query_utils import get_list_filter_clause
        inst_clause, inst_params = get_list_filter_clause("u.role_name", instructor)
        if inst_clause != "TRUE":
            where_sql += f" AND {inst_clause}"
            params.extend(inst_params)
            prev_where_sql += f" AND {inst_clause}"
            prev_params.extend(inst_params)

    def query_kpis(w_clause, w_params):
        sql = f"""
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
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON g.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON p.sk_program_id = p.sk_program_id
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_user u ON u.sk_user_id = f.sk_user_id
            WHERE {w_clause}
        """
        row = fetch_one(sql, w_params)
        
        top_region_sql = f"""
            SELECT
                COALESCE(g.region_name, 'Unknown') AS top_region,
                COUNT(f.sk_fact_session_id) AS top_region_sessions
            FROM {DATAMART_SCHEMA_NAME}.fact_session f
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON d.date_id = f.date_id
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON g.sk_geography_id = f.sk_geography_id
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_user u ON u.sk_user_id = f.sk_user_id
            WHERE {w_clause}
            GROUP BY g.region_name
            ORDER BY top_region_sessions DESC, top_region
            LIMIT 1
        """
        tr_row = fetch_one(top_region_sql, w_params)
        
        return {
            "total_instructors": int(row.get("total_instructors", 0) or 0),
            "avg_sessions_per_instructor": round(float(row.get("avg_sessions_per_instructor", 0) or 0), 1),
            "top_region": tr_row.get("top_region", "-") if tr_row else "-",
            "top_region_sessions": int(tr_row.get("top_region_sessions", 0) or 0) if tr_row else 0,
            "unprocessed_sessions": int(row.get("unprocessed_sessions", 0) or 0)
        }

    curr_res = query_kpis(where_sql, params)
    prev_res = query_kpis(prev_where_sql, prev_params)
    
    single_year = resolved_years[0] if len(resolved_years) == 1 else None
    prev_year = single_year - 1 if single_year is not None else None
    
    kpis_meta = [
        {"key": "total_instructors", "label": "Active Instructors", "icon": "fas fa-chalkboard-teacher", "color": "linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%)"},
        {"key": "avg_sessions_per_instructor", "label": "Avg Sessions/Mo", "icon": "fas fa-chart-line", "color": "linear-gradient(135deg, #22c55e 0%, #16a34a 100%)"},
        {"key": "top_region_sessions", "label": "Top Region", "icon": "fas fa-map-marked-alt", "color": "linear-gradient(135deg, #001f3f 0%, #001226 100%)"},
        {"key": "unprocessed_sessions", "label": "Unprocessed", "icon": "fas fa-exclamation-circle", "color": "linear-gradient(135deg, #dc3545 0%, #c82333 100%)"}
    ]
    
    kpi_list = []
    sparklines = {}
    for m in kpis_meta:
        k = m["key"]
        curr_val = float(curr_res.get(k) or 0)
        prev_val = float(prev_res.get(k) or 0)
        if curr_val == int(curr_val): curr_val = int(curr_val)
        if prev_val == int(prev_val): prev_val = int(prev_val)
        
        trend = calc_trend(curr_val, prev_val)
        insights = get_kpi_insight(m["label"], curr_val, prev_val, single_year, prev_year, max_month, month, quarter)
        
        kpi_list.append({
            "label": m["label"],
            "value": curr_val,
            "icon": m["icon"],
            "color": m["color"],
            "trend": trend,
            "insights": insights,
            "trends": [prev_val, curr_val]
        })
        
        sparklines[k.replace("total_", "").replace("_sessions", "").replace("avg_sessions_per_", "avg")] = [prev_val, curr_val]
        
    return {
        "kpis": kpi_list,
        "sparklines": sparklines,
        "metrics": curr_res
    }

def get_instructor_session_log(years=None, region=None, program=None, instructor=None, month=None, quarter=None, limit=10, offset=0, dt_params=None) -> dict:
    from backend.services.query_utils import get_datatables_sql
    where_clause, params = _build_filters(years, region, program, instructor, month, quarter)

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
            COUNT(DISTINCT f.sk_fact_session_id) AS sessions,
            STRING_AGG(DISTINCT COALESCE(act.activity_name, 'NA'), ', ') AS activity_types,
            COALESCE(SUM(fae.total_exposure_count), 0) AS students,
            TO_CHAR(MAX(d.full_date), 'Mon DD') AS last_session
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON d.date_id = f.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_user u ON u.sk_user_id = f.sk_user_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_activity_type act ON f.sk_activity_type_id = act.sk_activity_type_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.fact_attendance_exposure fae ON fae.session_nk_id = f.session_nk_id
        WHERE {where_clause} AND {search_sql}
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
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_user u ON u.sk_user_id = u.sk_user_id
            WHERE {where_clause} AND {search_sql}
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

def get_multi_program_instructors(years=None, region=None, program=None, instructor=None, month=None, quarter=None, limit=5) -> list[dict]:
    where_clause, params = _build_filters(years, region, program, instructor, month, quarter)

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
        WHERE {where_clause}
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

def get_sessions_by_instructor_type(years=None, region=None, program=None, instructor=None, month=None, quarter=None) -> list[dict]:
    where_clause, params = _build_filters(years, region, program, instructor, month, quarter)
    rows = fetch_all(
        f"""
        SELECT
            COALESCE(u.role_name, 'Unknown') AS label,
            COUNT(f.sk_fact_session_id) AS value
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON d.date_id = f.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_user u ON u.sk_user_id = f.sk_user_id
        WHERE {where_clause}
        GROUP BY u.role_name
        ORDER BY value DESC
        """,
        params,
    )
    return [{"label": row["label"], "value": float(row["value"] or 0)} for row in rows]

def get_instructor_productivity(years=None, region=None, program=None, instructor=None, month=None, quarter=None, limit=20) -> list[dict]:
    data = get_instructor_session_log(years=years, region=region, program=program, instructor=instructor, month=month, quarter=quarter, limit=limit)
    return [{"label": row["name"], "value": float(row["sessions"])} for row in data["table"]]

def get_monthly_instructor_activity(years=None, region=None, program=None, instructor=None, month=None, quarter=None) -> list[dict]:
    where_clause, params = _build_filters(years, region, program, instructor, month, quarter)
    rows = fetch_all(
        f"""
        SELECT
            TO_CHAR(d.full_date, 'Mon') AS label,
            COUNT(f.sk_fact_session_id) AS value,
            EXTRACT(MONTH FROM d.full_date) AS sort_key
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON d.date_id = f.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        WHERE {where_clause}
        GROUP BY TO_CHAR(d.full_date, 'Mon'), EXTRACT(MONTH FROM d.full_date)
        ORDER BY sort_key
        """,
        params,
    )
    return [{"label": row["label"], "value": float(row["value"])} for row in rows]
