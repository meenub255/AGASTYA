from backend.services.query_utils import fetch_all, fetch_one
from backend.config import DATAMART_SCHEMA_NAME, SOURCE_SCHEMA_NAME

def get_vehicle_report_filters(region_name=None):
    from backend.services.query_utils import get_list_filter_clause
    try:
        # 1. Available Regions
        region_query = f"SELECT DISTINCT region_name FROM {DATAMART_SCHEMA_NAME}.dim_geography WHERE region_name IS NOT NULL ORDER BY region_name"
        regions = [row["region_name"] for row in fetch_all(region_query)]
        
        # 2. Available Areas (Centers) - Linked to Region if selected
        where_sql, params = get_list_filter_clause("region_name", region_name)
        area_query = f"SELECT DISTINCT area_name FROM {DATAMART_SCHEMA_NAME}.dim_geography WHERE {where_sql} AND area_name IS NOT NULL ORDER BY area_name"
        
        areas = [row["area_name"] for row in fetch_all(area_query, params)]
        
        # 3. Years and Months from dim_date
        years = [row["year_actual"] for row in fetch_all(f"SELECT DISTINCT year_actual FROM {DATAMART_SCHEMA_NAME}.dim_date WHERE year_actual IS NOT NULL ORDER BY year_actual DESC")]
        months = [{"id": row["month_actual"], "name": row["month_name"].strip()} for row in fetch_all(f"SELECT DISTINCT month_actual, TO_CHAR(TO_DATE(month_actual::text, 'MM'), 'Month') as month_name FROM {DATAMART_SCHEMA_NAME}.dim_date ORDER BY month_actual")]
        
        return {
            "regions": regions,
            "areas": areas,
            "years": years,
            "months": months
        }
    except Exception as e:
        print(f"Error fetching vehicle filters: {e}")
        return {"regions": [], "areas": [], "years": [], "months": []}

def get_vehicle_report_data(region=None, area=None, year=None, month=None, limit=15, offset=0, dt_params=None):
    from backend.services.query_utils import parse_datatables_params, get_datatables_sql, get_list_filter_clause
    try:
        clauses = []
        params = []
        
        c, p = get_list_filter_clause("r.NAME", region)
        clauses.append(c); params.extend(p)
        
        c, p = get_list_filter_clause("a.NAME", area)
        clauses.append(c); params.extend(p)
        
        # Year/Month are from the log.date column in this service
        c, p = get_list_filter_clause("EXTRACT(YEAR FROM log.DATE)", year, cast_type="int")
        clauses.append(c); params.extend(p)
        
        c, p = get_list_filter_clause("EXTRACT(MONTH FROM log.DATE)", month, cast_type="int")
        clauses.append(c); params.extend(p)
        
        where_sql = " AND ".join(clauses)

        # 1. KPIs
        kpi_sql = f"""
            SELECT 
                SUM(COALESCE(log.closed_reading, 0) - COALESCE(log.open_reading, 0)) as total_kms,
                SUM(COALESCE(log.fuel_quantity, 0)) as total_fuel_qty,
                SUM(COALESCE(log.fuel_quantity, 0) * COALESCE(log.fuel_price, 0)) as total_fuel_cost,
                COUNT(DISTINCT log.date) as used_days
            FROM {SOURCE_SCHEMA_NAME}.txn_vehicle_log log
            JOIN {SOURCE_SCHEMA_NAME}.mst_vehicle v ON log.vehicle_id = v.id
            LEFT JOIN {SOURCE_SCHEMA_NAME}.mst_area a ON v.area_id = a.id
            LEFT JOIN {SOURCE_SCHEMA_NAME}.mst_region r ON a.region_id = r.id
            WHERE {where_sql} AND log.is_deleted = 0
        """
        kpi_res = fetch_one(kpi_sql, params)
        total_kms = float(kpi_res.get("total_kms") or 0)
        used_days = int(kpi_res.get("used_days") or 1)
        avg_km_day = total_kms / used_days if used_days > 0 else 0

        # DataTable Logic
        search_sql = "TRUE"
        search_params = []
        sort_sql = "ORDER BY log.date DESC"
        
        if dt_params:
            searchable_cols = ["v.vehicle_name", "v.vehicle_number", "a.name", "r.name", "dr.name"]
            sortable_cols = ["vehicle_name", "date", "registration_no", "center_name", "region_name", "driver_name", "initial_km", "end_km", "total_kms"]
            
            inner_search_sql, inner_search_params, inner_sort_sql = get_datatables_sql(dt_params, searchable_cols, sortable_cols)
            search_sql = inner_search_sql
            search_params = inner_search_params
            if inner_sort_sql:
                sort_sql = inner_sort_sql

        # Count for pagination
        count_sql = f"""
            SELECT COUNT(*) as count
            FROM {SOURCE_SCHEMA_NAME}.txn_vehicle_log log
            JOIN {SOURCE_SCHEMA_NAME}.mst_vehicle v ON log.vehicle_id = v.id
            LEFT JOIN {SOURCE_SCHEMA_NAME}.mst_user dr ON log.driver_id = dr.id
            LEFT JOIN {SOURCE_SCHEMA_NAME}.mst_area a ON v.area_id = a.id
            LEFT JOIN {SOURCE_SCHEMA_NAME}.mst_region r ON a.region_id = r.id
            WHERE {where_sql} AND {search_sql} AND log.is_deleted = 0
        """
        total_count = fetch_one(count_sql, params + search_params).get("count", 0)

        # 2. Granular Table
        sql = f"""
            SELECT 
                v.vehicle_name,
                log.date,
                v.vehicle_number as registration_no,
                COALESCE(a.name, 'N/A') as center_name,
                COALESCE(r.name, 'N/A') as region_name,
                dr.name as driver_name,
                log.open_reading as initial_km,
                log.closed_reading as end_km,
                (COALESCE(log.closed_reading, 0) - COALESCE(log.open_reading, 0)) as total_kms
            FROM {SOURCE_SCHEMA_NAME}.txn_vehicle_log log
            JOIN {SOURCE_SCHEMA_NAME}.mst_vehicle v ON log.vehicle_id = v.id
            LEFT JOIN {SOURCE_SCHEMA_NAME}.mst_user dr ON log.driver_id = dr.id
            LEFT JOIN {SOURCE_SCHEMA_NAME}.mst_area a ON v.area_id = a.id
            LEFT JOIN {SOURCE_SCHEMA_NAME}.mst_region r ON a.region_id = r.id
            WHERE {where_sql} AND {search_sql} AND log.is_deleted = 0
            {sort_sql}
            LIMIT %s OFFSET %s
        """
        rows = fetch_all(sql, params + search_params + [limit, offset])

        return {
            "kpis": [
                {"label": "Total KMs", "value": round(total_kms, 2), "icon": "fas fa-road", "color": "bg-info"},
                {"label": "Cumulative Avg KM/Day", "value": round(avg_km_day, 2), "icon": "fas fa-tachometer-alt", "color": "bg-success"},
                {"label": "Total Fuel Quantity", "value": round(float(kpi_res.get("total_fuel_qty") or 0), 2), "icon": "fas fa-gas-pump", "color": "bg-navy-blue"},
                {"label": "Total Fuel Cost", "value": round(float(kpi_res.get("total_fuel_cost") or 0), 2), "icon": "fas fa-rupee-sign", "color": "bg-danger"},
            ],
            "table": [{**row, "date": row["date"].strftime("%Y-%m-%d") if row["date"] else None} for row in rows],
            "total_count": total_count
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"kpis": [], "table": [], "total_count": 0, "error": str(e)}
