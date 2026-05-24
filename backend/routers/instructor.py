from fastapi import APIRouter, Query, Request
from backend.services import instructor_service

router = APIRouter(prefix="/instructor", tags=["instructor"])

@router.get("/data")
def get_instructor_data(
    years:      list[str] | None = Query(None),
    region:     list[str] | None = Query(None),
    program:    list[str] | None = Query(None),
    instructor: list[str] | None = Query(None),
    month:      list[str] | None = Query(None),
    quarter:    list[str] | None = Query(None)
):
    """Unified data endpoint for Instructor Dashboard."""
    return instructor_service.get_unified_instructor_data(
        years=years, region=region, program=program, instructor=instructor, month=month, quarter=quarter
    )

@router.get("/filters")
def get_filters():
    from backend.services import dashboard_service
    return dashboard_service._get_filter_options()

@router.get("/kpis")
def get_kpis(
    years:      list[str] | None = Query(None),
    region:     list[str] | None = Query(None),
    program:    list[str] | None = Query(None),
    instructor: list[str] | None = Query(None),
    month:      list[str] | None = Query(None),
    quarter:    list[str] | None = Query(None)
):
    return instructor_service.get_instructor_kpis(
        years=years, region=region, program=program, instructor=instructor, month=month, quarter=quarter
    )

@router.get("/type-breakdown")
def get_type_breakdown(
    years:      list[str] | None = Query(None),
    region:     list[str] | None = Query(None),
    program:    list[str] | None = Query(None),
    instructor: list[str] | None = Query(None),
    month:      list[str] | None = Query(None),
    quarter:    list[str] | None = Query(None)
):
    return {
        "data": instructor_service.get_sessions_by_instructor_type(
            years=years, region=region, program=program, instructor=instructor, month=month, quarter=quarter
        )
    }

@router.get("/monthly")
def get_monthly(
    years:      list[str] | None = Query(None),
    region:     list[str] | None = Query(None),
    program:    list[str] | None = Query(None),
    instructor: list[str] | None = Query(None),
    month:      list[str] | None = Query(None),
    quarter:    list[str] | None = Query(None)
):
    return {
        "data": instructor_service.get_monthly_instructor_activity(
            years=years, region=region, program=program, instructor=instructor, month=month, quarter=quarter
        )
    }

@router.get("/multi-program")
def get_multi_program(
    years:      list[str] | None = Query(None),
    region:     list[str] | None = Query(None),
    program:    list[str] | None = Query(None),
    instructor: list[str] | None = Query(None),
    month:      list[str] | None = Query(None),
    quarter:    list[str] | None = Query(None)
):
    return {
        "data": instructor_service.get_multi_program_instructors(
            years=years, region=region, program=program, instructor=instructor, month=month, quarter=quarter
        )
    }

@router.get("/session-log")
def instructor_session_log(
    request: Request,
    years:      list[str] | None = Query(default=None),
    region:     list[str] | None = Query(default=None),
    program:    list[str] | None = Query(default=None),
    instructor: list[str] | None = Query(default=None),
    month:      list[str] | None = Query(default=None),
    quarter:    list[str] | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=25),
    offset: int = Query(default=0)
):
    from backend.services.query_utils import parse_datatables_params
    dt_params = parse_datatables_params(dict(request.query_params))

    if "length" in request.query_params:
        limit = dt_params["length"]
        offset = dt_params["start"]

    return instructor_service.get_instructor_session_log(
        years=years, region=region, program=program, instructor=instructor, month=month, quarter=quarter, limit=limit, offset=offset, dt_params=dt_params
    )

@router.get("/export")
def export_data(
    years:      list[str] | None = Query(default=None),
    region:     list[str] | None = Query(default=None),
    program:    list[str] | None = Query(default=None),
    instructor: list[str] | None = Query(default=None),
    month:      list[str] | None = Query(default=None),
    quarter:    list[str] | None = Query(default=None)
):
    from backend.services.export_utils import json_to_excel_streaming_response
    data = instructor_service.get_instructor_session_log(
        years=years, region=region, program=program, instructor=instructor, month=month, quarter=quarter, limit=100000, offset=0
    )
    return json_to_excel_streaming_response(data["table"], "instructor_report.xlsx")
