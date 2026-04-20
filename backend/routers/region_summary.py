from fastapi import APIRouter, Query, Request
from backend.services import region_summary_service

router = APIRouter(prefix="/region-summary", tags=["region-summary"])

@router.get("/filters")
def get_filters():
    return region_summary_service.get_region_summary_filters()

@router.get("/data")
def get_data(
    request: Request,
    region: str | None = Query(default=None),
    program_type: str | None = Query(default=None),
    year: str | None = Query(default=None),
    month: str | None = Query(default=None),
    limit: int = Query(default=15),
    offset: int = Query(default=0)
):
    from backend.services.query_utils import parse_datatables_params
    dt_params = parse_datatables_params(dict(request.query_params))

    if "length" in request.query_params:
        limit = dt_params["length"]
        offset = dt_params["start"]

    return region_summary_service.get_region_summary_data(
        region=region,
        program_type=program_type,
        year=year,
        month=month,
        limit=limit,
        offset=offset,
        dt_params=dt_params
    )

@router.get("/export")
def export_data(
    region: str | None = Query(None),
    program_type: str | None = Query(None),
    year: str | None = Query(None),
    month: str | None = Query(None)
):
    from backend.services.export_utils import json_to_excel_streaming_response
    data = region_summary_service.get_region_summary_data(region, program_type, year, month, limit=100000, offset=0)
    return json_to_excel_streaming_response(data["table"], "region_summary_report.xlsx")
