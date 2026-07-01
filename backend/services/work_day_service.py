from backend.services.query_utils import fetch_all, fetch_one
from backend.config import DATAMART_SCHEMA_NAME


def get_work_day_filters():
    # INNER JOIN with fact_session to show only locations with data
    locations_query = f"""
        SELECT DISTINCT g.region_name, g.area_name AS area 
        FROM {DATAMART_SCHEMA_NAME}.dim_geography g
        INNER JOIN {DATAMART_SCHEMA_NAME}.fact_session f ON g.sk_geography_id = f.sk_geography_id
        WHERE g.region_name IS NOT NULL 
        ORDER BY g.region_name, g.area_name
    """
    locations = fetch_all(locations_query)
    
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
        "regions": sorted(list(set(row["region_name"] for row in locations))),
        "areas": sorted(list(set(row["area"] for row in locations if row.get("area")))),
        "years": years,
        "months": months,
        "quarters": [1, 2, 3, 4]
    }


def get_work_day_data(region=None, area=None, years=None, month=None, quarter=None, limit=15, offset=0, dt_params=None):
    from backend.services.query_utils import build_standard_filters, calc_trend, get_kpi_insight, get_datatables_sql
    from backend.config import DEFAULT_YEAR
    
    where_sql, params, max_month = build_standard_filters(
        years=years,
        region=region,
        area=area,
        month=month,
        quarter=quarter
    )
    
    effective_years = years
    if effective_years is None or (isinstance(effective_years, list) and len(effective_years) == 0):
        effective_years = [DEFAULT_YEAR]
    single_year = None
    if len(effective_years) == 1:
        try: single_year = int(str(effective_years[0])[:4])
        except (ValueError, TypeError): pass
    prev_year = single_year - 1 if single_year is not None else None
    
    # Current period KPIs
    kpi_sql = f"""
        SELECT 
            COUNT(DISTINCT f.sk_user_id) as total_instructors,
            COUNT(DISTINCT CONCAT(f.sk_user_id, '_', f.date_id)) as total_working_days,
            COUNT(DISTINCT f.sk_geography_id) as active_centers
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        WHERE {where_sql}
    """
    curr = fetch_one(kpi_sql, params)
    
    # Previous period KPIs
    prev_year_vals = [int(y) - 1 for y in effective_years]
    prev_where_sql, prev_params, _ = build_standard_filters(
        years=prev_year_vals, region=region, area=area, month=month, quarter=quarter
    )
    prev = fetch_one(f"""
        SELECT 
            COUNT(DISTINCT f.sk_user_id) as total_instructors,
            COUNT(DISTINCT CONCAT(f.sk_user_id, '_', f.date_id)) as total_working_days,
            COUNT(DISTINCT f.sk_geography_id) as active_centers
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        WHERE {prev_where_sql}
    """, prev_params)
    
    c_inst = int(curr.get('total_instructors', 0) or 0)
    p_inst = int(prev.get('total_instructors', 0) or 0)
    c_days = int(curr.get('total_working_days', 0) or 0)
    p_days = int(prev.get('total_working_days', 0) or 0)
    c_avg = round(c_days / c_inst, 2) if c_inst > 0 else 0
    p_avg = round(p_days / p_inst, 2) if p_inst > 0 else 0
    c_centers = int(curr.get('active_centers', 0) or 0)
    p_centers = int(prev.get('active_centers', 0) or 0)
    
    kpis_data = [
        {"label": "Total Instructors", "curr": c_inst, "prev": p_inst, "icon": "fas fa-users", "color": "bg-info"},
        {"label": "Total Working Days", "curr": c_days, "prev": p_days, "icon": "fas fa-calendar-check", "color": "bg-success"},
        {"label": "Avg Days/Instructor", "curr": c_avg, "prev": p_avg, "icon": "fas fa-chart-line", "color": "bg-navy-blue"},
        {"label": "Active Centers", "curr": c_centers, "prev": p_centers, "icon": "fas fa-map-marker-alt", "color": "bg-danger"}
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

    # 2. DataTable Logic
    search_sql = "TRUE"
    search_params = []
    sort_sql = "ORDER BY days_worked DESC, instructor_name ASC"
    
    if dt_params:
        searchable_cols = ["u.user_name", "g.region_name", "g.area_name"]
        sortable_cols = ["instructor_name", "region", "area", "days_worked"]
        
        inner_search_sql, inner_search_params, inner_sort_sql = get_datatables_sql(dt_params, searchable_cols, sortable_cols)
        search_sql = inner_search_sql
        search_params = inner_search_params
        if inner_sort_sql:
            sort_sql = inner_sort_sql

    # Get total count (Filtered by sidebar AND table search)
    count_sql = f"""
        SELECT COUNT(*) FROM (
            SELECT u.user_name
            FROM {DATAMART_SCHEMA_NAME}.fact_session f
            JOIN {DATAMART_SCHEMA_NAME}.dim_user u ON f.sk_user_id = u.sk_user_id
            JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
            JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            WHERE {where_sql} AND {search_sql}
            GROUP BY u.user_name, g.region_name, g.area_name
        ) as sub
    """
    total_count_row = fetch_one(count_sql, params + search_params)
    total_count = total_count_row.get("count", 0) if total_count_row else 0

    # Get paginated data
    sql = f"""
        SELECT 
            u.user_name as instructor_name,
            g.region_name as region,
            COALESCE(g.area_name, 'N/A') as area,
            COUNT(DISTINCT d.full_date) as days_worked,
            STRING_AGG(DISTINCT TO_CHAR(d.full_date, 'DD'), ', ' ORDER BY TO_CHAR(d.full_date, 'DD')) as dates_active
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        JOIN {DATAMART_SCHEMA_NAME}.dim_user u ON f.sk_user_id = u.sk_user_id
        JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        WHERE {where_sql} AND {search_sql}
        GROUP BY u.user_name, g.region_name, g.area_name
        {sort_sql}
        LIMIT %s OFFSET %s
    """
    rows = fetch_all(sql, params + search_params + [limit, offset])
    
    return {
        "kpis": kpi_list,
        "sparklines": sparklines,
        "table": rows, 
        "total_count": total_count
    }


def get_work_day_insights(region=None, area=None, years=None, month=None, quarter=None):
    from backend.services.query_utils import build_standard_filters
    from backend.config import DEFAULT_YEAR
    from concurrent.futures import ThreadPoolExecutor

    where_sql, params, max_month = build_standard_filters(
        years=years, region=region, area=area, month=month, quarter=quarter
    )

    DW = DATAMART_SCHEMA_NAME

    SQL_REGION_DIST = f"""
        SELECT COALESCE(g.region_name,'Unknown') AS label,
               COUNT(DISTINCT f.sk_user_id) AS value
        FROM {DW}.fact_session f
        JOIN {DW}.dim_date d ON f.date_id = d.date_id
        JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        WHERE {where_sql} AND g.region_name IS NOT NULL
        GROUP BY g.region_name ORDER BY value DESC"""

    SQL_TOP_IGNATORS = f"""
        SELECT u.user_name AS label,
               COUNT(DISTINCT d.full_date) AS value
        FROM {DW}.fact_session f
        JOIN {DW}.dim_user u ON f.sk_user_id = u.sk_user_id
        JOIN {DW}.dim_date d ON f.date_id = d.date_id
        JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        WHERE {where_sql}
        GROUP BY u.user_name ORDER BY value DESC LIMIT 10"""

    SQL_MONTHLY_TREND = f"""
        SELECT TO_CHAR(d.full_date, 'Mon YYYY') AS label,
               COUNT(DISTINCT f.sk_user_id) AS active_ignators,
               COUNT(DISTINCT CONCAT(f.sk_user_id,'_',f.date_id)) AS working_days,
               MIN(d.full_date) AS sort_key
        FROM {DW}.fact_session f
        JOIN {DW}.dim_date d ON f.date_id = d.date_id
        JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        WHERE {where_sql}
        GROUP BY TO_CHAR(d.full_date, 'Mon YYYY')
        ORDER BY sort_key"""

    SQL_AREA_DIST = f"""
        SELECT COALESCE(g.area_name,'Unknown') AS label,
               COUNT(DISTINCT f.sk_user_id) AS value
        FROM {DW}.fact_session f
        JOIN {DW}.dim_date d ON f.date_id = d.date_id
        JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        WHERE {where_sql} AND g.area_name IS NOT NULL
        GROUP BY g.area_name ORDER BY value DESC LIMIT 10"""

    SQL_DAYS_DISTRIBUTION = f"""
        WITH ignator_days AS (
            SELECT u.user_name, COUNT(DISTINCT d.full_date) AS days
            FROM {DW}.fact_session f
            JOIN {DW}.dim_user u ON f.sk_user_id = u.sk_user_id
            JOIN {DW}.dim_date d ON f.date_id = d.date_id
            JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            WHERE {where_sql}
            GROUP BY u.user_name
        )
        SELECT
            CASE
                WHEN days <= 5 THEN '1-5 days'
                WHEN days <= 10 THEN '6-10 days'
                WHEN days <= 15 THEN '11-15 days'
                WHEN days <= 20 THEN '16-20 days'
                WHEN days <= 25 THEN '21-25 days'
                ELSE '26-31 days'
            END AS label,
            COUNT(*) AS value
        FROM ignator_days
        GROUP BY label
        ORDER BY MIN(days)"""

    SQL_UNDERUTILIZED = f"""
        WITH ignator_days AS (
            SELECT u.user_name AS ignator,
                   COALESCE(g.region_name,'Unknown') AS region,
                   COALESCE(g.area_name,'N/A') AS area,
                   COUNT(DISTINCT d.full_date) AS days
            FROM {DW}.fact_session f
            JOIN {DW}.dim_user u ON f.sk_user_id = u.sk_user_id
            JOIN {DW}.dim_date d ON f.date_id = d.date_id
            JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            WHERE {where_sql}
            GROUP BY u.user_name, g.region_name, g.area_name
        )
        SELECT ignator AS label, days AS value,
               region AS extra1, area AS extra2
        FROM ignator_days
        WHERE days <= 5
        ORDER BY days ASC LIMIT 15"""

    SQL_REGION_EFFICIENCY = f"""
        WITH region_stats AS (
            SELECT g.region_name,
                   COUNT(DISTINCT f.sk_user_id) AS ignators,
                   COUNT(DISTINCT d.full_date) AS total_sessions,
                   COUNT(DISTINCT CONCAT(f.sk_user_id,'_',f.date_id)) AS ignator_days
            FROM {DW}.fact_session f
            JOIN {DW}.dim_date d ON f.date_id = d.date_id
            JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
            WHERE {where_sql} AND g.region_name IS NOT NULL
            GROUP BY g.region_name
        )
        SELECT region_name AS label,
               ignators AS value,
               total_sessions AS extra1,
               ignator_days AS extra2
        FROM region_stats
        WHERE ignators > 0
        ORDER BY ignators DESC"""

    SQL_KPI = f"""
        SELECT COUNT(DISTINCT f.sk_user_id) AS total_ignators,
               COUNT(DISTINCT CONCAT(f.sk_user_id,'_',f.date_id)) AS total_working_days,
               COUNT(DISTINCT f.sk_geography_id) AS active_centers
        FROM {DW}.fact_session f
        JOIN {DW}.dim_date d ON f.date_id = d.date_id
        JOIN {DW}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        WHERE {where_sql}"""

    with ThreadPoolExecutor(max_workers=8) as ex:
        f_region   = ex.submit(fetch_all,  SQL_REGION_DIST,  params)
        f_top      = ex.submit(fetch_all,  SQL_TOP_IGNATORS, params)
        f_area     = ex.submit(fetch_all,  SQL_AREA_DIST,    params)
        f_dist     = ex.submit(fetch_all,  SQL_DAYS_DISTRIBUTION, params)
        f_under    = ex.submit(fetch_all,  SQL_UNDERUTILIZED, params)
        f_eff      = ex.submit(fetch_all,  SQL_REGION_EFFICIENCY, params)
        f_kpi      = ex.submit(fetch_one,  SQL_KPI,          params)

    kpi = f_kpi.result() or {}
    total_ignators   = int(kpi.get("total_ignators", 0) or 0)
    total_work_days  = int(kpi.get("total_working_days", 0) or 0)
    active_centers   = int(kpi.get("active_centers", 0) or 0)
    avg_days = round(total_work_days / total_ignators, 1) if total_ignators > 0 else 0

    return {
        "kpis": {
            "total_ignators": total_ignators,
            "total_working_days": total_work_days,
            "active_centers": active_centers,
            "avg_days_per_ignator": avg_days
        },
        "charts": {
            "region_distribution": [{"label": r["label"], "value": int(r["value"])} for r in f_region.result()],
            "top_ignators": [{"label": r["label"], "value": int(r["value"])} for r in f_top.result()],
            "area_distribution": [{"label": r["label"], "value": int(r["value"])} for r in f_area.result()],
            "days_distribution": [{"label": r["label"], "value": int(r["value"])} for r in f_dist.result()],
            "underutilized": [{"label": r["label"], "value": int(r["value"]), "region": r.get("extra1",""), "area": r.get("extra2","")} for r in f_under.result()],
            "region_efficiency": [{"label": r["label"], "ignators": int(r["value"]), "sessions": int(r["extra1"] or 0), "total_days": int(r["extra2"] or 0)} for r in f_eff.result()]
        }
    }
