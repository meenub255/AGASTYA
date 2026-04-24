from fastapi import APIRouter, Query, Request
from backend.services import work_day_service

router = APIRouter(prefix="/work-day", tags=["work-day"])

@router.get("/filters")
def get_filters():
    return work_day_service.get_work_day_filters()

@router.get("/data")
def get_data(
    request: Request,
    region: list[str] | None = Query(None),
    area:   list[str] | None = Query(None),
    year:   list[str] | None = Query(None),
    month:  list[str] | None = Query(None),
    limit:  int        = Query(default=15),
    offset: int        = Query(default=0),
):
    from backend.services.query_utils import parse_datatables_params
    dt_params = parse_datatables_params(dict(request.query_params))
    
    if "length" in request.query_params:
        limit = dt_params["length"]
        offset = dt_params["start"]

    return work_day_service.get_work_day_data(region, area, year, month, limit, offset, dt_params)

@router.get("/export")
def export_data(
    region: list[str] | None = Query(None),
    area:   list[str] | None = Query(None),
    year:   list[str] | None = Query(None),
    month:  list[str] | None = Query(None)
):
    from backend.services.export_utils import json_to_excel_streaming_response
    data = work_day_service.get_work_day_data(region, area, year, month, limit=100000, offset=0)
    return json_to_excel_streaming_response(data["table"], "work_day_report.xlsx")
