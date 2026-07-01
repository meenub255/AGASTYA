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
        
        return {"regions": regions, "years": years, "months": months, "quarters": [1, 2, 3, 4]}
    except Exception as e:
        logger.error(f"manpower vehicle filters error: {e}")
        return {"regions": [], "years": [], "months": [], "quarters": []}


def get_manpower_vehicle_data(region=None, years=None, month=None, quarter=None, limit=15, offset=0, dt_params=None):
    from backend.services.query_utils import build_standard_filters, calculate_ytd_kpis, get_datatables_sql
    try:
        kpi_defs = [
            {"key": "total_kms", "label": "Total KMs Travelled", "sql": "COALESCE(SUM(v.distance_travelled), 0)", "icon": "fas fa-road", "color": "linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%)"},
            {"key": "total_fuel_cost", "label": "Total Fuel Cost (₹)", "sql": "COALESCE(SUM(v.fuel_cost), 0)", "icon": "fas fa-rupee-sign", "color": "linear-gradient(135deg, #22c55e 0%, #16a34a 100%)"},
            {"key": "total_fuel_qty", "label": "Total Fuel (L)", "sql": "COALESCE(SUM(v.fuel_quantity), 0)", "icon": "fas fa-gas-pump", "color": "linear-gradient(135deg, #001f3f 0%, #001226 100%)"},
            {"key": "active_drivers", "label": "Active Drivers", "sql": "COUNT(DISTINCT v.sk_driver_id)", "icon": "fas fa-truck", "color": "linear-gradient(135deg, #dc3545 0%, #c82333 100%)"}
        ]
        
        from_clause = f"""
            {DW}.fact_vehicle_operations v
            LEFT JOIN {DW}.dim_geography g ON v.sk_geography_id = g.sk_geography_id
            LEFT JOIN {DW}.dim_date d       ON v.date_id = d.date_id
        """
        
        kpi_list, sparklines = calculate_ytd_kpis(
            kpi_defs=kpi_defs,
            from_clause=from_clause,
            years=years,
            region=region,
            month=month,
            quarter=quarter
        )
        
        where_sql, params, max_month = build_standard_filters(
            years=years,
            region=region,
            month=month,
            quarter=quarter
        )

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

        return {"kpis": kpi_list, "sparklines": sparklines, "table": table, "total_count": int(total_count)}
    except Exception as e:
        logger.error(f"manpower vehicle data error: {e}", exc_info=True)
        return {"kpis": [], "table": [], "total_count": 0}


def get_manpower_vehicle_insights(region=None, years=None, month=None, quarter=None):
    from backend.services.query_utils import build_standard_filters
    from concurrent.futures import ThreadPoolExecutor

    where_sql, params, max_month = build_standard_filters(
        years=years, region=region, month=month, quarter=quarter
    )

    SQL_EFFICIENCY = f"""
        SELECT COALESCE(g.region_name,'Unknown') AS label,
               ROUND(COALESCE(SUM(v.distance_travelled),0)::numeric,0)::int AS kms,
               ROUND(COALESCE(SUM(v.fuel_quantity),0)::numeric,1)::float AS fuel,
               ROUND(COALESCE(SUM(v.fuel_cost),0)::numeric,0)::int AS cost,
               COUNT(DISTINCT v.sk_driver_id) AS drivers,
               COUNT(CASE WHEN v.was_vehicle_used THEN 1 END) AS vehicles
        FROM {DW}.fact_vehicle_operations v
        LEFT JOIN {DW}.dim_geography g ON v.sk_geography_id = g.sk_geography_id
        LEFT JOIN {DW}.dim_date d ON v.date_id = d.date_id
        WHERE {where_sql} AND g.region_name IS NOT NULL
        GROUP BY g.region_name"""

    SQL_PROGRAM_FLEET = f"""
        SELECT COALESCE(p.program_name,'Unknown') AS label,
               COALESCE(g.region_name,'Unknown') AS region,
               ROUND(COALESCE(SUM(v.distance_travelled),0)::numeric,0)::int AS kms,
               ROUND(COALESCE(SUM(v.fuel_cost),0)::numeric,0)::int AS cost,
               COUNT(DISTINCT v.sk_driver_id) AS drivers
        FROM {DW}.fact_vehicle_operations v
        LEFT JOIN {DW}.dim_geography g ON v.sk_geography_id = g.sk_geography_id
        LEFT JOIN {DW}.dim_program p ON v.sk_program_id = p.sk_program_id
        LEFT JOIN {DW}.dim_date d ON v.date_id = d.date_id
        WHERE {where_sql} AND p.program_name IS NOT NULL
        GROUP BY p.program_name, g.region_name
        HAVING SUM(v.distance_travelled) > 0
        ORDER BY kms DESC LIMIT 15"""

    SQL_MONTHLY_FUEL = f"""
        SELECT TO_CHAR(d.full_date, 'Mon YYYY') AS label,
               ROUND(COALESCE(SUM(v.distance_travelled),0)::numeric,0)::int AS kms,
               ROUND(COALESCE(SUM(v.fuel_quantity),0)::numeric,0)::int AS fuel,
               ROUND(COALESCE(SUM(v.fuel_cost),0)::numeric,0)::int AS cost,
               MIN(d.full_date) AS sort_key
        FROM {DW}.fact_vehicle_operations v
        LEFT JOIN {DW}.dim_date d ON v.date_id = d.date_id
        LEFT JOIN {DW}.dim_geography g ON v.sk_geography_id = g.sk_geography_id
        WHERE {where_sql}
        GROUP BY TO_CHAR(d.full_date, 'Mon YYYY')
        ORDER BY sort_key"""

    SQL_KPI = f"""
        SELECT ROUND(COALESCE(SUM(v.distance_travelled),0)::numeric,0)::int AS total_kms,
               ROUND(COALESCE(SUM(v.fuel_cost),0)::numeric,0)::int AS total_cost,
               ROUND(COALESCE(SUM(v.fuel_quantity),0)::numeric,0)::int AS total_fuel,
               COUNT(DISTINCT v.sk_driver_id) AS active_drivers
        FROM {DW}.fact_vehicle_operations v
        LEFT JOIN {DW}.dim_date d ON v.date_id = d.date_id
        LEFT JOIN {DW}.dim_geography g ON v.sk_geography_id = g.sk_geography_id
        WHERE {where_sql}"""

    with ThreadPoolExecutor(max_workers=4) as ex:
        f_eff = ex.submit(fetch_all, SQL_EFFICIENCY, params)
        f_prog = ex.submit(fetch_all, SQL_PROGRAM_FLEET, params)
        f_monthly = ex.submit(fetch_all, SQL_MONTHLY_FUEL, params)
        f_kpi = ex.submit(fetch_one, SQL_KPI, params)

    kpi = f_kpi.result() or {}
    eff_rows = f_eff.result()

    region_data = []
    for r in eff_rows:
        kms = r['kms'] or 0
        fuel = r['fuel'] or 0
        cost = r['cost'] or 0
        drivers = r['drivers'] or 0
        vehicles = r['vehicles'] or 0
        eff = round(kms / fuel, 1) if fuel > 0 else 0
        cpk = round(cost / kms, 1) if kms > 0 else 0
        kpd = round(kms / drivers) if drivers > 0 else 0
        region_data.append({
            'label': r['label'], 'kms': kms, 'fuel': fuel, 'cost': cost,
            'drivers': drivers, 'vehicles': vehicles,
            'efficiency': eff, 'cost_per_km': cpk, 'kms_per_driver': kpd
        })

    return {
        'kpis': {
            'total_kms': kpi.get('total_kms', 0),
            'total_cost': kpi.get('total_cost', 0),
            'total_fuel': kpi.get('total_fuel', 0),
            'active_drivers': kpi.get('active_drivers', 0)
        },
        'charts': {
            'region_scatter': [{'label': r['label'], 'x': r['efficiency'], 'y': r['cost_per_km'], 'r': max(5, min(40, r['kms'] // 2000)), 'kms': r['kms'], 'drivers': r['drivers']} for r in region_data if r['kms'] > 0],
            'region_bubble': [{'label': r['label'], 'kms': r['kms'], 'drivers': r['drivers'], 'vehicles': r['vehicles'], 'efficiency': r['efficiency'], 'cost_per_km': r['cost_per_km'], 'kms_per_driver': r['kms_per_driver']} for r in region_data if r['kms'] > 0],
            'program_fleet': [{'label': r['label'], 'region': r['region'], 'kms': r['kms'], 'cost': r['cost'], 'drivers': r['drivers']} for r in f_prog.result()],
            'monthly_trend': [{'label': r['label'], 'kms': r['kms'], 'fuel': r['fuel'], 'cost': r['cost']} for r in f_monthly.result()]
        }
    }
