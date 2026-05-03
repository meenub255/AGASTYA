from fastapi import APIRouter, Query, Request
from backend.services import category_overview_service
from backend.services.query_utils import parse_datatables_params

router = APIRouter(prefix="/category-overview", tags=["category-overview"])


def _extract_dt(params: dict):
    """Extract DataTables params from request query if present."""
    if "draw" in params:
        return parse_datatables_params(params)
    return None


@router.get("/instructor")
def instructor_overview(request: Request,
    years: list[str] | None = Query(None),
    region: list[str] | None = Query(None),
    program: list[str] | None = Query(None),
    start: int = Query(0), length: int = Query(15),
):
    dt = _extract_dt(dict(request.query_params))
    return category_overview_service.get_instructor_overview(
        region=region, year=years, program=program,
        limit=length, offset=start, dt_params=dt,
    )


@router.get("/program-impact")
def program_impact_overview(request: Request,
    years: list[str] | None = Query(None),
    region: list[str] | None = Query(None),
    program: list[str] | None = Query(None),
    start: int = Query(0), length: int = Query(15),
):
    dt = _extract_dt(dict(request.query_params))
    return category_overview_service.get_program_impact_overview(
        region=region, year=years, program=program,
        limit=length, offset=start, dt_params=dt,
    )


@router.get("/operations")
def operations_overview(request: Request,
    years: list[str] | None = Query(None),
    region: list[str] | None = Query(None),
    program: list[str] | None = Query(None),
    start: int = Query(0), length: int = Query(15),
):
    dt = _extract_dt(dict(request.query_params))
    return category_overview_service.get_operations_overview(
        region=region, year=years, program=program,
        limit=length, offset=start, dt_params=dt,
    )
