from fastapi import APIRouter, Query, HTTPException, Request
from typing import Optional
from backend.services.vehicle_report_service import get_vehicle_report_data, get_vehicle_report_filters

router = APIRouter(prefix="/vehicle-report", tags=["Vehicle Report"])

@router.get("/filters")
def vehicle_filters(region_name: list[str] | None = Query(None)):
    return get_vehicle_report_filters(region_name)

@router.get("/data")
def vehicle_data(
    request: Request,
    region: list[str] | None = Query(None),
    area: list[str] | None = Query(None),
    years: list[str] | None = Query(None),
    month: list[str] | None = Query(None),
    limit: int = Query(15),
    offset: int = Query(0)
):
    from backend.services.query_utils import parse_datatables_params
    dt_params = parse_datatables_params(dict(request.query_params))

    if "length" in request.query_params:
        limit = dt_params["length"]
        offset = dt_params["start"]

    res = get_vehicle_report_data(region, area, years, month, limit, offset, dt_params)
    if "error" in res:
        raise HTTPException(status_code=500, detail=res["error"])
    return res

@router.get("/export")
def vehicle_export(
    region: list[str] | None = Query(None),
    area: list[str] | None = Query(None),
    years: list[str] | None = Query(None),
    month: list[str] | None = Query(None)
):
    from backend.services.export_utils import json_to_excel_streaming_response
    data = get_vehicle_report_data(region, area, years, month, limit=100000, offset=0)
    return json_to_excel_streaming_response(data["table"], "vehicle_report.xlsx")
