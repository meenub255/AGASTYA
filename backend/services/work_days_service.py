from backend.db import get_datamart_conn
import pandas as pd
from typing import Dict, List, Any, Optional

def get_work_days_filters(region_id: Optional[int] = None):
    conn = get_datamart_conn()
    filters = {"regions": [], "areas": [], "years": [], "months": []}
    
    try:
        # Regions
        regions_df = pd.read_sql("SELECT ID, NAME FROM MST_REGION WHERE IS_DELETED = 0 OR IS_DELETED IS NULL ORDER BY NAME", conn)
        filters["regions"] = regions_df.to_dict(orient="records")
        
        # Areas (filtered by region if provided)
        area_query = "SELECT ID, NAME, REGION_ID FROM MST_AREA WHERE (IS_DELETED = 0 OR IS_DELETED IS NULL)"
        if region_id:
            area_query += f" AND REGION_ID = {region_id}"
        area_query += " ORDER BY NAME"
        areas_df = pd.read_sql(area_query, conn)
        filters["areas"] = areas_df.to_dict(orient="records")
        
        # Fixed Years and Months for simplicity (matches other reports)
        filters["years"] = [2023, 2024, 2025, 2026]
        filters["months"] = [
            {"id": 1, "name": "January"}, {"id": 2, "name": "February"}, {"id": 3, "name": "March"},
            {"id": 4, "name": "April"}, {"id": 5, "name": "May"}, {"id": 6, "name": "June"},
            {"id": 7, "name": "July"}, {"id": 8, "name": "August"}, {"id": 9, "name": "September"},
            {"id": 10, "name": "October"}, {"id": 11, "name": "November"}, {"id": 12, "name": "December"}
        ]
    finally:
        conn.close()
    return filters

def get_work_days_data(region_id: Optional[int] = None, area_id: Optional[int] = None, 
                       year: Optional[int] = None, month: Optional[int] = None,
                       limit: int = 15, offset: int = 0, dt_params: Dict = None):
    from backend.services.query_utils import get_datatables_sql
    conn = get_datamart_conn()
    
    where_clauses = ["1=1"]
    params = []
    
    if region_id:
        where_clauses.append("reg.ID = %s")
        params.append(region_id)
    if area_id:
        where_clauses.append("ar.ID = %s")
        params.append(area_id)
    if year:
        where_clauses.append("EXTRACT(YEAR FROM log.DATE) = %s")
        params.append(year)
    if month:
        where_clauses.append("EXTRACT(MONTH FROM log.DATE) = %s")
        params.append(month)
        
    where_str = " AND ".join(where_clauses)
    
    try:
        # KPI Query (sidebar filters only)
        kpi_query = f"""
            SELECT 
                COUNT(DISTINCT log.INSTRUCTOR_ID) as total_instructors,
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
