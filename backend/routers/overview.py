from fastapi import APIRouter, Query

from backend.models.schemas import KPIBundle, SeriesBundle
from backend.services import overview_service


router = APIRouter(prefix="/overview", tags=["overview"])


@router.get("/kpis", response_model=KPIBundle)
def overview_kpis(
    years: list[str] | None = Query(default=None),
    region: list[str] | None = Query(default=None),
    program: list[str] | None = Query(default=None),
):
    return {"metrics": overview_service.get_overview_kpis(years=years, region=region, program=program)}


@router.get("/program-targets")
def program_targets(
    years: list[str] | None = Query(default=None),
    region: list[str] | None = Query(default=None),
    program: list[str] | None = Query(default=None),
    limit: int = Query(default=10),
    offset: int = Query(default=0)
):
    return overview_service.get_program_targets(years=years, region=region, program=program, limit=limit, offset=offset)


@router.get("/sessions-by-activity", response_model=SeriesBundle)
def sessions_by_activity(
    years: list[str] | None = Query(default=None),
    region: list[str] | None = Query(default=None),
    program: list[str] | None = Query(default=None),
):
    return {
        "title": "Sessions by activity type",
        "data": overview_service.get_sessions_by_activity(years=years, region=region, program=program),
    }


@router.get("/sessions-by-donor", response_model=SeriesBundle)
def sessions_by_donor(
    years: list[str] | None = Query(default=None),
    region: list[str] | None = Query(default=None),
    program: list[str] | None = Query(default=None),
):
    return {
        "title": "Sessions by donor",
        "data": overview_service.get_sessions_by_donor(years=years, region=region, program=program),
    }
