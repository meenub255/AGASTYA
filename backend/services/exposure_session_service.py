import logging
from backend.services.query_utils import fetch_all, fetch_one
from backend.config import DATAMART_SCHEMA_NAME

logger = logging.getLogger(__name__)
DW = DATAMART_SCHEMA_NAME


def get_exposure_session_filters():
    try:
        # INNER JOIN with fact_session to ensure data exists
        regions = [r["region_name"] for r in fetch_all(f"""
            SELECT DISTINCT g.region_name 
            FROM {DW}.dim_geography g
            INNER JOIN {DW}.fact_session f ON g.sk_geography_id = f.sk_geography_id
            WHERE g.region_name IS NOT NULL 
            ORDER BY g.region_name
        """)]
        programs = [r["program_name"] for r in fetch_all(f"""
            SELECT DISTINCT p.program_name 
            FROM {DW}.dim_program p
            INNER JOIN {DW}.fact_session f ON p.sk_program_id = f.sk_program_id
            WHERE p.program_name IS NOT NULL 
            ORDER BY p.program_name
        """)]
        years = [r["year_actual"] for r in fetch_all(f"""
            SELECT DISTINCT d.year_actual 
            FROM {DW}.dim_date d
            INNER JOIN {DW}.fact_session f ON d.date_id = f.date_id
            WHERE d.year_actual IS NOT NULL 
            ORDER BY d.year_actual DESC
        """)]
        months = [{"id": r["month_actual"], "name": r["month_name"].strip()} for r in fetch_all(f"""
            SELECT DISTINCT d.month_actual, TO_CHAR(TO_DATE(d.month_actual::text,'MM'),'Month') AS month_name 
            FROM {DW}.dim_date d
            INNER JOIN {DW}.fact_session f ON d.date_id = f.date_id
            ORDER BY d.month_actual
        """)]
        return {"regions": regions, "programs": programs, "years": years, "months": months}
    except Exception as e:
        logger.error(f"exposure session filters error: {e}")
        return {"regions": [], "programs": [], "years": [], "months": []}


def get_exposure_session_data(region=None, program=None, years=None, month=None, quarter=None, limit=15, offset=0, dt_params=None, group_by="month"):
    from backend.services.query_utils import build_standard_filters, calculate_ytd_kpis, get_datatables_sql, get_time_grouping_expressions
    try:
        kpi_defs = [
            {"key": "total_students", "label": "Total Students Exposed", "sql": "COALESCE(SUM(e.boys_count + e.girls_count), 0)", "icon": "fas fa-user-graduate", "color": "linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%)"},
            {"key": "total_boys", "label": "Total Boys", "sql": "COALESCE(SUM(e.boys_count), 0)", "icon": "fas fa-male", "color": "linear-gradient(135deg, #22c55e 0%, #16a34a 100%)"},
            {"key": "total_girls", "label": "Total Girls", "sql": "COALESCE(SUM(e.girls_count), 0)", "icon": "fas fa-female", "color": "linear-gradient(135deg, #001f3f 0%, #001226 100%)"},
            {"key": "total_sessions", "label": "Total Sessions", "sql": "COUNT(DISTINCT f.session_nk_id)", "icon": "fas fa-chalkboard", "color": "linear-gradient(135deg, #dc3545 0%, #c82333 100%)"}
        ]
        
        from_clause = f"""
            {DW}.fact_session f
            LEFT JOIN {DW}.dim_geography g  ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_program p    ON f.sk_program_id = p.sk_program_id
            LEFT JOIN {DW}.dim_date d       ON f.date_id = d.date_id
            LEFT JOIN {DW}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
        """
        
        kpis, sparklines = calculate_ytd_kpis(
            kpi_defs=kpi_defs,
            from_clause=from_clause,
            years=years,
            region=region,
            program=program,
            month=month,
            quarter=quarter
        )
        
        where_sql, params, max_month = build_standard_filters(
            years=years,
            region=region,
            program=program,
            month=month,
            quarter=quarter
        )

        # 2. DataTable Logic
        search_sql = "TRUE"
        search_params = []
        sort_sql = "ORDER BY d.full_date DESC"
        
        if dt_params:
            searchable_cols = ["COALESCE(g.region_name, '')", "COALESCE(g.area_name, '')", "COALESCE(p.program_name, '')", "COALESCE(s.school_name, '')", "COALESCE(e.class_name, '')"]
            sortable_cols = ["region_name", "area_name", "program_name", "session_date", "school_name", "class_name", "boys", "girls", "total_exposure"]
            
            inner_search_sql, inner_search_params, inner_sort_sql = get_datatables_sql(dt_params, searchable_cols, sortable_cols)
            search_sql = inner_search_sql
            search_params = inner_search_params
            if inner_sort_sql:
                sort_sql = inner_sort_sql

        # 3. Get total count (Filtered by sidebar AND table search)
        count_sql = f"""
            SELECT COUNT(*) FROM (
                SELECT e.session_nk_id, e.class_name
                FROM {DW}.fact_session f
                LEFT JOIN {DW}.dim_geography g  ON f.sk_geography_id = g.sk_geography_id
                LEFT JOIN {DW}.dim_program p    ON f.sk_program_id = p.sk_program_id
                LEFT JOIN {DW}.dim_date d       ON f.date_id = d.date_id
                LEFT JOIN {DW}.dim_school s     ON f.sk_school_id = s.sk_school_id
                JOIN {DW}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
                WHERE {where_sql} AND {search_sql}
                GROUP BY e.session_nk_id, e.class_name, g.region_name, g.area_name, p.program_name, d.full_date, s.school_name
            ) AS sub
        """
        total_count_row = fetch_one(count_sql, params + search_params)
        total_count = total_count_row.get("count", 0) if total_count_row else 0

        # 4. Get paginated data
        table = fetch_all(f"""
            SELECT
                COALESCE(g.region_name, 'Unknown')    AS region_name,
                COALESCE(g.area_name, 'Unknown')      AS area_name,
                COALESCE(p.program_name, 'Unknown')   AS program_name,
                d.full_date                            AS session_date,
                COALESCE(s.school_name, 'Unknown')    AS school_name,
                COALESCE(e.class_name, 'Unknown')     AS class_name,
                COALESCE(SUM(e.boys_count), 0)        AS boys,
                COALESCE(SUM(e.girls_count), 0)       AS girls,
                COALESCE(SUM(e.total_exposure_count), 0) AS total_exposure
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_geography g  ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_program p    ON f.sk_program_id = p.sk_program_id
            LEFT JOIN {DW}.dim_date d       ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_school s     ON f.sk_school_id = s.sk_school_id
            JOIN {DW}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            WHERE {where_sql} AND {search_sql}
            GROUP BY g.region_name, g.area_name, p.program_name, d.full_date, s.school_name, e.class_name
            {sort_sql}
            LIMIT %s OFFSET %s
        """, params + search_params + [limit, offset])

        formatted = []
        for r in table:
            row = dict(r)
            if row.get("session_date"):
                row["session_date"] = row["session_date"].strftime("%Y-%m-%d")
            formatted.append(row)

        # Chart 1: Gender Split (doughnut chart)
        boys_val = 0
        girls_val = 0
        for k in kpis:
            if k["label"] == "Total Boys":
                boys_val = k["value"]
            elif k["label"] == "Total Girls":
                girls_val = k["value"]

        gender_split = [
            {"label": "Boys",  "value": int(boys_val)},
            {"label": "Girls", "value": int(girls_val)},
        ]

        label_expr, sort_expr, grp_expr = get_time_grouping_expressions(group_by)

        # Chart 2: Exposure Trend (dynamic date grouping)
        exposure_by_month = fetch_all(f"""
            SELECT {label_expr} AS label,
                   COALESCE(SUM(e.total_exposure_count), 0) AS value
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_geography g  ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_program p    ON f.sk_program_id = p.sk_program_id
            LEFT JOIN {DW}.dim_date d       ON f.date_id = d.date_id
            LEFT JOIN {DW}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            WHERE {where_sql} AND d.full_date IS NOT NULL
            GROUP BY {grp_expr}
            ORDER BY {sort_expr}
        """, params)

        return {
            "kpis": kpis,
            "sparklines": sparklines,
            "table": formatted,
            "total_count": int(total_count),
            "charts": {
                "gender_split":      gender_split,
                "exposure_by_month": [{"label": r["label"], "value": float(r["value"])} for r in exposure_by_month],
            }
        }
    except Exception as e:
        logger.error(f"exposure session data error: {e}", exc_info=True)
        return {"kpis": [], "table": [], "total_count": 0}

