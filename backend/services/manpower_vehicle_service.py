import logging
from backend.services.query_utils import fetch_all, fetch_one
from backend.config import DATAMART_SCHEMA_NAME

logger = logging.getLogger(__name__)
DW = DATAMART_SCHEMA_NAME


def get_manpower_vehicle_filters():
    try:
        # INNER JOIN with fact_vehicle_operations to ensure data exists
        regions = [r["region_name"] for r in fetch_all(f"""
            SELECT DISTINCT g.region_name 
            FROM {DW}.dim_geography g
            INNER JOIN {DW}.fact_vehicle_operations v ON g.sk_geography_id = v.sk_geography_id
            WHERE g.region_name IS NOT NULL 
            ORDER BY g.region_name
        """)]
        
        years = [r["year_actual"] for r in fetch_all(f"""
            SELECT DISTINCT d.year_actual 
            FROM {DW}.dim_date d
            INNER JOIN {DW}.fact_vehicle_operations v ON d.date_id = v.date_id
            WHERE d.year_actual IS NOT NULL 
            ORDER BY d.year_actual DESC
        """)]
        
        months = [{"id": r["month_actual"], "name": r["month_name"].strip()} for r in fetch_all(f"""
            SELECT DISTINCT d.month_actual, TO_CHAR(TO_DATE(d.month_actual::text,'MM'),'Month') AS month_name 
            FROM {DW}.dim_date d
            INNER JOIN {DW}.fact_vehicle_operations v ON d.date_id = v.date_id
            ORDER BY d.month_actual
        """)]
        
        return {"regions": regions, "years": years, "months": months}
    except Exception as e:
        logger.error(f"manpower vehicle filters error: {e}")
        return {"regions": [], "years": [], "months": []}


def get_manpower_vehicle_data(region=None, year=None, month=None, limit=15, offset=0, dt_params=None):
    from backend.services.query_utils import parse_datatables_params, get_datatables_sql, get_list_filter_clause
    try:
        clauses = []
        params = []
        
        c, p = get_list_filter_clause("g.region_name", region)
        clauses.append(c); params.extend(p)
        
        c, p = get_list_filter_clause("d.year_actual", year, cast_type="int")
        clauses.append(c); params.extend(p)
        
        c, p = get_list_filter_clause("d.month_actual", month, cast_type="int")
        clauses.append(c); params.extend(p)
        
        where_sql = " AND ".join(clauses)

        # KPI Query (sidebar filters only)
        kpi_row = fetch_one(f"""
            SELECT
                COALESCE(SUM(v.distance_travelled), 0)   AS total_kms,
                COALESCE(SUM(v.fuel_cost), 0)            AS total_fuel_cost,
                COALESCE(SUM(v.fuel_quantity), 0)        AS total_fuel_qty,
                COUNT(DISTINCT v.sk_driver_id)           AS active_drivers
            FROM {DW}.fact_vehicle_operations v
            LEFT JOIN {DW}.dim_geography g ON v.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d       ON v.date_id = d.date_id
            WHERE {where_sql}
        """, params)

        kpis = [
            {"label": "Total KMs Travelled",   "value": int(kpi_row.get("total_kms", 0) or 0),        "icon": "fas fa-road",          "color": "bg-info"},
            {"label": "Total Fuel Cost (₹)",   "value": round(float(kpi_row.get("total_fuel_cost", 0) or 0), 2), "icon": "fas fa-rupee-sign",    "color": "bg-success"},
            {"label": "Total Fuel (L)",         "value": round(float(kpi_row.get("total_fuel_qty", 0) or 0), 1), "icon": "fas fa-gas-pump",      "color": "bg-navy-blue"},
            {"label": "Active Drivers",         "value": int(kpi_row.get("active_drivers", 0) or 0),    "icon": "fas fa-truck",         "color": "bg-danger"},
        ]

        # DataTable Logic
        search_sql = "TRUE"
        search_params = []
        sort_sql = "ORDER BY total_kms DESC"
        
        if dt_params:
            searchable_cols = ["COALESCE(g.region_name, 'Unknown')", "COALESCE(p.program_name, 'Unknown')"]
            sortable_cols = ["region_name", "program_name", "drivers", "total_kms", "total_fuel_l", "total_cost", "vehicles_used"]
            
            inner_search_sql, inner_search_params, inner_sort_sql = get_datatables_sql(dt_params, searchable_cols, sortable_cols)
            search_sql = inner_search_sql
            search_params = inner_search_params
            if inner_sort_sql:
                sort_sql = inner_sort_sql

        # Get total count (Filtered by sidebar AND table search)
        count_sql = f"""
            SELECT COUNT(*) FROM (
                SELECT g.region_name
                FROM {DW}.fact_vehicle_operations v
                LEFT JOIN {DW}.dim_geography g ON v.sk_geography_id = g.sk_geography_id
                LEFT JOIN {DW}.dim_program p    ON v.sk_program_id = p.sk_program_id
                LEFT JOIN {DW}.dim_date d       ON v.date_id = d.date_id
                WHERE {where_sql} AND {search_sql}
                GROUP BY g.region_name, p.program_name
            ) AS sub
        """
        total_count = fetch_one(count_sql, params + search_params).get("count", 0)

        # Get paginated data
        table = fetch_all(f"""
            SELECT
                COALESCE(g.region_name, 'Unknown')          AS region_name,
                COALESCE(p.program_name, 'Unknown')         AS program_name,
                COUNT(DISTINCT v.sk_driver_id)              AS drivers,
                COALESCE(SUM(v.distance_travelled), 0)      AS total_kms,
                ROUND(COALESCE(SUM(v.fuel_quantity), 0)::numeric, 1) AS total_fuel_l,
                ROUND(COALESCE(SUM(v.fuel_cost), 0)::numeric, 2)     AS total_cost,
                COUNT(CASE WHEN v.was_vehicle_used THEN 1 END)        AS vehicles_used
            FROM {DW}.fact_vehicle_operations v
            LEFT JOIN {DW}.dim_geography g ON v.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_program p    ON v.sk_program_id = p.sk_program_id
            LEFT JOIN {DW}.dim_date d       ON v.date_id = d.date_id
            WHERE {where_sql} AND {search_sql}
            GROUP BY g.region_name, p.program_name
            {sort_sql}
            LIMIT %s OFFSET %s
        """, params + search_params + [limit, offset])

        return {"kpis": kpis, "table": table, "total_count": int(total_count)}

        return {"kpis": kpis, "table": table, "total_count": int(total_count)}
    except Exception as e:
        logger.error(f"manpower vehicle data error: {e}", exc_info=True)
        return {"kpis": [], "table": [], "total_count": 0}
