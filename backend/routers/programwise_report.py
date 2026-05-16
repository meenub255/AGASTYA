from fastapi import APIRouter, Query, Request
from backend.services import programwise_report_service

router = APIRouter(prefix="/programwise-report", tags=["programwise-report"])

@router.get("/filters")
def get_filters():
    return programwise_report_service.get_programwise_report_filters()

@router.get("/data")
def get_data(
    request: Request,
    category: list[str] | None = Query(None),
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

    return programwise_report_service.get_programwise_report_data(category, years, month, limit, offset, dt_params)

@router.get("/export")
def export_data(
    category: list[str] | None = Query(None),
    years: list[str] | None = Query(None),
    month: list[str] | None = Query(None)
):
    from backend.services.export_utils import json_to_excel_streaming_response
    data = programwise_report_service.get_programwise_report_data(category, years, month, limit=100000, offset=0)
    return json_to_excel_streaming_response(data["table"], "programwise_report.xlsx")
