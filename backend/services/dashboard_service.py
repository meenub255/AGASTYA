from backend.services.query_utils import fetch_all
from backend.config import DATAMART_SCHEMA_NAME

def _get_filter_options():
    regions_query = f"""
        SELECT DISTINCT g.region_name 
        FROM {DATAMART_SCHEMA_NAME}.dim_geography g
        INNER JOIN {DATAMART_SCHEMA_NAME}.fact_session f ON g.sk_geography_id = f.sk_geography_id
        WHERE g.region_name IS NOT NULL 
        ORDER BY g.region_name
    """
    regions = [row["region_name"] for row in fetch_all(regions_query)]

    programs_query = f"""
        SELECT DISTINCT p.program_name 
        FROM {DATAMART_SCHEMA_NAME}.dim_program p
        INNER JOIN {DATAMART_SCHEMA_NAME}.fact_session f ON p.sk_program_id = f.sk_program_id
        WHERE p.program_name IS NOT NULL 
        ORDER BY p.program_name
    """
    programs = [row["program_name"] for row in fetch_all(programs_query)]

    years_query = f"""
        SELECT DISTINCT d.year_actual 
        FROM {DATAMART_SCHEMA_NAME}.dim_date d
        INNER JOIN {DATAMART_SCHEMA_NAME}.fact_session f ON d.date_id = f.date_id
        WHERE d.year_actual IS NOT NULL 
        ORDER BY d.year_actual DESC
    """
    years = [f"{int(row['year_actual'])}-{str(int(row['year_actual'])+1)[2:]}" for row in fetch_all(years_query) if row.get("year_actual")]

    months = [{"id": row["month_actual"], "name": row["month_name"].strip()} for row in fetch_all(f"""
        SELECT DISTINCT d.month_actual, TO_CHAR(TO_DATE(d.month_actual::text, 'MM'), 'Month') as month_name 
        FROM {DATAMART_SCHEMA_NAME}.dim_date d
        INNER JOIN {DATAMART_SCHEMA_NAME}.fact_session f ON d.date_id = f.date_id
        ORDER BY d.month_actual
    """)]

    return {
        "regions": regions,
        "programs": programs,
        "years": years,
        "months": months,
        "quarters": [1, 2, 3, 4]
    }
