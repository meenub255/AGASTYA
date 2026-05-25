from backend.services.query_utils import fetch_all, fetch_one
from backend.config import DATAMART_SCHEMA_NAME, SOURCE_SCHEMA_NAME

def get_vehicle_report_filters(region_name=None):
    from backend.services.query_utils import get_list_filter_clause
    try:
        # INNER JOIN with txn_vehicle_log to ensure data exists
        region_query = f"""
            SELECT DISTINCT r.name as region_name 
            FROM {SOURCE_SCHEMA_NAME}.mst_region r
            LEFT JOIN {SOURCE_SCHEMA_NAME}.mst_area a ON r.mst_region_id = a.region_id
            LEFT JOIN {SOURCE_SCHEMA_NAME}.mst_vehicle v ON a.mst_area_id = v.area_id
            LEFT JOIN {SOURCE_SCHEMA_NAME}.txn_vehicle_log log ON v.mst_vehicle_id = log.vehicle_id
            WHERE r.name IS NOT NULL AND log.is_deleted = '0' AND log.DATE != '0000-00-00'
            ORDER BY r.name
        """
        regions = [row["region_name"] for row in fetch_all(region_query)]
        
        # 2. Available Areas (Centers) - Linked to Region if selected AND have logs
        where_sql, params = get_list_filter_clause("r.name", region_name)
        area_query = f"""
            SELECT DISTINCT a.name as area_name 
            FROM {SOURCE_SCHEMA_NAME}.mst_area a
            LEFT JOIN {SOURCE_SCHEMA_NAME}.mst_region r ON r.mst_region_id = a.region_id
            LEFT JOIN {SOURCE_SCHEMA_NAME}.mst_vehicle v ON a.mst_area_id = v.area_id
            LEFT JOIN {SOURCE_SCHEMA_NAME}.txn_vehicle_log log ON v.mst_vehicle_id = log.vehicle_id
            WHERE {where_sql} AND a.name IS NOT NULL AND log.is_deleted = '0' AND log.DATE != '0000-00-00'
            ORDER BY a.name
        """
        areas = [row["area_name"] for row in fetch_all(area_query, params)]
        
        # 3. Years and Months from log dates
        years = [row["year_actual"] for row in fetch_all(f"""
            SELECT DISTINCT EXTRACT(YEAR FROM log.DATE::TIMESTAMP)::int as year_actual 
            FROM {SOURCE_SCHEMA_NAME}.txn_vehicle_log log
            WHERE log.is_deleted = '0' AND log.DATE != '0000-00-00'
            ORDER BY year_actual DESC
        """)]
        
        months = [{"id": row["month_actual"], "name": row["month_name"].strip()} for row in fetch_all(f"""
            SELECT DISTINCT EXTRACT(MONTH FROM log.DATE::TIMESTAMP)::int as month_actual, 
                   TO_CHAR(log.DATE::TIMESTAMP, 'Month') as month_name 
            FROM {SOURCE_SCHEMA_NAME}.txn_vehicle_log log
            WHERE log.is_deleted = '0' AND log.DATE != '0000-00-00'
            ORDER BY month_actual
        """)]
        
        return {
            "regions": regions,
            "areas": areas,
            "years": years,
            "months": months,
            "quarters": [1, 2, 3, 4]
        }
    except Exception as e:
        print(f"Error fetching vehicle filters: {e}")
        return {"regions": [], "areas": [], "years": [], "months": [], "quarters": []}

def get_vehicle_report_data(region=None, area=None, years=None, month=None, quarter=None, limit=15, offset=0, dt_params=None):
    from backend.services.query_utils import get_list_filter_clause, get_datatables_sql, calc_trend, get_kpi_insight, get_ytd_max_month
    from backend.config import DEFAULT_YEAR
    try:
        clauses = []
        params = []
        
        c, p = get_list_filter_clause("r.NAME", region)
        clauses.append(c); params.extend(p)
        
        c, p = get_list_filter_clause("a.NAME", area)
        clauses.append(c); params.extend(p)
        
        # Year/Month are from the log.date column in this service
        c, p = get_list_filter_clause("EXTRACT(YEAR FROM log.DATE::TIMESTAMP)", years, cast_type="int")
        clauses.append(c); params.extend(p)
        
        if month:
            c, p = get_list_filter_clause("EXTRACT(MONTH FROM log.DATE::TIMESTAMP)", month, cast_type="int", use_default_year=False)
            clauses.append(c); params.extend(p)
        
        if quarter:
            fiscal_q_expr = "CASE WHEN EXTRACT(MONTH FROM log.DATE::TIMESTAMP) IN (4,5,6) THEN 1 WHEN EXTRACT(MONTH FROM log.DATE::TIMESTAMP) IN (7,8,9) THEN 2 WHEN EXTRACT(MONTH FROM log.DATE::TIMESTAMP) IN (10,11,12) THEN 3 ELSE 4 END"
            c, p = get_list_filter_clause(fiscal_q_expr, quarter, cast_type="int")
            clauses.append(c); params.extend(p)
        
        # Apply YTD capping if no month/quarter specified
        effective_years = years
        if effective_years is None or (isinstance(effective_years, list) and len(effective_years) == 0):
            effective_years = [DEFAULT_YEAR]
        
        single_year = None
        if len(effective_years) == 1:
            try: single_year = int(effective_years[0])
            except (ValueError, TypeError): pass
        prev_year = single_year - 1 if single_year is not None else None
        
        max_month = None
        if not month and not quarter and single_year:
            max_month = get_ytd_max_month(single_year)
            clauses.append("EXTRACT(MONTH FROM log.DATE::TIMESTAMP) <= %s")
            params.append(max_month)
        
        where_sql = " AND ".join(clauses) + " AND log.DATE != '0000-00-00'"

        # 1. Current KPIs
        kpi_sql = f"""
            SELECT 
                SUM(COALESCE(log.closed_reading::numeric, 0) - COALESCE(log.open_reading::numeric, 0)) as total_kms,
                SUM(COALESCE(log.fuel_quantity::numeric, 0)) as total_fuel_qty,
                SUM(COALESCE(log.fuel_quantity::numeric, 0) * COALESCE(log.fuel_price::numeric, 0)) as total_fuel_cost,
                COUNT(DISTINCT log.date) as used_days
            FROM {SOURCE_SCHEMA_NAME}.txn_vehicle_log log
            LEFT JOIN {SOURCE_SCHEMA_NAME}.mst_vehicle v ON log.vehicle_id = v.mst_vehicle_id
            LEFT JOIN {SOURCE_SCHEMA_NAME}.mst_area a ON v.area_id = a.mst_area_id
            LEFT JOIN {SOURCE_SCHEMA_NAME}.mst_region r ON a.region_id = r.mst_region_id
            WHERE {where_sql} AND log.is_deleted = '0'
        """
        kpi_res = fetch_one(kpi_sql, params)
        total_kms = float(kpi_res.get("total_kms") or 0)
        used_days = int(kpi_res.get("used_days") or 1)
        avg_km_day = total_kms / used_days if used_days > 0 else 0
        
        c_kms = round(total_kms, 2)
        c_avg = round(avg_km_day, 2)
        c_fuel = round(float(kpi_res.get("total_fuel_qty") or 0), 2)
        c_cost = round(float(kpi_res.get("total_fuel_cost") or 0), 2)
        
        # Previous period KPIs
        prev_clauses = []
        prev_params_list = []
        c2, p2 = get_list_filter_clause("r.NAME", region)
        prev_clauses.append(c2); prev_params_list.extend(p2)
        c2, p2 = get_list_filter_clause("a.NAME", area)
        prev_clauses.append(c2); prev_params_list.extend(p2)
        
        prev_year_vals = [int(y) - 1 for y in effective_years]
        c2, p2 = get_list_filter_clause("EXTRACT(YEAR FROM log.DATE::TIMESTAMP)", prev_year_vals, cast_type="int")
        prev_clauses.append(c2); prev_params_list.extend(p2)
        
        if month:
            c2, p2 = get_list_filter_clause("EXTRACT(MONTH FROM log.DATE::TIMESTAMP)", month, cast_type="int", use_default_year=False)
            prev_clauses.append(c2); prev_params_list.extend(p2)
        if quarter:
            c2, p2 = get_list_filter_clause(fiscal_q_expr, quarter, cast_type="int")
            prev_clauses.append(c2); prev_params_list.extend(p2)
        if not month and not quarter and prev_year:
            prev_max = get_ytd_max_month(prev_year)
            prev_clauses.append("EXTRACT(MONTH FROM log.DATE::TIMESTAMP) <= %s")
            prev_params_list.append(prev_max)
        
        prev_where = " AND ".join(prev_clauses) + " AND log.DATE != '0000-00-00'"
        prev_res = fetch_one(f"""
            SELECT 
                SUM(COALESCE(log.closed_reading::numeric, 0) - COALESCE(log.open_reading::numeric, 0)) as total_kms,
                SUM(COALESCE(log.fuel_quantity::numeric, 0)) as total_fuel_qty,
                SUM(COALESCE(log.fuel_quantity::numeric, 0) * COALESCE(log.fuel_price::numeric, 0)) as total_fuel_cost,
                COUNT(DISTINCT log.date) as used_days
            FROM {SOURCE_SCHEMA_NAME}.txn_vehicle_log log
            LEFT JOIN {SOURCE_SCHEMA_NAME}.mst_vehicle v ON log.vehicle_id = v.mst_vehicle_id
            LEFT JOIN {SOURCE_SCHEMA_NAME}.mst_area a ON v.area_id = a.mst_area_id
            LEFT JOIN {SOURCE_SCHEMA_NAME}.mst_region r ON a.region_id = r.mst_region_id
            WHERE {prev_where} AND log.is_deleted = '0'
        """, prev_params_list)
        
        p_kms = round(float(prev_res.get("total_kms") or 0), 2)
        p_days = int(prev_res.get("used_days") or 1)
        p_avg = round(p_kms / p_days, 2) if p_days > 0 else 0
        p_fuel = round(float(prev_res.get("total_fuel_qty") or 0), 2)
        p_cost = round(float(prev_res.get("total_fuel_cost") or 0), 2)
        
        kpis_data = [
            {"label": "Total KMs", "curr": c_kms, "prev": p_kms, "icon": "fas fa-road", "color": "bg-info"},
            {"label": "Cumulative Avg KM/Day", "curr": c_avg, "prev": p_avg, "icon": "fas fa-tachometer-alt", "color": "bg-success"},
            {"label": "Total Fuel Quantity", "curr": c_fuel, "prev": p_fuel, "icon": "fas fa-gas-pump", "color": "bg-navy-blue"},
            {"label": "Total Fuel Cost", "curr": c_cost, "prev": p_cost, "icon": "fas fa-rupee-sign", "color": "bg-danger"},
        ]
        
        kpi_list = []
        sparklines = {}
        for item in kpis_data:
            trend = calc_trend(item["curr"], item["prev"])
            insights = get_kpi_insight(item["label"], float(item["curr"]), float(item["prev"]), single_year, prev_year, max_month, month, quarter)
            kpi_list.append({
                "label": item["label"], "value": item["curr"], "icon": item["icon"], "color": item["color"],
                "trend": trend, "insights": insights, "trends": [item["prev"], item["curr"]]
            })
            sparklines[item["label"].lower().replace(" ", "_")] = [item["prev"], item["curr"]]

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
            LEFT JOIN {SOURCE_SCHEMA_NAME}.mst_vehicle v ON log.vehicle_id = v.mst_vehicle_id
            LEFT JOIN {SOURCE_SCHEMA_NAME}.mst_user dr ON log.driver_id = dr.mst_user_id
            LEFT JOIN {SOURCE_SCHEMA_NAME}.mst_area a ON v.area_id = a.mst_area_id
            LEFT JOIN {SOURCE_SCHEMA_NAME}.mst_region r ON a.region_id = r.mst_region_id
            WHERE {where_sql} AND {search_sql} AND log.is_deleted = '0'
        """
        total_count = fetch_one(count_sql, params + search_params).get("count", 0)

        # 2. Granular Table
        sql = f"""
            SELECT 
                v.vehicle_name,
                log.date::TIMESTAMP as date,
                v.vehicle_number as registration_no,
                COALESCE(a.name, 'N/A') as center_name,
                COALESCE(r.name, 'N/A') as region_name,
                dr.name as driver_name,
                log.open_reading as initial_km,
                log.closed_reading as end_km,
                (COALESCE(log.closed_reading::numeric, 0) - COALESCE(log.open_reading::numeric, 0)) as total_kms
            FROM {SOURCE_SCHEMA_NAME}.txn_vehicle_log log
            LEFT JOIN {SOURCE_SCHEMA_NAME}.mst_vehicle v ON log.vehicle_id = v.mst_vehicle_id
            LEFT JOIN {SOURCE_SCHEMA_NAME}.mst_user dr ON log.driver_id = dr.mst_user_id
            LEFT JOIN {SOURCE_SCHEMA_NAME}.mst_area a ON v.area_id = a.mst_area_id
            LEFT JOIN {SOURCE_SCHEMA_NAME}.mst_region r ON a.region_id = r.mst_region_id
            WHERE {where_sql} AND {search_sql} AND log.is_deleted = '0'
            {sort_sql}
            LIMIT %s OFFSET %s
        """
        rows = fetch_all(sql, params + search_params + [limit, offset])

        return {
            "kpis": kpi_list,
            "sparklines": sparklines,
            "table": [{**row, "date": row["date"].strftime("%Y-%m-%d") if row["date"] else None} for row in rows],
            "total_count": total_count
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"kpis": [], "sparklines": {}, "table": [], "total_count": 0, "error": str(e)}
