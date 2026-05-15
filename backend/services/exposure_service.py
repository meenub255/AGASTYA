from backend.services.query_utils import build_dimension_filters, fetch_all, fetch_one


def _base_where(start=None, end=None, region=None, program=None):
    return build_dimension_filters(
        start=start,
        end=end,
        region=region,
        program=program,
        year_expression="d.year_actual",
        location_expression="g.region_name",
        program_expression="p.program_name",
    )



def get_total_students(
    start: int | None = None,
    end: int | None = None,
    region: str | None = None,
    program: str | None = None,
) -> int:
    where_clause, params = _base_where(start, end, region, program)
    row = fetch_one(
        f"""
        SELECT (COALESCE(e_sum.total_exposure_count, 0) + COALESCE(f_sum.comm_count, 0)) AS total_students
        FROM (
            SELECT COALESCE(SUM(fae.total_exposure_count), 0) AS total_exposure_count
            FROM dw.fact_attendance_exposure fae
            LEFT JOIN dw.dim_date d ON d.date_id = fae.date_id
            LEFT JOIN dw.dim_geography g ON g.sk_geography_id = fae.sk_geography_id
            LEFT JOIN dw.dim_program p ON p.sk_program_id = fae.sk_program_id
            {where_clause}
        ) e_sum,
        (
            SELECT COALESCE(SUM(f.community_men_count + f.community_women_count), 0) AS comm_count
            FROM dw.fact_session f
            LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
            LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
            LEFT JOIN dw.dim_program p ON p.sk_program_id = f.sk_program_id
            {where_clause}
        ) f_sum
        """,
        params * 2,
    )
    return int(row.get("total_students", 0) or 0)



def get_exposure_kpis(
    start: int | None = None,
    end: int | None = None,
    region: str | None = None,
    program: str | None = None,
) -> dict[str, float]:
    where_clause, params = _base_where(start, end, region, program)
    row = fetch_one(
        f"""
        SELECT
            (
                (SELECT COALESCE(SUM(total_exposure_count), 0) FROM dw.fact_attendance_exposure fae 
                 LEFT JOIN dw.dim_date d ON d.date_id = fae.date_id 
                 LEFT JOIN dw.dim_geography g ON g.sk_geography_id = fae.sk_geography_id 
                 LEFT JOIN dw.dim_program p ON p.sk_program_id = fae.sk_program_id {where_clause})
                +
                (SELECT COALESCE(SUM(community_men_count + community_women_count), 0) FROM dw.fact_session f
                 LEFT JOIN dw.dim_date d ON d.date_id = f.date_id 
                 LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id 
                 LEFT JOIN dw.dim_program p ON p.sk_program_id = f.sk_program_id {where_clause})
            ) AS total_students,
            COALESCE(SUM(f.no_of_teachers_participated), 0) AS teachers_reached,
            (SELECT COALESCE(AVG(total_exposure_count), 0) FROM dw.fact_attendance_exposure fae 
             LEFT JOIN dw.dim_date d ON d.date_id = fae.date_id 
             LEFT JOIN dw.dim_geography g ON g.sk_geography_id = fae.sk_geography_id 
             LEFT JOIN dw.dim_program p ON p.sk_program_id = fae.sk_program_id {where_clause}) AS avg_students_per_exposure
        FROM dw.fact_session f
        LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN dw.dim_program p ON p.sk_program_id = f.sk_program_id
        {where_clause}
        """,
        params * 4,
    )
    return {
        "total_students": int(row.get("total_students", 0) or 0),
        "teachers_reached": int(row.get("teachers_reached", 0) or 0),
        "avg_students_per_exposure": round(float(row.get("avg_students_per_exposure", 0) or 0), 1),
    }



def get_program_metrics(
    start: int | None = None,
    end: int | None = None,
    region: str | None = None,
    program: str | None = None,
    limit: int = 20,
) -> list[dict]:
    where_clause, params = _base_where(start, end, region, program)
    rows = fetch_all(
        f"""
        SELECT
            COALESCE(p.program_name, 'Unknown') AS label,
            COALESCE(SUM(fae.total_exposure_count), 0) AS value
        FROM dw.fact_attendance_exposure fae
        LEFT JOIN dw.dim_date d ON d.date_id = fae.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = fae.sk_geography_id
        LEFT JOIN dw.dim_program p ON p.sk_program_id = fae.sk_program_id
        {where_clause}
        GROUP BY p.program_name
        ORDER BY value DESC, label
        LIMIT %s
        """,
        [*params, limit],
    )
    return [{"label": row["label"], "value": float(row["value"])} for row in rows]



def get_program_distribution(
    start: int | None = None,
    end: int | None = None,
    region: str | None = None,
    program: str | None = None,
) -> list[dict]:
    where_clause, params = _base_where(start, end, region, program)
    rows = fetch_all(
        f"""
        SELECT
            COALESCE(p.program_name, 'Unknown') AS label,
            COUNT(*) AS value
        FROM dw.fact_attendance_exposure fae
        LEFT JOIN dw.dim_date d ON d.date_id = fae.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = fae.sk_geography_id
        LEFT JOIN dw.dim_program p ON p.sk_program_id = fae.sk_program_id
        {where_clause}
        GROUP BY p.program_name
        ORDER BY value DESC, label
        LIMIT 20
        """,
        params,
    )
    return [{"label": row["label"], "value": float(row["value"])} for row in rows]


def get_gender_split(
    start: int | None = None,
    end: int | None = None,
    region: str | None = None,
    program: str | None = None,
) -> dict[str, int]:
    where_clause, params = _base_where(start, end, region, program)
    row = fetch_one(
        f"""
        SELECT
            COALESCE(SUM(fae.girls_count), 0) AS girls,
            COALESCE(SUM(fae.boys_count), 0) AS boys
        FROM dw.fact_attendance_exposure fae
        LEFT JOIN dw.dim_date d ON d.date_id = fae.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = fae.sk_geography_id
        LEFT JOIN dw.dim_program p ON p.sk_program_id = fae.sk_program_id
        {where_clause}
        """,
        params,
    )
    return {"girls": int(row.get("girls", 0) or 0), "boys": int(row.get("boys", 0) or 0)}



def get_top_schools(
    start: int | None = None,
    end: int | None = None,
    region: str | None = None,
    program: str | None = None,
    limit: int = 5,
) -> list[dict]:
    where_clause, params = _base_where(start, end, region, program)
    rows = fetch_all(
        f"""
        SELECT
            COALESCE(s.school_name, 'Unknown') AS label,
            COALESCE(g.region_name, 'Unknown') AS state,
            COALESCE(g.area_name, 'Unknown') AS area,
            COALESCE(SUM(fae.total_exposure_count), 0) AS value
        FROM dw.fact_attendance_exposure fae
        LEFT JOIN dw.dim_school s ON s.sk_school_id = fae.sk_school_id
        LEFT JOIN dw.dim_date d ON d.date_id = fae.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = fae.sk_geography_id
        LEFT JOIN dw.dim_program p ON p.sk_program_id = fae.sk_program_id
        {where_clause}
        GROUP BY s.school_name, g.region_name, g.area_name
        ORDER BY value DESC, label
        LIMIT %s
        """,
        [*params, limit],
    )
    return [
        {"label": row["label"], "subtitle": f"{row['state']} - {row['area']}", "value": float(row["value"] or 0)}
        for row in rows
    ]





def get_cohort_breakdown(
    start: int | None = None,
    end: int | None = None,
    region: str | None = None,
    program: str | None = None,
) -> list[dict]:
    where_clause, params = _base_where(start, end, region, program)
    row = fetch_one(
        f"""
        SELECT
            (SELECT COALESCE(SUM(total_exposure_count), 0) FROM dw.fact_attendance_exposure fae 
             LEFT JOIN dw.dim_date d ON d.date_id = fae.date_id 
             LEFT JOIN dw.dim_geography g ON g.sk_geography_id = fae.sk_geography_id 
             LEFT JOIN dw.dim_program p ON p.sk_program_id = fae.sk_program_id {where_clause}) AS students,
            COALESCE(SUM(f.no_of_teachers_participated), 0) AS teachers
        FROM dw.fact_session f
        LEFT JOIN dw.dim_date d ON d.date_id = f.date_id
        LEFT JOIN dw.dim_geography g ON g.sk_geography_id = f.sk_geography_id
        LEFT JOIN dw.dim_program p ON p.sk_program_id = f.sk_program_id
        {where_clause}
        """,
        params * 2,
    )
    return [
        {"label": "Students", "value": float(row.get("students", 0) or 0)},
        {"label": "Teachers", "value": float(row.get("teachers", 0) or 0)},
    ]



def get_program_options() -> list[str]:
    rows = fetch_all(
        """
        SELECT DISTINCT p.program_name
        FROM dw.dim_program p
        INNER JOIN dw.fact_session f ON p.sk_program_id = f.sk_program_id
        WHERE p.program_name IS NOT NULL
        ORDER BY p.program_name
        """
    )

    return [str(row["program_name"]) for row in rows if row.get("program_name")]
