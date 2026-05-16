from backend.services.query_utils import build_dimension_filters, fetch_all, fetch_one
from backend.config import DATAMART_SCHEMA_NAME

def _build_filters(years=None, region=None, program=None):
    return build_dimension_filters(
        year=years,
        region=region,
        program=program,
        year_expression="d.year_actual",
        location_expression="g.region_name",
        program_expression="p.program_name",
    )

def get_unified_region_data(years=None, region=None, program=None):
    """Unified data for Region Dashboard."""
    kpis = get_region_kpis(years, region, program)
    impact = get_region_impact(years, region, program)
    monthly = get_monthly_region_impact(years, region, program)
    
    return {
        "kpis": kpis,
        "impact": impact,
        "monthly_impact": monthly
    }

def get_region_kpis(years=None, region=None, program=None) -> dict:
    where_clause, params = _build_filters(years, region, program)

    row = fetch_one(
        f"""
        SELECT
            (SELECT COALESCE(SUM(total_exposure_count), 0) FROM {DATAMART_SCHEMA_NAME}.fact_attendance_exposure fae
             LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON d.date_id = fae.date_id
             LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON g.sk_geography_id = fae.sk_geography_id
             LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON p.sk_program_id = fae.sk_program_id
             {where_clause}) AS total_students_reached,
            COUNT(DISTINCT g.nk_region_id) AS total_states,
            COUNT(f.sk_fact_session_id) AS total_sessions,
            COALESCE(
                (SELECT SUM(total_exposure_count) FROM {DATAMART_SCHEMA_NAME}.fact_attendance_exposure fae {where_clause.replace('g.', 'ge.') if where_clause else ''}) / NULLIF(COUNT(DISTINCT g.nk_region_id), 0),
                0
            ) AS avg_students_per_state_period
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON d.date_id = f.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = f.sk_geography_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON p.sk_program_id = f.sk_program_id
        {where_clause}
        """,
        params,
    )

    return {
        "total_students_reached": int(row.get("total_students_reached", 0) or 0),
        "total_states": int(row.get("total_states", 0) or 0),
        "total_sessions": int(row.get("total_sessions", 0) or 0),
        "avg_students_per_state_period": round(float(row.get("avg_students_per_state_period", 0) or 0), 2),
    }

def get_region_impact(years=None, region=None, program=None) -> list[dict]:
    where_clause, params = _build_filters(years, region, program)

    rows = fetch_all(
        f"""
        SELECT
            COALESCE(g.region_name, 'Unknown') AS label,
            COALESCE(SUM(fae.total_exposure_count), 0) AS value
        FROM {DATAMART_SCHEMA_NAME}.fact_attendance_exposure fae
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON d.date_id = fae.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON g.sk_geography_id = fae.sk_geography_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON p.sk_program_id = fae.sk_program_id
        {where_clause}
        GROUP BY g.region_name
        ORDER BY value DESC, label
        LIMIT 20
        """,
        params,
    )
    return [{"label": row["label"], "value": float(row["value"])} for row in rows]

def get_monthly_region_impact(years=None, region=None, program=None) -> list[dict]:
    where_clause, params = _build_filters(years, region, program)

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
        {where_clause}
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
