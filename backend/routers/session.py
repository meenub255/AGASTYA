from fastapi import APIRouter, Query

from backend.models.schemas import CountResponse, KPIBundle, OptionsResponse, SeriesBundle
from backend.services import session_service


router = APIRouter(prefix="/session", tags=["session"])


@router.get("/count", response_model=CountResponse)
def session_count(start: list[str] | None = Query(default=None), end: list[str] | None = Query(default=None)):
    return {"count": session_service.get_session_count(start=start, end=end)}


@router.get("/kpis", response_model=KPIBundle)
def session_kpis(
    start: list[str] | None = Query(default=None),
    end: list[str] | None = Query(default=None),
    region: list[str] | None = Query(default=None),
    program: list[str] | None = Query(default=None),
):
    return {"metrics": session_service.get_session_kpis(start=start, end=end, region=region, program=program)}


@router.get("/monthly", response_model=SeriesBundle)
def monthly_sessions(
    start: list[str] | None = Query(default=None),
    end: list[str] | None = Query(default=None),
    region: list[str] | None = Query(default=None),
    program: list[str] | None = Query(default=None),
):
    return {
        "title": "Monthly Sessions",
        "data": session_service.get_monthly_sessions(start=start, end=end, region=region, program=program),
    }


@router.get("/by-region", response_model=SeriesBundle)
def sessions_by_region(
    start: list[str] | None = Query(default=None),
    end: list[str] | None = Query(default=None),
    region: list[str] | None = Query(default=None),
    program: list[str] | None = Query(default=None),
):
    return {
        "title": "Sessions by Region",
        "data": session_service.get_sessions_by_region(start=start, end=end, region=region, program=program),
    }


@router.get("/filter-options", response_model=OptionsResponse)
def session_filter_options():
    return {"years": session_service.get_available_years()}
