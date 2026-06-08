from fastapi import APIRouter, Query
from backend.services import overview_service
from backend.services import region_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

@router.get("/filters")
def get_filters(
    years: list[str] | None = Query(None),
    regions: list[str] | None = Query(None)
):
    from backend.services.query_utils import fetch_all, get_list_filter_clause
    from backend.config import DATAMART_SCHEMA_NAME
    
    # Ensure we have lists even if called manually or with None
    if years is None or not isinstance(years, list): years = []
    if regions is None or not isinstance(regions, list): regions = []
    
    # 1. Fetch Years (only those with data)
    years_query = f"""
        SELECT DISTINCT d.year_actual 
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON d.date_id = f.date_id
        WHERE d.year_actual IS NOT NULL
        ORDER BY d.year_actual DESC
    """
    years_data = [str(r["year_actual"]) for r in fetch_all(years_query)]
    
    # 2. Fetch Regions (filtered by years)
    where_clauses = []
    params = []
    if years:
        sql, p = get_list_filter_clause("d.year_actual", [int(y) for y in years])
        where_clauses.append(sql)
        params.extend(p)
    
    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
    
    regions_query = f"""
        SELECT DISTINCT g.region_name 
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON d.date_id = f.date_id
        WHERE {where_sql} AND g.region_name IS NOT NULL
        ORDER BY g.region_name
    """
    regions_data = [r["region_name"] for r in fetch_all(regions_query, params)]
    
    # 3. Fetch Programs (filtered by years and regions)
    if regions:
        sql, p = get_list_filter_clause("g.region_name", regions)
        where_clauses.append(sql)
        params.extend(p)
    
    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
    
    programs_query = f"""
        SELECT DISTINCT p.program_name 
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON p.sk_program_id = f.sk_program_id
        JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON d.date_id = f.date_id
        WHERE {where_sql} AND p.program_name IS NOT NULL
        ORDER BY p.program_name
    """
    programs_data = [r["program_name"] for r in fetch_all(programs_query, params)]
    
    # 4. Fetch Months
    months_query = f"""
        SELECT DISTINCT d.month_actual, TO_CHAR(TO_DATE(d.month_actual::text, 'MM'), 'Month') as month_name 
        FROM {DATAMART_SCHEMA_NAME}.dim_date d
        INNER JOIN {DATAMART_SCHEMA_NAME}.fact_session f ON d.date_id = f.date_id
        ORDER BY d.month_actual
    """
    months_data = [{"id": r["month_actual"], "name": r["month_name"].strip()} for r in fetch_all(months_query)]
    
    return {
        "years": years_data,
        "regions": regions_data,
        "programs": programs_data,
        "months": months_data
    }



@router.get("/data")
def get_data(
    years: list[str] | None = Query(None),
    region: list[str] | None = Query(None),
    program: list[str] | None = Query(None),
    month: list[str] | None = Query(None)
):
    kpis = overview_service.get_overview_kpis(years, region, program, month=month)
    charts = overview_service.get_overview_charts(years, region, program, month=month)

    formatted_charts = {
        "instructors_by_region": {
            "labels": [item["label"] for item in charts["instructors_by_region"]],
            "datasets": [{
                "label": "Instructors",
                "data": [item["value"] for item in charts["instructors_by_region"]],
                "backgroundColor": "#3b82f6"
            }]
        },
        "drivers_by_region": {
            "labels": [item["label"] for item in charts["drivers_by_region"]],
            "datasets": [{
                "label": "Drivers",
                "data": [item["value"] for item in charts["drivers_by_region"]],
                "backgroundColor": "#10b981"
            }]
        },
        "programs_by_region": {
            "labels": [item["label"] for item in charts["programs_by_region"]],
            "datasets": [{
                "label": "Programs",
                "data": [item["value"] for item in charts["programs_by_region"]],
                "backgroundColor": "#f59e0b"
            }]
        }
    }

    trends = overview_service.get_overview_trends(years, region, program, month=month)

    sparklines = {}
    if trends and len(trends) >= 2:
        sparklines = {
            "instructors": [trends[0].get("instructors", 0), trends[1].get("instructors", 0)],
            "drivers": [trends[0].get("drivers", 0), trends[1].get("drivers", 0)],
            "states": [trends[0].get("states", 0), trends[1].get("states", 0)],
            "programs": [trends[0].get("programs", 0), trends[1].get("programs", 0)]
        }

    return {
        "kpis": kpis,
        "charts": formatted_charts,
        "trends": trends,
        "sparklines": sparklines
    }

@router.get("/drill-down")
def get_drilldown(
    region: str = Query(...),
    years: list[str] | None = Query(None),
    program: list[str] | None = Query(None),
    month: list[str] | None = Query(None)
):
    return overview_service.get_drilldown_data(region=region, years=years, program=program, month=month)

@router.get("/export")
def export_data(
    years: list[str] | None = Query(None),
    region: list[str] | None = Query(None),
    program: list[str] | None = Query(None),
    month: list[str] | None = Query(None)
):
    from backend.services.export_utils import json_to_excel_streaming_response
    targets = overview_service.get_program_targets(years, region, program, month=month, limit=100000, offset=0)
    
    formatted_table = []
    for row in targets["table"]:
        formatted_table.append({
            "Program": row["label"],
            "Donor": row["donor"],
            "Sessions Actual": row["completed_sessions"],
            "Sessions Target": row["target_sessions"],
            "Progress %": row["progress_pct"],
            "Students Reached": row["students_reached"],
            "End Date": row["end_date"],
            "Status": row["status"]
        })
    return json_to_excel_streaming_response(formatted_table, "overview_report.xlsx")
