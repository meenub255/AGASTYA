from fastapi import APIRouter, Query

from backend.models.schemas import CountResponse, KPIBundle, OptionsResponse, SeriesBundle
from backend.services import exposure_service


router = APIRouter(prefix="/exposure", tags=["exposure"])


@router.get("/total-students", response_model=CountResponse)
def total_students(
    start: list[str] | None = Query(default=None),
    end: list[str] | None = Query(default=None),
    region: list[str] | None = Query(default=None),
    program: list[str] | None = Query(default=None),
):
    return {
        "count": exposure_service.get_total_students(start=start, end=end, region=region, program=program)
    }


@router.get("/kpis", response_model=KPIBundle)
def exposure_kpis(
    start: list[str] | None = Query(default=None),
    end: list[str] | None = Query(default=None),
    region: list[str] | None = Query(default=None),
    program: list[str] | None = Query(default=None),
):
    return {"metrics": exposure_service.get_exposure_kpis(start=start, end=end, region=region, program=program)}


@router.get("/gender-split")
def gender_split(
    start: list[str] | None = Query(default=None),
    end: list[str] | None = Query(default=None),
    region: list[str] | None = Query(default=None),
    program: list[str] | None = Query(default=None),
):
    return {"metrics": exposure_service.get_gender_split(start=start, end=end, region=region, program=program)}


@router.get("/community-gender-split")
def community_gender_split(
    start: list[str] | None = Query(default=None),
    end: list[str] | None = Query(default=None),
    region: list[str] | None = Query(default=None),
    program: list[str] | None = Query(default=None),
):
    return {"metrics": exposure_service.get_community_gender_split(start=start, end=end, region=region, program=program)}


@router.get("/top-schools")
def top_schools(
    start: list[str] | None = Query(default=None),
    end: list[str] | None = Query(default=None),
    region: list[str] | None = Query(default=None),
    program: list[str] | None = Query(default=None),
    limit: int = Query(default=5, ge=1, le=20),
):
    return {
        "title": "Top Schools by Students Reached",
        "data": exposure_service.get_top_schools(start=start, end=end, region=region, program=program, limit=limit),
    }


@router.get("/cohort-breakdown", response_model=SeriesBundle)
def cohort_breakdown(
    start: list[str] | None = Query(default=None),
    end: list[str] | None = Query(default=None),
    region: list[str] | None = Query(default=None),
    program: list[str] | None = Query(default=None),
):
    return {
        "title": "Exposure by Cohort Type",
        "data": exposure_service.get_cohort_breakdown(start=start, end=end, region=region, program=program),
    }


@router.get("/program-metrics", response_model=SeriesBundle)
def program_metrics(
    start: list[str] | None = Query(default=None),
    end: list[str] | None = Query(default=None),
    region: list[str] | None = Query(default=None),
    program: list[str] | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=25),
):
    return {
        "title": "Program Metrics",
        "data": exposure_service.get_program_metrics(
            start=start, end=end, region=region, program=program, limit=limit
        ),
    }


@router.get("/program-distribution", response_model=SeriesBundle)
def program_distribution(
    start: list[str] | None = Query(default=None),
    end: list[str] | None = Query(default=None),
    region: list[str] | None = Query(default=None),
    program: list[str] | None = Query(default=None),
):
    return {
        "title": "Program Distribution",
        "data": exposure_service.get_program_distribution(start=start, end=end, region=region, program=program),
    }


@router.get("/programs", response_model=OptionsResponse)
def program_options():
    return {"programs": exposure_service.get_program_options()}
