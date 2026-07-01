import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from backend.services.query_utils import fetch_all, fetch_one, get_list_filter_clause, get_datatables_sql
from backend.config import DATAMART_SCHEMA_NAME, DEFAULT_YEAR

logger = logging.getLogger(__name__)
DW = DATAMART_SCHEMA_NAME


def _build_clauses(region=None, years=None, program=None, force_max_month=None):
    from backend.services.query_utils import apply_ytd_filter
    clauses, params = [], []
    c, p = get_list_filter_clause("g.region_name", region); clauses.append(c); params.extend(p)
    c, p = get_list_filter_clause("d.year_actual", years, cast_type="int"); clauses.append(c); params.extend(p)
    if program:
        if isinstance(program, list):
            clean_programs = [pr for pr in program if pr and pr != ""]
            if clean_programs:
                clauses.append("f.sk_activity_type_id IN (SELECT sk_activity_type_id FROM dw.dim_activity_type WHERE activity_name = ANY(%s))")
                params.append(clean_programs)
        else:
            if program and program != "":
                clauses.append("f.sk_activity_type_id IN (SELECT sk_activity_type_id FROM dw.dim_activity_type WHERE activity_name = %s)")
                params.append(program)
    where_sql = " AND ".join(clauses) if clauses else "TRUE"
    where_sql, params = apply_ytd_filter(where_sql, params, years, date_alias="d", force_max_month=force_max_month)
    return where_sql, params


def calc_trend(curr, prev):
    if not prev:
        return {"pct": 0, "dir": "neutral"}
    diff = curr - prev
    pct = round((diff / prev) * 100, 1) if prev > 0 else 0
    direction = "up" if diff > 0 else ("down" if diff < 0 else "neutral")
    return {"pct": pct, "dir": direction}


# ═══════════════════════════════════════════════════════════════
#  INSTRUCTOR PERFORMANCE INSIGHTS GENERATOR
# ═══════════════════════════════════════════════════════════════

def generate_instructor_insights(curr_vals, prev_vals, trends, single_year, prev_year, max_month=None):
    insights = {}
    meta = {
        "total_instructors": {
            "title": "Instructors Count Insights",
            "icon": "fas fa-users",
            "color": "linear-gradient(135deg, #17a2b8 0%, #117a8b 100%)",
            "name": "Instructors"
        },
        "total_sessions": {
            "title": "Sessions Conducted Insights",
            "icon": "fas fa-chalkboard",
            "color": "linear-gradient(135deg, #28a745 0%, #218838 100%)",
            "name": "Sessions Conducted"
        },
        "avg_per_instructor": {
            "title": "Avg Sessions per Instructor Insights",
            "icon": "fas fa-chart-line",
            "color": "linear-gradient(135deg, #001f3f 0%, #001226 100%)",
            "name": "Avg / Instructor"
        },
        "total_students": {
            "title": "Students Impacted Insights",
            "icon": "fas fa-user-graduate",
            "color": "linear-gradient(135deg, #dc3545 0%, #c82333 100%)",
            "name": "Students Impacted"
        }
    }
    
    for key, info in meta.items():
        curr_val = curr_vals.get(key, 0)
        prev_val = prev_vals.get(key, 0) if prev_vals else 0
        curr_avg = curr_val
        prev_avg = prev_val
        trend = trends.get(key, {"pct": 0, "dir": "neutral"}) if trends else {"pct": 0, "dir": "neutral"}
        
        def fmt(v):
            v = float(v)
            return str(int(v)) if v == int(v) else f"{v:.1f}"

        if single_year is not None:
            pct_str = f"{abs(trend['pct'])}%"
            if trend['dir'] == 'up':
                change_desc = f"representing an increase of <strong>{pct_str}</strong> compared to last year"
            elif trend['dir'] == 'down':
                change_desc = f"representing a decrease of <strong>{pct_str}</strong> compared to last year"
            else:
                change_desc = "remaining unchanged compared to last year"
                
            months_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
            month_range_str = f"Jan-{months_names[max_month-1]}" if (max_month and 1 <= max_month <= 12) else "YTD"
            
            if key == "avg_per_instructor":
                comparison_text = f"In the current year-to-date period ({month_range_str}) of <strong>{single_year}</strong>, the average {info['name'].lower()} is <strong>{fmt(curr_val)}</strong> while the previous year-to-date period ({month_range_str}) of <strong>{prev_year}</strong> was <strong>{fmt(prev_val)}</strong> ({change_desc})."
            else:
                comparison_text = f"In the current year-to-date period ({month_range_str}) of <strong>{single_year}</strong>, the total {info['name'].lower()} is <strong>{fmt(curr_val)}</strong> while the previous year-to-date period ({month_range_str}) of <strong>{prev_year}</strong> was <strong>{fmt(prev_val)}</strong> ({change_desc})."
        else:
            if key == "avg_per_instructor":
                comparison_text = f"Currently viewing aggregated data across multiple years. Average {info['name'].lower()} is <strong>{fmt(curr_val)}</strong>."
            else:
                comparison_text = f"Currently viewing aggregated data across multiple years. Total {info['name'].lower()} is <strong>{fmt(curr_val)}</strong>."
            
        rationale = ""
        suggestions = []
        
        if key == "total_instructors":
            if trend['dir'] == 'down':
                rationale = f"Monthly average active instructors decreased from {fmt(prev_avg)} to {fmt(curr_avg)} in {single_year} (down {abs(trend['pct'])}%). This decline is driven by seasonal attrition, verification delays during onboarding, and training capacity halts in newly-formed districts."
                suggestions = [
                    "<strong>Deploy a Retention Incentive Matrix:</strong> Offer tiered completion bonuses to trainers completing consecutive teaching cycles.",
                    "<strong>Streamline Recruitment Timelines:</strong> Digitize background checks to cut onboarding delays from 30 to 12 days.",
                    "<strong>Establish a Standby Trainer Pool:</strong> Maintain a 15% reserve of certified backup instructors to prevent mid-term class vacancies.",
                    "<strong>Partner with Teacher Training Institutes:</strong> Secure talent pipelines with B.Ed and D.Ed colleges to auto-onboard high-potential graduates.",
                    "<strong>Enhance Safety &amp; Transit Allowances:</strong> Subsidize travel to remote regions to boost field trainer satisfaction."
                ]
            elif trend['dir'] == 'up':
                rationale = f"Monthly average active instructors increased from {fmt(prev_avg)} to {fmt(curr_avg)} in {single_year} (up {trend['pct']}%). This indicates successful district onboarding campaigns and positive engagement from teacher education partners."
                suggestions = [
                    "<strong>Scale Peer Mentorship:</strong> Assign senior instructors as mentors for new recruits to ensure high teaching standards.",
                    "<strong>Optimize Route Allocation:</strong> Use clustering algorithms to align instructors with the closest schools, minimizing travel fatigue.",
                    "<strong>Introduce Cross-Subject Certifications:</strong> Upskill trainers in multiple curricular modules to maximize placement flexibility.",
                    "<strong>Publish Impact Case Studies:</strong> Highlight instructor success stories to boost regional recruiting and donor interest."
                ]
            else:
                rationale = f"Monthly average active instructors remained steady at {fmt(curr_avg)} (no significant change). Balanced turnover and recruitment suggest operational stability but lack of geographical growth."
                suggestions = [
                    "<strong>Initiate Skills Audits:</strong> Audit existing instructor capabilities against new session requirements.",
                    "<strong>Create Career Pathways:</strong> Establish coordinator positions to incentivize long-term retention.",
                    "<strong>Launch Local Talent Scouting:</strong> Map potential recruit sources in neighboring districts ahead of expansion."
                ]
                
        elif key == "total_sessions":
            if trend['dir'] == 'down':
                rationale = f"Monthly average sessions conducted dropped from {fmt(prev_avg)} to {fmt(curr_avg)} in {single_year} (down {abs(trend['pct'])}%). Principal delays, local weather/harvest-related school closures, and transport breakdowns in remote zones contributed to underperformance."
                suggestions = [
                    "<strong>Implement Live Scheduler Dashboards:</strong> Deploy real-time scheduling tools to track and re-allocate postponed sessions immediately.",
                    "<strong>Establish Block Coordination Protocols:</strong> Coordinate directly with school administrators to secure dedicated time blocks during exam seasons.",
                    "<strong>Create Mobile Delivery Teams:</strong> Equip mobile reserve groups with vehicles to execute sessions in districts facing transit challenges.",
                    "<strong>Run Standardized Make-up Cycles:</strong> Introduce weekend or after-school catch-up sessions for schools that missed classes.",
                    "<strong>Upgrade Local Center Coordination:</strong> Appoint center heads to resolve conflicts with school scheduling instantly."
                ]
            elif trend['dir'] == 'up':
                rationale = f"Monthly average sessions conducted increased from {fmt(prev_avg)} to {fmt(curr_avg)} in {single_year} (up {trend['pct']}%). This positive trend reflects enhanced administrative coordination and improved logistics reliability."
                suggestions = [
                    "<strong>Reward High-Session Hubs:</strong> Launch regional awards for hubs maintaining 100% scheduled session compliance.",
                    "<strong>Implement Standardized Curriculum Packages:</strong> Package teaching kits to ensure fast classroom setup and execution.",
                    "<strong>Conduct School Principal Surveys:</strong> Collect quarterly feedback from principals to sustain session booking efficiency.",
                    "<strong>Establish Cross-Hub Resource Sharing:</strong> Share materials and reserve instructors during peak campaign months."
                ]
            else:
                rationale = f"Monthly average sessions conducted held steady at {fmt(curr_avg)}. This indicates stable scheduling but suggests capacity has capped under the current structure."
                suggestions = [
                    "<strong>Audit Calendar Gaps:</strong> Identify under-scheduled weekdays to maximize classroom utilization.",
                    "<strong>Introduce Dual-Session Formats:</strong> Run concurrent morning and afternoon sessions to increase capacity without expanding headcount."
                ]
                
        elif key == "avg_per_instructor":
            if trend['dir'] == 'down':
                rationale = f"Average sessions per instructor dropped from {prev_val} to {curr_val} in {single_year} (down {abs(trend['pct'])}%). This indicates underutilized workforce capacity, excessive transit times, or administrative overhead delaying classroom delivery."
                suggestions = [
                    "<strong>Deploy Dynamic Routing:</strong> Optimize instructor travel plans using route mapping software to minimize transit time and increase teaching hours.",
                    "<strong>Enforce Standard Weekly Quotas:</strong> Set a baseline target of 4 completed sessions per week per active instructor.",
                    "<strong>Automate Session Logging:</strong> Remove manual paperwork by integrating digital mobile session logs, freeing up trainer time.",
                    "<strong>Launch Refresher Training Camps:</strong> Conduct monthly sessions for low-volume instructors to address delivery obstacles.",
                    "<strong>Establish Lead Instructor Audits:</strong> Task regional coordinators with audit visits to low-utilization schools to resolve delays."
                ]
            elif trend['dir'] == 'up':
                rationale = f"Average sessions per instructor rose from {prev_val} to {curr_val} in {single_year} (up {trend['pct']}%). This indicates excellent resource utilization, efficient logistics, and highly motivated staff."
                suggestions = [
                    "<strong>Reward Productivity Leaders:</strong> Introduce quarterly recognition and financial bonuses for top-decile instructors.",
                    "<strong>Document Efficiency Playbooks:</strong> Have top-performing instructors document their scheduling tricks to share with peer groups.",
                    "<strong>Monitor Burnout Indicators:</strong> Set maximum session ceilings to protect trainers from excessive travel and fatigue.",
                    "<strong>Optimize Group Travel:</strong> Arrange pooled transit for trainers covering the same school clusters."
                ]
            else:
                rationale = f"Average sessions per instructor remained flat at {curr_val}. Resource utilization is stable but has room for productivity gains."
                suggestions = [
                    "<strong>Conduct Utilization Reviews:</strong> Review and reassign low-utilization instructors to high-demand clusters.",
                    "<strong>Standardize Scheduling Templates:</strong> Provide simple templates for instructors to pre-book their entire semester."
                ]
                
        elif key == "total_students":
            if trend['dir'] == 'down':
                rationale = f"Students impacted dropped from {prev_val} to {curr_val} in {single_year} (down {abs(trend['pct'])}%). The decline is driven by lower daily school attendance rates, shifting demographics, and lack of pre-session community mobilizations."
                suggestions = [
                    "<strong>Host Student Attendance Drives:</strong> Partner with school principals to run attendance contests coinciding with program visits.",
                    "<strong>Optimized Time Slots:</strong> Schedule program sessions during morning assembly or peak high-attendance class periods.",
                    "<strong>Create Student Ambassador Badges:</strong> Reward active student participants with badges to generate peer excitement and word-of-mouth.",
                    "<strong>Mobilize Parent-Teacher Meetings:</strong> Showcase program value to parents during quarterly meetings to increase home-side backing.",
                    "<strong>Provide Engagement Incentives:</strong> Distribute learning materials, certificates, and stationery to drive classroom participation."
                ]
            elif trend['dir'] == 'up':
                rationale = f"Students impacted increased from {prev_val} to {curr_val} in {single_year} (up {trend['pct']}%). This positive shift indicates strong community trust and high engagement rates within classrooms."
                suggestions = [
                    "<strong>Launch Inter-School Competitions:</strong> Organize regional science/skills exhibits to showcase student creations.",
                    "<strong>Deploy Advanced Curriculums:</strong> Introduce level-2 training modules to keep successfully reached cohorts engaged.",
                    "<strong>Digitize Classroom Elements:</strong> Integrate interactive mobile projections or tablet tools to sustain large group attention.",
                    "<strong>Establish Impact Portals:</strong> Share student exposure metrics with education boards to validate project scale."
                ]
            else:
                rationale = f"Students impacted remained stable at {curr_val}. Reach is flat, suggesting classroom attendance is constrained by school capacity."
                suggestions = [
                    "<strong>Execute Classroom Audits:</strong> Audit session capacities to ensure instructors are assigned to appropriately-sized student groups.",
                    "<strong>Introduce Multi-Section Scheduling:</strong> Combine smaller sections or split over-crowded classrooms to ensure optimal teaching environments."
                ]
                
        insights[key] = {
            "title": info["title"],
            "icon": info["icon"],
            "color": info["color"],
            "name": info["name"],
            "comparison_text": comparison_text,
            "rationale": rationale,
            "suggestions": suggestions
        }
    return insights


def get_instructor_overview(region=None, years=None, program=None, limit=15, offset=0, dt_params=None):
    try:
        from backend.services.query_utils import get_ytd_max_month
        # Determine single year up-front so prev_year clauses can be built before threading
        single_year = None
        if years and len(years) == 1:
            try:
                single_year = int(str(years[0])[:4])
            except (ValueError, TypeError):
                pass
        elif not years:
            single_year = DEFAULT_YEAR

        max_month = get_ytd_max_month(single_year) if single_year is not None else None
        where_sql, params = _build_clauses(region, years, program, force_max_month=max_month)

        prev_year = single_year - 1 if single_year is not None else None
        prev_where_sql, prev_params = (_build_clauses(region, [str(prev_year)], program, force_max_month=max_month)
                                       if prev_year is not None else (where_sql, params))

        # DataTables params resolved early so table queries can run in parallel
        search_sql, search_params = "TRUE", []
        sort_sql = "ORDER BY sessions DESC"
        if dt_params:
            s, sp, so = get_datatables_sql(dt_params, ["u.user_name", "u.role_name", "g.region_name"],
                                           ["name", "role", "region", "sessions", "students", "schools"])
            search_sql, search_params = s, sp
            if so: sort_sql = so

        # ── Parallel query execution ──────────────────────────────────────────
        SQL_KPI = f"""
            SELECT COUNT(DISTINCT f.sk_user_id) AS total_instructors,
                   COUNT(DISTINCT f.sk_fact_session_id) AS total_sessions,
                   COALESCE(SUM(e.total_exposure_count), 0) AS total_students
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d      ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_program p   ON f.sk_program_id = p.sk_program_id
            LEFT JOIN {DW}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            WHERE {where_sql}"""

        SQL_PREV_KPI = f"""
            SELECT COUNT(DISTINCT f.sk_user_id) AS total_instructors,
                   COUNT(DISTINCT f.sk_fact_session_id) AS total_sessions,
                   COALESCE(SUM(e.total_exposure_count), 0) AS total_students
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d      ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_program p   ON f.sk_program_id = p.sk_program_id
            LEFT JOIN {DW}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            WHERE {prev_where_sql}"""

        SQL_TYPE = f"""
            SELECT COALESCE(NULLIF(INITCAP(TRIM(u.role_name)),''), 'Unknown') AS label,
                   COUNT(DISTINCT f.sk_fact_session_id) AS value
            FROM {DW}.fact_session f
            JOIN {DW}.dim_user u      ON f.sk_user_id = u.sk_user_id
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d      ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_program p   ON f.sk_program_id = p.sk_program_id
            WHERE {where_sql} AND u.user_name IS NOT NULL
            GROUP BY u.role_name ORDER BY value DESC LIMIT 8"""

        SQL_TREND = f"""
            SELECT TO_CHAR(d.full_date, 'Mon YYYY') AS label,
                   COUNT(DISTINCT f.sk_fact_session_id) AS value, MIN(d.full_date) AS sort_key
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_date d      ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_program p   ON f.sk_program_id = p.sk_program_id
            WHERE {where_sql} GROUP BY TO_CHAR(d.full_date, 'Mon YYYY') ORDER BY sort_key"""

        SQL_REGION = f"""
            SELECT COALESCE(g.region_name, 'Unknown') AS label,
                   COUNT(DISTINCT f.sk_fact_session_id) AS value
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d      ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_program p   ON f.sk_program_id = p.sk_program_id
            WHERE {where_sql} AND g.region_name IS NOT NULL
            GROUP BY g.region_name ORDER BY value DESC LIMIT 8"""

        SQL_COUNT = f"""
            SELECT COUNT(*) FROM (
                SELECT u.sk_user_id FROM {DW}.fact_session f
                JOIN {DW}.dim_user u ON f.sk_user_id = u.sk_user_id
                LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
                LEFT JOIN {DW}.dim_date d ON f.date_id = d.date_id
                LEFT JOIN {DW}.dim_program p ON f.sk_program_id = p.sk_program_id
                WHERE {where_sql} AND {search_sql} AND u.user_name IS NOT NULL
                GROUP BY u.sk_user_id
            ) sub"""

        SQL_TABLE = f"""
            SELECT COALESCE(u.user_name,'Unknown') AS name,
                   COALESCE(INITCAP(u.role_name),'Unknown') AS role,
                   COALESCE(g.region_name,'Unknown') AS region,
                   COUNT(DISTINCT f.sk_fact_session_id) AS sessions,
                   COALESCE(SUM(e.total_exposure_count),0) AS students,
                   COUNT(DISTINCT f.sk_school_id) AS schools
            FROM {DW}.fact_session f
            JOIN {DW}.dim_user u ON f.sk_user_id = u.sk_user_id
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_program p ON f.sk_program_id = p.sk_program_id
            LEFT JOIN {DW}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            WHERE {where_sql} AND {search_sql} AND u.user_name IS NOT NULL
            GROUP BY u.sk_user_id, u.user_name, u.role_name, g.region_name
            {sort_sql} LIMIT %s OFFSET %s"""

        SQL_SPARKLINE = f"""
            SELECT d.year_actual, d.month_actual, MIN(d.full_date) AS sort_key,
                   COUNT(DISTINCT f.sk_user_id) AS instructors,
                   COUNT(DISTINCT f.sk_fact_session_id) AS sessions,
                   COALESCE(SUM(e.total_exposure_count), 0) AS students
            FROM {DW}.fact_session f
            JOIN {DW}.dim_user u ON f.sk_user_id = u.sk_user_id
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d      ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_program p   ON f.sk_program_id = p.sk_program_id
            LEFT JOIN {DW}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            WHERE {where_sql} AND u.user_name IS NOT NULL
            GROUP BY d.year_actual, d.month_actual ORDER BY sort_key LIMIT 24"""

        futures_map = {}
        with ThreadPoolExecutor(max_workers=8) as ex:
            futures_map["kpi"]      = ex.submit(fetch_one,  SQL_KPI,      params)
            futures_map["type"]     = ex.submit(fetch_all,  SQL_TYPE,     params)
            futures_map["trend"]    = ex.submit(fetch_all,  SQL_TREND,    params)
            futures_map["region"]   = ex.submit(fetch_all,  SQL_REGION,   params)
            futures_map["count"]    = ex.submit(fetch_one,  SQL_COUNT,    params + search_params)
            futures_map["table"]    = ex.submit(fetch_all,  SQL_TABLE,    params + search_params + [limit, offset])
            futures_map["sparkline"]= ex.submit(fetch_all,  SQL_SPARKLINE,params)
            if prev_year is not None:
                futures_map["prev_kpi"] = ex.submit(fetch_one, SQL_PREV_KPI, prev_params)

        kpi          = futures_map["kpi"].result()
        type_rows    = futures_map["type"].result()
        trend_rows   = futures_map["trend"].result()
        region_rows  = futures_map["region"].result()
        count_row    = futures_map["count"].result()
        table        = futures_map["table"].result()
        sparkline_rows = futures_map["sparkline"].result()

        ti = int(kpi.get("total_instructors", 0) or 0)
        ts = int(kpi.get("total_sessions", 0) or 0)
        stu = int(kpi.get("total_students", 0) or 0)
        avg = round(ts / ti, 1) if ti else 0

        trends_yo_y = None
        prev_vals = None
        if prev_year is not None and "prev_kpi" in futures_map:
            try:
                prev_kpi = futures_map["prev_kpi"].result()
                p_ti = int(prev_kpi.get("total_instructors", 0) or 0)
                p_ts = int(prev_kpi.get("total_sessions", 0) or 0)
                p_stu = int(prev_kpi.get("total_students", 0) or 0)
                p_avg = round(p_ts / p_ti, 1) if p_ti else 0

                # Compute monthly averages for trend-based comparison
                curr_months_row = fetch_one(f"""SELECT COUNT(DISTINCT d.month_actual) AS m
                    FROM {DW}.fact_session f
                    LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
                    LEFT JOIN {DW}.dim_date d ON f.date_id = d.date_id
                    LEFT JOIN {DW}.dim_program p ON f.sk_program_id = p.sk_program_id
                    WHERE {where_sql}""", params)
                prev_months_row = fetch_one(f"""SELECT COUNT(DISTINCT d.month_actual) AS m
                    FROM {DW}.fact_session f
                    LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
                    LEFT JOIN {DW}.dim_date d ON f.date_id = d.date_id
                    LEFT JOIN {DW}.dim_program p ON f.sk_program_id = p.sk_program_id
                    WHERE {prev_where_sql}""", prev_params)
                cm = max(int(curr_months_row.get("m", 1) or 1), 1)
                pm = max(int(prev_months_row.get("m", 1) or 1), 1)

                ti_avg  = round(ti / cm, 1)
                p_ti_avg = round(p_ti / pm, 1)
                ts_avg  = round(ts / cm, 1)
                p_ts_avg = round(p_ts / pm, 1)
                stu_avg  = round(stu / cm, 1)
                p_stu_avg = round(p_stu / pm, 1)

                prev_vals = {
                    "total_instructors": p_ti,
                    "total_sessions": p_ts,
                    "avg_per_instructor": p_avg,
                    "total_students": p_stu
                }
                trends_yo_y = {
                    "total_instructors": calc_trend(ti, p_ti),
                    "total_sessions":    calc_trend(ts, p_ts),
                    "avg_per_instructor": calc_trend(avg, p_avg),
                    "total_students":    calc_trend(stu, p_stu),
                }
            except Exception as e:
                logger.error(f"instructor previous year fetch error: {e}")

        curr_vals = {
            "total_instructors": ti,
            "total_sessions": ts,
            "avg_per_instructor": avg,
            "total_students": stu
        }
        insights = generate_instructor_insights(curr_vals, prev_vals, trends_yo_y, single_year, prev_year, max_month)

        kpis_response = {"total_instructors": ti, "total_sessions": ts,
                         "avg_per_instructor": avg, "total_students": stu, "insights": insights}
        if trends_yo_y:
            kpis_response["trends"] = trends_yo_y

        charts = {
            "by_type":   [{"label": r["label"], "value": int(r["value"])} for r in type_rows],
            "trend":     [{"label": r["label"], "value": int(r["value"])} for r in trend_rows],
            "by_region": [{"label": r["label"], "value": int(r["value"])} for r in region_rows],
        }
        count = count_row.get("count", 0) if count_row else 0
        monthly_trends = []
        for r in sparkline_rows:
            inst_c = int(r["instructors"] or 0)
            sess_c = int(r["sessions"] or 0)
            monthly_trends.append({"instructors": inst_c, "sessions": sess_c,
                                    "avg": round(sess_c / inst_c, 1) if inst_c else 0,
                                    "students": int(r["students"] or 0)})

        sparklines = {
            "instructors": [prev_vals.get("total_instructors", ti) if prev_vals else ti, ti],
            "sessions": [prev_vals.get("total_sessions", ts) if prev_vals else ts, ts],
            "avg": [prev_vals.get("avg_per_instructor", avg) if prev_vals else avg, avg],
            "students": [prev_vals.get("total_students", stu) if prev_vals else stu, stu]
        }

        return {"kpis": kpis_response, "charts": charts, "table": table,
                "total_count": int(count), "trends": monthly_trends, "sparklines": sparklines}
    except Exception as ex:
        logger.error(f"instructor overview error: {ex}", exc_info=True)
        return {"kpis": {}, "charts": {}, "table": [], "total_count": 0, "trends": [], "sparklines": {}}


# ═══════════════════════════════════════════════════════════════
#  PROGRAM IMPACT INSIGHTS GENERATOR
# ═══════════════════════════════════════════════════════════════

def generate_program_insights(curr_vals, prev_vals, trends, single_year, prev_year, max_month=None):
    insights = {}
    meta = {
        "total_programs": {
            "title": "Programs Count Insights",
            "icon": "fas fa-project-diagram",
            "color": "linear-gradient(135deg, #17a2b8 0%, #117a8b 100%)",
            "name": "Programs"
        },
        "total_schools": {
            "title": "Schools Reached Insights",
            "icon": "fas fa-school",
            "color": "linear-gradient(135deg, #28a745 0%, #218838 100%)",
            "name": "Schools Reached"
        },
        "total_students": {
            "title": "Students Impacted Insights",
            "icon": "fas fa-user-graduate",
            "color": "linear-gradient(135deg, #001f3f 0%, #001226 100%)",
            "name": "Students Reached"
        },
        "total_sessions": {
            "title": "Sessions Conducted Insights",
            "icon": "fas fa-chalkboard-teacher",
            "color": "linear-gradient(135deg, #dc3545 0%, #c82333 100%)",
            "name": "Total Sessions"
        }
    }
    
    for key, info in meta.items():
        curr_val = curr_vals.get(key, 0)
        prev_val = prev_vals.get(key, 0) if prev_vals else 0
        curr_avg = curr_val
        prev_avg = prev_val
        trend = trends.get(key, {"pct": 0, "dir": "neutral"}) if trends else {"pct": 0, "dir": "neutral"}

        def fmt(v):
            v = float(v)
            return str(int(v)) if v == int(v) else f"{v:.1f}"

        if single_year is not None:
            pct_str = f"{abs(trend['pct'])}%"
            if trend['dir'] == 'up':
                change_desc = f"representing an increase of <strong>{pct_str}</strong> compared to last year"
            elif trend['dir'] == 'down':
                change_desc = f"representing a decrease of <strong>{pct_str}</strong> compared to last year"
            else:
                change_desc = "remaining unchanged compared to last year"
                
            months_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
            month_range_str = f"Jan-{months_names[max_month-1]}" if (max_month and 1 <= max_month <= 12) else "YTD"
            
            comparison_text = f"In the current year-to-date period ({month_range_str}) of <strong>{single_year}</strong>, the total {info['name'].lower()} is <strong>{fmt(curr_val)}</strong> while the previous year-to-date period ({month_range_str}) of <strong>{prev_year}</strong> was <strong>{fmt(prev_val)}</strong> ({change_desc})."
        else:
            comparison_text = f"Currently viewing aggregated data across multiple years. Total {info['name'].lower()} is <strong>{fmt(curr_val)}</strong>."
            
        rationale = ""
        suggestions = []
        
        if key == "total_programs":
            if trend['dir'] == 'down':
                rationale = f"Active programs dropped from {prev_val} to {curr_val} in {single_year} (down {abs(trend['pct'])}%). This indicates transition of localized grants and restructuring of outdated curricular titles."
                suggestions = [
                    "<strong>Diversify CSR Funding Pipelines:</strong> target mid-sized local businesses to cover program execution dependencies.",
                    "<strong>Provide Live Donor Portals:</strong> Give sponsors real-time views of classroom photos and feedback reviews to secure renewals.",
                    "<strong>Create Modular Pilot Kits:</strong> Design low-cost 2-week educational syllabus kits to test out initiatives before scaling.",
                    "<strong>Align Curriculums with Government Standards:</strong> Explicitly support state education board objectives to open up public fund grants.",
                    "<strong>Build an Alumni Demand Loop:</strong> Leverage senior graduates to showcase local impact, stimulating demand from neighboring boards."
                ]
            elif trend['dir'] == 'up':
                rationale = f"Active program initiatives grew from {prev_val} to {curr_val} in {single_year} (up {trend['pct']}%). This indicates strong corporate partner trust and high demand for vocational/digital classes."
                suggestions = [
                    "<strong>Standardize Program Toolkits:</strong> Package curricula into modular boxes to ensure fast deployment by new instructors.",
                    "<strong>Establish Shared Resource Frameworks:</strong> Coordinate material usage across projects to lower marginal execution costs.",
                    "<strong>Cross-Promote to Existing Donors:</strong> Offer integrated program bundles to existing corporate sponsors during annual agreements.",
                    "<strong>Conduct Quality Benchmark Audits:</strong> Run monthly tests to guarantee consistent program delivery during periods of fast scale-up."
                ]
            else:
                rationale = f"Active programs are constant at {curr_val}. While programmatic offerings are stable, the metric highlights potential stagnation in donor acquisitions."
                suggestions = [
                    "<strong>Perform Knowledge Retentive Reviews:</strong> Analyze curriculum effectiveness to consolidate overlapping training programs.",
                    "<strong>Reallocate Underused Assets:</strong> Reassign training kits from dormant projects to high-demand modules."
                ]
                
        elif key == "total_schools":
            if trend['dir'] == 'down':
                rationale = f"Schools reached decreased from {prev_val} to {curr_val} in {single_year} (down {abs(trend['pct'])}%). Delays in local administration approvals, transport barriers, and consolidating remote schools into larger clusters explain the decrease."
                suggestions = [
                    "<strong>Establish a Block MoU Taskforce:</strong> Form a dedicated liaison desk to finalize school permissions 90 days before the session starts.",
                    "<strong>Deploy Mobile Training Vans:</strong> Use specialized vehicles to transport training materials directly to schools in remote areas.",
                    "<strong>Execute District-Level Cluster Signups:</strong> Secure blanket approvals from district education officers instead of approaching individual schools.",
                    "<strong>Partner with Local NGOs:</strong> Use grassroots community organizations to handle local logistics and clearance hurdles.",
                    "<strong>Scale Contiguous Geographies:</strong> Focus expansions on schools adjacent to high-performing centers to share existing hubs."
                ]
            elif trend['dir'] == 'up':
                rationale = f"Schools reached increased from {prev_val} to {curr_val} in {single_year} (up {trend['pct']}%). This success indicates strong government coordination and successful outreach campaigns in target districts."
                suggestions = [
                    "<strong>Appoint Regional School Coordinators:</strong> Appoint school liaison officers to maintain teacher enthusiasm.",
                    "<strong>Setup Local Material Hubs:</strong> Establish regional supply centers to reduce school kit delivery delays.",
                    "<strong>Run School Principal Showcases:</strong> Host annual forums showing student models to strengthen educational network bonds.",
                    "<strong>Optimize Hub Route Timings:</strong> Create fixed schedules for school supply vehicles to keep deliveries on time."
                ]
            else:
                rationale = f"Schools reached remained flat at {curr_val}. Expansion is paused to focus on saturating school populations inside current regions."
                suggestions = [
                    "<strong>Conduct School Density Assessments:</strong> Target a higher percentage of schools within the current states to maximize local presence.",
                    "<strong>Deepen Institutional Saturation:</strong> Introduce program options across all grades in already-reached schools."
                ]
                
        elif key == "total_students":
            if trend['dir'] == 'down':
                rationale = f"Students reached dropped from {prev_val} to {curr_val} in {single_year} (down {abs(trend['pct'])}%). This indicates seasonal class absences, schedule conflicts with major exams, or insufficient classroom mobilization."
                suggestions = [
                    "<strong>Launch Student Attendance Competitions:</strong> Work with teachers to offer small awards for sections reaching 100% attendance during program visits.",
                    "<strong>Reschedule Session Windows:</strong> Time classes during high-attendance morning slots instead of late afternoon slots.",
                    "<strong>Coordinate with Parent Committees:</strong> Educate parents on vocational training benefits to ensure they support student participation.",
                    "<strong>Incorporate Interactive Learning Kits:</strong> Integrate hands-on models and tablet activities to maximize classroom interest.",
                    "<strong>Optimize Cohort Sizing:</strong> Combine small school sections to ensure trainers teach to full classroom capacities."
                ]
            elif trend['dir'] == 'up':
                rationale = f"Students reached rose from {prev_val} to {curr_val} in {single_year} (up {trend['pct']}%). This growth reflects excellent student interest and strong classroom mobilization from partner schools."
                suggestions = [
                    "<strong>Host Regional Student Showcases:</strong> Organize exhibitions where students can display project work to local communities.",
                    "<strong>Roll Out Level-2 Specializations:</strong> Launch follow-up modules to sustain engagement with successfully reached cohorts.",
                    "<strong>Leverage Peer-to-Peer Mentoring:</strong> Train high-performing students to act as assistant leaders inside classrooms.",
                    "<strong>Distribute Completion Certificates:</strong> Award official credentials to motivate students to attend the complete curriculum."
                ]
            else:
                rationale = f"Students reached held steady at {curr_val}. Reach is constant, indicating classrooms are currently operating at maximum physical sizes."
                suggestions = [
                    "<strong>Establish Multi-Section Scheduling:</strong> Split overcrowded classes to improve the student-to-instructor ratio.",
                    "<strong>Run Double-Session Rotations:</strong> Run twin cohorts (morning/afternoon) to reach more students with current staff."
                ]
                
        elif key == "total_sessions":
            if trend['dir'] == 'down':
                rationale = f"Total sessions executed decreased from {prev_val} to {curr_val} in {single_year} (down {abs(trend['pct'])}%). Missed slots due to weather, transport disruptions, and poor school schedule integration are the primary causes."
                suggestions = [
                    "<strong>Adopt Automated Scheduling Tools:</strong> Implement mobile calendars that send instant alerts to school principals and trainers.",
                    "<strong>Run Make-up Sessions:</strong> Dedicate specific weeks at the end of the term to catch up on cancelled classes.",
                    "<strong>Standardize Route Prep Checklists:</strong> Introduce vehicle checklists to prevent morning dispatch delays and missed sessions.",
                    "<strong>Build School Calendar Syncs:</strong> Coordinate session calendars with schools 60 days in advance to avoid test weeks.",
                    "<strong>Cross-Train Reserve Instructors:</strong> Certify administration staff in curricula to cover instructor sick days."
                ]
            elif trend['dir'] == 'up':
                rationale = f"Sessions conducted grew from {prev_val} to {curr_val} in {single_year} (up {trend['pct']}%). Improved fleet reliability and strong instructor coordination drove this increase."
                suggestions = [
                    "<strong>Reward 100% Compliance Hubs:</strong> Launch recognition awards for regional teams that hit all scheduled monthly sessions.",
                    "<strong>Optimize Trainer Load Balances:</strong> Balance teaching calendars to prevent instructor fatigue and session cancellations.",
                    "<strong>Implement Fast Setup Toolkits:</strong> Supply trainers with pre-packed visual aids to reduce classroom setup times."
                ]
            else:
                rationale = f"Sessions executed remained stable at {curr_val}. Operations are consistent but constrained by current coordinator limits."
                suggestions = [
                    "<strong>Audit Weekday Operations:</strong> Identify under-scheduled slots on Mondays/Fridays to increase total sessions.",
                    "<strong>Implement Continuous Enrollment Models:</strong> Run rolling enrollments to keep training slots occupied year-round."
                ]
                
        insights[key] = {
            "title": info["title"],
            "icon": info["icon"],
            "color": info["color"],
            "name": info["name"],
            "comparison_text": comparison_text,
            "rationale": rationale,
            "suggestions": suggestions
        }
    return insights


def get_program_impact_overview(region=None, years=None, program=None, limit=15, offset=0, dt_params=None):
    try:
        from backend.services.query_utils import get_ytd_max_month
        # ── resolve year context up-front ─────────────────────────────────────
        single_year = None
        if years and len(years) == 1:
            try:
                single_year = int(str(years[0])[:4])
            except (ValueError, TypeError):
                pass
        elif not years:
            single_year = DEFAULT_YEAR
            
        max_month = get_ytd_max_month(single_year) if single_year is not None else None
        where_sql, params = _build_clauses(region, years, program, force_max_month=max_month)
        
        prev_year = single_year - 1 if single_year is not None else None
        prev_where_sql, prev_params = (_build_clauses(region, [str(prev_year)], program, force_max_month=max_month)
                                       if prev_year is not None else (where_sql, params))

        search_sql, search_params = "TRUE", []
        sort_sql = "ORDER BY sessions DESC"
        if dt_params:
            s, sp, so = get_datatables_sql(dt_params, ["p.program_name", "p.donor_name", "g.region_name"],
                                           ["program", "donor", "sessions", "schools", "students", "instructors"])
            search_sql, search_params = s, sp
            if so: sort_sql = so

        # ── SQL templates ─────────────────────────────────────────────────────
        SQL_KPI = f"""
            SELECT COUNT(DISTINCT p.program_name) AS total_programs,
                   COUNT(DISTINCT f.sk_school_id) AS total_schools,
                   COALESCE(SUM(e.total_exposure_count),0) AS total_students,
                   COUNT(DISTINCT f.sk_fact_session_id) AS total_sessions
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_program p ON f.sk_program_id = p.sk_program_id
            LEFT JOIN {DW}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            WHERE {where_sql}"""

        SQL_PREV_KPI = f"""
            SELECT COUNT(DISTINCT p.program_name) AS total_programs,
                   COUNT(DISTINCT f.sk_school_id) AS total_schools,
                   COALESCE(SUM(e.total_exposure_count),0) AS total_students,
                   COUNT(DISTINCT f.sk_fact_session_id) AS total_sessions
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_program p ON f.sk_program_id = p.sk_program_id
            LEFT JOIN {DW}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            WHERE {prev_where_sql}"""

        SQL_PROG = f"""
            SELECT COALESCE(p.program_name,'Unknown') AS label,
                   COUNT(DISTINCT f.sk_fact_session_id) AS value
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_program p ON f.sk_program_id = p.sk_program_id
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d ON f.date_id = d.date_id
            WHERE {where_sql} AND p.program_name IS NOT NULL
            GROUP BY p.program_name ORDER BY value DESC LIMIT 8"""

        SQL_TREND = f"""
            SELECT TO_CHAR(d.full_date, 'Mon YYYY') AS label,
                   COALESCE(SUM(e.total_exposure_count),0) AS value, MIN(d.full_date) AS sort_key
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_date d ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_program p ON f.sk_program_id = p.sk_program_id
            LEFT JOIN {DW}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            WHERE {where_sql} GROUP BY TO_CHAR(d.full_date, 'Mon YYYY') ORDER BY sort_key"""

        SQL_REGION = f"""
            SELECT COALESCE(g.region_name,'Unknown') AS label,
                   COALESCE(SUM(e.total_exposure_count),0) AS value
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_program p ON f.sk_program_id = p.sk_program_id
            LEFT JOIN {DW}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            WHERE {where_sql} AND g.region_name IS NOT NULL
            GROUP BY g.region_name ORDER BY value DESC LIMIT 8"""

        SQL_COUNT = f"""
            SELECT COUNT(*) FROM (
                SELECT p.sk_program_id FROM {DW}.fact_session f
                LEFT JOIN {DW}.dim_program p ON f.sk_program_id = p.sk_program_id
                LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
                LEFT JOIN {DW}.dim_date d ON f.date_id = d.date_id
                WHERE {where_sql} AND {search_sql} GROUP BY p.sk_program_id
            ) sub"""

        SQL_TABLE = f"""
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
            {sort_sql} LIMIT %s OFFSET %s"""

        SQL_SPARKLINE = f"""
            SELECT d.year_actual, d.month_actual, MIN(d.full_date) AS sort_key,
                   COUNT(DISTINCT p.program_name) AS programs,
                   COUNT(DISTINCT f.sk_school_id) AS schools,
                   COALESCE(SUM(e.total_exposure_count), 0) AS students,
                   COUNT(DISTINCT f.sk_fact_session_id) AS sessions
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d      ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_program p   ON f.sk_program_id = p.sk_program_id
            LEFT JOIN {DW}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            WHERE {where_sql} GROUP BY d.year_actual, d.month_actual ORDER BY sort_key LIMIT 24"""

        futures_map = {}
        with ThreadPoolExecutor(max_workers=8) as ex:
            futures_map["kpi"]      = ex.submit(fetch_one,  SQL_KPI,      params)
            futures_map["prog"]     = ex.submit(fetch_all,  SQL_PROG,     params)
            futures_map["trend"]    = ex.submit(fetch_all,  SQL_TREND,    params)
            futures_map["region"]   = ex.submit(fetch_all,  SQL_REGION,   params)
            futures_map["count"]    = ex.submit(fetch_one,  SQL_COUNT,    params + search_params)
            futures_map["table"]    = ex.submit(fetch_all,  SQL_TABLE,    params + search_params + [limit, offset])
            futures_map["sparkline"]= ex.submit(fetch_all,  SQL_SPARKLINE,params)
            if prev_year is not None:
                futures_map["prev_kpi"] = ex.submit(fetch_one, SQL_PREV_KPI, prev_params)

        kpi          = futures_map["kpi"].result()
        prog_rows    = futures_map["prog"].result()
        trend_rows   = futures_map["trend"].result()
        region_rows  = futures_map["region"].result()
        count_row    = futures_map["count"].result()
        table        = futures_map["table"].result()
        sparkline_rows = futures_map["sparkline"].result()

        tp    = int(kpi.get("total_programs", 0) or 0)
        t_sch = int(kpi.get("total_schools",  0) or 0)
        t_stu = int(kpi.get("total_students", 0) or 0)
        t_sess= int(kpi.get("total_sessions", 0) or 0)

        trends_yo_y = None
        prev_vals = None
        if prev_year is not None and "prev_kpi" in futures_map:
            try:
                prev_kpi = futures_map["prev_kpi"].result()
                p_tp    = int(prev_kpi.get("total_programs", 0) or 0)
                p_t_sch = int(prev_kpi.get("total_schools",  0) or 0)
                p_t_stu = int(prev_kpi.get("total_students", 0) or 0)
                p_t_sess= int(prev_kpi.get("total_sessions", 0) or 0)
                prev_vals = {"total_programs": p_tp, "total_schools": p_t_sch,
                             "total_students": p_t_stu, "total_sessions": p_t_sess}
                trends_yo_y = {
                    "total_programs": calc_trend(tp, p_tp),
                    "total_schools":  calc_trend(t_sch, p_t_sch),
                    "total_students": calc_trend(t_stu, p_t_stu),
                    "total_sessions": calc_trend(t_sess, p_t_sess),
                }
            except Exception as e:
                logger.error(f"program previous year fetch error: {e}")

        curr_vals = {"total_programs": tp, "total_schools": t_sch,
                     "total_students": t_stu, "total_sessions": t_sess}
        insights = generate_program_insights(curr_vals, prev_vals, trends_yo_y, single_year, prev_year, max_month)

        kpis_response = {"total_programs": tp, "total_schools": t_sch,
                         "total_students": t_stu, "total_sessions": t_sess, "insights": insights}
        if trends_yo_y:
            kpis_response["trends"] = trends_yo_y

        charts = {
            "by_program": [{"label": r["label"], "value": int(r["value"])} for r in prog_rows],
            "trend":      [{"label": r["label"], "value": int(r["value"])} for r in trend_rows],
            "by_region":  [{"label": r["label"], "value": int(r["value"])} for r in region_rows],
        }
        count = count_row.get("count", 0) if count_row else 0
        monthly_trends = [{"programs": int(r["programs"] or 0), "schools": int(r["schools"] or 0),
                           "students": int(r["students"] or 0), "sessions": int(r["sessions"] or 0)}
                          for r in sparkline_rows]

        sparklines = {
            "programs": [prev_vals.get("total_programs", tp) if prev_vals else tp, tp],
            "schools": [prev_vals.get("total_schools", t_sch) if prev_vals else t_sch, t_sch],
            "students": [prev_vals.get("total_students", t_stu) if prev_vals else t_stu, t_stu],
            "sessions": [prev_vals.get("total_sessions", t_sess) if prev_vals else t_sess, t_sess]
        }

        return {"kpis": kpis_response, "charts": charts, "table": table,
                "total_count": int(count), "trends": monthly_trends, "sparklines": sparklines}
    except Exception as ex:
        logger.error(f"program impact overview error: {ex}", exc_info=True)
        return {"kpis": {}, "charts": {}, "table": [], "total_count": 0, "trends": [], "sparklines": {}}


# ═══════════════════════════════════════════════════════════════
#  OPERATIONS INSIGHTS GENERATOR
# ═══════════════════════════════════════════════════════════════

def generate_operations_insights(curr_vals, prev_vals, trends, single_year, prev_year, max_month=None):
    insights = {}
    meta = {
        "working_days": {
            "title": "Total Working Days Insights",
            "icon": "fas fa-calendar-check",
            "color": "linear-gradient(135deg, #17a2b8 0%, #117a8b 100%)",
            "name": "Working Days"
        },
        "active_drivers": {
            "title": "Active Drivers Insights",
            "icon": "fas fa-truck",
            "color": "linear-gradient(135deg, #28a745 0%, #218838 100%)",
            "name": "Active Drivers"
        },
        "total_kms": {
            "title": "Distance Travelled Insights",
            "icon": "fas fa-road",
            "color": "linear-gradient(135deg, #001f3f 0%, #001226 100%)",
            "name": "Total KMs Travelled"
        },
        "active_centers": {
            "title": "Active Centers Insights",
            "icon": "fas fa-map-marker-alt",
            "color": "linear-gradient(135deg, #dc3545 0%, #c82333 100%)",
            "name": "Active Centers"
        }
    }
    
    for key, info in meta.items():
        curr_val = curr_vals.get(key, 0)
        prev_val = prev_vals.get(key, 0) if prev_vals else 0
        trend = trends.get(key, {"pct": 0, "dir": "neutral"}) if trends else {"pct": 0, "dir": "neutral"}
        
        def fmt(v):
            v = float(v)
            return str(int(v)) if v == int(v) else f"{v:.1f}"

        if single_year is not None:
            pct_str = f"{abs(trend['pct'])}%"
            if trend['dir'] == 'up':
                change_desc = f"representing an increase of <strong>{pct_str}</strong> compared to last year"
            elif trend['dir'] == 'down':
                change_desc = f"representing a decrease of <strong>{pct_str}</strong> compared to last year"
            else:
                change_desc = "remaining unchanged compared to last year"
                
            months_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
            month_range_str = f"Jan-{months_names[max_month-1]}" if (max_month and 1 <= max_month <= 12) else "YTD"
            
            comparison_text = f"In the current year-to-date period ({month_range_str}) of <strong>{single_year}</strong>, the total {info['name'].lower()} is <strong>{fmt(curr_val)}</strong> while the previous year-to-date period ({month_range_str}) of <strong>{prev_year}</strong> was <strong>{fmt(prev_val)}</strong> ({change_desc})."
        else:
            comparison_text = f"Currently viewing aggregated data across multiple years. Total {info['name'].lower()} is <strong>{fmt(curr_val)}</strong>."
            
        rationale = ""
        suggestions = []
        
        if key == "working_days":
            if trend['dir'] == 'down':
                rationale = f"Total working days dropped from {prev_val} to {curr_val} in {single_year} (down {abs(trend['pct'])}%). This indicates scheduling issues, instructor call-offs, or administrative delays in session tracking."
                suggestions = [
                    "<strong>Streamline Attendance Submissions:</strong> Implement mobile one-click attendance check-ins for field coordinators.",
                    "<strong>Establish Backup Scheduling Rules:</strong> Pre-approve substitute coverages to keep active training days on calendar.",
                    "<strong>Optimize Weekly Operational Layouts:</strong> Distribute teaching slots evenly across weekdays (avoiding Monday gaps).",
                    "<strong>Simplify Daily Log Paperwork:</strong> Eliminate redundant post-trip write-ups to encourage timely digital submissions.",
                    "<strong>Conduct Center Attendance Audits:</strong> Direct regional leads to address scheduling compliance bottlenecks at underperforming hubs."
                ]
            elif trend['dir'] == 'up':
                rationale = f"Total working days increased from {prev_val} to {curr_val} in {single_year} (up {trend['pct']}%). This indicates excellent workforce dedication, structured scheduling, and robust data logging."
                suggestions = [
                    "<strong>Standardize Schedule Handbooks:</strong> Map out successful coordination processes to replicate in new operational centers.",
                    "<strong>Recognize Hub Attendance Leaders:</strong> Reward teams that achieve 100% planned calendar check-ins monthly.",
                    "<strong>Build Predictive Shift Allocation:</strong> Use historic data to schedule reserve slots on days with traditionally high call-off rates."
                ]
            else:
                rationale = f"Total working days are constant at {curr_val}. Workforce activity is steady but constrained by current supervisor quotas."
                suggestions = [
                    "<strong>Analyze Center Operations:</strong> Perform checks on under-performing days of the week to maximize calendar density.",
                    "<strong>Introduce Seasonal Coverage Pools:</strong> Recruit contract trainers to support permanent staff during peak harvest periods."
                ]
                
        elif key == "active_drivers":
            if trend['dir'] == 'down':
                rationale = f"Active drivers count decreased from {prev_val} to {curr_val} in {single_year} (down {abs(trend['pct'])}%). Competitive commercial transport salaries, driver attrition, and route consolidation are the main causes."
                suggestions = [
                    "<strong>Revamp Driver Salary Structures:</strong> Align local rates with market logistics standards to increase retention.",
                    "<strong>Launch Fuel Efficiency Rewards:</strong> Share route savings directly with drivers who meet consumption targets.",
                    "<strong>Contract On-Demand Agencies:</strong> Keep active backup driver support agreements ready for peak delivery seasons.",
                    "<strong>Optimize Central Warehouse Loading:</strong> Speed up vehicle loading times to increase daily route driver capacities.",
                    "<strong>Deliver Preventive Fleet Care:</strong> Schedule vehicle inspections on weekends to prevent weekday driver stand-downs."
                ]
            elif trend['dir'] == 'up':
                rationale = f"Active drivers count increased from {prev_val} to {curr_val} in {single_year} (up {trend['pct']}%). This growth supports the expansion of delivery networks to remote school clusters."
                suggestions = [
                    "<strong>Deploy Defensive Driving Training:</strong> Conduct regular safety training to minimize vehicle wear and collision costs.",
                    "<strong>Establish Roadside Rest Hubs:</strong> Set up secure rest facilities along long-distance routes to support driver safety.",
                    "<strong>Implement Digital Pre-Trip Inspections:</strong> Require drivers to complete digital inspection lists before starting trips."
                ]
            else:
                rationale = f"Active driver count remains stable at {curr_val}. Current logistics lines are supported, but there is zero redundancy for route growth."
                suggestions = [
                    "<strong>Cross-Train Warehouse Teams:</strong> License warehouse staff to drive light duty vehicles in emergencies.",
                    "<strong>Standardize Shift Handovers:</strong> Optimize schedule switches to maximize daily vehicle driving limits."
                ]
                
        elif key == "total_kms":
            if trend['dir'] == 'down':
                rationale = f"Total KMs travelled decreased from {prev_val} to {curr_val} in {single_year} (down {abs(trend['pct'])}%). This indicates improved route planning, vehicle breakdowns, or reduced school visit frequencies."
                suggestions = [
                    "<strong>Deploy Dynamic Routing Softwares:</strong> Optimize distribution plans to cut unnecessary travel times and fuel expenses.",
                    "<strong>Set Up Local Spares Hubs:</strong> Position parts inventories closer to active regions to minimize vehicle repair times.",
                    "<strong>Track Fleet Idle Statistics:</strong> Monitor GPS coordinates to detect and resolve unauthorized detours.",
                    "<strong>Establish Multi-School Dropoff Schedules:</strong> Deliver materials to multiple adjacent schools in a single circular trip.",
                    "<strong>Run Standardized Driver Log Audits:</strong> Inspect daily route records to align distances with planned Google Map pathing."
                ]
            elif trend['dir'] == 'up':
                rationale = f"Total distance travelled increased from {prev_val} to {curr_val} in {single_year} (up {trend['pct']}%). This reflects geographical expansion and increased delivery frequencies to remote zones."
                suggestions = [
                    "<strong>Negotiate Bulk Fuel Pricing:</strong> Contract with fuel networks to secure discounts and lower transportation overhead.",
                    "<strong>Evaluate Hub-and-Spoke Logistics:</strong> Transit goods from central depots to satellite sorting hubs to lower per-mile costs.",
                    "<strong>Standardize Fleet Checkup Schedules:</strong> Mandate tire changes and engine service intervals to manage vehicle lifetimes."
                ]
            else:
                rationale = f"Total KMs travelled remained flat at {curr_val}. Fleet logistics paths are constant and fully utilized."
                suggestions = [
                    "<strong>Consolidate Delivery Cycles:</strong> Combine supply deliveries to reduce fuel costs and vehicle wear.",
                    "<strong>Conduct Route Efficiency Audits:</strong> Re-examine current maps to identify shorter alternative routes."
                ]
                
        elif key == "active_centers":
            if trend['dir'] == 'down':
                rationale = f"Active centers dropped from {prev_val} to {curr_val} in {single_year} (down {abs(trend['pct'])}%). Delayed renewals of government MoUs, funding sunsets, or consolidations of small regional offices caused the decrease."
                suggestions = [
                    "<strong>Setup Center MoU Taskforces:</strong> Form dedicated government liaison desks to handle center approvals 120 days in advance.",
                    "<strong>Build Standard Center Blueprints:</strong> Simplify site selection and training setup to quicken center openings.",
                    "<strong>Partner with Local Education Trusts:</strong> Share properties with district NGOs to lower rent and infrastructure startup costs.",
                    "<strong>Deliver Regional Impact Showcases:</strong> Highlight center community benefits to local officials to secure spaces.",
                    "<strong>Align Expansion with High Density:</strong> Establish new sites in areas adjacent to existing centers to share administrative teams."
                ]
            elif trend['dir'] == 'up':
                rationale = f"Active centers increased from {prev_val} to {curr_val} in {single_year} (up {trend['pct']}%). This growth demonstrates successful district entries and strong backing from regional boards."
                suggestions = [
                    "<strong>Establish Central Admin Nodes:</strong> Manage clusters of centers through single administrative leads.",
                    "<strong>Deploy Site Quality Audits:</strong> Audit class setups at new sites to guarantee consistency.",
                    "<strong>Deliver State Department Impact Portals:</strong> Provide live views to board directors to secure long-term funding."
                ]
            else:
                rationale = f"Active centers held steady at {curr_val}. Operations are focused on strengthening existing districts before entering new regions."
                suggestions = [
                    "<strong>Saturate Local School Networks:</strong> Connect with more schools in current center zones to maximize local impact.",
                    "<strong>Host Regional Community Days:</strong> Open centers to the public during weekends to improve community connections."
                ]
                
        insights[key] = {
            "title": info["title"],
            "icon": info["icon"],
            "color": info["color"],
            "name": info["name"],
            "comparison_text": comparison_text,
            "rationale": rationale,
            "suggestions": suggestions
        }
    return insights


def get_operations_overview(region=None, years=None, program=None, limit=15, offset=0, dt_params=None):
    try:
        from backend.services.query_utils import get_ytd_max_month, apply_ytd_filter
        # ── resolve year context ──────────────────────────────────────────────
        single_year = None
        if years and len(years) == 1:
            try:
                single_year = int(str(years[0])[:4])
            except (ValueError, TypeError):
                pass
        elif not years:
            single_year = DEFAULT_YEAR
            
        max_month = get_ytd_max_month(single_year) if single_year is not None else None
        where_sql, params = _build_clauses(region, years, program, force_max_month=max_month)

        # ── vehicle WHERE clause (no program filter) ──────────────────────────
        veh_clauses, veh_params = [], []
        c, p = get_list_filter_clause("g.region_name", region); veh_clauses.append(c); veh_params.extend(p)
        c, p = get_list_filter_clause("d.year_actual", years, cast_type="int"); veh_clauses.append(c); veh_params.extend(p)
        veh_where_sql = " AND ".join(veh_clauses) if veh_clauses else "TRUE"
        veh_where_sql, veh_params = apply_ytd_filter(veh_where_sql, veh_params, years, date_alias="d", force_max_month=max_month)

        prev_year = single_year - 1 if single_year is not None else None
        prev_where_sql, prev_params = (_build_clauses(region, [str(prev_year)], program, force_max_month=max_month)
                                       if prev_year is not None else (where_sql, params))

        prev_veh_params = []
        if prev_year is not None:
            c, p = get_list_filter_clause("g.region_name", region); prev_veh_params.extend(p)
            c, p = get_list_filter_clause("d.year_actual", [str(prev_year)], cast_type="int"); prev_veh_params.extend(p)
            prev_veh_clauses = []
            c, _ = get_list_filter_clause("g.region_name", region); prev_veh_clauses.append(c)
            c, _ = get_list_filter_clause("d.year_actual", [str(prev_year)], cast_type="int"); prev_veh_clauses.append(c)
            prev_veh_where_sql = " AND ".join(prev_veh_clauses) if prev_veh_clauses else "TRUE"
            prev_veh_where_sql, prev_veh_params = apply_ytd_filter(prev_veh_where_sql, prev_veh_params, [str(prev_year)], date_alias="d", force_max_month=max_month)
        else:
            prev_veh_where_sql, prev_veh_params = veh_where_sql, veh_params

        search_sql, search_params = "TRUE", []
        sort_sql = "ORDER BY working_days DESC"
        if dt_params:
            s, sp, so = get_datatables_sql(dt_params, ["g.region_name"],
                                           ["region", "instructors", "working_days", "drivers", "kms", "fuel_cost"])
            search_sql, search_params = s, sp
            if so: sort_sql = so

        # ── SQL templates ─────────────────────────────────────────────────────
        SQL_SESS_KPI = f"""
            SELECT COUNT(DISTINCT CONCAT(f.sk_user_id,'_',f.date_id)) AS working_days,
                   COUNT(DISTINCT f.sk_geography_id) AS active_centers
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_program p ON f.sk_program_id = p.sk_program_id
            WHERE {where_sql}"""

        SQL_VEH_KPI = f"""
            SELECT COUNT(DISTINCT v.sk_driver_id) AS active_drivers,
                   COALESCE(SUM(v.distance_travelled),0) AS total_kms
            FROM {DW}.fact_vehicle_operations v
            LEFT JOIN {DW}.dim_geography g ON v.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d ON v.date_id = d.date_id
            WHERE {veh_where_sql}"""

        SQL_PREV_SESS = f"""
            SELECT COUNT(DISTINCT CONCAT(f.sk_user_id,'_',f.date_id)) AS working_days,
                   COUNT(DISTINCT f.sk_geography_id) AS active_centers
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_program p ON f.sk_program_id = p.sk_program_id
            WHERE {prev_where_sql}"""

        SQL_PREV_VEH = f"""
            SELECT COUNT(DISTINCT v.sk_driver_id) AS active_drivers,
                   COALESCE(SUM(v.distance_travelled),0) AS total_kms
            FROM {DW}.fact_vehicle_operations v
            LEFT JOIN {DW}.dim_geography g ON v.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d ON v.date_id = d.date_id
            WHERE {prev_veh_where_sql}"""

        SQL_KM_REGION = f"""
            SELECT COALESCE(g.region_name,'Unknown') AS label,
                   COALESCE(SUM(v.distance_travelled),0) AS value
            FROM {DW}.fact_vehicle_operations v
            LEFT JOIN {DW}.dim_geography g ON v.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d ON v.date_id = d.date_id
            WHERE {veh_where_sql} AND g.region_name IS NOT NULL
            GROUP BY g.region_name ORDER BY value DESC LIMIT 8"""

        SQL_TREND = f"""
            SELECT TO_CHAR(d.full_date, 'Mon YYYY') AS label,
                   COUNT(DISTINCT CONCAT(f.sk_user_id,'_',f.date_id)) AS value,
                   MIN(d.full_date) AS sort_key
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_date d ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_program p ON f.sk_program_id = p.sk_program_id
            WHERE {where_sql} GROUP BY TO_CHAR(d.full_date, 'Mon YYYY') ORDER BY sort_key"""

        SQL_VEH_USAGE = f"""
            SELECT COALESCE(g.region_name,'Unknown') AS label,
                   COUNT(DISTINCT v.sk_driver_id) AS value
            FROM {DW}.fact_vehicle_operations v
            LEFT JOIN {DW}.dim_geography g ON v.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d ON v.date_id = d.date_id
            WHERE {veh_where_sql} AND g.region_name IS NOT NULL
            GROUP BY g.region_name ORDER BY value DESC LIMIT 8"""

        SQL_COUNT = f"""
            SELECT COUNT(*) FROM (
                SELECT g.region_name FROM {DW}.fact_session f
                LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
                LEFT JOIN {DW}.dim_date d ON f.date_id = d.date_id
                LEFT JOIN {DW}.dim_program p ON f.sk_program_id = p.sk_program_id
                WHERE {where_sql} AND {search_sql} AND g.region_name IS NOT NULL
                GROUP BY g.region_name
            ) sub"""

        SQL_TABLE = f"""
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
            GROUP BY g.region_name {sort_sql} LIMIT %s OFFSET %s"""

        SQL_SESS_TREND = f"""
            SELECT d.year_actual, d.month_actual, MIN(d.full_date) AS sort_key,
                   COUNT(DISTINCT CONCAT(f.sk_user_id,'_',f.date_id)) AS working_days,
                   COUNT(DISTINCT f.sk_geography_id) AS active_centers
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d      ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_program p   ON f.sk_program_id = p.sk_program_id
            WHERE {where_sql} GROUP BY d.year_actual, d.month_actual ORDER BY sort_key LIMIT 24"""

        SQL_VEH_TREND = f"""
            SELECT d.year_actual, d.month_actual, MIN(d.full_date) AS sort_key,
                   COUNT(DISTINCT v.sk_driver_id) AS active_drivers,
                   COALESCE(SUM(v.distance_travelled), 0) AS total_kms
            FROM {DW}.fact_vehicle_operations v
            LEFT JOIN {DW}.dim_geography g ON v.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d      ON v.date_id = d.date_id
            WHERE {veh_where_sql} GROUP BY d.year_actual, d.month_actual ORDER BY sort_key LIMIT 24"""

        futures_map = {}
        with ThreadPoolExecutor(max_workers=12) as ex:
            futures_map["sess_kpi"]   = ex.submit(fetch_one,  SQL_SESS_KPI,   params)
            futures_map["veh_kpi"]    = ex.submit(fetch_one,  SQL_VEH_KPI,    veh_params)
            futures_map["km_region"]  = ex.submit(fetch_all,  SQL_KM_REGION,  veh_params)
            futures_map["trend"]      = ex.submit(fetch_all,  SQL_TREND,      params)
            futures_map["veh_usage"]  = ex.submit(fetch_all,  SQL_VEH_USAGE,  veh_params)
            futures_map["count"]      = ex.submit(fetch_one,  SQL_COUNT,      params + search_params)
            futures_map["table"]      = ex.submit(fetch_all,  SQL_TABLE,      params + search_params + [limit, offset])
            futures_map["sess_trend"] = ex.submit(fetch_all,  SQL_SESS_TREND, params)
            futures_map["veh_trend"]  = ex.submit(fetch_all,  SQL_VEH_TREND,  veh_params)
            if prev_year is not None:
                futures_map["prev_sess"] = ex.submit(fetch_one, SQL_PREV_SESS, prev_params)
                futures_map["prev_veh"]  = ex.submit(fetch_one, SQL_PREV_VEH,  prev_veh_params)

        sess_kpi     = futures_map["sess_kpi"].result()
        veh_kpi      = futures_map["veh_kpi"].result()
        km_rows      = futures_map["km_region"].result()
        trend_rows   = futures_map["trend"].result()
        veh_rows     = futures_map["veh_usage"].result()
        count_row    = futures_map["count"].result()
        table        = futures_map["table"].result()
        sess_trend_rows = futures_map["sess_trend"].result()
        veh_trend_rows  = futures_map["veh_trend"].result()

        wd = int(sess_kpi.get("working_days",   0) or 0)
        ac = int(sess_kpi.get("active_centers", 0) or 0)
        ad = int(veh_kpi.get("active_drivers",  0) or 0)
        tk = int(veh_kpi.get("total_kms",       0) or 0)

        trends_yo_y = None
        prev_vals = None
        if prev_year is not None and "prev_sess" in futures_map:
            try:
                prev_sess_kpi = futures_map["prev_sess"].result()
                prev_veh_kpi  = futures_map["prev_veh"].result()
                p_wd = int(prev_sess_kpi.get("working_days",   0) or 0)
                p_ac = int(prev_sess_kpi.get("active_centers", 0) or 0)
                p_ad = int(prev_veh_kpi.get("active_drivers",  0) or 0)
                p_tk = int(prev_veh_kpi.get("total_kms",       0) or 0)
                prev_vals = {"working_days": p_wd, "active_drivers": p_ad,
                             "total_kms": p_tk, "active_centers": p_ac}
                trends_yo_y = {
                    "working_days":   calc_trend(wd, p_wd),
                    "active_drivers": calc_trend(ad, p_ad),
                    "total_kms":      calc_trend(tk, p_tk),
                    "active_centers": calc_trend(ac, p_ac),
                }
            except Exception as e:
                logger.error(f"operations previous year fetch error: {e}")

        curr_vals = {"working_days": wd, "active_drivers": ad,
                     "total_kms": tk, "active_centers": ac}
        insights = generate_operations_insights(curr_vals, prev_vals, trends_yo_y, single_year, prev_year, max_month)

        kpis_response = {"working_days": wd, "active_drivers": ad,
                         "total_kms": tk, "active_centers": ac, "insights": insights}
        if trends_yo_y:
            kpis_response["trends"] = trends_yo_y

        charts = {
            "km_by_region":  [{"label": r["label"], "value": int(r["value"])} for r in km_rows],
            "trend":         [{"label": r["label"], "value": int(r["value"])} for r in trend_rows],
            "vehicle_usage": [{"label": r["label"], "value": int(r["value"])} for r in veh_rows],
        }
        count = count_row.get("count", 0) if count_row else 0

        veh_map = {(r["year_actual"], r["month_actual"]): r for r in veh_trend_rows}
        monthly_trends = []
        for r in sess_trend_rows:
            key = (r["year_actual"], r["month_actual"])
            v   = veh_map.get(key, {"active_drivers": 0, "total_kms": 0})
            monthly_trends.append({
                "working_days":   int(r["working_days"] or 0),
                "active_drivers": int(v.get("active_drivers", 0) or 0),
                "total_kms":      int(v.get("total_kms", 0) or 0),
                "active_centers": int(r["active_centers"] or 0),
            })

        sparklines = {
            "working_days": [prev_vals.get("working_days", wd) if prev_vals else wd, wd],
            "active_drivers": [prev_vals.get("active_drivers", ad) if prev_vals else ad, ad],
            "total_kms": [prev_vals.get("total_kms", tk) if prev_vals else tk, tk],
            "active_centers": [prev_vals.get("active_centers", ac) if prev_vals else ac, ac]
        }

        return {"kpis": kpis_response, "charts": charts, "table": table,
                "total_count": int(count), "trends": monthly_trends, "sparklines": sparklines}
    except Exception as ex:
        logger.error(f"operations overview error: {ex}", exc_info=True)
        return {"kpis": {}, "charts": {}, "table": [], "total_count": 0, "trends": [], "sparklines": {}}
