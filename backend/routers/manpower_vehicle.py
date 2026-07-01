from fastapi import APIRouter, Query, Request
from backend.services import manpower_vehicle_service

router = APIRouter(prefix="/manpower-vehicle", tags=["manpower-vehicle"])

@router.get("/filters")
def get_filters():
    return manpower_vehicle_service.get_manpower_vehicle_filters()

@router.get("/data")
def get_data(
    request: Request,
    region: list[str] | None = Query(None),
    years:   list[str] | None = Query(None),
    month:  list[str] | None = Query(None),
    quarter: list[str] | None = Query(None),
    limit:  int        = Query(default=15),
    offset: int        = Query(default=0),
):
    from backend.services.query_utils import parse_datatables_params
    dt_params = parse_datatables_params(dict(request.query_params))

    if "length" in request.query_params:
        limit = dt_params["length"]
        offset = dt_params["start"]

    return manpower_vehicle_service.get_manpower_vehicle_data(region, years, month, quarter, limit, offset, dt_params)

@router.get("/insights")
def get_insights(
    region: list[str] | None = Query(None),
    years:   list[str] | None = Query(None),
    month:  list[str] | None = Query(None),
    quarter: list[str] | None = Query(None),
):
    return manpower_vehicle_service.get_manpower_vehicle_insights(region, years, month, quarter)

@router.get("/export")
def export_data(
    region: list[str] | None = Query(None),
    years:   list[str] | None = Query(None),
    month:  list[str] | None = Query(None),
    quarter: list[str] | None = Query(None),
):
    from backend.services.export_utils import json_to_excel_streaming_response
    data = manpower_vehicle_service.get_manpower_vehicle_data(region, years, month, quarter, limit=100000, offset=0)
    return json_to_excel_streaming_response(data["table"], "manpower_vehicle_dashboard.xlsx")
