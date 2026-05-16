from fastapi import APIRouter, Query, Request
from backend.services.work_days_service import get_work_days_filters, get_work_days_data
from typing import Optional

router = APIRouter(prefix="/work-days", tags=["Work Days Report"])

@router.get("/filters")
async def work_days_filters(region: list[str] | None = Query(None)):
    return get_work_days_filters(region)

@router.get("/data")
async def work_days_data(
    region: list[str] | None = Query(None),
    area: list[str] | None = Query(None),
    years: list[str] | None = Query(None),
    month: list[str] | None = Query(None),
    limit: int = 15,
    offset: int = 0
):
    return get_work_days_data(region, area, years, month, limit, offset)

@router.get("/export")
async def work_days_export(
    region: list[str] | None = Query(None),
    area: list[str] | None = Query(None),
    years: list[str] | None = Query(None),
    month: list[str] | None = Query(None)
):
    from backend.services.export_utils import json_to_excel_streaming_response
    data = get_work_days_data(region, area, years, month, limit=100000, offset=0)
    return json_to_excel_streaming_response(data["table"], "work_days.xlsx")
