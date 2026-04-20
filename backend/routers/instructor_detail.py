from fastapi import APIRouter, Query, Request
from backend.services import instructor_detail_service

router = APIRouter(prefix="/instructor-detail", tags=["instructor-detail"])

@router.get("/filters")
def get_filters():
    return instructor_detail_service.get_instructor_detail_filters()

@router.get("/data")
def get_data(
    request: Request,
    instructor_name: str | None = Query(None),
    year: str | None = Query(None),
    month: str | None = Query(None),
    limit: int = Query(15),
    offset: int = Query(0)
):
    from backend.services.query_utils import parse_datatables_params
    dt_params = parse_datatables_params(dict(request.query_params))

    if "length" in request.query_params:
        limit = dt_params["length"]
        offset = dt_params["start"]

    return instructor_detail_service.get_instructor_detail_data(instructor_name, year, month, limit, offset, dt_params)

@router.get("/export")
def export_data(
    instructor_name: str | None = Query(None),
    year: str | None = Query(None),
    month: str | None = Query(None)
):
    from backend.services.export_utils import json_to_excel_streaming_response
    data = instructor_detail_service.get_instructor_detail_data(instructor_name, year, month, limit=100000, offset=0)
    return json_to_excel_streaming_response(data["table"], "instructor_detail_report.xlsx")
