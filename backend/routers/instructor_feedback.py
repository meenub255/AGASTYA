from fastapi import APIRouter, Query, Request
from backend.services import instructor_feedback_service

router = APIRouter(prefix="/instructor-feedback", tags=["instructor-feedback"])

@router.get("/filters")
def get_filters():
    return instructor_feedback_service.get_instructor_feedback_filters()

@router.get("/data")
def get_data(
    request: Request,
    instructor_name: list[str] | None = Query(None),
    years: list[str] | None = Query(None),
    month: list[str] | None = Query(None),
    quarter: list[str] | None = Query(None),
    limit: int = Query(15),
    offset: int = Query(0)
):
    from backend.services.query_utils import parse_datatables_params
    dt_params = parse_datatables_params(dict(request.query_params))

    if "length" in request.query_params:
        limit = dt_params["length"]
        offset = dt_params["start"]

    return instructor_feedback_service.get_instructor_feedback_data(instructor_name, years, month, quarter, limit, offset, dt_params)

@router.get("/export")
def export_data(
    instructor_name: list[str] | None = Query(None),
    years: list[str] | None = Query(None),
    month: list[str] | None = Query(None),
    quarter: list[str] | None = Query(None)
):
    from backend.services.export_utils import json_to_excel_streaming_response
    data = instructor_feedback_service.get_instructor_feedback_data(instructor_name, years, month, quarter, limit=100000, offset=0)
    return json_to_excel_streaming_response(data["table"], "instructor_feedback_report.xlsx")
