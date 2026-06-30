from collections.abc import Sequence
import logging
import datetime

logger = logging.getLogger(__name__)

from backend.config import DEFAULT_YEAR
from backend.db import get_datamart_conn


def parse_fy_string(fy_str: str) -> tuple[int, int] | None:
    """
    Parses a Financial Year string like '2026-27' or '2025-26' into a
    (fy_start_year, fy_end_year) tuple, e.g. (2026, 2027).
    Returns None if the string is not a valid FY format.
    FY runs April (month 4) of fy_start_year to March (month 3) of fy_end_year.
    """
    if not isinstance(fy_str, str) or '-' not in fy_str:
        return None
    parts = fy_str.split('-')
    if len(parts) != 2:
        return None
    try:
        start = int(parts[0])
        # End year suffix can be 2-digit or 4-digit
        suffix = parts[1]
        if len(suffix) == 2:
            end = int(str(start)[:2] + suffix)
        elif len(suffix) == 4:
            end = int(suffix)
        else:
            return None
        if end != start + 1:
            return None
        return (start, end)
    except (ValueError, TypeError):
        return None


def fy_to_date_clause(fy_years: list[str], date_alias: str = "d") -> tuple[str, list]:
    """
    Converts a list of FY year strings like ['2026-27', '2025-26'] into a
    SQL WHERE clause fragment that correctly filters across the two calendar
    years each FY spans.

    FY XXXX-YY = months 4-12 of XXXX UNION months 1-3 of YY.
    Returns (sql_clause, params) suitable for AND-ing into a WHERE clause.
    """
    if not fy_years:
        return "TRUE", []

    conditions = []
    params = []
    for fy_str in fy_years:
        parsed = parse_fy_string(fy_str)
        if parsed:
            start_yr, end_yr = parsed
            # FY = (year=start_yr AND month>=4) OR (year=end_yr AND month<=3)
            cond = (
                f"(({date_alias}.year_actual = %s AND {date_alias}.month_actual >= 4) "
                f"OR ({date_alias}.year_actual = %s AND {date_alias}.month_actual <= 3))"
            )
            conditions.append(cond)
            params.extend([start_yr, end_yr])
        else:
            # Treat as plain calendar year
            try:
                cal_yr = int(str(fy_str)[:4])
                conditions.append(f"{date_alias}.year_actual = %s")
                params.append(cal_yr)
            except (ValueError, TypeError):
                pass

    if not conditions:
        return "TRUE", []
    return "(" + " OR ".join(conditions) + ")", params


def get_current_fy() -> str:
    """
    Returns the current Financial Year label string, e.g. '2026-27'.
    FY starts in April. If current month < April, we are in FY (year-1)-year.
    """
    now = datetime.datetime.now()
    if now.month >= 4:
        return f"{now.year}-{str(now.year + 1)[2:]}"
    else:
        return f"{now.year - 1}-{str(now.year)[2:]}"


def get_ytd_max_month(year: int) -> int:
    """
    Returns the maximum month (1-12) to include in the YTD calculations for the given year.
    If the year is 2026, it returns 5.
    If it is the current calendar year, it caps at current calendar month.
    Always caps at the current calendar month to exclude future sessions.
    """
    current_yr = datetime.datetime.now().year
    current_mo = datetime.datetime.now().month
    if year >= current_yr:
        return current_mo
    return 12

def apply_ytd_filter(where_clause: str, params: list, years: list | None, date_alias: str = "d", force_max_month: int | None = None) -> tuple[str, list]:
    max_month = None
    if force_max_month is not None:
        max_month = force_max_month
    else:
        single_year = None
        if years and len(years) == 1:
            try:
                single_year = int(str(years[0])[:4])
            except (ValueError, TypeError):
                pass
        elif years is None or len(years) == 0:
            single_year = DEFAULT_YEAR

        if single_year is not None:
            max_month = get_ytd_max_month(single_year)

    if max_month is not None:
        month_expr = f"{date_alias}.month_actual"
        
        where_clause_stripped = where_clause.strip() if where_clause else ""
        starts_with_where = where_clause_stripped.upper().startswith("WHERE")
        
        if starts_with_where:
            # It starts with WHERE (e.g. from build_dimension_filters)
            if len(where_clause_stripped) > 5:
                where_clause = where_clause + f" AND {month_expr} <= %s"
            else:
                where_clause = f"WHERE {month_expr} <= %s"
        else:
            # It does not start with WHERE (e.g. raw condition list)
            if where_clause_stripped != "":
                where_clause = where_clause + f" AND {month_expr} <= %s"
            else:
                where_clause = f"{month_expr} <= %s"
                
        params.append(max_month)
        
    return where_clause, params

def build_standard_filters(
    years=None,
    region=None,
    area=None,
    program=None,
    month=None,
    quarter=None,
    date_alias: str = "d",
    region_expr: str = "g.region_name",
    area_expr: str = "g.area_name",
    program_expr: str = "p.program_name",
    force_max_month: int | None = None
) -> tuple[str, list, int | None]:
    """
    Builds the standard WHERE clause and params, including:
    - Region, Area, Program, Years, Month, and Quarter filters.
    - Automatic YTD capping if month and quarter are not specified.
    Returns: where_sql, params, max_month
    """
    clauses = []
    params = []
    
    # 1. Region
    if region is not None:
        c, p = get_list_filter_clause(region_expr, region)
        if c != "TRUE":
            clauses.append(c); params.extend(p)
            
    # 2. Area
    if area is not None:
        c, p = get_list_filter_clause(area_expr, area)
        if c != "TRUE":
            clauses.append(c); params.extend(p)
            
    # 3. Program (mapped to Activity Type filter)
    if program is not None:
        if isinstance(program, list):
            clean_programs = [pr for pr in program if pr and pr != ""]
            if clean_programs:
                clauses.append("f.sk_activity_type_id IN (SELECT sk_activity_type_id FROM dw.dim_activity_type WHERE activity_name = ANY(%s))")
                params.append(clean_programs)
        else:
            if program and program != "":
                clauses.append("f.sk_activity_type_id IN (SELECT sk_activity_type_id FROM dw.dim_activity_type WHERE activity_name = %s)")
                params.append(program)
            
    # 4. Years — support both FY strings ('2026-27') and plain calendar years
    effective_years = years
    if effective_years is None or (isinstance(effective_years, list) and len(effective_years) == 0):
        effective_years = [get_current_fy()]

    if effective_years:
        year_list = effective_years if isinstance(effective_years, list) else [effective_years]
        fy_strings = [v for v in year_list if parse_fy_string(str(v)) is not None]
        cal_years  = [v for v in year_list if parse_fy_string(str(v)) is None]

        if fy_strings:
            fy_sql, fy_params = fy_to_date_clause(fy_strings, date_alias=date_alias)
            if fy_sql != "TRUE":
                clauses.append(fy_sql)
                params.extend(fy_params)

        if cal_years:
            c, p = get_list_filter_clause(f"{date_alias}.year_actual", cal_years, cast_type="int")
            if c != "TRUE":
                clauses.append(c); params.extend(p)

    # 5. Quarter
    if quarter is not None:
        fiscal_q_expr = f"CASE WHEN {date_alias}.month_actual IN (4,5,6) THEN 1 WHEN {date_alias}.month_actual IN (7,8,9) THEN 2 WHEN {date_alias}.month_actual IN (10,11,12) THEN 3 ELSE 4 END"
        c, p = get_list_filter_clause(fiscal_q_expr, quarter, cast_type="int")
        if c != "TRUE":
            clauses.append(c); params.extend(p)
            
    # 6. Month
    if month is not None:
        c, p = get_list_filter_clause(f"{date_alias}.month_actual", month, cast_type="int")
        if c != "TRUE":
            clauses.append(c); params.extend(p)
            
    # 7. Apply YTD capping and future-session exclusion
    # Always exclude future sessions
    clauses.append(f"{date_alias}.full_date <= CURRENT_DATE")

    max_month = None
    if not month and not quarter:
        if force_max_month is not None:
            max_month = force_max_month
        else:
            # Determine current FY context for YTD capping
            current_fy = get_current_fy()
            single_fy = None
            if effective_years and len(effective_years) == 1:
                single_fy = str(effective_years[0])
            elif not effective_years:
                single_fy = current_fy

            if single_fy is not None:
                parsed = parse_fy_string(single_fy)
                if parsed:
                    if single_fy == current_fy:
                        import datetime as _dt
                        max_month = _dt.datetime.now().month
                else:
                    # Plain calendar year
                    try:
                        single_year = int(str(single_fy)[:4])
                        max_month = get_ytd_max_month(single_year)
                    except (ValueError, TypeError):
                        pass
                
        if max_month is not None:
            clauses.append(f"{date_alias}.month_actual <= %s")
            params.append(max_month)
            
    where_sql = " AND ".join(clauses) if clauses else "TRUE"
    return where_sql, params, max_month


def get_list_filter_clause(column: str, value: str | list[str] | None, cast_type: str | None = None, use_default_year: bool = True) -> tuple[str, list]:
    """
    Returns a SQL clause and params for both single values and lists.
    Uses ANY() for PostgreSQL lists.
    """
    if value is None:
        if use_default_year and ("year" in column.lower() or "date" in column.lower()):
            value = [DEFAULT_YEAR]
        else:
            return "TRUE", []
    
    if value == "" or (isinstance(value, list) and not value):
        return "TRUE", []
    
    if isinstance(value, list):
        # Filter out empty strings from list
        clean_values = [v for v in value if v and v != ""]
        if not clean_values:
            return "TRUE", []
        
        if cast_type == "int":
            clean_values = [int(v) for v in clean_values if str(v).isdigit()]
            if not clean_values: return "TRUE", []

        return f"{column} = ANY(%s)", [clean_values]
    
    if cast_type == "int" and str(value).isdigit():
        value = int(value)
        
    return f"{column} = %s", [value]


def build_dimension_filters(
    *,
    start: int | list[int] | str | list[str] | None = None,
    end: int | list[int] | str | list[str] | None = None,
    year: int | list[int] | str | list[str] | None = None,
    region: str | list[str] | None = None,
    program: str | list[str] | None = None,
    date_expression: str | None = None,
    year_expression: str | None = None,
    location_expression: str | None = None,
    program_expression: str | None = None,
    instructor: str | list[str] | None = None,
    instructor_expression: str | None = None,
    use_default_year: bool = True,
) -> tuple[str, list[object]]:
    """
    Build a WHERE clause and params list from dimension filters.
    Supports FY strings like '2026-27' (April-March financial year) which
    are correctly expanded to cover two calendar years.
    """
    clauses: list[str] = []
    params: list[object] = []

    def add_list_filter(col, val, cast_type=None):
        if val is None or val == "" or (isinstance(val, list) and not val):
            return
        if isinstance(val, list):
            clean = [v for v in val if v and v != ""]
            if not clean:
                return
            if cast_type == "int":
                clean = [int(v) for v in clean if str(v).isdigit()]
                if not clean:
                    return
            clauses.append(f"{col} = ANY(%s)")
            params.append(clean)
        else:
            if cast_type == "int" and str(val).isdigit():
                val = int(val)
            clauses.append(f"{col} = %s")
            params.append(val)

    # ── Year / Financial Year handling ────────────────────────────────────────
    # Values may be FY strings like '2026-27' or plain calendar years like 2026.
    # FY '2026-27' spans April 2026 - March 2027 (two calendar years).
    effective_year = year
    if effective_year is None and use_default_year:
        effective_year = [get_current_fy()]   # default to current financial year

    if effective_year is not None:
        year_list = effective_year if isinstance(effective_year, list) else [effective_year]
        year_list = [v for v in year_list if v is not None and v != ""]

        # Split into FY strings vs plain calendar years
        fy_strings = [v for v in year_list if parse_fy_string(str(v)) is not None]
        cal_years  = [v for v in year_list if parse_fy_string(str(v)) is None]

        if fy_strings:
            date_alias = (year_expression or "d.year_actual").split(".")[0]
            fy_sql, fy_params = fy_to_date_clause(fy_strings, date_alias=date_alias)
            if fy_sql != "TRUE":
                clauses.append(fy_sql)
                params.extend(fy_params)

        if cal_years:
            add_list_filter(
                year_expression or f"EXTRACT(YEAR FROM {date_expression})",
                cal_years,
                cast_type="int"
            )

    if start is not None:
        if isinstance(start, list):
            add_list_filter(
                year_expression or f"EXTRACT(YEAR FROM {date_expression})",
                start, cast_type="int"
            )
        else:
            col = year_expression or (f"EXTRACT(YEAR FROM {date_expression})" if date_expression else None)
            if col:
                clauses.append(f"{col} >= %s")
                params.append(int(start) if str(start).isdigit() else start)

    if end is not None:
        if not isinstance(end, list):
            col = year_expression or (f"EXTRACT(YEAR FROM {date_expression})" if date_expression else None)
            if col:
                clauses.append(f"{col} <= %s")
                params.append(int(end) if str(end).isdigit() else end)

    if location_expression:
        add_list_filter(location_expression, region)

    if program is not None:
        if isinstance(program, list):
            clean_programs = [pr for pr in program if pr and pr != ""]
            if clean_programs:
                clauses.append(
                    "f.sk_activity_type_id IN "
                    "(SELECT sk_activity_type_id FROM dw.dim_activity_type WHERE activity_name = ANY(%s))"
                )
                params.append(clean_programs)
        else:
            if program and program != "":
                clauses.append(
                    "f.sk_activity_type_id IN "
                    "(SELECT sk_activity_type_id FROM dw.dim_activity_type WHERE activity_name = %s)"
                )
                params.append(program)

    if instructor_expression:
        add_list_filter(instructor_expression, instructor)

    if not clauses:
        return "", params

    return "WHERE " + " AND ".join(clauses), params



def fetch_one(query: str, params: Sequence[object] | None = None) -> dict:
    conn = get_datamart_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(query, params or [])
            row = cur.fetchone()
            return dict(row or {})
    finally:
        conn.close()


def fetch_all(query: str, params: Sequence[object] | None = None) -> list[dict]:
    conn = get_datamart_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(query, params or [])
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def parse_datatables_params(params: dict):
    """
    Extracts DataTables parameters from a flat dictionary (e.g. request.query_params).
    """
    return {
        "draw": int(params.get("draw", 1)),
        "start": int(params.get("start", 0)),
        "length": int(params.get("length", 15)),
        "search_value": params.get("search[value]", ""),
        "sort_col_idx": int(params.get("order[0][column]", 0)) if "order[0][column]" in params else None,
        "sort_dir": params.get("order[0][dir]", "asc")
    }


def get_datatables_sql(dt_params: dict, searchable_columns: list[str], sortable_columns: list[str] = None):
    """
    Generates SQL snippets for searching and sorting.
    """
    search_sql = "1=1"
    search_params = []
    
    if dt_params["search_value"] and searchable_columns:
        clauses = []
        for col in searchable_columns:
            clauses.append(f"CAST({col} AS TEXT) ILIKE %s")
            search_params.append(f"%{dt_params['search_value']}%")
        search_sql = "(" + " OR ".join(clauses) + ")"

    sort_sql = ""
    if dt_params["sort_col_idx"] is not None and sortable_columns and dt_params["sort_col_idx"] < len(sortable_columns):
        col_name = sortable_columns[dt_params["sort_col_idx"]]
        if col_name:
            direction = "DESC" if dt_params["sort_dir"].lower() == "desc" else "ASC"
            sort_sql = f'ORDER BY "{col_name}" {direction}'

    return search_sql, search_params, sort_sql

def calc_trend(curr, prev):
    if not prev:
        return {"pct": 0, "dir": "neutral"}
    diff = curr - prev
    pct = round((diff / prev) * 100, 1) if prev > 0 else 0
    direction = "up" if diff > 0 else ("down" if diff < 0 else "neutral")
    return {"pct": pct, "dir": direction}

def get_kpi_insight(
    label: str,
    curr_val: float,
    prev_val: float,
    single_year: int | None,
    prev_year: int | None,
    max_month: int | None,
    month_filter: list | None = None,
    quarter_filter: list | None = None
) -> dict:
    """
    Generates standard KPI insights structure including YoY comparison text,
    trend direction, and exactly 3 strategic suggestions.
    """
    trend = calc_trend(curr_val, prev_val)
    is_up = trend["dir"] == "up"
    is_down = trend["dir"] == "down"
    pct_str = f"{abs(trend['pct'])}%"
    
    def fmt(v):
        return str(int(v)) if v == int(v) else f"{v:.1f}"
        
    months_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    
    if month_filter and len(month_filter) == 1:
        month_range_str = months_names[int(month_filter[0]) - 1]
    elif quarter_filter and len(quarter_filter) == 1:
        q = int(quarter_filter[0])
        if q == 1: month_range_str = "Apr-Jun"
        elif q == 2: month_range_str = "Jul-Sep"
        elif q == 3: month_range_str = "Oct-Dec"
        else: month_range_str = "Jan-Mar"
    elif max_month:
        month_range_str = f"Jan-{months_names[max_month-1]}" if 1 <= max_month <= 12 else "YTD"
    else:
        month_range_str = "YTD"
        
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
        
    suggestions_db = {
        "instructors": {
            "up": [
                "<strong>Scale Peer Mentorship Program:</strong> Appoint senior instructors as regional mentors to maintain delivery quality across new cohorts.",
                "<strong>Implement Multi-Curriculum Cross-Training:</strong> Conduct workshops to certify existing instructors in secondary subjects, improving utility.",
                "<strong>Optimize Deployment Logistics:</strong> Use geo-clustering algorithms to assign instructors to schools, reducing travel time."
            ],
            "down": [
                "<strong>Streamline Recruitment Timelines:</strong> Reduce the hiring bottleneck by digitizing background checks, cutting onboarding time.",
                "<strong>Deploy a Retention Incentive Matrix:</strong> Introduce tiered quarterly retention bonuses and merit certificates for instructors.",
                "<strong>Establish a Standby Trainer Pool:</strong> Maintain a 15% reserve of certified backup instructors to cover attrition."
            ],
            "neutral": [
                "<strong>Initiate Regional Skills Audits:</strong> Map current instructor capabilities against upcoming specialized program requirements.",
                "<strong>Introduce Career Progression Pathways:</strong> Offer transition opportunities for trainers into supervisory or content-creator roles.",
                "<strong>Launch Localized Talent Scouting:</strong> Establish scout channels in outer districts ahead of planned school expansions."
            ]
        },
        "sessions": {
            "up": [
                "<strong>Reward High-Session Hubs:</strong> Launch regional awards for hubs maintaining 100% scheduled session compliance.",
                "<strong>Implement Standardized Curriculum Packages:</strong> Package teaching kits to ensure fast classroom setup and execution.",
                "<strong>Establish Cross-Hub Resource Sharing:</strong> Share materials and reserve instructors during peak campaign months."
            ],
            "down": [
                "<strong>Adopt Automated Scheduling Tools:</strong> Implement mobile calendars that send instant alerts to school principals and trainers.",
                "<strong>Run Make-up Sessions:</strong> Dedicate specific weeks at the end of the term to catch up on cancelled classes.",
                "<strong>Cross-Train Reserve Instructors:</strong> Certify administration staff in curricula to cover instructor sick days."
            ],
            "neutral": [
                "<strong>Audit Calendar Gaps:</strong> Identify under-scheduled weekdays to maximize classroom utilization.",
                "<strong>Introduce Dual-Session Formats:</strong> Run concurrent morning and afternoon sessions to increase capacity without expanding headcount.",
                "<strong>Standardize Scheduling Templates:</strong> Provide simple templates for instructors to pre-book their entire semester."
            ]
        },
        "students": {
            "up": [
                "<strong>Roll Out Level-2 Specializations:</strong> Launch follow-up modules to sustain engagement with successfully reached cohorts.",
                "<strong>Leverage Peer-to-Peer Mentoring:</strong> Train high-performing students to act as assistant leaders inside classrooms.",
                "<strong>Distribute Completion Certificates:</strong> Award official credentials to motivate students to attend the complete curriculum."
            ],
            "down": [
                "<strong>Launch Student Attendance Competitions:</strong> Work with teachers to offer small awards for sections reaching 100% attendance.",
                "<strong>Reschedule Session Windows:</strong> Time classes during high-attendance morning slots instead of late afternoon slots.",
                "<strong>Incorporate Interactive Learning Kits:</strong> Integrate hands-on models and tablet activities to maximize classroom interest."
            ],
            "neutral": [
                "<strong>Execute Classroom Audits:</strong> Audit session capacities to ensure instructors are assigned to appropriately-sized student groups.",
                "<strong>Introduce Multi-Section Scheduling:</strong> Combine smaller sections or split over-crowded classrooms to ensure optimal teaching environments.",
                "<strong>Run Double-Session Rotations:</strong> Run twin cohorts (morning/afternoon) to reach more students with current staff."
            ]
        }
    }
    
    l_lower = label.lower()
    cat = "sessions"
    if "instructor" in l_lower or "staff" in l_lower or "lead" in l_lower or "driver" in l_lower or "user" in l_lower or "member" in l_lower or "people" in l_lower:
        cat = "instructors"
    elif "student" in l_lower or "exposure" in l_lower or "reached" in l_lower or "people" in l_lower or "pupil" in l_lower or "child" in l_lower:
        cat = "students"
        
    s_dir = trend["dir"]
    sugs = suggestions_db[cat][s_dir][:3]
    
    icon_map = {
        "instructors": "fas fa-users",
        "students": "fas fa-user-graduate",
        "sessions": "fas fa-chalkboard-teacher"
    }
    
    color_map = {
        "instructors": "linear-gradient(135deg, #f39c12 0%, #e67e22 100%)",
        "students": "linear-gradient(135deg, #e74c3c 0%, #c0392b 100%)",
        "sessions": "linear-gradient(135deg, #2ecc71 0%, #27ae60 100%)"
    }
    
    return {
        "title": f"{label} Performance Insights",
        "icon": icon_map[cat],
        "color": color_map[cat],
        "name": label,
        "comparison_text": comparison_text,
        "suggestions": sugs
    }

def calculate_ytd_kpis(
    *,
    kpi_defs: list[dict],
    from_clause: str,
    years: list | None = None,
    region: list | None = None,
    area: list | None = None,
    program: list | None = None,
    month: list | None = None,
    quarter: list | None = None,
    date_alias: str = "d",
    region_expr: str = "g.region_name",
    area_expr: str = "g.area_name",
    program_expr: str = "p.program_name"
) -> tuple[list[dict], dict]:
    """
    Helper function to calculate YTD KPIs, YoY trends, sparklines, and insights.
    """
    # 1. Build current period filters
    where_sql, params, max_month = build_standard_filters(
        years=years,
        region=region,
        area=area,
        program=program,
        month=month,
        quarter=quarter,
        date_alias=date_alias,
        region_expr=region_expr,
        area_expr=area_expr,
        program_expr=program_expr
    )
    
    # 2. Query current period
    select_clause = ", ".join([f"{d['sql']} AS {d['key']}" for d in kpi_defs])
    curr_sql = f"SELECT {select_clause} FROM {from_clause} WHERE {where_sql}"
    curr_row = fetch_one(curr_sql, params)
    
    # 3. Build previous period filters
    effective_years = [int(y) for y in (years or [DEFAULT_YEAR])]
    prev_year_vals = [y - 1 for y in effective_years]
    
    prev_where_sql, prev_params, _ = build_standard_filters(
        years=prev_year_vals,
        region=region,
        area=area,
        program=program,
        month=month,
        quarter=quarter,
        date_alias=date_alias,
        region_expr=region_expr,
        area_expr=area_expr,
        program_expr=program_expr,
        force_max_month=max_month
    )
    
    # Query previous period
    prev_sql = f"SELECT {select_clause} FROM {from_clause} WHERE {prev_where_sql}"
    prev_row = fetch_one(prev_sql, prev_params)
    
    # 4. Resolve year context for insights
    single_year = int(str(effective_years[0])[:4]) if len(effective_years) == 1 else None
    prev_year = single_year - 1 if single_year is not None else None
    
    kpis = []
    sparklines = {}
    
    for d in kpi_defs:
        key = d["key"]
        label = d["label"]
        icon = d["icon"]
        color = d["color"]
        
        # Coerce to float to handle SUMs, averages etc.
        curr_val = float(curr_row.get(key) or 0)
        prev_val = float(prev_row.get(key) or 0)
        
        # Format integer values nicely
        if curr_val == int(curr_val): curr_val = int(curr_val)
        if prev_val == int(prev_val): prev_val = int(prev_val)
        
        trend = calc_trend(curr_val, prev_val)
        insights = get_kpi_insight(label, curr_val, prev_val, single_year, prev_year, max_month, month, quarter)
        
        kpis.append({
            "label": label,
            "value": curr_val,
            "icon": icon,
            "color": color,
            "trend": trend,
            "insights": insights,
            "trends": [prev_val, curr_val]
        })
        
        # Sparklines mapping: exact 2-point YTD comparison data
        sparkline_key = key.replace("total_", "").replace("active_", "")
        sparklines[sparkline_key] = [prev_val, curr_val]
        
    return kpis, sparklines

def get_time_grouping_expressions(
    group_by: str = "month",
    date_col: str = "d.full_date",
    month_col: str = "d.month_actual",
    year_col: str = "d.year_actual"
) -> tuple[str, str, str]:
    """
    Returns (label_expr, sort_expr, grp_expr) for dynamic date/time SQL grouping.
    """
    group_by = (group_by or "month").lower()
    fiscal_q_expr = f"CASE WHEN {month_col} IN (4,5,6) THEN 1 WHEN {month_col} IN (7,8,9) THEN 2 WHEN {month_col} IN (10,11,12) THEN 3 ELSE 4 END"
    fiscal_y_expr = f"CASE WHEN {month_col} >= 4 THEN {year_col} ELSE {year_col} - 1 END"

    if group_by == "day":
        label_expr = f"TO_CHAR({date_col}, 'YYYY-MM-DD')"
        sort_expr = f"MIN({date_col})"
        grp_expr = date_col
    elif group_by == "quarter":
        label_expr = f"'Q' || {fiscal_q_expr} || ' ' || {fiscal_y_expr}"
        sort_expr = f"MIN({date_col})"
        grp_expr = f"{fiscal_q_expr}, {fiscal_y_expr}"
    elif group_by == "year":
        label_expr = f"{year_col}::text"
        sort_expr = f"{year_col}"
        grp_expr = year_col
    else:  # month (default)
        label_expr = f"TO_CHAR({date_col}, 'YYYY-MM')"
        sort_expr = f"MIN({date_col})"
        grp_expr = f"TO_CHAR({date_col}, 'YYYY-MM')"
        
    return label_expr, sort_expr, grp_expr




