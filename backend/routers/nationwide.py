from fastapi import APIRouter, Query, Request
from backend.services import nationwide_service

router = APIRouter(prefix="/nationwide", tags=["nationwide"])

@router.get("/filters")
def get_filters():
    return nationwide_service.get_nationwide_filters()

@router.get("/data")
def get_data(
    request: Request,
    year:       list[str] | None = Query(None),
    region:     list[str] | None = Query(None),
    limit:      int        = Query(default=15),
    offset:     int        = Query(default=0),
):
    from backend.services.query_utils import parse_datatables_params
    dt_params = parse_datatables_params(dict(request.query_params))

    if "length" in request.query_params:
        limit = dt_params["length"]
        offset = dt_params["start"]

    return nationwide_service.get_nationwide_data(year, region, limit, offset, dt_params)

@router.get("/export")
def export_data(
    year:       list[str] | None = Query(None),
    region:     list[str] | None = Query(None),
):
    from backend.services.export_utils import json_to_excel_streaming_response
    data = nationwide_service.get_nationwide_data(year, region, limit=100000, offset=0)
    return json_to_excel_streaming_response(data["table"], "nationwide_dashboard.xlsx")
