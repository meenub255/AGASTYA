from fastapi import APIRouter, Query
from backend.services import region_service

router = APIRouter(prefix="/region", tags=["region"])

@router.get("/data")
def get_region_data(
    years:      list[str] | None = Query(None),
    region:     list[str] | None = Query(None),
    program:    list[str] | None = Query(None)
):
    """Unified data endpoint for Region Dashboard."""
    return region_service.get_unified_region_data(years=years, region=region, program=program)

@router.get("/filters")
def get_filters():
    from backend.services import dashboard_service
    return dashboard_service._get_filter_options()

@router.get("/kpis")
def region_kpis(
    years:      list[str] | None = Query(None),
    region:     list[str] | None = Query(None),
    program:    list[str] | None = Query(None)
):
    return {"metrics": region_service.get_region_kpis(years=years, region=region, program=program)}

@router.get("/impact")
def region_impact(
    years:      list[str] | None = Query(None),
    region:     list[str] | None = Query(None),
    program:    list[str] | None = Query(None)
):
    return {
        "title": "Region Impact",
        "data": region_service.get_region_impact(years=years, region=region, program=program),
    }

@router.get("/monthly-impact")
def monthly_region_impact(
    years:      list[str] | None = Query(None),
    region:     list[str] | None = Query(None),
    program:    list[str] | None = Query(None)
):
    return {
        "title": "Monthly Region Impact",
        "data": region_service.get_monthly_region_impact(years=years, region=region, program=program),
    }

@router.get("/options")
def region_options():
    return {"regions": region_service.get_region_options()}
