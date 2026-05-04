import logging
from backend.services.query_utils import fetch_all, fetch_one
from backend.config import DATAMART_SCHEMA_NAME

logger = logging.getLogger(__name__)
DW = DATAMART_SCHEMA_NAME


def get_performance_mgmt_filters(region=None, year=None):
    from backend.services.query_utils import get_list_filter_clause
    try:
        # 1. Available Years (always shown based on all fact data)
        years = [r["year_actual"] for r in fetch_all(
            f"SELECT DISTINCT d.year_actual FROM {DW}.fact_session f JOIN {DW}.dim_date d ON f.date_id = d.date_id ORDER BY d.year_actual DESC"
        )]

        # 2. Available Regions (filtered by selected year)
        y_clauses, y_params = get_list_filter_clause("d.year_actual", year, cast_type="int")
        regions = [r["region_name"] for r in fetch_all(f"""
            SELECT DISTINCT g.region_name 
            FROM {DW}.fact_session f 
            JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            JOIN {DW}.dim_date d ON f.date_id = d.date_id
            WHERE {y_clauses} AND g.region_name IS NOT NULL
            ORDER BY g.region_name
        """, y_params)]

        # 3. Available Months (filtered by selected year AND region)
        m_clauses = []
        m_params = []
        c, p = get_list_filter_clause("d.year_actual", year, cast_type="int"); m_clauses.append(c); m_params.extend(p)
        c, p = get_list_filter_clause("g.region_name", region); m_clauses.append(c); m_params.extend(p)
        m_where = " AND ".join(m_clauses) if m_clauses else "TRUE"

        months = [{"id": r["month_actual"], "name": r["month_name"].strip()} for r in fetch_all(f"""
            SELECT DISTINCT d.month_actual, TO_CHAR(TO_DATE(d.month_actual::text,'MM'),'Month') AS month_name 
            FROM {DW}.fact_session f
            JOIN {DW}.dim_date d ON f.date_id = d.date_id
            JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            WHERE {m_where}
            ORDER BY d.month_actual
        """, m_params)]

        quarters = [1, 2, 3, 4]
        return {"regions": regions, "years": years, "months": months, "quarters": quarters}
    except Exception as e:
        logger.error(f"performance mgmt filters error: {e}")
        return {"regions": [], "years": [], "months": [], "quarters": []}


def get_performance_mgmt_data(region=None, year=None, month=None, quarter=None, limit=15, offset=0, dt_params=None, period=None, group_by="month"):
    from backend.services.query_utils import parse_datatables_params, get_datatables_sql, get_list_filter_clause
    try:
        clauses = []
        params = []
        
        c, p = get_list_filter_clause("g.region_name", region)
        clauses.append(c); params.extend(p)
        
        c, p = get_list_filter_clause("d.year_actual", year, cast_type="int")
        clauses.append(c); params.extend(p)
        
        # Quarter Filter (Fiscal)
        fiscal_q_expr = "CASE WHEN d.month_actual IN (4,5,6) THEN 1 WHEN d.month_actual IN (7,8,9) THEN 2 WHEN d.month_actual IN (10,11,12) THEN 3 ELSE 4 END"
        c, p = get_list_filter_clause(fiscal_q_expr, quarter, cast_type="int")
        clauses.append(c); params.extend(p)
        
        c, p = get_list_filter_clause("d.month_actual", month, cast_type="int")
        clauses.append(c); params.extend(p)
        
        # Parse period label for drilldown filter
        if group_by == "month" and period:
            parts = period.split(" ")
            if len(parts) == 2:
                clauses.append("TO_CHAR(TO_DATE(d.month_actual::text,'MM'),'Mon') = %s")
                params.append(parts[0])
                clauses.append("d.year_actual = %s")
                params.append(int(parts[1]))
        elif group_by == "quarter" and period:
            parts = period.split(" ")
            if len(parts) == 2:
                q_val = int(parts[0].replace('Q', ''))
                y_val = int(parts[1])
                clauses.append("CASE WHEN d.month_actual IN (4,5,6) THEN 1 WHEN d.month_actual IN (7,8,9) THEN 2 WHEN d.month_actual IN (10,11,12) THEN 3 ELSE 4 END = %s")
                params.append(q_val)
                clauses.append("CASE WHEN d.month_actual >= 4 THEN d.year_actual ELSE d.year_actual - 1 END = %s")
                params.append(y_val)
        elif group_by == "year" and period:
            clauses.append("d.year_actual = %s")
            params.append(int(period))
        
        where_sql = " AND ".join(clauses) if clauses else "TRUE"

        # KPI Query
        kpi_row = fetch_one(f"""
            SELECT
                COUNT(DISTINCT f.sk_user_id)                   AS total_instructors,
                COUNT(DISTINCT f.sk_fact_session_id)           AS total_sessions,
                COALESCE(SUM(e.total_exposure_count), 0)       AS total_students
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d       ON f.date_id = d.date_id
            LEFT JOIN {DW}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            WHERE {where_sql}
        """, params)

        total_instructors = int(kpi_row.get("total_instructors", 0) or 0)
        total_sessions    = int(kpi_row.get("total_sessions", 0) or 0)
        avg_per_inst      = round(total_sessions / total_instructors, 1) if total_instructors else 0

        # Insight Logic (Top Region)
        top_region_row = fetch_one(f"""
            SELECT COALESCE(g.region_name, 'Unknown') as region_name, 
                   COUNT(DISTINCT f.sk_fact_session_id) as sessions,
                   COALESCE(SUM(e.total_exposure_count), 0) as students,
                   COUNT(DISTINCT f.sk_user_id) as instructors
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d ON f.date_id = d.date_id
            LEFT JOIN {DW}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            WHERE {where_sql}
            GROUP BY g.region_name
            ORDER BY sessions DESC
            LIMIT 1
        """, params)
        
        top_region = top_region_row.get("region_name", "N/A") if top_region_row else "N/A"
        top_sessions = int(top_region_row.get("sessions", 0)) if top_region_row else 0
        top_students = int(top_region_row.get("students", 0)) if top_region_row else 0
        top_instructors = int(top_region_row.get("instructors", 0)) if top_region_row else 0

        # Build Status & Reasons dynamically
        sess_status = "High" if total_sessions > 500 else ("Low/Decline" if total_sessions < 100 else "Average")
        sess_reason = f"Excellent execution driven by {top_region}." if sess_status == "High" else (
                      f"Lower volume across regions; {top_region} led with only {top_sessions} sessions." if sess_status == "Low/Decline" else 
                      "Consistent performance inline with expectations.")
                      
        inst_status = "Stable"
        inst_reason = f"Active participation across regions, led by {top_region} ({top_instructors} active)."
        
        avg_status = "High" if avg_per_inst >= 20 else ("Low/Decline" if avg_per_inst < 10 else "Average")
        avg_reason = "Instructors are highly engaged and delivering frequently." if avg_status == "High" else (
                     "Instructor engagement has dropped, pulling down average delivery." if avg_status == "Low/Decline" else 
                     "Steady delivery rate per instructor.")
                     
        stu_status = "High" if int(kpi_row.get("total_students", 0) or 0) > 10000 else "Average"
        stu_reason = f"Strong attendance, majorly supported by {top_region} ({top_students} students)."

        # Trend Calculation (Period-over-Period)
        # We need to find the previous period based on the current filters
        prev_where_sql = "TRUE"
        prev_params = []
        
        # Simple implementation: If one year is selected, compare to previous year.
        # If one month is selected, compare to previous month.
        if year and len(year) == 1 and (not month or len(month) == 0):
            prev_year = [str(int(year[0]) - 1)]
            c, p = get_list_filter_clause("g.region_name", region); prev_params.extend(p)
            c, p = get_list_filter_clause("d.year_actual", prev_year, cast_type="int"); prev_params.extend(p)
            prev_where_sql = " AND ".join([get_list_filter_clause("g.region_name", region)[0], get_list_filter_clause("d.year_actual", prev_year, cast_type="int")[0]])
        elif month and len(month) == 1 and year and len(year) == 1:
            m_val = int(month[0])
            y_val = int(year[0])
            prev_m = m_val - 1
            prev_y = y_val
            if prev_m == 0:
                prev_m = 12
                prev_y = y_val - 1
            
            c, p = get_list_filter_clause("g.region_name", region); prev_params.extend(p)
            prev_params.append(prev_y)
            prev_params.append(prev_m)
            prev_where_sql = get_list_filter_clause("g.region_name", region)[0] + " AND d.year_actual = %s AND d.month_actual = %s"
        
        prev_kpi_row = fetch_one(f"""
            SELECT
                COUNT(DISTINCT f.sk_user_id)                   AS total_instructors,
                COUNT(DISTINCT f.sk_fact_session_id)           AS total_sessions,
                COALESCE(SUM(e.total_exposure_count), 0)       AS total_students
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d       ON f.date_id = d.date_id
            LEFT JOIN {DW}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            WHERE {prev_where_sql}
        """, prev_params)

        def calc_trend(curr, prev):
            if not prev: return {"pct": 0, "dir": "neutral"}
            diff = curr - prev
            pct = round((diff / prev) * 100, 1) if prev > 0 else 0
            direction = "up" if diff > 0 else ("down" if diff < 0 else "neutral")
            return {"pct": pct, "dir": direction}

        prev_instructors = int(prev_kpi_row.get("total_instructors", 0) or 0)
        prev_sessions = int(prev_kpi_row.get("total_sessions", 0) or 0)
        prev_avg = round(prev_sessions / prev_instructors, 1) if prev_instructors else 0
        prev_students = int(prev_kpi_row.get("total_students", 0) or 0)

        kpis = [
            {
                "label": "Total Instructors", "value": total_instructors, "icon": "fas fa-users", "color": "bg-info",
                "trend": calc_trend(total_instructors, prev_instructors),
                "insights": {"top_performing": top_region, "status": inst_status, "reason": inst_reason}
            },
            {
                "label": "Avg Sessions/Instructor", "value": avg_per_inst, "icon": "fas fa-chart-line", "color": "bg-success",
                "trend": calc_trend(avg_per_inst, prev_avg),
                "insights": {"top_performing": top_region, "status": avg_status, "reason": avg_reason}
            },
            {
                "label": "Total Sessions", "value": total_sessions, "icon": "fas fa-chalkboard-teacher", "color": "bg-navy-blue",
                "trend": calc_trend(total_sessions, prev_sessions),
                "insights": {"top_performing": top_region, "status": sess_status, "reason": sess_reason}
            },
            {
                "label": "Total Students Impacted", "value": int(kpi_row.get("total_students", 0) or 0), "icon": "fas fa-user-graduate", "color": "bg-danger",
                "trend": calc_trend(int(kpi_row.get("total_students", 0) or 0), prev_students),
                "insights": {"top_performing": top_region, "status": stu_status, "reason": stu_reason}
            },
        ]

        # DataTable Logic
        search_sql = "TRUE"
        search_params = []
        sort_sql = "ORDER BY sessions DESC"
        
        if dt_params:
            searchable_cols = ["u.user_name", "u.role_name", "g.region_name"]
            sortable_cols = ["instructor_name", "role", "region_name", "programs", "sessions", "schools", "students_impacted", "avg_duration_min"]
            
            inner_search_sql, inner_search_params, inner_sort_sql = get_datatables_sql(dt_params, searchable_cols, sortable_cols)
            search_sql = inner_search_sql
            search_params = inner_search_params
            if inner_sort_sql:
                sort_sql = inner_sort_sql

        # Get total count (Filtered by sidebar AND table search)
        count_sql = f"""
            SELECT COUNT(*) FROM (
                SELECT u.user_name
                FROM {DW}.fact_session f
                LEFT JOIN {DW}.dim_user u       ON f.sk_user_id = u.sk_user_id
                LEFT JOIN {DW}.dim_geography g  ON f.sk_geography_id = g.sk_geography_id
                LEFT JOIN {DW}.dim_date d       ON f.date_id = d.date_id
                WHERE {where_sql} AND {search_sql}
                GROUP BY u.user_name, u.role_name, g.region_name
            ) as sub
        """
        total_count = fetch_one(count_sql, params + search_params).get("count", 0)

        # Get paginated data
        table = fetch_all(f"""
            SELECT
                COALESCE(u.user_name, 'Unknown')                   AS instructor_name,
                COALESCE(u.role_name, 'Unknown')                   AS role,
                COALESCE(g.region_name, 'Unknown')                 AS region_name,
                COUNT(DISTINCT f.sk_program_id)                    AS programs,
                COUNT(DISTINCT f.sk_fact_session_id)               AS sessions,
                COUNT(DISTINCT f.sk_school_id)                     AS schools,
                COALESCE(SUM(e.total_exposure_count), 0)           AS students_impacted,
                ROUND(AVG(COALESCE(f.session_duration_minutes,0)),1) AS avg_duration_min
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_user u       ON f.sk_user_id = u.sk_user_id
            LEFT JOIN {DW}.dim_geography g  ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d       ON f.date_id = d.date_id
            LEFT JOIN {DW}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            WHERE {where_sql} AND {search_sql}
            GROUP BY u.user_name, u.role_name, g.region_name
            {sort_sql}
            LIMIT %s OFFSET %s
        """, params + search_params + [limit, offset])

        return {
            "kpis": kpis,
            "table": table,
            "recordsTotal": int(total_count),
            "recordsFiltered": int(total_count)
        }
    except Exception as e:
        logger.error(f"performance mgmt data error: {e}", exc_info=True)
        return {
            "kpis": [],
            "table": [],
            "recordsTotal": 0,
            "recordsFiltered": 0
        }


def get_performance_mgmt_chart_data(
    region=None, year=None, month=None, quarter=None,
    group_by="month"  # 'day', 'month', 'quarter', 'year'
):
    """Returns session trend data (actual + computed target + daily hi/lo) for candlestick chart."""
    from backend.services.query_utils import get_list_filter_clause
    try:
        clauses, params = [], []
        c, p = get_list_filter_clause("g.region_name", region); clauses.append(c); params.extend(p)
        c, p = get_list_filter_clause("d.year_actual", year, cast_type="int"); clauses.append(c); params.extend(p)
        c, p = get_list_filter_clause("d.month_actual", month, cast_type="int"); clauses.append(c); params.extend(p)
        
        fiscal_q_expr = "CASE WHEN d.month_actual IN (4,5,6) THEN 1 WHEN d.month_actual IN (7,8,9) THEN 2 WHEN d.month_actual IN (10,11,12) THEN 3 ELSE 4 END"
        c, p = get_list_filter_clause(fiscal_q_expr, quarter, cast_type="int"); clauses.append(c); params.extend(p)
        where = " AND ".join(clauses)

        # Choose grouping dimension
        if group_by == "day":
            label_expr = "TO_CHAR(d.full_date, 'DD Mon YYYY')"
            sort_expr  = "MIN(d.full_date)"
            grp_expr   = "d.full_date"
        elif group_by == "quarter":
            fiscal_y_expr = "CASE WHEN d.month_actual >= 4 THEN d.year_actual ELSE d.year_actual - 1 END"
            label_expr = "'Q' || " + fiscal_q_expr + " || ' ' || " + fiscal_y_expr
            sort_expr  = "MIN(d.full_date)"
            grp_expr   = fiscal_q_expr + ", " + fiscal_y_expr
        elif group_by == "year":
            label_expr = "d.year_actual::text"
            sort_expr  = "d.year_actual"
            grp_expr   = "d.year_actual"
        else:  # month (default)
            label_expr = "TO_CHAR(TO_DATE(d.month_actual::text, 'MM'), 'Mon') || ' ' || d.year_actual"
            sort_expr  = "MIN(d.full_date)"
            grp_expr   = "d.month_actual, d.year_actual"

        rows = fetch_all(f"""
            SELECT
                {label_expr}                              AS period_label,
                {sort_expr}                               AS sort_key,
                COUNT(DISTINCT f.sk_fact_session_id)      AS actual_sessions,
                MAX(daily.day_sessions)                   AS high_sessions,
                MIN(daily.day_sessions)                   AS low_sessions
            FROM {DW}.fact_session f
            JOIN {DW}.dim_date d       ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            JOIN (
                SELECT date_id, COUNT(DISTINCT sk_fact_session_id) AS day_sessions
                FROM {DW}.fact_session
                GROUP BY date_id
            ) daily ON f.date_id = daily.date_id
            WHERE {where}
            GROUP BY {grp_expr}
            ORDER BY sort_key
        """, params)

        # Compute target = 110% of prior period actual (first period target = 0)
        result = []
        for i, r in enumerate(rows):
            actual = int(r["actual_sessions"] or 0)
            if i == 0:
                target = round(actual * 0.9)  # first bar: 90% as soft target baseline
            else:
                target = round(int(rows[i - 1]["actual_sessions"] or 0) * 1.1)
            result.append({
                "label":   r["period_label"],
                "actual":  actual,
                "target":  target,
                "high":    int(r["high_sessions"] or actual),
                "low":     int(r["low_sessions"] or actual),
                "open":    target,   # candlestick open = target
                "close":   actual,   # candlestick close = actual
                "met":     actual >= target,
            })
        return {"data": result, "group_by": group_by}
    except Exception as e:
        logger.error(f"chart_data error: {e}", exc_info=True)
        return {"data": [], "group_by": group_by}

def get_performance_mgmt_region_chart(
    region=None, year=None, month=None, quarter=None, period=None, group_by="month"
):
    """Returns top 5 regions by sessions and students impacted for an insightful secondary chart."""
    from backend.services.query_utils import get_list_filter_clause
    try:
        clauses, params = [], []
        c, p = get_list_filter_clause("g.region_name", region); clauses.append(c); params.extend(p)
        c, p = get_list_filter_clause("d.year_actual", year, cast_type="int"); clauses.append(c); params.extend(p)
        c, p = get_list_filter_clause("d.month_actual", month, cast_type="int"); clauses.append(c); params.extend(p)
        
        fiscal_q_expr = "CASE WHEN d.month_actual IN (4,5,6) THEN 1 WHEN d.month_actual IN (7,8,9) THEN 2 WHEN d.month_actual IN (10,11,12) THEN 3 ELSE 4 END"
        c, p = get_list_filter_clause(fiscal_q_expr, quarter, cast_type="int"); clauses.append(c); params.extend(p)
        
        # Parse period label for drilldown filter if it exists
        if group_by == "month" and period:
            parts = period.split(" ")
            if len(parts) == 2:
                clauses.append("TO_CHAR(TO_DATE(d.month_actual::text,'MM'),'Mon') = %s")
                params.append(parts[0])
                clauses.append("d.year_actual = %s")
                params.append(int(parts[1]))
        elif group_by == "quarter" and period:
            parts = period.split(" ")
            if len(parts) == 2:
                q_val = int(parts[0].replace('Q', ''))
                y_val = int(parts[1])
                clauses.append("CASE WHEN d.month_actual IN (4,5,6) THEN 1 WHEN d.month_actual IN (7,8,9) THEN 2 WHEN d.month_actual IN (10,11,12) THEN 3 ELSE 4 END = %s")
                params.append(q_val)
                clauses.append("CASE WHEN d.month_actual >= 4 THEN d.year_actual ELSE d.year_actual - 1 END = %s")
                params.append(y_val)
        elif group_by == "year" and period:
            clauses.append("d.year_actual = %s")
            params.append(int(period))

        where_sql = " AND ".join(clauses) if clauses else "TRUE"

        query = f"""
            SELECT 
                COALESCE(g.region_name, 'Unknown') as region_name,
                COUNT(DISTINCT f.sk_fact_session_id) as sessions,
                COALESCE(SUM(e.total_exposure_count), 0) as students
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d ON f.date_id = d.date_id
            LEFT JOIN {DW}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            WHERE {where_sql}
            GROUP BY g.region_name
            ORDER BY sessions DESC
        """
        
        data = fetch_all(query, params)
        return {"data": data}
    except Exception as e:
        logger.error(f"region_chart error: {e}", exc_info=True)
        return {"data": []}


def get_performance_mgmt_drilldown(
    period_label: str,
    group_by: str = "month",
    region=None, year=None
):
    """Returns instructor-level breakdown for a clicked chart bar."""
    from backend.services.query_utils import get_list_filter_clause
    try:
        clauses, params = [], []
        if region:
            region_list = [region] if isinstance(region, str) else region
            # Normalize both sides: lowercase and replace underscores with spaces for consistent matching
            clauses.append("REPLACE(LOWER(g.region_name), '_', ' ') = ANY(%s)")
            params.append([r.lower().replace("_", " ") for r in region_list])
        
        c, p = get_list_filter_clause("d.year_actual", year, cast_type="int"); clauses.append(c); params.extend(p)

        # Parse period label for date filter
        months_short = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        if group_by == "month" and period_label:
            parts = period_label.split(" ")
            if len(parts) == 2 and parts[0] in months_short:
                clauses.append("TO_CHAR(TO_DATE(d.month_actual::text,'MM'),'Mon') = %s")
                params.append(parts[0])
                clauses.append("d.year_actual = %s")
                params.append(int(parts[1]))
        elif group_by == "quarter" and period_label:
            parts = period_label.split(" ")
            if len(parts) == 2:
                q_val = int(parts[0].replace('Q', ''))
                y_val = int(parts[1])
                clauses.append("CASE WHEN d.month_actual IN (4,5,6) THEN 1 WHEN d.month_actual IN (7,8,9) THEN 2 WHEN d.month_actual IN (10,11,12) THEN 3 ELSE 4 END = %s")
                params.append(q_val)
                clauses.append("CASE WHEN d.month_actual >= 4 THEN d.year_actual ELSE d.year_actual - 1 END = %s")
                params.append(y_val)
        elif group_by == "year" and period_label:
            clauses.append("d.year_actual = %s")
            params.append(int(period_label))

        where = " AND ".join(clauses) if clauses else "TRUE"

        table = fetch_all(f"""
            SELECT
                COALESCE(u.user_name, 'Unknown')                   AS instructor_name,
                COALESCE(u.role_name, 'Unknown')                   AS role,
                COALESCE(g.region_name, 'Unknown')                 AS region_name,
                COUNT(DISTINCT f.sk_program_id)                    AS programs,
                COUNT(DISTINCT f.sk_fact_session_id)               AS sessions,
                COUNT(DISTINCT f.sk_school_id)                     AS schools,
                COALESCE(SUM(e.total_exposure_count), 0)           AS students_impacted,
                ROUND(AVG(COALESCE(f.session_duration_minutes,0)),1) AS avg_duration_min
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_user u       ON f.sk_user_id = u.sk_user_id
            LEFT JOIN {DW}.dim_geography g  ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d       ON f.date_id = d.date_id
            LEFT JOIN {DW}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            WHERE {where}
            GROUP BY u.user_name, u.role_name, g.region_name
            ORDER BY sessions DESC
            LIMIT 50
        """, params)
        return {"table": table, "period": period_label}
    except Exception as e:
        logger.error(f"drilldown error: {e}", exc_info=True)
        return {"table": [], "period": period_label}
