from fastapi import APIRouter, Query
from backend.services import overview_service
from backend.services import region_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

@router.get("/filters")
def get_filters(region_name: list[str] | None = Query(None)):
    from backend.services.query_utils import fetch_all, get_list_filter_clause
    from backend.config import DATAMART_SCHEMA_NAME
    
    # 1. Fetch Regions via service
    regions = region_service.get_region_options()
    
    # 2. Fetch Programs (Conditional or All)
    if region_name:
        where_sql, params = get_list_filter_clause("g.region_name", region_name)
        # Fetch only programs with data for these regions
        prog_query = f"""
            SELECT DISTINCT p.program_name 
            FROM {DATAMART_SCHEMA_NAME}.fact_session f
            JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON g.sk_geography_id = f.sk_geography_id
            JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON p.sk_program_id = f.sk_program_id
            WHERE {where_sql}
            ORDER BY p.program_name
        """
        prog_rows = fetch_all(prog_query, params)
    else:
        # If no region, we return empty to signify it's inactive per user request
        prog_rows = []
    
    programs = [r["program_name"] for r in prog_rows if r.get("program_name")]
    
    years = [row["year"] for row in fetch_all(f"SELECT DISTINCT year_actual AS year FROM {DATAMART_SCHEMA_NAME}.dim_date WHERE year_actual IS NOT NULL ORDER BY year_actual DESC")]

    return {
        "regions": regions,
        "programs": programs,
        "years": years
    }



@router.get("/data")
def get_data(
    years: list[str] | None = Query(None),
    region: list[str] | None = Query(None),
    program: list[str] | None = Query(None)
):
    kpis = overview_service.get_overview_kpis(years, region, program)
    charts = overview_service.get_overview_charts(years, region, program)

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
            "labels": ["N/A"],
            "datasets": [{
                "label": "Drivers",
                "data": [0],
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

    return {
        "kpis": kpis,
        "charts": formatted_charts
    }

@router.get("/drill-down")
def get_drilldown(
    region: str = Query(...),
    years: list[str] | None = Query(None),
    program: list[str] | None = Query(None),
):
    return overview_service.get_drilldown_data(region=region, year=years, program=program)

@router.get("/export")
def export_data(
    years: list[str] | None = Query(None),
    region: list[str] | None = Query(None),
    program: list[str] | None = Query(None)
):
    from backend.services.export_utils import json_to_excel_streaming_response
    targets = overview_service.get_program_targets(years, region, program, limit=100000, offset=0)
    
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
