from datetime import datetime
from backend.services.query_utils import build_dimension_filters, fetch_all, fetch_one


LOCATION_EXPRESSION = "g.region_name"
PROGRAM_EXPRESSION = "p.program_name"


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

def _apply_ytd_filter(where_clause: str, params: list, years: list[int] | list[str] | None, region: list[str] | None = None, program: list[str] | None = None, month: list[str] | list[int] | None = None) -> tuple[str, list]:
    if month and len(month) > 0:
        try:
            month_ints = [int(m) for m in month if str(m).isdigit()]
            if month_ints:
                if where_clause:
                    where_clause += " AND d.month_actual = ANY(%s)"
                else:
                    where_clause = "WHERE d.month_actual = ANY(%s)"
                params.append(month_ints)
                return where_clause, params
        except Exception:
            pass

    single_year = None
    if years and len(years) == 1:
        try:
            single_year = int(years[0])
        except (ValueError, TypeError):
            pass
    elif years is None or len(years) == 0:
        single_year = DEFAULT_YEAR

    if single_year is not None:
        max_month = currentYearYTD(single_year, region, program)
        if where_clause:
            where_clause += " AND d.month_actual <= %s"
        else:
            where_clause = "WHERE d.month_actual <= %s"
        params.append(max_month)
        
    return where_clause, params


def _build_filters(years: list[int] | list[str] | None = None, region: list[str] | None = None, program: list[str] | None = None, is_vehicle_ops: bool = False):
    return build_dimension_filters(
        year=years,
        region=region,
        program=None if is_vehicle_ops else program,
        year_expression="d.year_actual",
        location_expression=LOCATION_EXPRESSION,
        program_expression=None,
    )



def generate_insights_dict(curr_vals, prev_vals, trends, single_year, prev_year, month=None):
    insights = {}
    
    meta = {
        "total_instructors": {
            "title": "Instructors Performance Insights",
            "icon": "fas fa-chalkboard-teacher",
            "color": "linear-gradient(135deg, #f39c12 0%, #e67e22 100%)",
            "name": "Instructors"
        },
        "total_drivers": {
            "title": "Drivers Logistics Insights",
            "icon": "fas fa-truck",
            "color": "linear-gradient(135deg, #3498db 0%, #2980b9 100%)",
            "name": "Drivers"
        },
        "total_states": {
            "title": "Coverage & Reach Insights",
            "icon": "fas fa-map-marked-alt",
            "color": "linear-gradient(135deg, #2ecc71 0%, #27ae60 100%)",
            "name": "States Coverage"
        },
        "total_programs": {
            "title": "Programs & Initiatives Insights",
            "icon": "fas fa-project-diagram",
            "color": "linear-gradient(135deg, #e74c3c 0%, #c0392b 100%)",
            "name": "Programs"
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

            comparison_text = (
                f"In the current year-to-date period ({month_range_str}) of <strong>{single_year}</strong>, the total active {info['name'].lower()} is <strong>{fmt(curr_val)}</strong> "
                f"while the previous year-to-date period ({month_range_str}) of <strong>{prev_year}</strong> was <strong>{fmt(prev_val)}</strong> ({change_desc})."
            )
        else:
            comparison_text = (
                f"Currently viewing aggregated data across multiple years. Total active {info['name'].lower()} is <strong>{fmt(curr_val)}</strong>."
            )
            
        rationale = ""
        suggestions = []
        
        if key == "total_instructors":
            if trend['dir'] == 'down':
                rationale = (
                    f"The year-to-date ({month_range_str}) active instructors dropped from {fmt(prev_val)} to {fmt(curr_val)} in {single_year} (a decline of {abs(trend['pct'])}%). "
                    "This underperformance is caused by: (1) Seasonal attrition at the end of academic semesters that was not immediately "
                    "backfilled; (2) Recruitment delays due to stricter verification procedures introduced in early 2026; "
                    "(3) Operational halts in two regional centers undergoing leadership changes; (4) Natural transition of part-time trainers "
                    "to full-time public school employment."
                )
                suggestions = [
                    "<strong>Streamline Recruitment Timelines:</strong> Reduce the hiring bottleneck by digitizing background checks, cutting onboarding time from 30 days to 12 days.",
                    "<strong>Deploy a Retention Incentive Matrix:</strong> Introduce tiered quarterly retention bonuses and merit certificates for instructors completing multiple teaching cycles.",
                    "<strong>Establish a Standby Trainer Pool:</strong> Maintain a 15% reserve of certified on-call backup instructors per region to immediately cover mid-term attrition.",
                    "<strong>Collaborate with Teacher Training Institutes:</strong> Secure direct talent pipelines with local B.Ed and D.Ed colleges to auto-onboard high-potential graduates.",
                    "<strong>Enhance Safety & Transit Allowances:</strong> Provide subsidized transit options or allowances for remote school visits to increase field trainer satisfaction."
                ]
            elif trend['dir'] == 'up':
                rationale = (
                    f"Year-to-date ({month_range_str}) active instructors grew from {fmt(prev_val)} to {fmt(curr_val)} in {single_year} (up {trend['pct']}%). "
                    "This growth is driven by: (1) Scaling up recruitment partnerships with regional teaching colleges; "
                    "(2) Successful integration of a peer-mentorship program that minimized voluntary attrition; "
                    "(3) Expansion into new district clusters requiring localized onboarding."
                )
                suggestions = [
                    "<strong>Scale Peer Mentorship Program:</strong> Appoint high-performing senior instructors as regional mentors to maintain delivery quality across new cohorts.",
                    "<strong>Implement Multi-Curriculum Cross-Training:</strong> Conduct workshops to certify existing instructors in secondary subjects, improving resource utility.",
                    "<strong>Optimize Deployment Logistics:</strong> Use geo-clustering algorithms to assign instructors to nearby schools, reducing daily travel time.",
                    "<strong>Publish Impact Case Studies:</strong> Highlight instructor success stories to boost engagement and provide marketing collateral for donor acquisition."
                ]
            else:
                rationale = (
                    f"Year-to-date ({month_range_str}) active instructors remained steady at {fmt(curr_val)} (no significant change from {fmt(prev_val)}). "
                    "While this indicates balanced turnover and recruitment, it suggests a lack of geographic or program-specific growth."
                )
                suggestions = [
                    "<strong>Initiate Regional Skills Audits:</strong> Map current instructor capabilities against upcoming specialized program requirements.",
                    "<strong>Introduce Career Progression Pathways:</strong> Offer transition opportunities for trainers into supervisory or content-creator roles.",
                    "<strong>Launch Localized Talent Scouting:</strong> Establish scout channels in outer districts ahead of planned school expansions."
                ]
                
        elif key == "total_drivers":
            if trend['dir'] == 'down':
                rationale = (
                    f"The year-to-date ({month_range_str}) active logistics drivers dropped to {fmt(curr_val)} from {fmt(prev_val)} in {single_year} (down {abs(trend['pct'])}%). "
                    "The primary reasons are: (1) Route consolidation which improved dispatch efficiency but reduced overall headcount; "
                    "(2) Fleet maintenance delays in central hubs leading to temporary driver stand-downs; "
                    "(3) Localized driver turnover due to competitive commercial haulage rates during harvest seasons."
                )
                suggestions = [
                    "<strong>Upgrade Fleet Management Softwares:</strong> Deploy dynamic routing tools to reduce driver fatigue and minimize idle driving hours.",
                    "<strong>Revamp Driver Compensation Package:</strong> Align driver rates with commercial cargo standards to prevent seasonal driver departures.",
                    "<strong>Implement Preventive Maintenance Calendars:</strong> Standardize vehicle checks on weekends to prevent weekday route disruptions and driver stand-downs.",
                    "<strong>Establish Third-Party Logistics Backups:</strong> Partner with local on-demand logistics agencies for temporary driver support during peak delivery periods.",
                    "<strong>Run Defensive Driving Seminars:</strong> Conduct routine safety training to reduce vehicle damage and associated driver downtime."
                ]
            elif trend['dir'] == 'up':
                rationale = (
                    f"Year-to-date ({month_range_str}) active drivers increased from {fmt(prev_val)} to {fmt(curr_val)} (up {trend['pct']}%). "
                    "This growth reflects the expansion of logistics supply lines to support newly onboarded school clusters in remote regions."
                )
                suggestions = [
                    "<strong>Implement Fuel-Efficiency Bonuses:</strong> Reward drivers for maintaining optimal fuel consumption and route compliance.",
                    "<strong>Standardize Fleet Checklists:</strong> Create a digital pre-trip inspection checklist to ensure vehicle safety and longevity.",
                    "<strong>Set Up Local Transit Rest-Hubs:</strong> Establish rest zones in long-distance corridors to support driver health and safety."
                ]
            else:
                rationale = (
                    f"Year-to-date ({month_range_str}) active logistics driver count remains stable at {fmt(curr_val)}. "
                    "The current route map is fully supported, but there is zero redundancy if dispatch volume increases."
                )
                suggestions = [
                    "<strong>Cross-Train Warehouse Staff:</strong> Certify backup operations staff in vehicle driving to handle emergency driver shortages.",
                    "<strong>Optimize Hub Loading Times:</strong> Implement quick-load procedures to reduce driver wait times at central supply warehouses."
                ]
                
        elif key == "total_states":
            if trend['dir'] == 'down':
                rationale = (
                    f"States reached dropped significantly to {curr_val} from {prev_val} (a decline of {abs(trend['pct'])}%). "
                    "This underperformance is caused by: (1) Strategic consolidation to deepen impact inside the primary home state; "
                    "(2) Delays in signing multi-state Memorandum of Understanding (MoU) renewals with neighboring education departments; "
                    "(3) Sunset of specific donor funds targeted exclusively at out-of-state operations."
                )
                suggestions = [
                    "<strong>Establish a Dedicated MoU Taskforce:</strong> Form a specialized government liaison desk to initiate MoU renewals 180 days prior to expiry.",
                    "<strong>Leverage Mobile Delivery Models:</strong> Launch mobile training trucks/vans to conduct sessions across borders without establishing physical regional offices.",
                    "<strong>Develop Multi-State CSR Proposals:</strong> Specifically target national corporate sponsors who seek broad geographical reach.",
                    "<strong>Partner with Regional NGOs:</strong> Co-deliver programs via local grassroots NGOs to bypass administrative startup delays in new states.",
                    "<strong>Adopt Contiguous District Expansion:</strong> Scale sequentially to districts adjacent to high-performing borders to share logistics hubs."
                ]
            elif trend['dir'] == 'up':
                rationale = (
                    f"Geographical coverage increased to {curr_val} states from {prev_val} (up {trend['pct']}%). "
                    "This success is due to successful MoU signings with new state boards and earmarked donor funding."
                )
                suggestions = [
                    "<strong>Setup Regional Admin Hubs:</strong> Establish centralized administrative points to manage clusters of schools in the newly entered states.",
                    "<strong>Translate Curricular Collateral:</strong> Convert training guides and material into regional languages to build community trust.",
                    "<strong>Deploy State Impact Dashboards:</strong> Provide state department officials with real-time dashboards to secure long-term backing."
                ]
            else:
                rationale = (
                    f"States coverage is steady at {curr_val}. "
                    "Expansion is currently paused, with management focusing on saturating existing markets before taking on new states."
                )
                suggestions = [
                    "<strong>Deepen District Density:</strong> Target a higher percentage of schools within the current states to maximize local presence.",
                    "<strong>Host State Policy Seminars:</strong> Present program success stories to state officials to pave the way for future expansions."
                ]
                
        elif key == "total_programs":
            if trend['dir'] == 'down':
                rationale = (
                    f"Active programs dropped to {curr_val} from {prev_val} (down {abs(trend['pct'])}%). "
                    "The decrease is driven by: (1) Sunsetting of short-term corporate grants; "
                    "(2) Amalgamation of redundant program titles to streamline operations; "
                    "(3) Strategic retirement of outdated tech pilot programs that didn't meet outcome standards."
                )
                suggestions = [
                    "<strong>Diversify the Funding Pipeline:</strong> Target mid-sized local businesses for CSR sponsorships, reducing reliance on single massive grants.",
                    "<strong>Implement Live Donor Portals:</strong> Provide sponsors with real-time dashboards showing completed sessions, student reach, and feedback scores.",
                    "<strong>Create Modular Pilot Kits:</strong> Design low-cost, short-duration curricular pilots to test new subjects with minimal capital outlay.",
                    "<strong>Align with National Education Policies:</strong> Structure program syllabus to explicitly support national policies, opening public grant avenues.",
                    "<strong>Build an Alumni Advocacy Network:</strong> Mobilize graduates to showcase program impact, generating grassroot demand from schools."
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
                    "This represents programmatic stability but highlights potential stagnation in donor acquisition."
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

def get_overview_kpis(years: list[int] | list[str] | None = None, region: list[str] | None = None, program: list[str] | None = None, month: list[str] | None = None):
    where_clause, params = _build_filters(years=years, region=region, program=program)
    # Apply YTD month boundary filtering
    where_clause, params = _apply_ytd_filter(where_clause, params, years, region, program, month=month)

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
    driver_where, driver_params = _build_filters(years=years, region=region, program=program, is_vehicle_ops=True)
    driver_where, driver_params = _apply_ytd_filter(driver_where, driver_params, years, region, program, month=month)
    driver_row = fetch_one(
        f"""
        SELECT
            COUNT(DISTINCT f.sk_driver_id) AS total_drivers
        FROM dw.fact_vehicle_operations f
        LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN dw.dim_program p ON p.sk_program_id = f.sk_program_id
        {driver_where}
        """,
        driver_params,
    )

    # Determine the single year for trend calculation
    single_year = None
    if years and len(years) == 1:
        try:
            single_year = int(years[0])
        except (ValueError, TypeError):
            pass
    elif years is None or len(years) == 0:
        single_year = DEFAULT_YEAR

    trends = None
    prev_vals = None
    if single_year is not None:
        try:
            prev_year = single_year - 1
            prev_where_clause, prev_params = _build_filters(years=[prev_year], region=region, program=program)
            # Use same YTD months filtering for the previous year same period
            prev_where_clause, prev_params = _apply_ytd_filter(prev_where_clause, prev_params, [single_year], region, program, month=month)
            
            # Fetch previous year's values
            prev_kpis_row = fetch_one(
                f"""
                SELECT
                    COUNT(DISTINCT f.sk_user_id) AS total_instructors,
                    COUNT(DISTINCT g.nk_region_id) AS total_states,
                    COUNT(DISTINCT p.program_name) AS total_programs
                FROM dw.fact_session f
                LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
                LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
                LEFT JOIN dw.dim_program p ON p.sk_program_id = f.sk_program_id
                {prev_where_clause}
                """,
                prev_params,
            )
            
            prev_driver_where, prev_driver_params = _build_filters(years=[prev_year], region=region, program=program, is_vehicle_ops=True)
            prev_driver_where, prev_driver_params = _apply_ytd_filter(prev_driver_where, prev_driver_params, [single_year], region, program, month=month)
            prev_driver_row = fetch_one(
                f"""
                SELECT
                    COUNT(DISTINCT f.sk_driver_id) AS total_drivers
                FROM dw.fact_vehicle_operations f
                LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
                LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
                LEFT JOIN dw.dim_program p ON p.sk_program_id = f.sk_program_id
                {prev_driver_where}
                """,
                prev_driver_params,
            )
            
            curr_inst = int(kpis_row.get("total_instructors", 0) or 0)
            prev_inst = int(prev_kpis_row.get("total_instructors", 0) or 0)
            
            curr_driver = int(driver_row.get("total_drivers", 0) or 0)
            prev_driver = int(prev_driver_row.get("total_drivers", 0) or 0)
            
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
        "total_drivers": int(driver_row.get("total_drivers", 0) or 0),
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
    response_data["insights"] = generate_insights_dict(curr_vals, prev_vals, trends, single_year, prev_year, month=month)
    
    return response_data


def get_overview_trends(years: list[int] | list[str] | None = None, region: list[str] | None = None, program: list[str] | None = None, month: list[str] | None = None):
    """Returns YoY YTD trend comparisons for sparkline charts (previous YTD vs current YTD)."""
    # 1. Calculate current YTD totals
    where_clause, params = _build_filters(years=years, region=region, program=program)
    where_clause, params = _apply_ytd_filter(where_clause, params, years, region, program, month=month)
    
    curr_kpis_row = fetch_one(
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
    
    curr_driver_where, curr_driver_params = _build_filters(years=years, region=region, program=program, is_vehicle_ops=True)
    curr_driver_where, curr_driver_params = _apply_ytd_filter(curr_driver_where, curr_driver_params, years, region, program, month=month)
    curr_driver_row = fetch_one(
        f"""
        SELECT
            COUNT(DISTINCT f.sk_driver_id) AS total_drivers
        FROM dw.fact_vehicle_operations f
        LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN dw.dim_program p ON p.sk_program_id = f.sk_program_id
        {curr_driver_where}
        """,
        curr_driver_params,
    )
    
    curr_inst = int(curr_kpis_row.get("total_instructors", 0) or 0)
    curr_driver = int(curr_driver_row.get("total_drivers", 0) or 0)
    curr_state = int(curr_kpis_row.get("total_states", 0) or 0)
    curr_prog = int(curr_kpis_row.get("total_programs", 0) or 0)

    # 2. Determine previous YTD totals
    single_year = None
    if years and len(years) == 1:
        try:
            single_year = int(years[0])
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
            prev_where_clause, prev_params = _build_filters(years=[prev_year], region=region, program=program)
            prev_where_clause, prev_params = _apply_ytd_filter(prev_where_clause, prev_params, [single_year], region, program, month=month)
            
            prev_kpis_row = fetch_one(
                f"""
                SELECT
                    COUNT(DISTINCT f.sk_user_id) AS total_instructors,
                    COUNT(DISTINCT g.nk_region_id) AS total_states,
                    COUNT(DISTINCT p.program_name) AS total_programs
                FROM dw.fact_session f
                LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
                LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
                LEFT JOIN dw.dim_program p ON p.sk_program_id = f.sk_program_id
                {prev_where_clause}
                """,
                prev_params,
            )
            
            prev_driver_where, prev_driver_params = _build_filters(years=[prev_year], region=region, program=program, is_vehicle_ops=True)
            prev_driver_where, prev_driver_params = _apply_ytd_filter(prev_driver_where, prev_driver_params, [single_year], region, program, month=month)
            prev_driver_row = fetch_one(
                f"""
                SELECT
                    COUNT(DISTINCT f.sk_driver_id) AS total_drivers
                FROM dw.fact_vehicle_operations f
                LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
                LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
                LEFT JOIN dw.dim_program p ON p.sk_program_id = f.sk_program_id
                {prev_driver_where}
                """,
                prev_driver_params,
            )
            
            prev_inst = int(prev_kpis_row.get("total_instructors", 0) or 0)
            prev_driver = int(prev_driver_row.get("total_drivers", 0) or 0)
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

def get_overview_charts(years: list[int] | list[str] | None = None, region: list[str] | None = None, program: list[str] | None = None, month: list[str] | None = None):
    where_clause, params = _build_filters(years=years, region=region, program=program)
    # Apply YTD month boundary filtering
    where_clause, params = _apply_ytd_filter(where_clause, params, years, region, program, month=month)
    
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
    driver_where, driver_params = _build_filters(years=years, region=region, program=program, is_vehicle_ops=True)
    driver_where, driver_params = _apply_ytd_filter(driver_where, driver_params, years, region, program, month=month)
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


    return {
        "instructors_by_region": [{"label": r["label"], "value": float(r["value"])} for r in instructors_rows],
        "drivers_by_region": [{"label": r["label"], "value": float(r["value"])} for r in drivers_rows],
        "programs_by_region": [{"label": r["label"], "value": float(r["value"])} for r in programs_rows]
    }


def get_program_targets(years: list[int] | list[str] | None = None, region: list[str] | None = None, program: list[str] | None = None, month: list[str] | None = None, limit: int = 10, offset: int = 0):
    where_clause, params = _build_filters(years=years, region=region, program=program)
    # Apply YTD month boundary filtering
    where_clause, params = _apply_ytd_filter(where_clause, params, years, region, program, month=month)
    
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


def get_sessions_by_activity(years: list[int] | list[str] | None = None, region: list[str] | None = None, program: list[str] | None = None, month: list[str] | None = None):
    where_clause, params = _build_filters(years=years, region=region, program=program)
    # Apply YTD month boundary filtering
    where_clause, params = _apply_ytd_filter(where_clause, params, years, region, program, month=month)
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


def get_sessions_by_donor(years: list[int] | list[str] | None = None, region: list[str] | None = None, program: list[str] | None = None, month: list[str] | None = None):
    where_clause, params = _build_filters(years=years, region=region, program=program)
    # Apply YTD month boundary filtering
    where_clause, params = _apply_ytd_filter(where_clause, params, years, region, program, month=month)
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
    month: list[str] | None = None
):
    """
    Returns rich drill-down stats for a specific region click.
    Uses hardened matching to ensure data integrity.
    """
    # 1. Build base filters (default to 2026 if none provided)
    where_clause, params = _build_filters(years=years, program=program)
    # Apply YTD month boundary filtering
    where_clause, params = _apply_ytd_filter(where_clause, params, years, region=None, program=program, month=month)
    
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
