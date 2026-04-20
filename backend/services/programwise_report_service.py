from backend.services.query_utils import fetch_all, fetch_one
from backend.config import DATAMART_SCHEMA_NAME

def get_programwise_report_filters():
    # Fetch categories (using donor_name as a proxy if program_category is missing)
    categories = [row["donor_name"] for row in fetch_all(f"SELECT DISTINCT donor_name FROM {DATAMART_SCHEMA_NAME}.dim_program WHERE donor_name IS NOT NULL ORDER BY donor_name")]
    
    years = [row["year_actual"] for row in fetch_all(f"SELECT DISTINCT year_actual FROM {DATAMART_SCHEMA_NAME}.dim_date WHERE year_actual IS NOT NULL ORDER BY year_actual DESC")]
    
    months = [{"id": row["month_actual"], "name": row["month_name"].strip()} for row in fetch_all(f"SELECT DISTINCT month_actual, TO_CHAR(TO_DATE(month_actual::text, 'MM'), 'Month') as month_name FROM {DATAMART_SCHEMA_NAME}.dim_date ORDER BY month_actual")]
    
    return {
        "categories": categories,
        "years": years,
        "months": months
    }


def get_programwise_report_data(category=None, year=None, month=None, limit=15, offset=0, dt_params=None):
    from backend.services.query_utils import parse_datatables_params, get_datatables_sql
    where_clauses = ["TRUE"]
    params = []
    
    if category:
        where_clauses.append("p.donor_name = %s")
        params.append(category)
    if year:
        where_clauses.append("d.year_actual = %s")
        params.append(int(year))
    if month:
        where_clauses.append("d.month_actual = %s")
        params.append(int(month))
    
    where_sql = " AND ".join(where_clauses)
    
    # 1. KPI Query (sidebar filters only)
    kpi_sql = f"""
        SELECT 
            COUNT(DISTINCT p.program_name) as total_programs,
            COUNT(DISTINCT f.sk_school_id) as total_schools,
            COUNT(DISTINCT f.sk_fact_session_id) as total_sessions,
            SUM(COALESCE(e.total_exposure_count, 0)) as total_students
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
        JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
        WHERE {where_sql}
    """
    kpis_raw = fetch_one(kpi_sql, params)
    
    kpi_list = [
        {"label": "Total Programs", "value": kpis_raw.get('total_programs', 0), "icon": "fas fa-project-diagram", "color": "bg-info"},
        {"label": "Total Schools", "value": kpis_raw.get('total_schools', 0), "icon": "fas fa-school", "color": "bg-success"},
        {"label": "Total Sessions", "value": kpis_raw.get('total_sessions', 0), "icon": "fas fa-chalkboard-teacher", "color": "bg-navy-blue"},
        {"label": "Total Students Impacted", "value": kpis_raw.get('total_students', 0), "icon": "fas fa-user-graduate", "color": "bg-danger"}
    ]

    # 2. DataTable Logic
    search_sql = "TRUE"
    search_params = []
    sort_sql = 'ORDER BY "School Sessions" DESC'
    
    if dt_params:
        searchable_cols = ["g.region_name", "g.area_name", "p.program_name", "p.donor_name"]
        sortable_cols = ["Region Name", "Area Name", "Program Name", "Donor Name", "No of Schools visited", "Total Number of Days worked", "School Sessions", "Average Session Durat", "Total Exposure"]
        # Map some columns to actual complex SQL if needed, but here simple aliases work for Postgres "ORDER BY"
        
        inner_search_sql, inner_search_params, inner_sort_sql = get_datatables_sql(dt_params, searchable_cols, sortable_cols)
        search_sql = inner_search_sql
        search_params = inner_search_params
        if inner_sort_sql:
            sort_sql = inner_sort_sql

    # Get total count (Filtered by sidebar AND table search)
    count_sql = f"""
        SELECT COUNT(*) FROM (
            SELECT p.program_name
            FROM {DATAMART_SCHEMA_NAME}.fact_session f
            JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
            JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
            WHERE {where_sql} AND {search_sql}
            GROUP BY p.program_name, g.region_name, g.area_name, p.donor_name
        ) as sub
    """
    total_count_row = fetch_one(count_sql, params + search_params)
    total_count = total_count_row.get("count", 0) if total_count_row else 0

    # Get paginated data
    sql = f"""
        SELECT 
            g.region_name as "Region Name",
            g.area_name as "Area Name",
            p.program_name as "Program Name",
            p.donor_name as "Donor Name",
            COUNT(DISTINCT f.sk_school_id) as "No of Schools visited",
            COUNT(DISTINCT f.date_id) as "Total Number of Days worked",
            COUNT(DISTINCT f.sk_fact_session_id) as "School Sessions",
            ROUND(AVG(COALESCE(f.session_duration_minutes, 0)), 2) as "Average Session Durat",
            SUM(COALESCE(e.total_exposure_count, 0)) as "Total Exposure"
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
        JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
        WHERE {where_sql} AND {search_sql}
        GROUP BY g.region_name, g.area_name, p.program_name, p.donor_name
        {sort_sql}
        LIMIT %s OFFSET %s
    """
    rows = fetch_all(sql, params + search_params + [limit, offset])
    
    return {
        "kpis": kpi_list,
        "table": rows, 
        "total_count": total_count
    }

