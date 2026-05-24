import logging
from backend.services.query_utils import fetch_all, fetch_one
from backend.config import DATAMART_SCHEMA_NAME, DEFAULT_YEAR

logger = logging.getLogger(__name__)
DW = DATAMART_SCHEMA_NAME
from datetime import datetime

def currentYearYTD(year: int) -> int:
    """
    Returns the maximum month (1-12) to include in the YTD calculations for the given year.
    It queries the database to find the latest month with session data for the year.
    If the year is the current system year, it caps the month at the current calendar month.
    """
    query = f"""
        SELECT MAX(d.month_actual) AS max_month
        FROM {DW}.fact_session f
        JOIN {DW}.dim_date d ON d.date_id = f.date_id
        WHERE d.year_actual = %s
    """
    row = fetch_one(query, [year])
    max_month = row.get("max_month")
    
    current_yr = datetime.now().year
    current_mo = datetime.now().month
    
    if max_month is None:
        if year == current_yr:
            return current_mo
        return 12
        
    if year == current_yr:
        return min(int(max_month), current_mo)
        
    return int(max_month)

def _apply_ytd_filter(clauses: list[str], params: list, years: list[int] | list[str] | None) -> int | None:
    single_year = None
    if years and len(years) == 1:
        try:
            single_year = int(years[0])
        except (ValueError, TypeError):
            pass
    elif years is None or len(years) == 0:
        single_year = DEFAULT_YEAR

    if single_year is not None:
        max_month = currentYearYTD(single_year)
        clauses.append("d.month_actual <= %s")
        params.append(max_month)
        return max_month
    return None


def get_performance_mgmt_filters(region=None, years=None):
    from backend.services.query_utils import get_list_filter_clause
    try:
        # 1. Available Years (always shown based on all fact data)
        years = [r["year_actual"] for r in fetch_all(
            f"SELECT DISTINCT d.year_actual FROM {DW}.fact_session f JOIN {DW}.dim_date d ON f.date_id = d.date_id ORDER BY d.year_actual DESC"
        )]

        # 2. Available Regions (filtered by selected year)
        y_clauses, y_params = get_list_filter_clause("d.year_actual", years, cast_type="int")
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
        c, p = get_list_filter_clause("d.year_actual", years, cast_type="int"); m_clauses.append(c); m_params.extend(p)
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


def get_performance_mgmt_data(region=None, years=None, month=None, quarter=None, limit=15, offset=0, dt_params=None, period=None, group_by="month"):
    from backend.services.query_utils import parse_datatables_params, get_datatables_sql, get_list_filter_clause
    try:
        clauses = []
        params = []
        
        c, p = get_list_filter_clause("g.region_name", region)
        clauses.append(c); params.extend(p)
        
        # Default to current year if no year provided
        effective_year = [int(y) for y in (years if years is not None and len(years) > 0 else [DEFAULT_YEAR])]
        c, p = get_list_filter_clause("d.year_actual", effective_year, cast_type="int")
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
        
        # Apply YTD month boundary filtering if month and quarter are not specified
        max_month = None
        if not month and not quarter:
            max_month = _apply_ytd_filter(clauses, params, effective_year)

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
        total_students_val = int(kpi_row.get("total_students", 0) or 0)

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
                     
        stu_status = "High" if total_students_val > 10000 else "Average"
        stu_reason = f"Strong attendance, majorly supported by {top_region} ({top_students} students)."

        # Previous Year same period
        prev_clauses = []
        prev_params = []
        
        c, p = get_list_filter_clause("g.region_name", region)
        prev_clauses.append(c); prev_params.extend(p)
        
        # Subtract 1 from all selected years
        prev_year_vals = [y - 1 for y in effective_year]
        c, p = get_list_filter_clause("d.year_actual", prev_year_vals, cast_type="int")
        prev_clauses.append(c); prev_params.extend(p)
        
        c, p = get_list_filter_clause(fiscal_q_expr, quarter, cast_type="int")
        prev_clauses.append(c); prev_params.extend(p)
        
        c, p = get_list_filter_clause("d.month_actual", month, cast_type="int")
        prev_clauses.append(c); prev_params.extend(p)
        
        # Apply the SAME YTD month boundary of the current year to the previous year
        if not month and not quarter:
            _apply_ytd_filter(prev_clauses, prev_params, effective_year)
            
        prev_where_sql = " AND ".join(prev_clauses) if prev_clauses else "TRUE"

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

        # Trend percentages using cumulative YTD totals
        trend_instructors = calc_trend(total_instructors, prev_instructors)
        trend_avg_sessions = calc_trend(avg_per_inst, prev_avg)
        trend_sessions = calc_trend(total_sessions, prev_sessions)
        trend_students = calc_trend(total_students_val, prev_students)
        
        overall_trend = trend_avg_sessions

        # Determine if filters are applied
        is_filtered = True if (years and len(years) > 0) or (month and len(month) > 0) or (region and len(region) > 0) or (quarter and len(quarter) > 0) else False

        # Build dynamic insights
        single_year = effective_year[0] if len(effective_year) == 1 else None
        prev_year = single_year - 1 if single_year is not None else None
        
        months_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        
        if month and len(month) == 1:
            month_range_str = months_names[int(month[0]) - 1]
        elif quarter and len(quarter) == 1:
            q = int(quarter[0])
            if q == 1: month_range_str = "Apr-Jun"
            elif q == 2: month_range_str = "Jul-Sep"
            elif q == 3: month_range_str = "Oct-Dec"
            else: month_range_str = "Jan-Mar"
        elif max_month:
            month_range_str = f"Jan-{months_names[max_month-1]}" if 1 <= max_month <= 12 else "YTD"
        else:
            month_range_str = "YTD"

        suggestions_db = {
            "Instructors": {
                "up": [
                    "<strong>Scale Peer Mentorship Program:</strong> Appoint senior instructors as regional mentors to maintain delivery quality across new cohorts.",
                    "<strong>Implement Multi-Curriculum Cross-Training:</strong> Conduct workshops to certify existing instructors in secondary subjects, improving utility.",
                    "<strong>Optimize Deployment Logistics:</strong> Use geo-clustering algorithms to assign instructors to nearby schools, reducing daily travel time."
                ],
                "down": [
                    "<strong>Streamline Recruitment Timelines:</strong> Reduce the hiring bottleneck by digitizing background checks, cutting onboarding time.",
                    "<strong>Deploy a Retention Incentive Matrix:</strong> Introduce tiered quarterly retention bonuses and merit certificates for instructors.",
                    "<strong>Establish a Standby Trainer Pool:</strong> Maintain a 15% reserve of certified on-call backup instructors per region to cover attrition."
                ],
                "neutral": [
                    "<strong>Initiate Regional Skills Audits:</strong> Map current instructor capabilities against upcoming specialized program requirements.",
                    "<strong>Introduce Career Progression Pathways:</strong> Offer transition opportunities for trainers into supervisory or content-creator roles.",
                    "<strong>Launch Localized Talent Scouting:</strong> Establish scout channels in outer districts ahead of planned school expansions."
                ]
            },
            "Avg Sessions": {
                "up": [
                    "<strong>Optimize High-Cadence Delivery:</strong> Document delivery schedules of high-performing instructors to establish best practices.",
                    "<strong>Introduce Peer Coaching:</strong> Pair instructors delivering fewer sessions with high-cadence instructors to share calendar strategies.",
                    "<strong>Align Target Benchmarks:</strong> Gradually adjust soft targets upwards for matured regions to reflect high average session delivery."
                ],
                "down": [
                    "<strong>Conduct Instructor Survey:</strong> Gather feedback to identify scheduling conflicts, travel issues, or administrative overhead.",
                    "<strong>Optimize District Route Planning:</strong> Group school assignments geographically to minimize travel time between sessions.",
                    "<strong>Provide Scheduling Software:</strong> Enable instructors to self-book sessions through an automated scheduling platform to prevent conflicts."
                ],
                "neutral": [
                    "<strong>Monitor Session Density:</strong> Track weekly session delivery per instructor to identify early indicators of burnout or stagnation.",
                    "<strong>Standardize Scheduling Calendars:</strong> Implement weekly schedule templates for field instructors to ensure steady cadence.",
                    "<strong>Incentivize Mid-Week Sessions:</strong> Offer minor travel allowances for teaching on historically low-volume weekdays (e.g. Wednesday)."
                ]
            },
            "Sessions": {
                "up": [
                    "<strong>Sustain School Partnerships:</strong> Send quarterly program impact reports to school headmasters to secure renewal commitments.",
                    "<strong>Scale to Surrounding Clusters:</strong> Map schools adjacent to current partners to scale session volume with minimal logistics overhead.",
                    "<strong>Conduct Refresher Onboarding:</strong> Accelerate onboarding for returning school cohorts to launch sessions earlier in the academic year."
                ],
                "down": [
                    "<strong>Re-engage Inactive Partner Schools:</strong> Conduct direct coordinator outreach to resolve administrative blocks delaying session startups.",
                    "<strong>Establish Regional Recovery Calendars:</strong> Set up makeup session slots on weekends/holidays to recover missed academic days.",
                    "<strong>Coordinate Fleet Availability:</strong> Align dispatch schedules of delivery vehicles to ensure timely arrival of classroom training kits."
                ],
                "neutral": [
                    "<strong>Balance Monthly Cadence:</strong> Audit calendar calendars to smooth out session spikes, avoiding end-of-quarter rush fatigue.",
                    "<strong>Review School MOU Commitments:</strong> Benchmark delivered sessions against agreed MOU targets to ensure partner accountability.",
                    "<strong>Diversify Training Formats:</strong> Supplement physical sessions with hybrid virtual classroom sessions to maintain delivery volume."
                ]
            },
            "Students": {
                "up": [
                    "<strong>Deploy Large-Assembly Formats:</strong> Expand use of group teaching layouts in auditoriums to maximize per-session attendance.",
                    "<strong>Strengthen Community Partnerships:</strong> Coordinate with parent-teacher groups to drive higher student turnout during off-peak seasons.",
                    "<strong>Create Student Referral Badges:</strong> Reward students who invite friends from adjacent classrooms to attend exposure programs."
                ],
                "down": [
                    "<strong>Optimize Session Timings:</strong> Reschedule program sessions to align with peak school attendance hours (avoiding late afternoons).",
                    "<strong>Establish Attendance Incentives:</strong> Distribute branded learning kits (notebooks, pens) to students achieving 100% session attendance.",
                    "<strong>Audit Classroom Capacity:</strong> Identify regional schools with low classroom density and shift focus to larger consolidated campuses."
                ],
                "neutral": [
                    "<strong>Monitor Attendance Ratios:</strong> Track daily student attendance rates per school to flag early dropouts and trigger parent alerts.",
                    "<strong>Host Regional Knowledge Carnivals:</strong> Organize weekend science/math fairs to re-engage student groups and boost program reach.",
                    "<strong>Standardize Classroom Size Limits:</strong> Establish optimal student-to-trainer ratios to protect delivery quality while scaling headcount."
                ]
            }
        }

        # Format helper
        def fmt(v):
            return str(int(v)) if v == int(v) else f"{v:.1f}"

        # Generate insights for each card
        insights_data = {}
        for key, label, curr_val, prev_val, trend in [
            ("total_instructors", "Instructors", total_instructors, prev_instructors, trend_instructors),
            ("avg_sessions", "Avg Sessions", avg_per_inst, prev_avg, trend_avg_sessions),
            ("total_sessions", "Sessions", total_sessions, prev_sessions, trend_sessions),
            ("total_students", "Students", total_students_val, prev_students, trend_students),
        ]:
            is_up = trend["dir"] == "up"
            is_down = trend["dir"] == "down"
            pct_str = f"{abs(trend['pct'])}%"
            
            if single_year is not None:
                if is_up:
                    change_desc = f"representing an increase of <strong>{pct_str}</strong> compared to last year"
                elif is_down:
                    change_desc = f"representing a decrease of <strong>{pct_str}</strong> compared to last year"
                else:
                    change_desc = "remaining unchanged compared to last year"
                
                comparison_text = (
                    f"In the current year-to-date period ({month_range_str}) of <strong>{single_year}</strong>, the total {label.lower()} is <strong>{fmt(curr_val)}</strong> "
                    f"while the previous year-to-date period ({month_range_str}) of <strong>{prev_year}</strong> was <strong>{fmt(prev_val)}</strong> ({change_desc})."
                )
            else:
                comparison_text = f"Currently viewing aggregated data across multiple years. Total {label.lower()} is <strong>{fmt(curr_val)}</strong>."
                
            sugs = suggestions_db[label][trend["dir"]][:3]
            
            insights_data[key] = {
                "title": f"{label} Performance Insights",
                "icon": "fas fa-users" if label == "Instructors" else (
                        "fas fa-chart-line" if label == "Avg Sessions" else (
                        "fas fa-chalkboard-teacher" if label == "Sessions" else "fas fa-user-graduate")),
                "color": "linear-gradient(135deg, #f39c12 0%, #e67e22 100%)" if label == "Instructors" else (
                         "linear-gradient(135deg, #3498db 0%, #2980b9 100%)" if label == "Avg Sessions" else (
                         "linear-gradient(135deg, #2ecc71 0%, #27ae60 100%)" if label == "Sessions" else (
                         "linear-gradient(135deg, #e74c3c 0%, #c0392b 100%)"))),
                "name": label,
                "comparison_text": comparison_text,
                "suggestions": sugs
            }

        kpis = [
            {
                "label": "Instructors", "subtitle": "Total Active",
                "value": total_instructors, "icon": "fas fa-users", "color": "bg-info",
                "trend": trend_instructors,
                "insights": insights_data["total_instructors"]
            },
            {
                "label": "Avg Sessions", "subtitle": "Per Instructor",
                "value": avg_per_inst, "icon": "fas fa-chart-line", "color": "bg-success",
                "trend": trend_avg_sessions,
                "insights": insights_data["avg_sessions"]
            },
            {
                "label": "Sessions", "subtitle": "Total Delivered",
                "value": total_sessions, "icon": "fas fa-chalkboard-teacher", "color": "bg-navy-blue",
                "trend": trend_sessions,
                "insights": insights_data["total_sessions"]
            },
            {
                "label": "Students", "subtitle": "Total Impacted",
                "value": total_students_val, "icon": "fas fa-user-graduate", "color": "bg-danger",
                "trend": trend_students,
                "insights": insights_data["total_students"]
            },
        ]

        sparklines = {
            "instructors": [prev_instructors, total_instructors],
            "avg_sessions": [prev_avg, avg_per_inst],
            "sessions": [prev_sessions, total_sessions],
            "students": [prev_students, total_students_val]
        }

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
            "recordsFiltered": int(total_count),
            "is_filtered": is_filtered,
            "overall_trend": overall_trend,
            "sparklines": sparklines
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
    region=None, years=None, month=None, quarter=None,
    group_by="month"  # 'day', 'month', 'quarter', 'year'
):
    """Returns session trend data (actual + computed target + daily hi/lo) for candlestick chart."""
    from backend.services.query_utils import get_list_filter_clause
    try:
        clauses, params = [], []
        c, p = get_list_filter_clause("g.region_name", region); clauses.append(c); params.extend(p)
        # Default to 2026 if no year provided
        effective_year = [int(y) for y in (years if years is not None and len(years) > 0 else [2026])]
        c, p = get_list_filter_clause("d.year_actual", effective_year, cast_type="int"); clauses.append(c); params.extend(p)
        c, p = get_list_filter_clause("d.month_actual", month, cast_type="int"); clauses.append(c); params.extend(p)
        
        fiscal_q_expr = "CASE WHEN d.month_actual IN (4,5,6) THEN 1 WHEN d.month_actual IN (7,8,9) THEN 2 WHEN d.month_actual IN (10,11,12) THEN 3 ELSE 4 END"
        c, p = get_list_filter_clause(fiscal_q_expr, quarter, cast_type="int"); clauses.append(c); params.extend(p)
        
        # Apply YTD month boundary filtering if month and quarter are not specified
        if not month and not quarter:
            _apply_ytd_filter(clauses, params, effective_year)

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
                COUNT(DISTINCT f.sk_user_id)              AS actual_instructors,
                COALESCE(SUM(e.total_exposure_count), 0)  AS actual_students,
                MAX(daily.day_sessions)                   AS high_sessions,
                MIN(daily.day_sessions)                   AS low_sessions
            FROM {DW}.fact_session f
            JOIN {DW}.dim_date d       ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
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
                "label":       r["period_label"],
                "actual":      actual,
                "target":      target,
                "instructors": int(r["actual_instructors"] or 0),
                "students":    int(r["actual_students"] or 0),
                "avg_sessions": round(actual / int(r["actual_instructors"]), 1) if int(r["actual_instructors"]) > 0 else 0,
                "high":        int(r["high_sessions"] or actual),
                "low":         int(r["low_sessions"] or actual),
                "open":        target,   # candlestick open = target
                "close":       actual,   # candlestick close = actual
                "met":         actual >= target,
            })
        return {"data": result, "group_by": group_by}
    except Exception as e:
        logger.error(f"chart_data error: {e}", exc_info=True)
        return {"data": [], "group_by": group_by}

def get_performance_mgmt_region_chart(
    region=None, years=None, month=None, quarter=None, period=None, group_by="month"
):
    """Returns top 5 regions by sessions and students impacted for an insightful secondary chart."""
    from backend.services.query_utils import get_list_filter_clause
    try:
        clauses, params = [], []
        c, p = get_list_filter_clause("g.region_name", region); clauses.append(c); params.extend(p)
        # Default to 2026 if no year provided
        effective_year = [int(y) for y in (years if years is not None and len(years) > 0 else [2026])]
        c, p = get_list_filter_clause("d.year_actual", effective_year, cast_type="int"); clauses.append(c); params.extend(p)
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
        
        # Apply YTD month boundary filtering if month, quarter, and period are not specified
        if not month and not quarter and not period:
            _apply_ytd_filter(clauses, params, effective_year)

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
    region=None, years=None, month=None, quarter=None
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
        
        # Default to 2026 if no year provided
        effective_year = [int(y) for y in (years if years is not None and len(years) > 0 else [2026])]
        c, p = get_list_filter_clause("d.year_actual", effective_year, cast_type="int"); clauses.append(c); params.extend(p)
        c, p = get_list_filter_clause("d.month_actual", month, cast_type="int"); clauses.append(c); params.extend(p)
        
        fiscal_q_expr = "CASE WHEN d.month_actual IN (4,5,6) THEN 1 WHEN d.month_actual IN (7,8,9) THEN 2 WHEN d.month_actual IN (10,11,12) THEN 3 ELSE 4 END"
        c, p = get_list_filter_clause(fiscal_q_expr, quarter, cast_type="int"); clauses.append(c); params.extend(p)

        # Apply YTD month boundary filtering if month/quarter filters and sub-year period are not specified
        is_sub_year_period = (group_by == "month" or group_by == "quarter" or group_by == "day") and period_label
        if not month and not quarter and not is_sub_year_period:
            _apply_ytd_filter(clauses, params, effective_year)

        # Parse period label for date filter
        months_short = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        if group_by == "month" and period_label:
            parts = period_label.split(" ")
            if len(parts) == 2 and parts[0] in months_short:
                clauses.append("TO_CHAR(TO_DATE(d.month_actual::text,'MM'),'Mon') = %s")
                params.append(parts[0])
                clauses.append("d.year_actual = %s")
                params.append(int(parts[1]))
        elif group_by == "day" and period_label:
            clauses.append("TO_CHAR(d.full_date, 'DD Mon YYYY') = %s")
            params.append(period_label)
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
            LIMIT 2000
        """, params)
        return {"table": table, "period": period_label}
    except Exception as e:
        logger.error(f"drilldown error: {e}", exc_info=True)
        return {"table": [], "period": period_label}
