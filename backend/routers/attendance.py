from fastapi import APIRouter, Query, Request
from backend.services import attendance_service

router = APIRouter(prefix="/attendance", tags=["attendance"])

@router.get("/filters")
def get_filters():
    return attendance_service.get_attendance_filters()

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
    
    # If DataTables is driving the request (start/length are present), override limit/offset
    if "length" in request.query_params:
        limit = dt_params["length"]
        offset = dt_params["start"]
        
    return attendance_service.get_attendance_data(region, area, years, month, quarter, limit, offset, dt_params)

@router.get("/export")
def export_data(
    region: list[str] | None = Query(None),
    area: list[str] | None = Query(None),
    years: list[str] | None = Query(None),
    month: list[str] | None = Query(None),
    quarter: list[str] | None = Query(None)
):
    from backend.services.export_utils import json_to_excel_streaming_response
    data = attendance_service.get_attendance_data(region, area, years, month, quarter, limit=100000, offset=0)
    return json_to_excel_streaming_response(data["table"], "attendance_report.xlsx")
