import logging
from backend.services.query_utils import fetch_all, fetch_one, get_list_filter_clause, get_datatables_sql
from backend.config import DATAMART_SCHEMA_NAME

logger = logging.getLogger(__name__)
DW = DATAMART_SCHEMA_NAME


def _build_clauses(region=None, year=None, program=None):
    clauses, params = [], []
    c, p = get_list_filter_clause("g.region_name", region); clauses.append(c); params.extend(p)
    c, p = get_list_filter_clause("d.year_actual", year, cast_type="int"); clauses.append(c); params.extend(p)
    c, p = get_list_filter_clause("p.program_name", program); clauses.append(c); params.extend(p)
    return " AND ".join(clauses), params


# ═══════════════════════════════════════════════════════════════
#  INSTRUCTOR PERFORMANCE OVERVIEW
# ═══════════════════════════════════════════════════════════════

def get_instructor_overview(region=None, year=None, program=None, limit=15, offset=0, dt_params=None):
    where_sql, params = _build_clauses(region, year, program)
    try:
        # KPIs
        kpi = fetch_one(f"""
            SELECT
                COUNT(DISTINCT f.sk_user_id)              AS total_instructors,
                COUNT(DISTINCT f.sk_fact_session_id)       AS total_sessions,
                COALESCE(SUM(e.total_exposure_count), 0)   AS total_students
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d      ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_program p   ON f.sk_program_id = p.sk_program_id
            LEFT JOIN {DW}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            WHERE {where_sql}
        """, params)

        ti = int(kpi.get("total_instructors", 0) or 0)
        ts = int(kpi.get("total_sessions", 0) or 0)
        stu = int(kpi.get("total_students", 0) or 0)
        avg = round(ts / ti, 1) if ti else 0

        kpis = [
            {"label": "Total Instructors", "value": ti, "icon": "fas fa-users", "color": "#17a2b8"},
            {"label": "Sessions Conducted", "value": ts, "icon": "fas fa-chalkboard", "color": "#28a745"},
            {"label": "Avg / Instructor", "value": avg, "icon": "fas fa-chart-line", "color": "#001f3f"},
            {"label": "Students Impacted", "value": stu, "icon": "fas fa-user-graduate", "color": "#dc3545"},
        ]

        # Chart 1 – Sessions by Instructor Type (doughnut)
        type_rows = fetch_all(f"""
            SELECT COALESCE(NULLIF(INITCAP(TRIM(u.role_name)),''), 'Unknown') AS label,
                   COUNT(DISTINCT f.sk_fact_session_id) AS value
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_user u      ON f.sk_user_id = u.sk_user_id
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d      ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_program p   ON f.sk_program_id = p.sk_program_id
            WHERE {where_sql}
            GROUP BY u.role_name ORDER BY value DESC LIMIT 8
        """, params)

        # Chart 2 – Monthly sessions trend (line)
        trend_rows = fetch_all(f"""
            SELECT TO_CHAR(d.full_date, 'Mon YYYY') AS label,
                   COUNT(DISTINCT f.sk_fact_session_id) AS value,
                   MIN(d.full_date) AS sort_key
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_date d      ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_program p   ON f.sk_program_id = p.sk_program_id
            WHERE {where_sql}
            GROUP BY TO_CHAR(d.full_date, 'Mon YYYY')
            ORDER BY sort_key
        """, params)

        # Chart 3 – Top regions by sessions (horizontal bar)
        region_rows = fetch_all(f"""
            SELECT COALESCE(g.region_name, 'Unknown') AS label,
                   COUNT(DISTINCT f.sk_fact_session_id) AS value
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d      ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_program p   ON f.sk_program_id = p.sk_program_id
            WHERE {where_sql} AND g.region_name IS NOT NULL
            GROUP BY g.region_name ORDER BY value DESC LIMIT 8
        """, params)

        charts = {
            "by_type":   [{"label": r["label"], "value": int(r["value"])} for r in type_rows],
            "trend":     [{"label": r["label"], "value": int(r["value"])} for r in trend_rows],
            "by_region": [{"label": r["label"], "value": int(r["value"])} for r in region_rows],
        }

        # Table – top instructors
        search_sql, search_params = "TRUE", []
        sort_sql = "ORDER BY sessions DESC"
        if dt_params:
            s, sp, so = get_datatables_sql(dt_params, ["u.user_name", "u.role_name", "g.region_name"],
                                           ["name", "role", "region", "sessions", "students", "schools"])
            search_sql, search_params = s, sp
            if so: sort_sql = so

        count = fetch_one(f"""
            SELECT COUNT(*) FROM (
                SELECT u.sk_user_id FROM {DW}.fact_session f
                LEFT JOIN {DW}.dim_user u ON f.sk_user_id = u.sk_user_id
                LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
                LEFT JOIN {DW}.dim_date d ON f.date_id = d.date_id
                LEFT JOIN {DW}.dim_program p ON f.sk_program_id = p.sk_program_id
                WHERE {where_sql} AND {search_sql}
                GROUP BY u.sk_user_id
            ) sub
        """, params + search_params).get("count", 0)

        table = fetch_all(f"""
            SELECT COALESCE(u.user_name,'Unknown') AS name,
                   COALESCE(INITCAP(u.role_name),'Unknown') AS role,
                   COALESCE(g.region_name,'Unknown') AS region,
                   COUNT(DISTINCT f.sk_fact_session_id) AS sessions,
                   COALESCE(SUM(e.total_exposure_count),0) AS students,
                   COUNT(DISTINCT f.sk_school_id) AS schools
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_user u ON f.sk_user_id = u.sk_user_id
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_program p ON f.sk_program_id = p.sk_program_id
            LEFT JOIN {DW}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            WHERE {where_sql} AND {search_sql}
            GROUP BY u.sk_user_id, u.user_name, u.role_name, g.region_name
            {sort_sql} LIMIT %s OFFSET %s
        """, params + search_params + [limit, offset])

        return {"kpis": kpis, "charts": charts, "table": table, "total_count": int(count)}
    except Exception as ex:
        logger.error(f"instructor overview error: {ex}", exc_info=True)
        return {"kpis": [], "charts": {}, "table": [], "total_count": 0}


# ═══════════════════════════════════════════════════════════════
#  PROGRAM IMPACT OVERVIEW
# ═══════════════════════════════════════════════════════════════

def get_program_impact_overview(region=None, year=None, program=None, limit=15, offset=0, dt_params=None):
    where_sql, params = _build_clauses(region, year, program)
    try:
        kpi = fetch_one(f"""
            SELECT COUNT(DISTINCT p.program_name) AS total_programs,
                   COUNT(DISTINCT f.sk_school_id) AS total_schools,
                   COALESCE(SUM(e.total_exposure_count),0) AS total_students,
                   COUNT(DISTINCT f.sk_fact_session_id) AS total_sessions
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_program p ON f.sk_program_id = p.sk_program_id
            LEFT JOIN {DW}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            WHERE {where_sql}
        """, params)

        kpis = [
            {"label": "Total Programs", "value": int(kpi.get("total_programs",0) or 0), "icon": "fas fa-project-diagram", "color": "#17a2b8"},
            {"label": "Schools Reached", "value": int(kpi.get("total_schools",0) or 0), "icon": "fas fa-school", "color": "#28a745"},
            {"label": "Students Reached", "value": int(kpi.get("total_students",0) or 0), "icon": "fas fa-user-graduate", "color": "#001f3f"},
            {"label": "Total Sessions", "value": int(kpi.get("total_sessions",0) or 0), "icon": "fas fa-chalkboard-teacher", "color": "#dc3545"},
        ]

        # Chart 1 – Sessions by Program (doughnut)
        prog_rows = fetch_all(f"""
            SELECT COALESCE(p.program_name,'Unknown') AS label,
                   COUNT(DISTINCT f.sk_fact_session_id) AS value
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_program p ON f.sk_program_id = p.sk_program_id
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d ON f.date_id = d.date_id
            WHERE {where_sql}
            GROUP BY p.program_name ORDER BY value DESC LIMIT 8
        """, params)

        # Chart 2 – Monthly student reach (line)
        trend_rows = fetch_all(f"""
            SELECT TO_CHAR(d.full_date, 'Mon YYYY') AS label,
                   COALESCE(SUM(e.total_exposure_count),0) AS value,
                   MIN(d.full_date) AS sort_key
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_date d ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_program p ON f.sk_program_id = p.sk_program_id
            LEFT JOIN {DW}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            WHERE {where_sql}
            GROUP BY TO_CHAR(d.full_date, 'Mon YYYY')
            ORDER BY sort_key
        """, params)

        # Chart 3 – Top regions by students (horizontal bar)
        region_rows = fetch_all(f"""
            SELECT COALESCE(g.region_name,'Unknown') AS label,
                   COALESCE(SUM(e.total_exposure_count),0) AS value
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_program p ON f.sk_program_id = p.sk_program_id
            LEFT JOIN {DW}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            WHERE {where_sql} AND g.region_name IS NOT NULL
            GROUP BY g.region_name ORDER BY value DESC LIMIT 8
        """, params)

        charts = {
            "by_program": [{"label": r["label"], "value": int(r["value"])} for r in prog_rows],
            "trend":      [{"label": r["label"], "value": int(r["value"])} for r in trend_rows],
            "by_region":  [{"label": r["label"], "value": int(r["value"])} for r in region_rows],
        }

        # Table – program summary
        search_sql, search_params = "TRUE", []
        sort_sql = "ORDER BY sessions DESC"
        if dt_params:
            s, sp, so = get_datatables_sql(dt_params, ["p.program_name", "p.donor_name", "g.region_name"],
                                           ["program", "donor", "sessions", "schools", "students", "instructors"])
            search_sql, search_params = s, sp
            if so: sort_sql = so

        count = fetch_one(f"""
            SELECT COUNT(*) FROM (
                SELECT p.sk_program_id FROM {DW}.fact_session f
                LEFT JOIN {DW}.dim_program p ON f.sk_program_id = p.sk_program_id
                LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
                LEFT JOIN {DW}.dim_date d ON f.date_id = d.date_id
                WHERE {where_sql} AND {search_sql}
                GROUP BY p.sk_program_id
            ) sub
        """, params + search_params).get("count", 0)

        table = fetch_all(f"""
            SELECT COALESCE(p.program_name,'Unknown') AS program,
                   COALESCE(p.donor_name,'Unknown') AS donor,
                   COUNT(DISTINCT f.sk_fact_session_id) AS sessions,
                   COUNT(DISTINCT f.sk_school_id) AS schools,
                   COALESCE(SUM(e.total_exposure_count),0) AS students,
                   COUNT(DISTINCT f.sk_user_id) AS instructors
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_program p ON f.sk_program_id = p.sk_program_id
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d ON f.date_id = d.date_id
            LEFT JOIN {DW}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            WHERE {where_sql} AND {search_sql}
            GROUP BY p.sk_program_id, p.program_name, p.donor_name
            {sort_sql} LIMIT %s OFFSET %s
        """, params + search_params + [limit, offset])

        return {"kpis": kpis, "charts": charts, "table": table, "total_count": int(count)}
    except Exception as ex:
        logger.error(f"program impact overview error: {ex}", exc_info=True)
        return {"kpis": [], "charts": {}, "table": [], "total_count": 0}


# ═══════════════════════════════════════════════════════════════
#  OPERATIONS OVERVIEW
# ═══════════════════════════════════════════════════════════════

def get_operations_overview(region=None, year=None, program=None, limit=15, offset=0, dt_params=None):
    where_sql, params = _build_clauses(region, year, program)
    try:
        # KPIs – combine session + vehicle facts
        sess_kpi = fetch_one(f"""
            SELECT COUNT(DISTINCT CONCAT(f.sk_user_id,'_',f.date_id)) AS working_days,
                   COUNT(DISTINCT f.sk_geography_id) AS active_centers
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_program p ON f.sk_program_id = p.sk_program_id
            WHERE {where_sql}
        """, params)

        # Vehicle KPIs – need separate where without program filter on vehicle table
        veh_where, veh_params = [], []
        c, p = get_list_filter_clause("g.region_name", region); veh_where.append(c); veh_params.extend(p)
        c, p = get_list_filter_clause("d.year_actual", year, cast_type="int"); veh_where.append(c); veh_params.extend(p)
        veh_where_sql = " AND ".join(veh_where)

        veh_kpi = fetch_one(f"""
            SELECT COUNT(DISTINCT v.sk_driver_id) AS active_drivers,
                   COALESCE(SUM(v.distance_travelled),0) AS total_kms
            FROM {DW}.fact_vehicle_operations v
            LEFT JOIN {DW}.dim_geography g ON v.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d ON v.date_id = d.date_id
            WHERE {veh_where_sql}
        """, veh_params)

        kpis = [
            {"label": "Total Working Days", "value": int(sess_kpi.get("working_days",0) or 0), "icon": "fas fa-calendar-check", "color": "#17a2b8"},
            {"label": "Active Drivers", "value": int(veh_kpi.get("active_drivers",0) or 0), "icon": "fas fa-truck", "color": "#28a745"},
            {"label": "Total KMs Travelled", "value": int(veh_kpi.get("total_kms",0) or 0), "icon": "fas fa-road", "color": "#001f3f"},
            {"label": "Active Centers", "value": int(sess_kpi.get("active_centers",0) or 0), "icon": "fas fa-map-marker-alt", "color": "#dc3545"},
        ]

        # Chart 1 – KMs by region (horizontal bar)
        km_rows = fetch_all(f"""
            SELECT COALESCE(g.region_name,'Unknown') AS label,
                   COALESCE(SUM(v.distance_travelled),0) AS value
            FROM {DW}.fact_vehicle_operations v
            LEFT JOIN {DW}.dim_geography g ON v.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d ON v.date_id = d.date_id
            WHERE {veh_where_sql} AND g.region_name IS NOT NULL
            GROUP BY g.region_name ORDER BY value DESC LIMIT 8
        """, veh_params)

        # Chart 2 – Working days trend (line)
        trend_rows = fetch_all(f"""
            SELECT TO_CHAR(d.full_date, 'Mon YYYY') AS label,
                   COUNT(DISTINCT CONCAT(f.sk_user_id,'_',f.date_id)) AS value,
                   MIN(d.full_date) AS sort_key
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_date d ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_program p ON f.sk_program_id = p.sk_program_id
            WHERE {where_sql}
            GROUP BY TO_CHAR(d.full_date, 'Mon YYYY')
            ORDER BY sort_key
        """, params)

        # Chart 3 – Vehicle usage by region (doughnut)
        veh_rows = fetch_all(f"""
            SELECT COALESCE(g.region_name,'Unknown') AS label,
                   COUNT(CASE WHEN v.was_vehicle_used THEN 1 END) AS value
            FROM {DW}.fact_vehicle_operations v
            LEFT JOIN {DW}.dim_geography g ON v.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d ON v.date_id = d.date_id
            WHERE {veh_where_sql} AND g.region_name IS NOT NULL
            GROUP BY g.region_name ORDER BY value DESC LIMIT 8
        """, veh_params)

        charts = {
            "km_by_region":  [{"label": r["label"], "value": int(r["value"])} for r in km_rows],
            "trend":         [{"label": r["label"], "value": int(r["value"])} for r in trend_rows],
            "vehicle_usage": [{"label": r["label"], "value": int(r["value"])} for r in veh_rows],
        }

        # Table – regional operations summary
        search_sql, search_params = "TRUE", []
        sort_sql = "ORDER BY working_days DESC"
        if dt_params:
            s, sp, so = get_datatables_sql(dt_params, ["g.region_name"],
                                           ["region", "instructors", "working_days", "drivers", "kms", "fuel_cost"])
            search_sql, search_params = s, sp
            if so: sort_sql = so

        count = fetch_one(f"""
            SELECT COUNT(*) FROM (
                SELECT g.region_name FROM {DW}.fact_session f
                LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
                LEFT JOIN {DW}.dim_date d ON f.date_id = d.date_id
                LEFT JOIN {DW}.dim_program p ON f.sk_program_id = p.sk_program_id
                WHERE {where_sql} AND {search_sql} AND g.region_name IS NOT NULL
                GROUP BY g.region_name
            ) sub
        """, params + search_params).get("count", 0)

        table = fetch_all(f"""
            SELECT COALESCE(g.region_name,'Unknown') AS region,
                   COUNT(DISTINCT f.sk_user_id) AS instructors,
                   COUNT(DISTINCT CONCAT(f.sk_user_id,'_',f.date_id)) AS working_days,
                   COUNT(DISTINCT f.sk_school_id) AS schools,
                   COUNT(DISTINCT f.sk_fact_session_id) AS sessions
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_program p ON f.sk_program_id = p.sk_program_id
            WHERE {where_sql} AND {search_sql} AND g.region_name IS NOT NULL
            GROUP BY g.region_name
            {sort_sql} LIMIT %s OFFSET %s
        """, params + search_params + [limit, offset])

        return {"kpis": kpis, "charts": charts, "table": table, "total_count": int(count)}
    except Exception as ex:
        logger.error(f"operations overview error: {ex}", exc_info=True)
        return {"kpis": [], "charts": {}, "table": [], "total_count": 0}
