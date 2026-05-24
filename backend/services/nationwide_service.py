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
        months = [{"id": r["month_actual"], "name": r["month_name"].strip()} for r in fetch_all(f"""
            SELECT DISTINCT d.month_actual, TO_CHAR(TO_DATE(d.month_actual::text,'MM'),'Month') AS month_name 
            FROM {DW}.dim_date d
            INNER JOIN {DW}.fact_session f ON d.date_id = f.date_id
            ORDER BY d.month_actual
        """)]
        return {"regions": regions, "years": years, "months": months, "quarters": [1, 2, 3, 4]}
    except Exception as e:
        logger.error(f"nationwide filters error: {e}")
        return {"regions": [], "years": [], "months": [], "quarters": []}


def get_nationwide_data(years=None, region=None, month=None, quarter=None, limit=15, offset=0, dt_params=None):
    from backend.services.query_utils import build_standard_filters, calc_trend, get_kpi_insight, get_datatables_sql, get_list_filter_clause
    from backend.config import DEFAULT_YEAR
    try:
        where_sql, params, max_month = build_standard_filters(
            years=years,
            region=region,
            month=month,
            quarter=quarter,
            date_alias="d"
        )
        
        effective_years = years
        if effective_years is None or (isinstance(effective_years, list) and len(effective_years) == 0):
            effective_years = [DEFAULT_YEAR]
            
        single_year = None
        if len(effective_years) == 1:
            try:
                single_year = int(effective_years[0])
            except (ValueError, TypeError):
                pass
        prev_year = single_year - 1 if single_year is not None else None

        # Current KPIs
        curr_kpi = fetch_one(f"""
            SELECT
                COUNT(DISTINCT f.sk_user_id)           AS total_instructors,
                COUNT(DISTINCT g.nk_region_id)         AS total_states,
                COUNT(DISTINCT f.sk_program_id)        AS total_programs
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_date d        ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_geography g   ON f.sk_geography_id = g.sk_geography_id
            WHERE {where_sql}
        """, params)

        # Separate query for drivers
        curr_driver = fetch_one(f"""
            SELECT COUNT(DISTINCT v.sk_driver_id) AS total_drivers
            FROM {DW}.fact_vehicle_operations v
            LEFT JOIN {DW}.dim_date d       ON v.date_id = d.date_id
            LEFT JOIN {DW}.dim_geography g  ON v.sk_geography_id = g.sk_geography_id
            WHERE {where_sql}
        """, params)

        # Previous Year KPIs (for YoY comparison)
        prev_year_vals = [int(y) - 1 for y in effective_years]
        prev_where_sql, prev_params, _ = build_standard_filters(
            years=prev_year_vals,
            region=region,
            month=month,
            quarter=quarter,
            date_alias="d"
        )

        prev_kpi = fetch_one(f"""
            SELECT
                COUNT(DISTINCT f.sk_user_id)           AS total_instructors,
                COUNT(DISTINCT g.nk_region_id)         AS total_states,
                COUNT(DISTINCT f.sk_program_id)        AS total_programs
            FROM {DW}.fact_session f
            LEFT JOIN {DW}.dim_date d        ON f.date_id = d.date_id
            LEFT JOIN {DW}.dim_geography g   ON f.sk_geography_id = g.sk_geography_id
            WHERE {prev_where_sql}
        """, prev_params)

        prev_driver = fetch_one(f"""
            SELECT COUNT(DISTINCT v.sk_driver_id) AS total_drivers
            FROM {DW}.fact_vehicle_operations v
            LEFT JOIN {DW}.dim_date d       ON v.date_id = d.date_id
            LEFT JOIN {DW}.dim_geography g  ON v.sk_geography_id = g.sk_geography_id
            WHERE {prev_where_sql}
        """, prev_params)

        kpis_data = [
            {"key": "total_instructors", "label": "Total Instructors", "curr": curr_kpi.get("total_instructors") or 0, "prev": prev_kpi.get("total_instructors") or 0, "icon": "fas fa-users", "color": "bg-info"},
            {"key": "total_drivers", "label": "Total Drivers", "curr": curr_driver.get("total_drivers") or 0, "prev": prev_driver.get("total_drivers") or 0, "icon": "fas fa-truck", "color": "bg-success"},
            {"key": "total_states", "label": "States Reached", "curr": curr_kpi.get("total_states") or 0, "prev": prev_kpi.get("total_states") or 0, "icon": "fas fa-map-marker-alt", "color": "bg-navy-blue"},
            {"key": "total_programs", "label": "Total Programs", "curr": curr_kpi.get("total_programs") or 0, "prev": prev_kpi.get("total_programs") or 0, "icon": "fas fa-project-diagram", "color": "bg-danger"},
        ]

        kpis = []
        sparklines = {}
        for item in kpis_data:
            curr_val = int(item["curr"])
            prev_val = int(item["prev"])
            trend = calc_trend(curr_val, prev_val)
            insights = get_kpi_insight(item["label"], curr_val, prev_val, single_year, prev_year, max_month, month, quarter)
            
            kpis.append({
                "label": item["label"],
                "value": curr_val,
                "icon": item["icon"],
                "color": item["color"],
                "trend": trend,
                "insights": insights,
                "trends": [prev_val, curr_val]
            })
            
            sparkline_key = item["key"].replace("total_", "")
            sparklines[sparkline_key] = [prev_val, curr_val]

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
            sortable_cols = ["region_name", "sessions", "schools_visited", "students_reached", "instructors", "drivers", "programs"]
            
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
            "sparklines": sparklines,
            "charts": {
                "sessions_trend_monthly": [{"label": r["label"], "value": float(r["value"])} for r in sessions_trend_monthly],
                "students_by_region":     [{"label": r["label"], "value": float(r["value"])} for r in students_by_region],
            },
            "table": table,
            "total_count": int(total_count),
        }
    except Exception as e:
        logger.error(f"nationwide data error: {e}", exc_info=True)
        return {"kpis": [], "sparklines": {}, "charts": {}, "table": [], "total_count": 0}
