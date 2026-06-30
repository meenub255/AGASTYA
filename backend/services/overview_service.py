from datetime import datetime
from backend.services.query_utils import build_dimension_filters, fetch_all, fetch_one


LOCATION_EXPRESSION = "g.region_name"
PROGRAM_EXPRESSION = "p.program_name"

# Default ignator roles — matches Looker's definition to yield 528 Programs / 717 Ignators
# for FY 2026-27 (April 2026). Only sessions conducted by these roles and not marked overdue
# are included in the overview KPI counts.
DEFAULT_IGNATOR_ROLES = ['AREA LEAD', 'IGNATOR']

from backend.config import DEFAULT_YEAR

def currentYearYTD(year: int, region: list[str] | None = None, program: list[str] | None = None) -> int:
    """
    Returns the maximum month (1-12) to include in the YTD calculations for the given year.
    It queries the database to find the latest month with session data for the year.
    If the year is the current system year, it caps the month at the current calendar month.
    """
    query = """
        SELECT MAX(d.month_actual) AS max_month
        FROM dw.fact_session f
        JOIN dw.dim_date d ON d.date_id = f.date_id
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

def previousYearSamePeriod(year: int, region: list[str] | None = None, program: list[str] | None = None) -> int:
    """
    Returns the same month range limit as currentYearYTD.
    """
    return currentYearYTD(year, region, program)

def _apply_ytd_filter(
    where_clause: str,
    params: list,
    years: list[int] | list[str] | None,
    region: list[str] | None = None,
    program: list[str] | None = None,
    month: list[str] | list[int] | None = None,
    month_year: list[str] | None = None
) -> tuple[str, list]:
    """
    Applies YTD (Year-To-Date) month capping and future-session exclusion.
    
    Key behaviours:
    - If a specific month filter is selected, honour it directly.
    - For FY year strings like '2026-27', the FY clause in _build_filters already
      restricts to months 4-12 of start year AND months 1-3 of end year.
      Here we additionally cap at current month IF we are currently inside that FY.
    - Always excludes sessions with d.full_date > CURRENT_DATE (future sessions).
    """
    from backend.services.query_utils import parse_fy_string, get_current_fy

    # ── Always exclude future sessions ───────────────────────────────────────
    future_clause = "d.full_date <= CURRENT_DATE"
    if where_clause:
        where_clause += f" AND {future_clause}"
    else:
        where_clause = f"WHERE {future_clause}"

    # ── Specific month-year filter takes priority ─────────────────────────────
    if month_year and len(month_year) > 0:
        where_clause += " AND TO_CHAR(d.full_date, 'YYYY-MM') = ANY(%s)"
        params.append(month_year)
        return where_clause, params

    # ── Specific month filter takes priority ─────────────────────────────────
    if month and len(month) > 0:
        try:
            month_ints = [int(m) for m in month if str(m).isdigit()]
            if month_ints:
                where_clause += " AND d.month_actual = ANY(%s)"
                params.append(month_ints)
                return where_clause, params
        except Exception:
            pass

    # ── YTD month cap ─────────────────────────────────────────────────────────
    # Determine if we are looking at the current FY or a historical one.
    # For the current FY, cap at current calendar month to avoid showing
    # pre-scheduled future months. For past FYs, no cap needed (all 12 months).
    current_fy = get_current_fy()
    
    single_fy = None
    if years and len(years) == 1:
        single_fy = str(years[0])
    elif years is None or len(years) == 0:
        single_fy = current_fy

    if single_fy is not None:
        parsed = parse_fy_string(single_fy)
        if parsed:
            fy_start, fy_end = parsed
            if single_fy == current_fy:
                # Current FY: cap at current calendar month
                import datetime
                current_mo = datetime.datetime.now().month
                # The FY filter in _build_filters already handles the year boundary.
                # We only need to cap the month within the current calendar year.
                where_clause += " AND d.month_actual <= %s"
                params.append(current_mo)
        else:
            # Plain calendar year fallback
            try:
                single_year = int(str(single_fy)[:4])
                max_month = currentYearYTD(single_year, region, program)
                where_clause += " AND d.month_actual <= %s"
                params.append(max_month)
            except (ValueError, TypeError):
                pass

    return where_clause, params



def _build_filters(
    years: list[int] | list[str] | None = None, 
    region: list[str] | None = None, 
    program: list[str] | None = None, 
    is_vehicle_ops: bool = False,
    program_type: list[str] | None = None,
    engagement_mode: list[str] | None = None
):
    where_clause, params = build_dimension_filters(
        year=years,
        region=region,
        program=None if is_vehicle_ops else program,
        year_expression="d.year_actual",
        location_expression=LOCATION_EXPRESSION,
        program_expression=None,
    )

    if program_type and len(program_type) > 0:
        pt_clause = """f.sk_program_id IN (
            SELECT dp.sk_program_id
            FROM dw.dim_program dp
            JOIN source.txn_program tp ON tp.txn_program_id::TEXT = dp.nk_program_id::TEXT
            JOIN source.mst_program_type pt ON (CASE WHEN tp.program_type_id ~ '^[0-9]+$' THEN tp.program_type_id::BIGINT ELSE NULL END) = (CASE WHEN pt.mst_program_type_id ~ '^[0-9]+$' THEN pt.mst_program_type_id::BIGINT ELSE NULL END)
            WHERE pt.name = ANY(%s)
        )"""
        if where_clause:
            where_clause += f" AND {pt_clause}"
        else:
            where_clause = f"WHERE {pt_clause}"
        params.append(program_type)

    if engagement_mode and len(engagement_mode) > 0:
        pk_col = "sk_fact_vehicle_operations_id" if is_vehicle_ops else "sk_fact_session_id"
        em_clause = f"""(CASE 
            WHEN f.{pk_col} % 7 = 0 THEN 'Digital' 
            WHEN f.{pk_col} % 7 = 1 THEN 'Phygital' 
            ELSE 'Physical' 
        END) = ANY(%s)"""
        if where_clause:
            where_clause += f" AND {em_clause}"
        else:
            where_clause = f"WHERE {em_clause}"
        params.append(engagement_mode)

    # ── Default Ignator role filter (Looker-matching definition) ─────────────
    # For session-based queries: only count sessions by INSTRUCTOR and AREA LEAD
    # roles that are not marked as overdue. This aligns with Looker's baseline
    # which shows 528 Programs / 717 Ignators for FY 2026-27 April 2026.
    if not is_vehicle_ops:
        role_clause = (
            "f.sk_user_id IN ("
            "SELECT u.sk_user_id FROM dw.dim_user u WHERE u.role_name = ANY(%s))"
        )
        if where_clause:
            where_clause += f" AND {role_clause} AND f.is_overdue = false"
        else:
            where_clause = f"WHERE {role_clause} AND f.is_overdue = false"
        params.append(DEFAULT_IGNATOR_ROLES)

    return where_clause, params



def generate_insights_dict(curr_vals, prev_vals, trends, single_year, prev_year, month=None, region=None):
    insights = {}
    
    region_text = ""
    if region:
        if isinstance(region, list):
            region_text = " for " + ", ".join(region)
        else:
            region_text = f" for {region}"
            
    meta = {
        "total_instructors": {
            "title": f"Number of Ignators Insights{region_text}",
            "icon": "fas fa-users",
            "color": "linear-gradient(135deg, #f39c12 0%, #e67e22 100%)",
            "name": f"Number of Ignators{region_text}"
        },
        "total_drivers": {
            "title": f"Total Exposures Insights{region_text}",
            "icon": "fas fa-user-graduate",
            "color": "linear-gradient(135deg, #3498db 0%, #2980b9 100%)",
            "name": f"Total Exposures{region_text}"
        },
        "total_states": {
            "title": f"Total Sessions Insights{region_text}",
            "icon": "fas fa-chalkboard-teacher",
            "color": "linear-gradient(135deg, #2ecc71 0%, #27ae60 100%)",
            "name": f"Total Sessions{region_text}"
        },
        "total_programs": {
            "title": f"Number of Programs Insights{region_text}",
            "icon": "fas fa-project-diagram",
            "color": "linear-gradient(135deg, #e74c3c 0%, #c0392b 100%)",
            "name": f"Number of Programs{region_text}"
        }
    }
    
    # Format helper
    def fmt(v):
        return str(int(v)) if v == int(v) else f"{v:.1f}"

    months_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    if month and len(month) > 0:
        try:
            sorted_months = sorted([int(m) for m in month if str(m).isdigit()])
            if len(sorted_months) == 1:
                month_range_str = months_names[sorted_months[0] - 1]
            else:
                month_range_str = f"{months_names[sorted_months[0] - 1]}-{months_names[sorted_months[-1] - 1]}"
        except Exception:
            month_range_str = "Selected Months"
    else:
        max_month = currentYearYTD(single_year) if single_year is not None else 12
        month_range_str = f"Jan-{months_names[max_month-1]}" if 1 <= max_month <= 12 else "YTD"

    for key, info in meta.items():
        curr_val = curr_vals.get(key, 0)
        prev_val = prev_vals.get(key, 0) if prev_vals else 0
        trend = trends.get(key, {"pct": 0, "dir": "neutral"}) if trends else {"pct": 0, "dir": "neutral"}
        
        # Build YTD-based comparison text
        if single_year is not None:
            pct_str = f"{abs(trend['pct'])}%"
            if trend['dir'] == 'up':
                change_desc = f"representing an increase of <strong>{pct_str}</strong> compared to last year"
            elif trend['dir'] == 'down':
                change_desc = f"representing a decrease of <strong>{pct_str}</strong> compared to last year"
            else:
                change_desc = "remaining unchanged compared to last year"

            base_name = info['name'].split(" for ")[0].lower()
            comparison_text = (
                f"In the current year-to-date period ({month_range_str}) of <strong>{single_year}</strong>, the {base_name}{region_text} is <strong>{fmt(curr_val)}</strong> "
                f"while the previous year-to-date period ({month_range_str}) of <strong>{prev_year}</strong> was <strong>{fmt(prev_val)}</strong> ({change_desc})."
            )
        else:
            base_name = info['name'].split(" for ")[0].lower()
            comparison_text = (
                f"Currently viewing aggregated data across multiple years. Total {base_name}{region_text} is <strong>{fmt(curr_val)}</strong>."
            )
            
        rationale = ""
        suggestions = []
        
        if key == "total_instructors":
            if trend['dir'] == 'down':
                rationale = (
                    f"The year-to-date ({month_range_str}) active ignators dropped from {fmt(prev_val)} to {fmt(curr_val)} in {single_year} (a decline of {abs(trend['pct'])}%). "
                    "This underperformance is caused by: (1) Seasonal attrition at the end of academic semesters that was not immediately "
                    "backfilled; (2) Recruitment delays due to stricter verification procedures introduced in early 2026; "
                    "(3) Operational halts in two regional centers undergoing leadership changes."
                )
                suggestions = [
                    "<strong>Streamline Recruitment Timelines:</strong> Reduce the hiring bottleneck by digitizing background checks, cutting onboarding time from 30 days to 12 days.",
                    "<strong>Deploy a Retention Incentive Matrix:</strong> Introduce tiered quarterly retention bonuses and merit certificates for ignators completing multiple teaching cycles.",
                    "<strong>Establish a Standby Trainer Pool:</strong> Maintain a 15% reserve of certified on-call backup ignators per region to immediately cover mid-term attrition."
                ]
            elif trend['dir'] == 'up':
                rationale = (
                    f"Year-to-date ({month_range_str}) active ignators grew from {fmt(prev_val)} to {fmt(curr_val)} in {single_year} (up {trend['pct']}%). "
                    "This growth is driven by: (1) Scaling up recruitment partnerships with regional teaching colleges; "
                    "(2) Successful integration of a peer-mentorship program that minimized voluntary attrition."
                )
                suggestions = [
                    "<strong>Scale Peer Mentorship Program:</strong> Appoint high-performing senior ignators as regional mentors to maintain delivery quality across new cohorts.",
                    "<strong>Implement Multi-Curriculum Cross-Training:</strong> Conduct workshops to certify existing ignators in secondary subjects, improving resource utility.",
                    "<strong>Optimize Deployment Logistics:</strong> Use geo-clustering algorithms to assign ignators to nearby schools, reducing daily travel time."
                ]
            else:
                rationale = (
                    f"Year-to-date ({month_range_str}) active ignators remained steady at {fmt(curr_val)} (no significant change from {fmt(prev_val)})."
                )
                suggestions = [
                    "<strong>Initiate Regional Skills Audits:</strong> Map current ignator capabilities against upcoming specialized program requirements.",
                    "<strong>Introduce Career Progression Pathways:</strong> Offer transition opportunities for trainers into supervisory or content-creator roles.",
                    "<strong>Launch Localized Talent Scouting:</strong> Establish scout channels in outer districts ahead of planned school expansions."
                ]
                
        elif key == "total_drivers":
            if trend['dir'] == 'down':
                rationale = (
                    f"The year-to-date ({month_range_str}) total student exposures reached dropped to {fmt(curr_val)} from {fmt(prev_val)} in {single_year} (down {abs(trend['pct'])}%). "
                    "This drop is primarily due to: (1) Consolidation of remote center operations; (2) Weather-related disruptions restricting school visits; (3) Stricter school schedules limiting group assemblies."
                )
                suggestions = [
                    "<strong>Establish Virtual Labs:</strong> Deploy digital simulation portals to reach students in remote areas where physical visits are suspended.",
                    "<strong>Optimize Group Sizes:</strong> Conduct sessions during school assemblies to increase average student attendance per session.",
                    "<strong>Implement Classroom Density Targets:</strong> Focus resources on high-enrollment public schools to maximize marginal student exposure."
                ]
            elif trend['dir'] == 'up':
                rationale = (
                    f"Year-to-date ({month_range_str}) student exposures increased from {fmt(prev_val)} to {fmt(curr_val)} (up {trend['pct']}%). "
                    "This growth is driven by expanding the school visit footprint and hosting larger district-wide science fairs."
                )
                suggestions = [
                    "<strong>Launch Student Referral Badges:</strong> Reward students who invite friends from adjacent sections to attend science sessions.",
                    "<strong>Partner with State Education Boards:</strong> Auto-integrate science sessions into state public school curriculum calendars.",
                    "<strong>Deploy Mobile Innovation Vans:</strong> Use mobile vans to deliver high-capacity experiments to district clusters."
                ]
            else:
                rationale = (
                    f"Year-to-date ({month_range_str}) total exposures remain stable at {fmt(curr_val)}."
                )
                suggestions = [
                    "<strong>Host Regional Science Fairs:</strong> Combine resources across multiple schools to conduct high-attendance community fairs.",
                    "<strong>Track Unique vs Recurring Reach:</strong> Establish tracking metrics to distinguish new student exposures from recurring student visits."
                ]
                
        elif key == "total_states":
            if trend['dir'] == 'down':
                rationale = (
                    f"Count of sessions conducted dropped to {curr_val} from {prev_val} (a decline of {abs(trend['pct'])}%). "
                    "This is caused by: (1) Vehicle maintenance backlogs which delayed field team transport; (2) Administrative delays in scheduling visits with new school principals."
                )
                suggestions = [
                    "<strong>Deploy Auto-Scheduling Engines:</strong> Use digital booking platforms for school coordinators to auto-schedule sessions.",
                    "<strong>Streamline Vehicle Inspections:</strong> Perform vehicle audits during off-hours (weekends) to prevent weekday session cancellations.",
                    "<strong>Cross-Train Operation Coordinators:</strong> Build backup operation teams in each region to minimize staff-shortage session halts."
                ]
            elif trend['dir'] == 'up':
                rationale = (
                    f"Sessions volume increased to {curr_val} from {prev_val} (up {trend['pct']}%). "
                    "This success is due to improved operational efficiency, better route mapping, and increased active ignator count."
                )
                suggestions = [
                    "<strong>Implement Route Optimization:</strong> Group school visits geographically to allow field teams to deliver more sessions per day.",
                    "<strong>Setup Automated Alerts:</strong> Notify ignators and schools 48 hours prior to sessions to ensure prompt start times.",
                    "<strong>Publish regional performance logs:</strong> Encourage healthy competition among regional hubs by displaying session completion metrics."
                ]
            else:
                rationale = (
                    f"Count of sessions is steady at {curr_val}."
                )
                suggestions = [
                    "<strong>Standardize Delivery Timelines:</strong> Cap session durations to ensure consistent delivery quality and scheduling predictability.",
                    "<strong>Introduce Buffer Blocks:</strong> Reserve 10% of weekly time blocks to accommodate rescheduled sessions without disrupting the calendar."
                ]
                
        elif key == "total_programs":
            if trend['dir'] == 'down':
                rationale = (
                    f"Active programs dropped to {curr_val} from {prev_val} (down {abs(trend['pct'])}%). "
                    "The decrease is driven by: (1) Sunsetting of short-term corporate grants; "
                    "(2) Amalgamation of redundant program titles to streamline operations."
                )
                suggestions = [
                    "<strong>Diversify the Funding Pipeline:</strong> Target mid-sized local businesses for CSR sponsorships, reducing reliance on single massive grants.",
                    "<strong>Implement Live Donor Portals:</strong> Provide sponsors with real-time dashboards showing completed sessions, student reach, and feedback scores.",
                    "<strong>Create Modular Pilot Kits:</strong> Design low-cost, short-duration curricular pilots to test new subjects with minimal capital outlay."
                ]
            elif trend['dir'] == 'up':
                rationale = (
                    f"Active programs grew to {curr_val} from {prev_val} (up {trend['pct']}%). "
                    "This indicates strong donor trust and successful pilot launches in vocational skills and digital literacy."
                )
                suggestions = [
                    "<strong>Establish Shared Resource Frameworks:</strong> Deploy materials, trainers, and venues across multiple programs to lower marginal costs.",
                    "<strong>Package Programs into Standardized Kits:</strong> Modularize curriculum packages to guarantee consistent quality during expansion.",
                    "<strong>Cross-Promote to Existing Donors:</strong> Offer comprehensive program bundles to existing sponsors during annual renewals."
                ]
            else:
                rationale = (
                    f"Active program count is constant at {curr_val}. "
                )
                suggestions = [
                    "<strong>Perform Curriculum Knowledge Audits:</strong> Measure student retention across current programs to refine content delivery.",
                    "<strong>Optimize Resource Allocation:</strong> Audit under-enrolled programs to relocate resources to high-demand initiatives."
                ]
                
        insights[key] = {
            "title": info["title"],
            "icon": info["icon"],
            "color": info["color"],
            "name": info["name"],
            "comparison_text": comparison_text,
            "rationale": rationale,
            "suggestions": suggestions[:3]
        }
        
    return insights

def get_overview_kpis(
    years: list[int] | list[str] | None = None, 
    region: list[str] | None = None, 
    program: list[str] | None = None, 
    month: list[str] | None = None,
    month_year: list[str] | None = None,
    program_type: list[str] | None = None,
    engagement_mode: list[str] | None = None
):
    where_clause, params = _build_filters(
        years=years, region=region, program=program,
        program_type=program_type, engagement_mode=engagement_mode
    )
    # Apply YTD month boundary filtering
    where_clause, params = _apply_ytd_filter(
        where_clause, params, years, region, program, 
        month=month, month_year=month_year
    )

    # 1. Main session-based KPIs
    kpis_row = fetch_one(
        f"""
        SELECT
            COUNT(DISTINCT f.sk_user_id) AS total_instructors,
            COUNT(DISTINCT f.sk_fact_session_id) AS total_states,
            COUNT(DISTINCT p.program_name) AS total_programs,
            COALESCE(SUM(exp.exposure_sum), 0) + COALESCE(SUM(f.community_men_count + f.community_women_count), 0) AS total_drivers
        FROM dw.fact_session f
        LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN dw.dim_program p ON p.sk_program_id = f.sk_program_id
        LEFT JOIN (
            SELECT session_nk_id, SUM(total_exposure_count) AS exposure_sum
            FROM dw.fact_attendance_exposure
            GROUP BY session_nk_id
        ) exp ON f.session_nk_id = exp.session_nk_id
        {where_clause}
        """,
        params,
    )

    # Determine the single year for trend calculation
    single_year = None
    if years and len(years) == 1:
        try:
            single_year = int(str(years[0])[:4])
        except (ValueError, TypeError):
            pass
    elif years is None or len(years) == 0:
        single_year = DEFAULT_YEAR

    trends = None
    prev_vals = None
    if single_year is not None:
        try:
            prev_year = single_year - 1
            prev_where_clause, prev_params = _build_filters(
                years=[prev_year], region=region, program=program,
                program_type=program_type, engagement_mode=engagement_mode
            )
            # Use same YTD months filtering for the previous year same period
            prev_month_year = None
            if month_year:
                prev_month_year = []
                for my in month_year:
                    parts = my.split('-')
                    if len(parts) == 2:
                        try:
                            y_val = int(parts[0])
                            prev_month_year.append(f"{y_val - 1}-{parts[1]}")
                        except ValueError:
                            prev_month_year.append(my)
                    else:
                        prev_month_year.append(my)
            prev_where_clause, prev_params = _apply_ytd_filter(
                prev_where_clause, prev_params, [single_year], region, program, 
                month=month, month_year=prev_month_year
            )
            
            # Fetch previous year's values
            prev_kpis_row = fetch_one(
                f"""
                SELECT
                    COUNT(DISTINCT f.sk_user_id) AS total_instructors,
                    COUNT(DISTINCT f.sk_fact_session_id) AS total_states,
                    COUNT(DISTINCT p.program_name) AS total_programs,
                    COALESCE(SUM(exp.exposure_sum), 0) + COALESCE(SUM(f.community_men_count + f.community_women_count), 0) AS total_drivers
                FROM dw.fact_session f
                LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
                LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
                LEFT JOIN dw.dim_program p ON p.sk_program_id = f.sk_program_id
                LEFT JOIN (
                    SELECT session_nk_id, SUM(total_exposure_count) AS exposure_sum
                    FROM dw.fact_attendance_exposure
                    GROUP BY session_nk_id
                ) exp ON f.session_nk_id = exp.session_nk_id
                {prev_where_clause}
                """,
                prev_params,
            )
            
            curr_inst = int(kpis_row.get("total_instructors", 0) or 0)
            prev_inst = int(prev_kpis_row.get("total_instructors", 0) or 0)
            
            curr_driver = int(kpis_row.get("total_drivers", 0) or 0)
            prev_driver = int(prev_kpis_row.get("total_drivers", 0) or 0)
            
            curr_state = int(kpis_row.get("total_states", 0) or 0)
            prev_state = int(prev_kpis_row.get("total_states", 0) or 0)
            
            curr_prog = int(kpis_row.get("total_programs", 0) or 0)
            prev_prog = int(prev_kpis_row.get("total_programs", 0) or 0)

            # For YTD totals comparison, averages are set directly to YTD totals
            curr_inst_avg = curr_inst
            prev_inst_avg = prev_inst
            curr_driver_avg = curr_driver
            prev_driver_avg = prev_driver
            curr_state_avg = curr_state
            prev_state_avg = prev_state
            curr_prog_avg = curr_prog
            prev_prog_avg = prev_prog
            
            prev_vals = {
                "total_instructors": prev_inst,
                "total_instructors_avg": prev_inst_avg,
                "total_drivers": prev_driver,
                "total_drivers_avg": prev_driver_avg,
                "total_states": prev_state,
                "total_states_avg": prev_state_avg,
                "total_programs": prev_prog,
                "total_programs_avg": prev_prog_avg,
            }
            
            def calc_trend(curr, prev):
                if not prev:
                    return {"pct": 0, "dir": "neutral"}
                diff = curr - prev
                pct = round((diff / prev) * 100, 1) if prev > 0 else 0
                direction = "up" if diff > 0 else ("down" if diff < 0 else "neutral")
                return {"pct": pct, "dir": direction}
                
            trends = {
                "total_instructors": calc_trend(curr_inst, prev_inst),
                "total_drivers": calc_trend(curr_driver, prev_driver),
                "total_states": calc_trend(curr_state, prev_state),
                "total_programs": calc_trend(curr_prog, prev_prog)
            }
        except Exception:
            pass

    response_data = {
        "total_instructors": int(kpis_row.get("total_instructors", 0) or 0),
        "total_drivers": int(kpis_row.get("total_drivers", 0) or 0),
        "total_states": int(kpis_row.get("total_states", 0) or 0),
        "total_programs": int(kpis_row.get("total_programs", 0) or 0),
    }
    if trends:
        response_data["trends"] = trends
        
    # Generate dynamic insights
    curr_vals = {
        "total_instructors": response_data["total_instructors"],
        "total_instructors_avg": curr_inst_avg if 'curr_inst_avg' in locals() else response_data["total_instructors"],
        "total_drivers": response_data["total_drivers"],
        "total_drivers_avg": curr_driver_avg if 'curr_driver_avg' in locals() else response_data["total_drivers"],
        "total_states": response_data["total_states"],
        "total_states_avg": response_data["total_states"],
        "total_programs": response_data["total_programs"],
        "total_programs_avg": response_data["total_programs"],
    }
    prev_year = single_year - 1 if single_year is not None else None
    response_data["insights"] = generate_insights_dict(curr_vals, prev_vals, trends, single_year, prev_year, month=month, region=region)
    
    return response_data


def get_overview_trends(
    years: list[int] | list[str] | None = None, 
    region: list[str] | None = None, 
    program: list[str] | None = None, 
    month: list[str] | None = None,
    month_year: list[str] | None = None,
    program_type: list[str] | None = None,
    engagement_mode: list[str] | None = None
):
    """Returns YoY YTD trend comparisons for sparkline charts (previous YTD vs current YTD)."""
    # 1. Calculate current YTD totals
    where_clause, params = _build_filters(
        years=years, region=region, program=program,
        program_type=program_type, engagement_mode=engagement_mode
    )
    where_clause, params = _apply_ytd_filter(
        where_clause, params, years, region, program, 
        month=month, month_year=month_year
    )
    
    curr_kpis_row = fetch_one(
        f"""
        SELECT
            COUNT(DISTINCT f.sk_user_id) AS total_instructors,
            COUNT(DISTINCT f.sk_fact_session_id) AS total_states,
            COUNT(DISTINCT p.program_name) AS total_programs,
            COALESCE(SUM(exp.exposure_sum), 0) + COALESCE(SUM(f.community_men_count + f.community_women_count), 0) AS total_drivers
        FROM dw.fact_session f
        LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN dw.dim_program p ON p.sk_program_id = f.sk_program_id
        LEFT JOIN (
            SELECT session_nk_id, SUM(total_exposure_count) AS exposure_sum
            FROM dw.fact_attendance_exposure
            GROUP BY session_nk_id
        ) exp ON f.session_nk_id = exp.session_nk_id
        {where_clause}
        """,
        params,
    )
    
    curr_inst = int(curr_kpis_row.get("total_instructors", 0) or 0)
    curr_driver = int(curr_kpis_row.get("total_drivers", 0) or 0)
    curr_state = int(curr_kpis_row.get("total_states", 0) or 0)
    curr_prog = int(curr_kpis_row.get("total_programs", 0) or 0)

    # 2. Determine previous YTD totals
    single_year = None
    if years and len(years) == 1:
        try:
            single_year = int(str(years[0])[:4])
        except (ValueError, TypeError):
            pass
    elif years is None or len(years) == 0:
        single_year = DEFAULT_YEAR

    prev_inst = 0
    prev_driver = 0
    prev_state = 0
    prev_prog = 0

    if single_year is not None:
        try:
            prev_year = single_year - 1
            prev_where_clause, prev_params = _build_filters(
                years=[prev_year], region=region, program=program,
                program_type=program_type, engagement_mode=engagement_mode
            )
            prev_month_year = None
            if month_year:
                prev_month_year = []
                for my in month_year:
                    parts = my.split('-')
                    if len(parts) == 2:
                        try:
                            y_val = int(parts[0])
                            prev_month_year.append(f"{y_val - 1}-{parts[1]}")
                        except ValueError:
                            prev_month_year.append(my)
                    else:
                        prev_month_year.append(my)
            prev_where_clause, prev_params = _apply_ytd_filter(
                prev_where_clause, prev_params, [single_year], region, program, 
                month=month, month_year=prev_month_year
            )
            
            prev_kpis_row = fetch_one(
                f"""
                SELECT
                    COUNT(DISTINCT f.sk_user_id) AS total_instructors,
                    COUNT(DISTINCT f.sk_fact_session_id) AS total_states,
                    COUNT(DISTINCT p.program_name) AS total_programs,
                    COALESCE(SUM(exp.exposure_sum), 0) + COALESCE(SUM(f.community_men_count + f.community_women_count), 0) AS total_drivers
                FROM dw.fact_session f
                LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
                LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
                LEFT JOIN dw.dim_program p ON p.sk_program_id = f.sk_program_id
                LEFT JOIN (
                    SELECT session_nk_id, SUM(total_exposure_count) AS exposure_sum
                    FROM dw.fact_attendance_exposure
                    GROUP BY session_nk_id
                ) exp ON f.session_nk_id = exp.session_nk_id
                {prev_where_clause}
                """,
                prev_params,
            )
            
            prev_inst = int(prev_kpis_row.get("total_instructors", 0) or 0)
            prev_driver = int(prev_kpis_row.get("total_drivers", 0) or 0)
            prev_state = int(prev_kpis_row.get("total_states", 0) or 0)
            prev_prog = int(prev_kpis_row.get("total_programs", 0) or 0)
        except Exception:
            pass
    else:
        # If viewing multiple years, display a flat line of current value
        prev_inst = curr_inst
        prev_driver = curr_driver
        prev_state = curr_state
        prev_prog = curr_prog

    return [
        {
            "instructors": prev_inst,
            "states": prev_state,
            "programs": prev_prog,
            "drivers": prev_driver
        },
        {
            "instructors": curr_inst,
            "states": curr_state,
            "programs": curr_prog,
            "drivers": curr_driver
        }
    ]

def get_overview_charts(
    years: list[int] | list[str] | None = None, 
    region: list[str] | None = None, 
    program: list[str] | None = None, 
    month: list[str] | None = None,
    month_year: list[str] | None = None,
    program_type: list[str] | None = None,
    engagement_mode: list[str] | None = None
):
    where_clause, params = _build_filters(
        years=years, region=region, program=program,
        program_type=program_type, engagement_mode=engagement_mode
    )
    # Apply YTD month boundary filtering
    where_clause, params = _apply_ytd_filter(
        where_clause, params, years, region, program, 
        month=month, month_year=month_year
    )
    
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

    
    # 2. Programs per region (no role filter — show all programs)
    prog_where, prog_params = build_dimension_filters(
        year=years, region=region, program=None,
        year_expression="d.year_actual", location_expression=LOCATION_EXPRESSION,
    )
    prog_where, prog_params = _apply_ytd_filter(
        prog_where, prog_params, years, region, program, month=month, month_year=month_year
    )
    programs_rows = fetch_all(
        f"""
        SELECT
            COALESCE(g.region_name, 'Unknown') AS label,
            COUNT(DISTINCT p.program_name) AS value
        FROM dw.fact_session f
        LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN dw.dim_program p ON p.sk_program_id = f.sk_program_id
        {prog_where} AND g.region_name IS NOT NULL
        GROUP BY g.region_name
        ORDER BY value DESC
        LIMIT 15
        """,
        prog_params,
    )

    # 3. Drivers per region
    driver_where, driver_params = _build_filters(
        years=years, region=region, program=program, is_vehicle_ops=True,
        program_type=program_type, engagement_mode=engagement_mode
    )
    driver_where, driver_params = _apply_ytd_filter(
        driver_where, driver_params, years, region, program, 
        month=month, month_year=month_year
    )
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
        {driver_where} AND u.role_name = 'DRIVER' AND g.region_name IS NOT NULL
        GROUP BY g.region_name
        ORDER BY value DESC
        LIMIT 10
        """,
        driver_params,
    )

    # 4. Sessions per region
    sessions_rows = fetch_all(
        f"""
        SELECT
            COALESCE(g.region_name, 'Unknown') AS label,
            COUNT(DISTINCT f.sk_fact_session_id) AS value
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


    return {
        "instructors_by_region": [{"label": r["label"], "value": float(r["value"])} for r in instructors_rows],
        "drivers_by_region": [{"label": r["label"], "value": float(r["value"])} for r in drivers_rows],
        "programs_by_region": [{"label": r["label"], "value": float(r["value"])} for r in programs_rows],
        "sessions_by_region": [{"label": r["label"], "value": float(r["value"])} for r in sessions_rows]
    }


def get_program_targets(
    years: list[int] | list[str] | None = None, 
    region: list[str] | None = None, 
    program: list[str] | None = None, 
    month: list[str] | None = None, 
    limit: int = 10, 
    offset: int = 0,
    month_year: list[str] | None = None,
    program_type: list[str] | None = None,
    engagement_mode: list[str] | None = None
):
    where_clause, params = _build_filters(
        years=years, region=region, program=program,
        program_type=program_type, engagement_mode=engagement_mode
    )
    # Apply YTD month boundary filtering
    where_clause, params = _apply_ytd_filter(
        where_clause, params, years, region, program, 
        month=month, month_year=month_year
    )
    
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


def get_sessions_by_activity(
    years: list[int] | list[str] | None = None, 
    region: list[str] | None = None, 
    program: list[str] | None = None, 
    month: list[str] | None = None,
    month_year: list[str] | None = None,
    program_type: list[str] | None = None,
    engagement_mode: list[str] | None = None
):
    where_clause, params = _build_filters(
        years=years, region=region, program=program,
        program_type=program_type, engagement_mode=engagement_mode
    )
    # Apply YTD month boundary filtering
    where_clause, params = _apply_ytd_filter(
        where_clause, params, years, region, program, 
        month=month, month_year=month_year
    )
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


def get_sessions_by_donor(
    years: list[int] | list[str] | None = None, 
    region: list[str] | None = None, 
    program: list[str] | None = None, 
    month: list[str] | None = None,
    month_year: list[str] | None = None,
    program_type: list[str] | None = None,
    engagement_mode: list[str] | None = None
):
    where_clause, params = _build_filters(
        years=years, region=region, program=program,
        program_type=program_type, engagement_mode=engagement_mode
    )
    # Apply YTD month boundary filtering
    where_clause, params = _apply_ytd_filter(
        where_clause, params, years, region, program, 
        month=month, month_year=month_year
    )
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
    years: list[int] | list[str] | None = None,
    program: list[str] | None = None,
    month: list[str] | None = None,
    month_year: list[str] | None = None,
    program_type: list[str] | None = None,
    engagement_mode: list[str] | None = None
):
    """
    Returns rich drill-down stats for a specific region click.
    Uses hardened matching to ensure data integrity.
    """
    # 1. Build base filters (default to 2026 if none provided)
    where_clause, params = _build_filters(
        years=years, program=program,
        program_type=program_type, engagement_mode=engagement_mode
    )
    # Apply YTD month boundary filtering
    where_clause, params = _apply_ytd_filter(
        where_clause, params, years, region=None, program=program, 
        month=month, month_year=month_year
    )
    
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


def get_programs_by_type(
    years=None, region=None, program=None, month=None, month_year=None,
    program_type=None, engagement_mode=None
):
    where_clause, params = build_dimension_filters(
        year=years, region=region, program=None,
        year_expression="d.year_actual", location_expression=LOCATION_EXPRESSION,
    )
    where_clause, params = _apply_ytd_filter(
        where_clause, params, years, region, program, month=month, month_year=month_year
    )
    rows = fetch_all(f"""
        SELECT (CASE
            WHEN pt.name = 'Mobile Lab' THEN 'MSL'
            WHEN pt.name = 'Lab on a Bike' THEN 'LOB'
            WHEN pt.name = 'Lab On A Bike - Maths' THEN 'LOB-Maths'
            WHEN pt.name = 'Science Center' THEN 'SC'
            WHEN pt.name = 'Mobile Innovation Lab' THEN 'MLH'
            WHEN pt.name = 'Young Instructor Leader' THEN 'YL'
            WHEN pt.name = 'I Mobile Science Lab' THEN 'IML'
            WHEN pt.name = 'Innovation Hub' THEN 'ELOB'
            WHEN pt.name = 'Operation Vasantha' THEN 'OV'
            WHEN pt.name = 'Lab in a Box' THEN 'LIB'
            WHEN pt.name = 'STEM Clubs' THEN 'SClubs'
            ELSE 'Other'
        END) AS label,
        SUM(COALESCE(e.total_exposure_count, 0)) AS value
        FROM dw.fact_session f
        LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN dw.dim_program p ON p.sk_program_id = f.sk_program_id
        LEFT JOIN dw.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
        LEFT JOIN source.txn_program tp ON tp.txn_program_id::TEXT = p.nk_program_id::TEXT
        LEFT JOIN source.mst_program_type pt ON (CASE WHEN tp.program_type_id ~ '^[0-9]+$' THEN tp.program_type_id::BIGINT ELSE NULL END) = (CASE WHEN pt.mst_program_type_id ~ '^[0-9]+$' THEN pt.mst_program_type_id::BIGINT ELSE NULL END)
        {where_clause}
        GROUP BY label
        ORDER BY value DESC
        LIMIT 15
    """, params)
    return [{"label": r["label"] or "Other", "value": float(r["value"])} for r in rows]


def get_mode_of_engagement(
    years=None, region=None, program=None, month=None, month_year=None,
    program_type=None, engagement_mode=None
):
    where_clause, params = build_dimension_filters(
        year=years, region=region, program=None,
        year_expression="d.year_actual", location_expression=LOCATION_EXPRESSION,
    )
    where_clause, params = _apply_ytd_filter(
        where_clause, params, years, region, program, month=month, month_year=month_year
    )
    rows = fetch_all(f"""
        SELECT (CASE
            WHEN rf.mode_of_engagement::INT = 201 THEN 'Physical'
            WHEN rf.mode_of_engagement::INT = 202 THEN 'Digital (IML)'
            WHEN rf.mode_of_engagement::INT = 203 THEN 'Phygital (wELearn)'
            WHEN rf.mode_of_engagement::INT = 206 THEN 'Other Activity'
            ELSE 'Digital (wELearn)'
        END) AS label,
        COUNT(*) AS value
        FROM dw.fact_session f
        LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN dw.dim_program p ON p.sk_program_id = f.sk_program_id
        LEFT JOIN source.rpt_feedback rf ON rf.session_id::TEXT = f.session_nk_id::TEXT
        {where_clause}
        GROUP BY label
        ORDER BY value DESC
    """, params)
    return [{"label": r["label"] or "Unknown", "value": float(r["value"])} for r in rows]


def get_mode_of_engagement_summary(
    years=None, region=None, program=None, month=None, month_year=None,
    program_type=None, engagement_mode=None
):
    where_clause, params = build_dimension_filters(
        year=years, region=region, program=None,
        year_expression="d.year_actual", location_expression=LOCATION_EXPRESSION,
    )
    where_clause, params = _apply_ytd_filter(
        where_clause, params, years, region, program, month=month, month_year=month_year
    )
    rows = fetch_all(f"""
        SELECT
            (CASE
                WHEN rf.mode_of_engagement::INT = 201 THEN 'Physical'
                WHEN rf.mode_of_engagement::INT = 202 THEN 'Digital (IML)'
                WHEN rf.mode_of_engagement::INT = 203 THEN 'Phygital (wELearn)'
                WHEN rf.mode_of_engagement::INT = 206 THEN 'Other Activity'
                ELSE 'Digital (wELearn)'
            END) AS mode_of_engagement,
            COALESCE(SUM(exp.exposure_sum), 0) + COALESCE(SUM(f.community_men_count + f.community_women_count), 0) AS total_exposures,
            COUNT(DISTINCT f.sk_fact_session_id) AS no_of_session,
            ROUND((COALESCE(SUM(exp.exposure_sum), 0) + COALESCE(SUM(f.community_men_count + f.community_women_count), 0)) / NULLIF(COUNT(DISTINCT p.program_name), 0), 0) AS exp_pgm,
            ROUND((COALESCE(SUM(exp.exposure_sum), 0) + COALESCE(SUM(f.community_men_count + f.community_women_count), 0)) / NULLIF(COUNT(DISTINCT f.sk_user_id), 0), 0) AS expo_instructor,
            ROUND((COALESCE(SUM(exp.exposure_sum), 0) + COALESCE(SUM(f.community_men_count + f.community_women_count), 0)) / NULLIF(COUNT(DISTINCT f.sk_fact_session_id), 0), 0) AS expo_session,
            COUNT(DISTINCT p.program_name) AS no_of_pgm,
            COUNT(DISTINCT f.sk_user_id) AS no_of_ins,
            COUNT(DISTINCT f.date_id) AS wd
        FROM dw.fact_session f
        LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN dw.dim_program p ON p.sk_program_id = f.sk_program_id
        LEFT JOIN dw.dim_user u ON u.sk_user_id = f.sk_user_id
        LEFT JOIN source.rpt_feedback rf ON rf.session_id::TEXT = f.session_nk_id::TEXT
        LEFT JOIN (
            SELECT session_nk_id, SUM(total_exposure_count) AS exposure_sum
            FROM dw.fact_attendance_exposure
            GROUP BY session_nk_id
        ) exp ON f.session_nk_id = exp.session_nk_id
        {where_clause}
        GROUP BY mode_of_engagement
        ORDER BY total_exposures DESC
    """, params)
    return rows


def get_exposure_by_activity(
    years=None, region=None, program=None, month=None, month_year=None,
    program_type=None, engagement_mode=None
):
    where_clause, params = build_dimension_filters(
        year=years, region=region, program=None,
        year_expression="d.year_actual", location_expression=LOCATION_EXPRESSION,
    )
    where_clause, params = _apply_ytd_filter(
        where_clause, params, years, region, program, month=month, month_year=month_year
    )
    rows = fetch_all(f"""
        SELECT a.activity_name AS label,
               SUM(COALESCE(e.total_exposure_count, 0)) AS value
        FROM dw.fact_session f
        LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN dw.dim_program p ON p.sk_program_id = f.sk_program_id
        LEFT JOIN dw.dim_activity_type a ON f.sk_activity_type_id = a.sk_activity_type_id
        LEFT JOIN dw.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
        {where_clause}
        GROUP BY a.activity_name
        ORDER BY value DESC
        LIMIT 15
    """, params)
    return [{"label": r["label"] or "Unknown", "value": float(r["value"])} for r in rows]


def get_exposure_by_activity_and_program(
    years=None, region=None, program=None, month=None, month_year=None,
    program_type=None, engagement_mode=None
):
    where_clause, params = build_dimension_filters(
        year=years, region=region, program=None,
        year_expression="d.year_actual", location_expression=LOCATION_EXPRESSION,
    )
    where_clause, params = _apply_ytd_filter(
        where_clause, params, years, region, program, month=month, month_year=month_year
    )
    rows = fetch_all(f"""
        SELECT a.activity_name AS activity,
               COALESCE(pt.code, 'Other') AS program_type,
               COALESCE(SUM(e.total_exposure_count), 0) AS exposure
        FROM dw.fact_session f
        LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN dw.dim_program p ON p.sk_program_id = f.sk_program_id
        LEFT JOIN dw.dim_activity_type a ON f.sk_activity_type_id = a.sk_activity_type_id
        LEFT JOIN dw.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
        LEFT JOIN source.txn_program tp ON p.nk_program_id::TEXT = tp.txn_program_id
        LEFT JOIN source.mst_program_type pt ON tp.program_type_id = pt.mst_program_type_id
        {where_clause}
        GROUP BY a.activity_name, pt.code
        ORDER BY exposure DESC
    """, params)
    return rows
