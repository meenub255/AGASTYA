from fastapi import APIRouter, Query, HTTPException, Request
from typing import Optional
from backend.services.vehicle_report_service import get_vehicle_report_data

router = APIRouter(prefix="/api/vehicle-report", tags=["Vehicle Report"])

@router.get("/data")
def vehicle_data(
    request: Request,
    region: Optional[str] = Query(None),
    area: Optional[str] = Query(None),
    year: Optional[str] = Query(None),
    month: Optional[str] = Query(None),
    limit: int = Query(15),
    offset: int = Query(0)
):
    from backend.services.query_utils import parse_datatables_params
    dt_params = parse_datatables_params(dict(request.query_params))

    if "length" in request.query_params:
        limit = dt_params["length"]
        offset = dt_params["start"]

    y = int(year) if year and year.strip() else None
    m = int(month) if month and month.strip() else None
    
    res = get_vehicle_report_data(region, area, y, m, limit, offset, dt_params)
    if "error" in res:
        raise HTTPException(status_code=500, detail=res["error"])
    return res

@router.get("/debug")
def vehicle_debug():
    return get_vehicle_report_data()
