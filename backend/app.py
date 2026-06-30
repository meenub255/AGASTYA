from fastapi import FastAPI, Request
# Triggering reload for performance dashboard fixes
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from pathlib import Path

from backend import upload
from backend.routers import (
    arealead_summary,
    attendance,
    exposure,
    instructor,
    instructor_detail,
    instructor_feedback,
    instructor_summary,
    overview,
    programwise_report,
    region,
    region_summary,
    school_visit,
    session,
    work_day,
    dashboard,
    vehicle_report,
    nationwide,
    regionwise,
    exposure_session,
    performance_mgmt,
    manpower_vehicle,
    category_overview,
)


# -----------------------------
# PATH FIX (NO config.py used)
# -----------------------------

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent

TEMPLATES_DIR = PROJECT_DIR / "frontend" / "templates"
STATIC_DIR = PROJECT_DIR / "frontend" / "static"


print("TEMPLATES:", TEMPLATES_DIR)
print("STATIC:", STATIC_DIR)


app = FastAPI(title="Pramana Analytics Dashboard")

@app.middleware("http")
async def add_export_format_middleware(request: Request, call_next):
    from backend.services.export_utils import export_format_var
    fmt = request.query_params.get("format", "excel")
    token = export_format_var.set(fmt)
    try:
        response = await call_next(request)
        return response
    finally:
        export_format_var.reset(token)


def map_ui_values(data):
    if isinstance(data, dict):
        return {k: map_ui_values(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [map_ui_values(x) for x in data]
    elif isinstance(data, str):
        import re
        # Replace plurals
        val = re.sub(r'\b(instructors|catalysers|catalyzers|ovvs)\b', 'ignators', data, flags=re.IGNORECASE)
        val = re.sub(r'\b(Instructors|Catalysers|Catalyzers|Ovvs)\b', 'Ignators', val)
        val = re.sub(r'\b(INSTRUCTORS|CATALYSERS|CATALYZERS|OVVS)\b', 'IGNATORS', val)
        # Replace singulars
        val = re.sub(r'\b(instructor|catalyser|catalyzer|ovv)\b', 'ignator', val, flags=re.IGNORECASE)
        val = re.sub(r'\b(Instructor|Catalyser|Catalyzer|Ovv)\b', 'Ignator', val)
        val = re.sub(r'\b(INSTRUCTOR|CATALYSER|CATALYZER|OVV)\b', 'IGNATOR', val)
        return val
    return data


@app.middleware("http")
async def translate_ui_middleware(request: Request, call_next):
    response = await call_next(request)
    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        import json
        from fastapi.responses import Response
        body = b""
        async for chunk in response.body_iterator:
            body += chunk
        try:
            data = json.loads(body.decode("utf-8"))
            mapped_data = map_ui_values(data)
            new_body = json.dumps(mapped_data).encode("utf-8")
            # Update Content-Length header as size might change
            headers = dict(response.headers)
            headers["content-length"] = str(len(new_body))
            return Response(
                content=new_body,
                status_code=response.status_code,
                headers=headers,
                media_type="application/json"
            )
        except Exception:
            async def re_iterator():
                yield body
            response.body_iterator = re_iterator()
            return response
    return response



templates = Jinja2Templates(
    directory=str(TEMPLATES_DIR.resolve())
)


app.mount(
    "/static",
    StaticFiles(directory=str(STATIC_DIR.resolve())),
    name="static",
)


# -----------------------------
# ROUTERS
# -----------------------------

app.include_router(overview.router)
app.include_router(dashboard.router)
app.include_router(session.router)
app.include_router(exposure.router)
app.include_router(attendance.router)
app.include_router(arealead_summary.router)
app.include_router(programwise_report.router)
app.include_router(region.router)
app.include_router(instructor.router)
app.include_router(region_summary.router)
app.include_router(instructor_summary.router)
app.include_router(instructor_detail.router)
app.include_router(instructor_feedback.router)
app.include_router(school_visit.router)
app.include_router(work_day.router)
app.include_router(vehicle_report.router)
app.include_router(upload.router)
app.include_router(nationwide.router)
app.include_router(regionwise.router)
app.include_router(exposure_session.router)
app.include_router(performance_mgmt.router)
app.include_router(manpower_vehicle.router)
app.include_router(category_overview.router)
# Trigger reload


@app.get("/debug-db")
def debug_db():
    from backend.db import get_datamart_conn
    from backend.config import DATAMART_SCHEMA_NAME
    try:
        conn = get_datamart_conn()
        with conn.cursor() as cur:
            cur.execute("SHOW search_path")
            search_path = cur.fetchone()
            
            cur.execute(f"SELECT COUNT(*) FROM {DATAMART_SCHEMA_NAME}.dim_program")
            prog_count = cur.fetchone()["count"]
            
            cur.execute(f"SELECT table_name FROM information_schema.tables WHERE table_schema = '{DATAMART_SCHEMA_NAME}' LIMIT 5")
            tables = [r["table_name"] for r in cur.fetchall()]
            
        conn.close()
        return {
            "status": "success", 
            "search_path": search_path,
            "schema_used": DATAMART_SCHEMA_NAME,
            "dim_program_count": prog_count,
            "sample_tables": tables
        }
    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e), "traceback": traceback.format_exc()}



def render_page(request, template_name, title, page_id):
    return templates.TemplateResponse(
        name=template_name,
        request=request,
        context={
            "page_title": title,
            "page_id": page_id,
        },
    )


# -----------------------------
# PAGES
# -----------------------------

@app.get("/", response_class=HTMLResponse)
def landing_page(request: Request):
    return render_page(
        request,
        "landing.html",
        "Pramana Analytics Dashboard",
        "landing",
    )


@app.get("/sessions", response_class=HTMLResponse)
def sessions_page(request: Request):
    return render_page(
        request,
        "session.html",
        "Sessions",
        "sessions",
    )


@app.get("/region-impact", response_class=HTMLResponse)
def region_page(request: Request):
    return render_page(
        request,
        "region.html",
        "Region Impact",
        "region",
    )


@app.get("/instructor-productivity", response_class=HTMLResponse)
def instructor_page(request: Request):
    return render_page(
        request,
        "instructor.html",
        "Ignator Performance",
        "instructor",
    )


@app.get("/program-metrics", response_class=HTMLResponse)
def exposure_page(request: Request):
    return render_page(
        request,
        "exposure.html",
        "Student Exposure & Outreach",
        "programs",
    )
# -----------------------------
# NEW PAGES
# -----------------------------

@app.get("/overview", response_class=HTMLResponse)
def overview_page(request: Request):
    return render_page(
        request,
        "index.html",
        "Overview",
        "overview",
    )

@app.get("/program-visits", response_class=HTMLResponse)
def program_visits_page(request: Request):
    return render_page(
        request, "school_visit.html", "Program wise School Visits", "program-visits"
    )

@app.get("/instructor-summary", response_class=HTMLResponse)
def instructor_summary_page(request: Request):
    return render_page(
        request, "instructor_summary.html", "Ignator Summary", "instructor-summary"
    )

@app.get("/region-summary", response_class=HTMLResponse)
def region_summary_page(request: Request):
    return render_page(request, "region_summary.html", "Region Summary", "region-summary")

@app.get("/instructor-detail", response_class=HTMLResponse)
def instructor_detail_page(request: Request):
    return render_page(
        request, "instructor_detail.html", "Ignator Detail", "instructor-detail"
    )

@app.get("/vehicle-report", response_class=HTMLResponse)
def vehicle_report_page(request: Request):
    return render_page(request, "vehicle_report.html", "Vehicle Report", "vehicle-report")

@app.get("/work-days-report", response_class=HTMLResponse)
def work_days_report_page(request: Request):
    return render_page(
        request, "work_day.html", "Work Days Report", "work-days-report"
    )

@app.get("/attendance", response_class=HTMLResponse)
def attendance_page(request: Request):
    return render_page(request, "attendance.html", "Attendance", "attendance")

@app.get("/arealead-summary", response_class=HTMLResponse)
def arealead_summary_page(request: Request):
    return render_page(request, "arealead_summary.html", "AreaLead Summary", "arealead-summary")

@app.get("/programwise-report", response_class=HTMLResponse)
def programwise_report_page(request: Request):
    return render_page(
        request, "programwise_report.html", "Programwise Report", "programwise-report"
    )

@app.get("/nationwide-dashboard", response_class=HTMLResponse)
def nationwide_dashboard_page(request: Request):
    return render_page(request, "nationwide_dashboard.html", "Nationwide Dashboard", "nationwide-dashboard")

@app.get("/regionwise-dashboard", response_class=HTMLResponse)
def regionwise_dashboard_page(request: Request):
    return render_page(request, "regionwise_dashboard.html", "Regionwise Dashboard", "regionwise-dashboard")

@app.get("/exposure-session-dashboard", response_class=HTMLResponse)
def exposure_session_dashboard_page(request: Request):
    return render_page(request, "exposure_session_dashboard.html", "Exposure Session Dashboard", "exposure-session-dashboard")

@app.get("/performance-management-dashboard", response_class=HTMLResponse)
def performance_management_dashboard_page(request: Request):
    return render_page(request, "performance_mgmt_dashboard.html", "Performance Management Dashboard", "performance-management-dashboard")

@app.get("/manpower-vehicle-dashboard", response_class=HTMLResponse)
def manpower_vehicle_dashboard_page(request: Request):
    return render_page(request, "manpower_vehicle_dashboard.html", "Manpower Vehicle Dashboard", "manpower-vehicle-dashboard")

@app.get("/instructor-feedback", response_class=HTMLResponse)
def instructor_feedback_page(request: Request):
    return render_page(request, "instructor_feedback.html", "Ignator Feedback", "instructor-feedback")

@app.get("/instructor-overview", response_class=HTMLResponse)
def instructor_overview_page(request: Request):
    return render_page(request, "instructor_overview.html", "Ignator Performance Overview", "instructor-overview")

@app.get("/program-impact-overview", response_class=HTMLResponse)
def program_impact_overview_page(request: Request):
    return render_page(request, "program_impact_overview.html", "Program Impact Overview", "program-impact-overview")

@app.get("/operations-overview", response_class=HTMLResponse)
def operations_overview_page(request: Request):
    return render_page(request, "operations_overview.html", "Operations Overview", "operations-overview")

@app.get("/vehicle-ops", response_class=HTMLResponse)
def vehicle_ops_page(request: Request):
    return render_page(request, "vehicle_ops.html", "Vehicle Operations", "vehicle-ops")


@app.get("/pramana-intelligence", response_class=HTMLResponse)
def pramana_intelligence_page(request: Request):
    return render_page(request, "pramana_intelligence.html", "Pramana Intelligence", "pramana-intelligence")
