from backend.services.query_utils import build_dimension_filters, fetch_all, fetch_one
from backend.config import DATAMART_SCHEMA_NAME

def _base_where(years=None, region=None, program=None):
    return build_dimension_filters(
        year=years,
        region=region,
        program=program,
        year_expression="d.year_actual",
        location_expression="g.region_name",
        program_expression="p.program_name",
    )

def get_unified_exposure_data(years=None, region=None, program=None, month=None, quarter=None):
    from backend.services.query_utils import build_standard_filters, get_kpi_insight, calc_trend
    
    where_clause, params, max_month = build_standard_filters(
        years=years,
        region=region,
        program=program,
        month=month,
        quarter=quarter
    )
    
    effective_years = years
    if effective_years is None or (isinstance(effective_years, list) and len(effective_years) == 0):
        effective_years = [DATAMART_SCHEMA_NAME] # Actually config.DEFAULT_YEAR is standard. We will resolve to DEFAULT_YEAR.
    
    from backend.config import DEFAULT_YEAR
    resolved_years = []
    if years:
        for y in years:
            try:
                resolved_years.append(int(y))
            except (ValueError, TypeError):
                pass
    if not resolved_years:
        resolved_years = [DEFAULT_YEAR]
        
    prev_year_vals = [y - 1 for y in resolved_years]
    
    prev_where_clause, prev_params, _ = build_standard_filters(
        years=prev_year_vals,
        region=region,
        program=program,
        month=month,
        quarter=quarter
    )
    
    def query_kpis(w_clause, w_params):
        kpi_sql = f"""
            SELECT
                (
                    SELECT COALESCE(SUM(total_exposure_count), 0) FROM {DATAMART_SCHEMA_NAME}.fact_attendance_exposure fae 
                     LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON d.date_id = fae.date_id 
                     LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON g.sk_geography_id = fae.sk_geography_id 
                     LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON p.sk_program_id = fae.sk_program_id 
                     WHERE {w_clause}
                ) AS total_students,
                (
                    SELECT COALESCE(SUM(f.community_men_count + f.community_women_count), 0) FROM {DATAMART_SCHEMA_NAME}.fact_session f
                     LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON d.date_id = f.date_id 
                     LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON g.sk_geography_id = f.sk_geography_id 
                     LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON p.sk_program_id = f.sk_program_id 
                     WHERE {w_clause}
                ) AS total_community,
                (
                    SELECT COALESCE(SUM(f.community_girls_count), 0) FROM {DATAMART_SCHEMA_NAME}.fact_session f
                     LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON d.date_id = f.date_id 
                     LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON g.sk_geography_id = f.sk_geography_id 
                     LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON p.sk_program_id = f.sk_program_id 
                     WHERE {w_clause}
                ) AS girls_count,
                (
                    SELECT COALESCE(SUM(f.community_boys_count), 0) FROM {DATAMART_SCHEMA_NAME}.fact_session f
                     LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON d.date_id = f.date_id 
                     LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON g.sk_geography_id = f.sk_geography_id 
                     LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON p.sk_program_id = f.sk_program_id 
                     WHERE {w_clause}
                ) AS boys_count,
                (
                    SELECT COALESCE(SUM(f.community_men_count), 0) FROM {DATAMART_SCHEMA_NAME}.fact_session f
                     LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON d.date_id = f.date_id 
                     LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON g.sk_geography_id = f.sk_geography_id 
                     LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON p.sk_program_id = f.sk_program_id 
                     WHERE {w_clause}
                ) AS men_count,
                (
                    SELECT COALESCE(SUM(f.community_women_count), 0) FROM {DATAMART_SCHEMA_NAME}.fact_session f
                     LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON d.date_id = f.date_id 
                     LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON g.sk_geography_id = f.sk_geography_id 
                     LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON p.sk_program_id = f.sk_program_id 
                     WHERE {w_clause}
                ) AS women_count,
                (
                    SELECT COALESCE(SUM(f.no_of_teachers_participated), 0) FROM {DATAMART_SCHEMA_NAME}.fact_session f
                     LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON d.date_id = f.date_id 
                     LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON g.sk_geography_id = f.sk_geography_id 
                     LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON p.sk_program_id = f.sk_program_id 
                     WHERE {w_clause}
                ) AS total_teachers,
                (
                    SELECT COALESCE(AVG(total_exposure_count), 0) FROM {DATAMART_SCHEMA_NAME}.fact_attendance_exposure fae 
                     LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON d.date_id = fae.date_id 
                     LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON g.sk_geography_id = fae.sk_geography_id 
                     LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON p.sk_program_id = fae.sk_program_id 
                     WHERE {w_clause}
                ) AS average_exposure
        """
        return fetch_one(kpi_sql, w_params * 8)
        
    kpi_res = query_kpis(where_clause, params)
    prev_res = query_kpis(prev_where_clause, prev_params)
    
    single_year = resolved_years[0] if len(resolved_years) == 1 else None
    prev_year = single_year - 1 if single_year is not None else None
    
    kpis_meta = [
        {"key": "total_students", "label": "Total Students", "icon": "fas fa-user-graduate", "color": "linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%)"},
        {"key": "total_community", "label": "Community", "icon": "fas fa-users", "color": "linear-gradient(135deg, #22c55e 0%, #16a34a 100%)"},
        {"key": "total_teachers", "label": "Teachers Reached", "icon": "fas fa-chalkboard-teacher", "color": "linear-gradient(135deg, #001f3f 0%, #001226 100%)"},
        {"key": "average_exposure", "label": "Avg / Session", "icon": "fas fa-chart-bar", "color": "linear-gradient(135deg, #dc3545 0%, #c82333 100%)"}
    ]
    
    kpi_list = []
    sparklines = {}
    for m in kpis_meta:
        k = m["key"]
        curr_val = float(kpi_res.get(k) or 0)
        prev_val = float(prev_res.get(k) or 0)
        if curr_val == int(curr_val): curr_val = int(curr_val)
        if prev_val == int(prev_val): prev_val = int(prev_val)
        
        trend = calc_trend(curr_val, prev_val)
        insights = get_kpi_insight(m["label"], curr_val, prev_val, single_year, prev_year, max_month, month, quarter)
        
        kpi_list.append({
            "label": m["label"],
            "value": curr_val,
            "icon": m["icon"],
            "color": m["color"],
            "trend": trend,
            "insights": insights,
            "trends": [prev_val, curr_val]
        })
        
        sparklines[k.replace("total_", "")] = [prev_val, curr_val]
    
    # 2. Top Schools
    top_schools = fetch_all(f"""
        SELECT COALESCE(s.school_name, 'Unknown') as name,
               SUM(COALESCE(e.total_exposure_count, 0)) as students
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_school s ON f.sk_school_id = s.sk_school_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
        WHERE {where_clause}
        GROUP BY s.school_name
        ORDER BY students DESC
        LIMIT 5
    """, params)

    # 3. Cohort Breakdown
    cohorts = fetch_all(f"""
        SELECT COALESCE(e.class_name, 'N/A') as type,
               SUM(COALESCE(e.total_exposure_count, 0)) as students
        FROM {DATAMART_SCHEMA_NAME}.fact_session f
        LEFT JOIN {DATAMART_SCHEMA_NAME}.fact_attendance_exposure e ON f.session_nk_id = e.session_nk_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_date d ON f.date_id = d.date_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_geography g ON f.sk_geography_id = g.sk_geography_id
        LEFT JOIN {DATAMART_SCHEMA_NAME}.dim_program p ON f.sk_program_id = p.sk_program_id
        WHERE {where_clause}
        GROUP BY e.class_name
        ORDER BY students DESC
    """, params)

    return {
        "kpis": kpi_list,
        "sparklines": sparklines,
        "raw_kpis": {
            "total_students": int(kpi_res.get("total_students") or 0),
            "total_community": int(kpi_res.get("total_community") or 0),
            "total_teachers": int(kpi_res.get("total_teachers") or 0),
            "average_exposure": round(float(kpi_res.get("average_exposure") or 0), 1),
            "girls": int(kpi_res.get("girls_count") or 0),
            "boys": int(kpi_res.get("boys_count") or 0),
            "men": int(kpi_res.get("men_count") or 0),
            "women": int(kpi_res.get("women_count") or 0)
        },
        "top_schools": top_schools,
        "cohort_breakdown": cohorts
    }

def get_program_options():
    rows = fetch_all(f"SELECT DISTINCT program_name FROM {DATAMART_SCHEMA_NAME}.dim_program ORDER BY program_name")
    return [r["program_name"] for r in rows]
