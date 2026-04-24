from fastapi import APIRouter, Query, Request
from backend.services import performance_mgmt_service

router = APIRouter(prefix="/performance-mgmt", tags=["performance-mgmt"])

@router.get("/filters")
def get_filters():
    return performance_mgmt_service.get_performance_mgmt_filters()

@router.get("/data")
def get_data(
    request: Request,
    region: list[str] | None = Query(None),
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

    return performance_mgmt_service.get_performance_mgmt_data(region, year, month, limit, offset, dt_params)

@router.get("/export")
def export_data(
    region: list[str] | None = Query(None),
    year:   list[str] | None = Query(None),
    month:  list[str] | None = Query(None),
):
    from backend.services.export_utils import json_to_excel_streaming_response
    data = performance_mgmt_service.get_performance_mgmt_data(region, year, month, limit=100000, offset=0)
    return json_to_excel_streaming_response(data["table"], "performance_mgmt_dashboard.xlsx")
