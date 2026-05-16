from fastapi import APIRouter, Query, Request
from backend.services import arealead_summary_service

router = APIRouter(prefix="/arealead-summary", tags=["arealead-summary"])

@router.get("/filters")
def get_filters():
    return arealead_summary_service.get_arealead_summary_filters()

@router.get("/data")
def get_data(
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

    return arealead_summary_service.get_arealead_summary_data(region, area, years, month, limit, offset, dt_params)

@router.get("/export")
def export_data(
    region: list[str] | None = Query(None),
    area: list[str] | None = Query(None),
    years: list[str] | None = Query(None),
    month: list[str] | None = Query(None)
):
    from backend.services.export_utils import json_to_excel_streaming_response
    data = arealead_summary_service.get_arealead_summary_data(region, area, years, month, limit=100000, offset=0)
    return json_to_excel_streaming_response(data["table"], "arealead_summary_report.xlsx")
