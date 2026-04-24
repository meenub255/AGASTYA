from backend.db import get_datamart_conn
import pandas as pd
from typing import Dict, List, Any, Optional
from backend.config import DATAMART_SCHEMA_NAME

def fetch_all(query, params=None):
    conn = get_datamart_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(query, params or [])
        columns = [desc[0].lower() for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        conn.close()

def get_work_days_filters(region_name: str | list[str] | None = None):
    from backend.services.query_utils import get_list_filter_clause
    
    region_query = f"SELECT DISTINCT region_name FROM {DATAMART_SCHEMA_NAME}.dim_geography WHERE region_name IS NOT NULL ORDER BY region_name"
    regions = [row["region_name"] for row in fetch_all(region_query)]
    
    where_sql, params = get_list_filter_clause("region_name", region_name)
    area_query = f"SELECT DISTINCT area_name FROM {DATAMART_SCHEMA_NAME}.dim_geography WHERE area_name IS NOT NULL AND {where_sql} ORDER BY area_name"
    areas = [row["area_name"] for row in fetch_all(area_query, params)]
    
    year_query = f"SELECT DISTINCT year_actual FROM {DATAMART_SCHEMA_NAME}.dim_date ORDER BY year_actual DESC"
    years = [row["year_actual"] for row in fetch_all(year_query)]
    
    month_query = f"SELECT DISTINCT month_actual, TO_CHAR(TO_DATE(month_actual::text, 'MM'), 'Month') as month_name FROM {DATAMART_SCHEMA_NAME}.dim_date ORDER BY month_actual"
    months = [{"id": row["month_actual"], "name": row["month_name"].strip()} for row in fetch_all(month_query)]
    
    return {"regions": regions, "areas": areas, "years": years, "months": months}

def get_work_days_data(region=None, area=None, year=None, month=None, limit=15, offset=0, dt_params=None):
    from backend.services.query_utils import get_list_filter_clause, get_datatables_sql
    conn = get_datamart_conn()
    
    clauses = []
    params = []
    
    c, p = get_list_filter_clause("g.region_name", region)
    clauses.append(c); params.extend(p)
    
    c, p = get_list_filter_clause("g.area_name", area)
    clauses.append(c); params.extend(p)
    
    c, p = get_list_filter_clause("d.year_actual", year, cast_type="int")
    clauses.append(c); params.extend(p)
    
    c, p = get_list_filter_clause("d.month_actual", month, cast_type="int")
    clauses.append(c); params.extend(p)
    
    where_sql = " AND ".join(clauses)
    
    try:
        kpi_query = f"""
            SELECT 
                COUNT(DISTINCT CONCAT(log.INSTRUCTOR_ID, '_', log.DATE)) as total_working_days,
                COUNT(DISTINCT ar.ID) as active_centers
            FROM TXN_SESSION log
            JOIN CONF_PROGRAM_SCHOOL_MAPPING psm ON log.PROGRAM_SCHOOL_MAPPED_ID = psm.ID
            JOIN MST_SCHOOL sch ON psm.SCHOOL_ID = sch.ID
            JOIN MST_AREA ar ON sch.AREA_ID = ar.ID
            JOIN MST_REGION reg ON ar.REGION_ID = reg.ID
            WHERE {where_str}
        """
        kpi_df = pd.read_sql(kpi_query, conn, params=params)
        kpis = kpi_df.iloc[0].to_dict()
        
        instructors = kpis.get('total_instructors', 0)
        working_days = kpis.get('total_working_days', 0)
        avg_days = round(working_days / instructors, 2) if instructors > 0 else 0
        
        kpi_list = [
            {"label": "Total Instructors", "value": instructors, "icon": "fas fa-users", "color": "bg-info"},
            {"label": "Total Working Days", "value": working_days, "icon": "fas fa-calendar-check", "color": "bg-success"},
            {"label": "Avg Days/Instructor", "value": avg_days, "icon": "fas fa-chart-line", "color": "bg-navy-blue"},
            {"label": "Active Centers", "value": kpis.get('active_centers', 0), "icon": "fas fa-map-marker-alt", "color": "bg-danger"}
        ]

        # DataTable Logic
        search_sql = "1=1"
        search_params = []
        sort_sql = "ORDER BY total_days DESC, instructor_name ASC"
        
        if dt_params:
            searchable_cols = ["inst.NAME", "reg.NAME", "ar.NAME"]
            sortable_cols = ["instructor_name", "region_area", "total_days"]
            
            inner_search_sql, inner_search_params, inner_sort_sql = get_datatables_sql(dt_params, searchable_cols, sortable_cols)
            search_sql = inner_search_sql
            search_params = inner_search_params
            if inner_sort_sql:
                sort_sql = inner_sort_sql

        # Count total rows for pagination
        count_query = f"""
            SELECT COUNT(*) FROM (
                SELECT inst.ID
                FROM TXN_SESSION log
                JOIN MST_USER inst ON log.INSTRUCTOR_ID = inst.ID
                JOIN CONF_PROGRAM_SCHOOL_MAPPING psm ON log.PROGRAM_SCHOOL_MAPPED_ID = psm.ID
                JOIN MST_SCHOOL sch ON psm.SCHOOL_ID = sch.ID
                JOIN MST_AREA ar ON sch.AREA_ID = ar.ID
                JOIN MST_REGION reg ON ar.REGION_ID = reg.ID
                WHERE {where_str} AND {search_sql}
                GROUP BY inst.ID, reg.NAME, ar.NAME
            ) as sub
        """
        total_rows = pd.read_sql(count_query, conn, params=params + search_params).iloc[0, 0]

        # Table Query
        table_query = f"""
            SELECT 
                inst.NAME as instructor_name,
                CONCAT(reg.NAME, ' / ', ar.NAME) as region_area,
                COUNT(DISTINCT log.DATE) as total_days,
                STRING_AGG(DISTINCT TO_CHAR(log.DATE, 'DD'), ', ' ORDER BY TO_CHAR(log.DATE, 'DD')) as dates_active
            FROM TXN_SESSION log
            JOIN MST_USER inst ON log.INSTRUCTOR_ID = inst.ID
            JOIN CONF_PROGRAM_SCHOOL_MAPPING psm ON log.PROGRAM_SCHOOL_MAPPED_ID = psm.ID
            JOIN MST_SCHOOL sch ON psm.SCHOOL_ID = sch.ID
            JOIN MST_AREA ar ON sch.AREA_ID = ar.ID
            JOIN MST_REGION reg ON ar.REGION_ID = reg.ID
            WHERE {where_str} AND {search_sql}
            GROUP BY inst.NAME, reg.NAME, ar.NAME
            {sort_sql}
            LIMIT %s OFFSET %s
        """
        table_params = params + search_params + [limit, offset]
        table_df = pd.read_sql(table_query, conn, params=table_params)

        return {
            "kpis": kpi_list,
            "table": table_df.to_dict(orient="records"),
            "total_count": int(total_rows)
        }
    finally:
        conn.close()
