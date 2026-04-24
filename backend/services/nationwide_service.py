import logging
from backend.services.query_utils import fetch_all, fetch_one
from backend.config import DATAMART_SCHEMA_NAME

logger = logging.getLogger(__name__)

DW = DATAMART_SCHEMA_NAME


def get_nationwide_filters():
    try:
        # Fetch only regions and years that actually have session data
        regions = [r["region_name"] for r in fetch_all(f"""
            SELECT DISTINCT g.region_name 
            FROM {DW}.dim_geography g
            INNER JOIN {DW}.fact_session f ON g.sk_geography_id = f.sk_geography_id
            WHERE g.region_name IS NOT NULL ORDER BY g.region_name
        """)]
        years = [r["year_actual"] for r in fetch_all(f"""
            SELECT DISTINCT d.year_actual 
            FROM {DW}.dim_date d
            INNER JOIN {DW}.fact_session f ON d.date_id = f.date_id
            WHERE d.year_actual IS NOT NULL ORDER BY d.year_actual DESC
        """)]
        return {"regions": regions, "years": years}
    except Exception as e:
        logger.error(f"nationwide filters error: {e}")
        return {"regions": [], "years": []}


def get_nationwide_data(year=None, region=None, limit=15, offset=0, dt_params=None):
    from backend.services.query_utils import parse_datatables_params, get_datatables_sql, get_list_filter_clause
    try:
        clauses = []
        params = []
        
        c, p = get_list_filter_clause("d.year_actual", year, cast_type="int")
        clauses.append(c); params.extend(p)
        
        c, p = get_list_filter_clause("g.region_name", region)
        clauses.append(c); params.extend(p)
        
        where_sql = " AND ".join(clauses)

        # KPIs
        kpi_row = fetch_one(f"""
            SELECT
                COUNT(DISTINCT f.sk_fact_session_id)  AS total_sessions,
                COALESCE(SUM(e.total_exposure_count), 0) AS total_students,
                COUNT(DISTINCT p.program_name)         AS total_programs,
                COUNT(DISTINCT f.sk_user_id)           AS total_instructors,
                COUNT(DISTINCT g.nk_region_id)         AS total_states
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_date d        ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_geography g   ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_program p     ON f.sk_program_id = p.sk_program_id
            LEFT JOIN {DW}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            WHERE {where_sql or 'TRUE'}
        """, params)

        # Separate query for drivers
        driver_row = fetch_one(f"""
            SELECT COUNT(DISTINCT v.sk_driver_id) AS total_drivers
            FROM {DW}.fact_vehicle_operations v
            LEFT JOIN {DW}.dim_date d       ON v.date_id = d.date_id
            LEFT JOIN {DW}.dim_geography g  ON v.sk_geography_id = g.sk_geography_id
            WHERE {where_sql}
        """, params)

        kpis = [
            {"label": "Total Instructors",    "value": int(kpi_row.get("total_instructors", 0) or 0), "icon": "fas fa-users",              "color": "bg-info"},
            {"label": "Total Drivers",        "value": int(driver_row.get("total_drivers", 0) or 0),  "icon": "fas fa-truck",              "color": "bg-success"},
            {"label": "States Reached",        "value": int(kpi_row.get("total_states", 0) or 0),      "icon": "fas fa-map-marker-alt",    "color": "bg-navy-blue"},
            {"label": "Total Programs",       "value": int(kpi_row.get("total_programs", 0) or 0),    "icon": "fas fa-project-diagram",    "color": "bg-danger"},
        ]

        # Chart 1: Monthly sessions trend (for line chart with trend line)
        sessions_trend_monthly = fetch_all(f"""
            SELECT TO_CHAR(d.full_date, 'YYYY-MM') AS label,
                   COUNT(DISTINCT f.sk_fact_session_id) AS value
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_date d      ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            WHERE {where_sql} AND d.full_date IS NOT NULL
            GROUP BY TO_CHAR(d.full_date, 'YYYY-MM')
            ORDER BY label
        """, params)

        # Chart 2: Students by region (for pie chart)
        students_by_region = fetch_all(f"""
            SELECT COALESCE(g.region_name, 'Unknown') AS label,
                   COALESCE(SUM(e.total_exposure_count), 0) AS value
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_date d       ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_geography g  ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            WHERE {where_sql}
            GROUP BY g.region_name ORDER BY value DESC LIMIT 10
        """, params)

        # DataTable Logic
        search_sql = "TRUE"
        search_params = []
        sort_sql = "ORDER BY sessions DESC"
        
        if dt_params:
            searchable_cols = ["COALESCE(g.region_name,'Unknown')"]
            sortable_cols = ["region_name", "sessions", "schools_visited", "students_reached", "instructors", "programs", "drivers"]
            
            inner_search_sql, inner_search_params, inner_sort_sql = get_datatables_sql(dt_params, searchable_cols, sortable_cols)
            search_sql = inner_search_sql
            search_params = inner_search_params
            if inner_sort_sql:
                sort_sql = inner_sort_sql

        # Get total count (Filtered by sidebar AND table search)
        count_sql = f"""
            SELECT COUNT(*) FROM (
                SELECT COALESCE(g.region_name,'Unknown')
                FROM {DW}.fact_session f
                LEFT JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
                LEFT JOIN {DW}.dim_date d       ON f.date_id = d.date_id
                WHERE {where_sql} AND {search_sql}
                GROUP BY COALESCE(g.region_name, 'Unknown')
            ) as sub
        """
        total_count = fetch_one(count_sql, params + search_params).get("count", 0)

        # Get paginated data
        table_params = params + params + search_params + [limit, offset]
        table = fetch_all(f"""
            SELECT
                COALESCE(g.region_name,'Unknown')              AS region_name,
                COUNT(DISTINCT f.sk_fact_session_id)           AS sessions,
                COUNT(DISTINCT f.sk_school_id)                 AS schools_visited,
                COALESCE(SUM(e.total_exposure_count), 0)       AS students_reached,
                COUNT(DISTINCT f.sk_user_id)                   AS instructors,
                COUNT(DISTINCT f.sk_program_id)                AS programs,
                (
                    SELECT COUNT(DISTINCT v.sk_driver_id)
                    FROM {DW}.fact_vehicle_operations v
                    LEFT JOIN {DW}.dim_geography dg ON v.sk_geography_id = dg.sk_geography_id
                    LEFT JOIN {DW}.dim_date dd ON v.date_id = dd.date_id
                    WHERE COALESCE(dg.region_name,'Unknown') = COALESCE(g.region_name,'Unknown')
                    AND {where_sql.replace('d.', 'dd.').replace('g.', 'dg.')}
                ) AS drivers
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_geography g   ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d        ON f.date_id = d.date_id
            LEFT JOIN {DW}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
            WHERE {where_sql} AND {search_sql}
            GROUP BY g.region_name 
            {sort_sql}
            LIMIT %s OFFSET %s
        """, table_params)

        return {
            "kpis": kpis,
            "charts": {
                "sessions_trend_monthly": [{"label": r["label"], "value": float(r["value"])} for r in sessions_trend_monthly],
                "students_by_region":     [{"label": r["label"], "value": float(r["value"])} for r in students_by_region],
            },
            "table": table,
            "total_count": int(total_count),
        }
    except Exception as e:
        logger.error(f"nationwide data error: {e}", exc_info=True)
        return {"kpis": [], "charts": {}, "table": [], "total_count": 0}
