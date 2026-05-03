import logging
from backend.services.query_utils import fetch_all, fetch_one
from backend.config import DATAMART_SCHEMA_NAME

logger = logging.getLogger(__name__)


def get_region_summary_filters(region_name: str | list[str] | None = None):
    from backend.services.query_utils import get_list_filter_clause
    try:
        # 1. Fetch only Regions that have data
        region_query = f"""
            SELECT DISTINCT g.region_name 
            FROM {DATAMART_SCHEMA_NAME}.dim_geography g
            INNER JOIN {DATAMART_SCHEMA_NAME}.fact_session f ON g.sk_geography_id = f.sk_geography_id
            WHERE g.region_name IS NOT NULL 
            ORDER BY g.region_name
        """
        regions = [row["region_name"] for row in fetch_all(region_query)]

        # 2. Fetch only programs that have data for the selected region
        where_sql, params = get_list_filter_clause("g.region_name", region_name)
        prog_query = f"""
            SELECT DISTINCT p.program_name 
            FROM {DATAMART_SCHEMA_NAME}.dim_program p
            INNER JOIN {DATAMART_SCHEMA_NAME}.fact_session f ON p.sk_program_id = f.sk_program_id
            INNER JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            WHERE p.program_name IS NOT NULL 
            AND {where_sql}
            ORDER BY p.program_name
        """
        programs = [row["program_name"] for row in fetch_all(prog_query, params)]
        
        years = [row["year_actual"] for row in fetch_all(f"""
            SELECT DISTINCT d.year_actual 
            FROM {DATAMART_SCHEMA_NAME}.dim_date d
            INNER JOIN {DATAMART_SCHEMA_NAME}.fact_session f ON d.date_id = f.date_id
            WHERE d.year_actual IS NOT NULL 
            ORDER BY d.year_actual DESC
        """)]
        
        months = [{"id": row["month_actual"], "name": row["month_name"].strip()} for row in fetch_all(f"""
            SELECT DISTINCT d.month_actual, TO_CHAR(TO_DATE(d.month_actual::text, 'MM'), 'Month') as month_name 
            FROM {DATAMART_SCHEMA_NAME}.dim_date d
            INNER JOIN {DATAMART_SCHEMA_NAME}.fact_session f ON d.date_id = f.date_id
            ORDER BY d.month_actual
        """)]
        
        return {
            "regions": regions,
            "programs": programs,
            "years": years,
            "months": months
        }
    except Exception as e:
        logger.error(f"Error fetching region summary filters: {e}")
        return {"regions": [], "programs": [], "years": [], "months": []}


def get_region_summary_data(region=None, program_type=None, year=None, month=None, limit=15, offset=0, dt_params=None):
    from backend.services.query_utils import parse_datatables_params, get_datatables_sql, get_list_filter_clause
    try:
        clauses = []
        params = []
        
        c, p = get_list_filter_clause("g.region_name", region)
        clauses.append(c); params.extend(p)
        
        c, p = get_list_filter_clause("p.program_name", program_type)
        clauses.append(c); params.extend(p)
        
        c, p = get_list_filter_clause("d.year_actual", year, cast_type="int")
        clauses.append(c); params.extend(p)
        
        c, p = get_list_filter_clause("d.month_actual", month, cast_type="int")
        clauses.append(c); params.extend(p)
        
        where_sql = " AND ".join(clauses)
        
        # KPI Query (sidebar filters only)
        kpi_sql = f"""
            SELECT 
                COUNT(f.sk_fact_session_id) as total_sessions,
                SUM(COALESCE(sess_agg.total_students, 0)) as total_exposure,
                SUM(CASE WHEN a.activity_name ILIKE '%%Fair%%' THEN 1 ELSE 0 END) as sf_count,
                SUM(CASE WHEN (p.program_name ILIKE '%%Teacher%%' OR a.activity_name ILIKE '%%Training%%') THEN 1 ELSE 0 END) as ttp_count
            FROM {DATAMART_SCHEMA_NAME}.fact_session f
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_activity_type a ON f.sk_activity_type_id = a.sk_activity_type_id
            LEFT JOIN (
                SELECT session_nk_id, SUM(total_exposure_count) as total_students
                FROM {DATAMART_SCHEMA_NAME}.fact_attendance_exposure
                GROUP BY session_nk_id
            ) sess_agg ON f.session_nk_id = sess_agg.session_nk_id
            WHERE {where_sql}
        """
        totals = fetch_one(kpi_sql, params)

        # DataTable Logic
        search_sql = "TRUE"
        search_params = []
        sort_sql = "ORDER BY region"
        
        if dt_params:
            searchable_cols = ["COALESCE(g.region_name, 'Unknown')"]
            sortable_cols = ["region", "sessions", "students_reached", "teachers_trained", "schools_covered"]
            
            inner_search_sql, inner_search_params, inner_sort_sql = get_datatables_sql(dt_params, searchable_cols, sortable_cols)
            search_sql = inner_search_sql
            search_params = inner_search_params
            if inner_sort_sql:
                sort_sql = inner_sort_sql

        # Get total count (Filtered by sidebar AND table search)
        count_sql = f"""
            SELECT COUNT(*) FROM (
                SELECT COALESCE(g.region_name, 'Unknown') as region
                FROM {DATAMART_SCHEMA_NAME}.fact_session f
                LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
                LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
                LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
                WHERE {where_sql} AND {search_sql}
                GROUP BY COALESCE(g.region_name, 'Unknown')
            ) as sub
        """
        total_count = fetch_one(count_sql, params + search_params).get("count", 0)

        # Main data query
        main_sql = f"""
            SELECT 
                COALESCE(g.region_name, 'Unknown') as region,
                COUNT(f.sk_fact_session_id) as sessions,
                SUM(COALESCE(sess_agg.total_students, 0)) as students_reached,
                SUM(COALESCE(f.no_of_teachers_participated, 0)) as teachers_trained,
                COUNT(DISTINCT f.sk_school_id) as schools_covered
            FROM {DATAMART_SCHEMA_NAME}.fact_session f
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
            LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
            LEFT JOIN (
                SELECT session_nk_id, SUM(total_exposure_count) as total_students
                FROM {DATAMART_SCHEMA_NAME}.fact_attendance_exposure
                GROUP BY session_nk_id
            ) sess_agg ON f.session_nk_id = sess_agg.session_nk_id
            WHERE {where_sql} AND {search_sql}
            GROUP BY COALESCE(g.region_name, 'Unknown')
            {sort_sql}
            LIMIT %s OFFSET %s
        """
        table_data = fetch_all(main_sql, params + search_params + [limit, offset])
        
        return {
            "kpis": [
                {"label": "Total Sessions", "value": int(totals.get("total_sessions", 0) or 0), "icon": "fas fa-clock"},
                {"label": "Total Schools Exposure", "value": int(totals.get("total_exposure", 0) or 0), "icon": "fas fa-user-graduate"},
                {"label": "Total Science Fair (SF)", "value": int(totals.get("sf_count", 0) or 0), "icon": "fas fa-flask"},
                {"label": "Total Teacher Training Program (TTP)", "value": int(totals.get("ttp_count", 0) or 0), "icon": "fas fa-chalkboard-teacher"},
            ],
            "table": table_data,
            "total_count": total_count
        }

    except Exception as e:
        logger.error(f"Error in region summary data: {e}", exc_info=True)
        return {"kpis": [], "table": [], "total_count": 0}




