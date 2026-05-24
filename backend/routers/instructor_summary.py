from fastapi import APIRouter, Query, Request
from backend.services import instructor_summary_service

router = APIRouter(prefix="/instructor-summary", tags=["instructor-summary"])

@router.get("/filters")
def get_filters(
    years:   list[str] | None = Query(None),
    region: list[str] | None = Query(None),
    area:   list[str] | None = Query(None),
):
    return instructor_summary_service.get_instructor_summary_filters(years, region, area)

@router.get("/data")
def get_data(
    request: Request,
    region: list[str] | None = Query(None),
    area: list[str] | None = Query(None),
    years: list[str] | None = Query(None),
    month: list[str] | None = Query(None),
    quarter: list[str] | None = Query(None),
    limit: int = Query(15),
    offset: int = Query(0)
):
    from backend.services.query_utils import parse_datatables_params
    dt_params = parse_datatables_params(dict(request.query_params))
    
    if "length" in request.query_params:
        limit = dt_params["length"]
        offset = dt_params["start"]

    return instructor_summary_service.get_instructor_summary_data(
        region=region,
        area=area,
        years=years,
        month=month,
        quarter=quarter,
        limit=limit,
        offset=offset,
        dt_params=dt_params
    )

@router.get("/export")
def export_data(
    region: list[str] | None = Query(None),
    area: list[str] | None = Query(None),
    years: list[str] | None = Query(None),
    month: list[str] | None = Query(None),
    quarter: list[str] | None = Query(None)
):
    from backend.services.export_utils import json_to_excel_streaming_response
    data = instructor_summary_service.get_instructor_summary_data(region, area, years, month, quarter, limit=100000, offset=0)
    return json_to_excel_streaming_response(data["table"], "instructor_summary_report.xlsx")

@router.get("/monthly")
def get_monthly_data(
    region: list[str] | None = Query(None),
    area: list[str] | None = Query(None),
    years: list[str] | None = Query(None),
    month: list[str] | None = Query(None),
    quarter: list[str] | None = Query(None)
):
    return {
        "title": "Monthly Activity Comparison",
        "data": instructor_summary_service.get_monthly_instructor_summary(region, area, years, month, quarter)
    }
