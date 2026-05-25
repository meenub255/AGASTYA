from backend.services.query_utils import fetch_all, fetch_one
from backend.config import DATAMART_SCHEMA_NAME

def get_unified_region_data(years=None, region=None, program=None, month=None, quarter=None):
    """Unified data for Region Dashboard."""
    kpis_data = get_region_kpis(years, region, program, month, quarter)
    impact = get_region_impact(years, region, program, month, quarter)
    monthly = get_monthly_region_impact(years, region, program, month, quarter)
    
    return {
        "kpis": kpis_data["kpis"],
        "sparklines": kpis_data["sparklines"],
        "impact": impact,
        "monthly_impact": monthly
    }

def get_region_kpis(years=None, region=None, program=None, month=None, quarter=None) -> dict:
    from backend.services.query_utils import calculate_ytd_kpis
    
    kpi_defs = [
        {
            "key": "total_students_reached",
            "label": "Students Reached",
            "sql": "COALESCE(SUM(fae.total_exposure_count), 0)",
            "icon": "fas fa-user-graduate",
            "color": "bg-danger"
        },
        {
            "key": "total_states",
            "label": "Total States",
            "sql": "COUNT(DISTINCT g.region_name)",
            "icon": "fas fa-map-marked-alt",
            "color": "bg-info"
        },
        {
            "key": "total_sessions",
            "label": "Total Sessions",
            "sql": "COUNT(DISTINCT f.sk_fact_session_id)",
            "icon": "fas fa-chalkboard-teacher",
            "color": "bg-navy-blue"
        },
        {
            "key": "avg_students_per_state_period",
            "label": "Avg Students per State",
            "sql": "COALESCE(SUM(fae.total_exposure_count) / NULLIF(COUNT(DISTINCT g.region_name), 0), 0)",
            "icon": "fas fa-globe",
            "color": "bg-success"
        }
    ]
    
    from_clause = f"""
        {DATAMART_SCHEMA_NAME}.fact_session f
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON d.date_id = f.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON p.sk_program_id = f.sk_program_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.fact_attendance_exposure fae ON f.session_nk_id = fae.session_nk_id
    """
    
    kpis, sparklines = calculate_ytd_kpis(
        kpi_defs=kpi_defs,
        from_clause=from_clause,
        years=years,
        region=region,
        program=program,
        month=month,
        quarter=quarter
    )
    
    return {
        "kpis": kpis,
        "sparklines": sparklines
    }

def get_region_impact(years=None, region=None, program=None, month=None, quarter=None) -> list[dict]:
    from backend.services.query_utils import build_standard_filters
    where_sql, params, _ = build_standard_filters(
        years=years,
        region=region,
        area=None,
        program=program,
        month=month,
        quarter=quarter,
        date_alias="d"
    )

    rows = fetch_all(
        f"""
        SELECT
            COALESCE(g.region_name, 'Unknown') AS label,
            COALESCE(SUM(fae.total_exposure_count), 0) AS value
        FROM {DATAMART_SCHEMA_NAME}.fact_attendance_exposure fae
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON d.date_id = fae.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON g.sk_geography_id = fae.sk_geography_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON p.sk_program_id = fae.sk_program_id
        WHERE {where_sql}
        GROUP BY g.region_name
        ORDER BY value DESC, label
        LIMIT 20
        """,
        params,
    )
    return [{"label": row["label"], "value": float(row["value"])} for row in rows]

def get_monthly_region_impact(years=None, region=None, program=None, month=None, quarter=None) -> list[dict]:
    from backend.services.query_utils import build_standard_filters
    where_sql, params, _ = build_standard_filters(
        years=years,
        region=region,
        area=None,
        program=program,
        month=month,
        quarter=quarter,
        date_alias="d"
    )

    rows = fetch_all(
        f"""
        SELECT
            TO_CHAR(DATE_TRUNC('month', d.full_date), 'YYYY-MM') AS label,
            COALESCE(SUM(fae.total_exposure_count), 0) AS value,
            DATE_TRUNC('month', d.full_date) AS sort_key
        FROM {DATAMART_SCHEMA_NAME}.fact_attendance_exposure fae
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON d.date_id = fae.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON g.sk_geography_id = fae.sk_geography_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON p.sk_program_id = fae.sk_program_id
        WHERE {where_sql}
        GROUP BY DATE_TRUNC('month', d.full_date)
        ORDER BY sort_key
        """,
        params,
    )
    return [{"label": row["label"], "value": float(row["value"])} for row in rows]

def get_region_options() -> list[str]:
    rows = fetch_all(
        f"""
        SELECT DISTINCT g.region_name as state
        FROM {DATAMART_SCHEMA_NAME}.dim_geography g
        INNER JOIN {DATAMART_SCHEMA_NAME}.fact_session f ON g.sk_geography_id = f.sk_geography_id
        WHERE g.region_name IS NOT NULL 
        ORDER BY g.region_name
        """
    )
    return [str(row["state"]) for row in rows if row.get("state")]
