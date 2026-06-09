-- Table: imt_sols_catalyzer_circle
CREATE TABLE imt_sols_catalyzer_circle (
    imt_sols_catalyzer_circle_id TEXT,
    code TEXT,
    name TEXT,
    is_deleted TEXT
);

-- Table: imt_sols_catalyzer_circle_mapping
CREATE TABLE imt_sols_catalyzer_circle_mapping (
    imt_sols_catalyzer_circle_mapping_id TEXT,
    is_deleted TEXT,
    user_id TEXT,
    circle_id TEXT
);

-- Table: imt_sols_category
CREATE TABLE imt_sols_category (
    imt_sols_category_id TEXT,
    code TEXT,
    name TEXT
);

-- Table: imt_sols_grading_cutoff
CREATE TABLE imt_sols_grading_cutoff (
    imt_sols_grading_cutoff_id TEXT,
    version_num TEXT,
    min_score_range TEXT,
    max_score_range TEXT,
    grade TEXT,
    is_deleted TEXT
);

-- Table: imt_sols_options
CREATE TABLE imt_sols_options (
    imt_sols_options_id TEXT,
    option_code TEXT,
    option_text TEXT,
    option_order_no TEXT,
    score TEXT,
    option_info TEXT,
    is_deleted TEXT,
    sols_question_id TEXT
);

-- Table: imt_sols_parameter
CREATE TABLE imt_sols_parameter (
    imt_sols_parameter_id TEXT,
    version_num TEXT,
    code TEXT,
    name TEXT,
    order_no TEXT,
    is_deleted TEXT
);

-- Table: imt_sols_program_category
CREATE TABLE imt_sols_program_category (
    imt_sols_program_category_id TEXT,
    code TEXT,
    name TEXT,
    is_deleted TEXT
);

-- Table: imt_sols_questions
CREATE TABLE imt_sols_questions (
    imt_sols_questions_id TEXT,
    version_num TEXT,
    question_code TEXT,
    question_text TEXT,
    question_order_no TEXT,
    question_info TEXT,
    is_deleted TEXT,
    sols_category_id TEXT,
    sols_parameter_id TEXT,
    sols_program_category_id TEXT
);

-- Table: imt_sols_round
CREATE TABLE imt_sols_round (
    imt_sols_round_id TEXT,
    code TEXT,
    name TEXT,
    is_deleted TEXT,
    visit_type TEXT
);

-- Table: imt_sols_round_role_mapping
CREATE TABLE imt_sols_round_role_mapping (
    imt_sols_round_role_mapping_id TEXT,
    is_deleted TEXT,
    observation_round_id TEXT,
    role_id TEXT
);

-- Table: mst_activity_type
CREATE TABLE mst_activity_type (
    mst_activity_type_id TEXT,
    code TEXT,
    name TEXT,
    additional_info TEXT,
    iflg TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT,
    is_adhoc TEXT
);

-- Table: mst_adhoc_session_feedback_answers
CREATE TABLE mst_adhoc_session_feedback_answers (
    mst_adhoc_session_feedback_answers_id TEXT,
    instructor_id TEXT,
    program_id TEXT,
    activity_type_id TEXT,
    answer_obj TEXT,
    date TEXT,
    exposures TEXT,
    is_overdue TEXT
);

-- Table: mst_area
CREATE TABLE mst_area (
    mst_area_id TEXT,
    name TEXT,
    code TEXT,
    iflg TEXT,
    region_id TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT
);

-- Table: mst_category
CREATE TABLE mst_category (
    mst_category_id TEXT,
    code TEXT,
    name TEXT,
    order_no TEXT
);

-- Table: mst_class
CREATE TABLE mst_class (
    mst_class_id TEXT,
    name TEXT,
    grade_id TEXT,
    section_id TEXT,
    medium_id TEXT,
    type_id TEXT,
    code TEXT,
    iflg TEXT,
    school_id TEXT,
    boys TEXT,
    girls TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT
);

-- Table: mst_class_2017_2018
CREATE TABLE mst_class_2017_2018 (
    mst_class_2017_2018_id TEXT,
    name TEXT,
    code TEXT,
    iflg TEXT,
    school_id TEXT,
    boys TEXT,
    girls TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT
);

-- Table: mst_class_2018_2019
CREATE TABLE mst_class_2018_2019 (
    mst_class_2018_2019_id TEXT,
    name TEXT,
    code TEXT,
    iflg TEXT,
    school_id TEXT,
    boys TEXT,
    girls TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT
);

-- Table: mst_class_2019_2020
CREATE TABLE mst_class_2019_2020 (
    mst_class_2019_2020_id TEXT,
    name TEXT,
    code TEXT,
    iflg TEXT,
    school_id TEXT,
    boys TEXT,
    girls TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT
);

-- Table: mst_class_2020_2021
CREATE TABLE mst_class_2020_2021 (
    mst_class_2020_2021_id TEXT,
    name TEXT,
    code TEXT,
    iflg TEXT,
    school_id TEXT,
    boys TEXT,
    girls TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT
);

-- Table: mst_class_2021_2022
CREATE TABLE mst_class_2021_2022 (
    mst_class_2021_2022_id TEXT,
    name TEXT,
    code TEXT,
    iflg TEXT,
    school_id TEXT,
    boys TEXT,
    girls TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT
);

-- Table: mst_class_2022_2023
CREATE TABLE mst_class_2022_2023 (
    mst_class_2022_2023_id TEXT,
    name TEXT,
    code TEXT,
    iflg TEXT,
    school_id TEXT,
    boys TEXT,
    girls TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT
);

-- Table: mst_class_2023_2024
CREATE TABLE mst_class_2023_2024 (
    mst_class_2023_2024_id TEXT,
    name TEXT,
    code TEXT,
    iflg TEXT,
    school_id TEXT,
    boys TEXT,
    girls TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT
);

-- Table: mst_class_2024_2025
CREATE TABLE mst_class_2024_2025 (
    mst_class_2024_2025_id TEXT,
    name TEXT,
    grade_id TEXT,
    section_id TEXT,
    medium_id TEXT,
    type_id TEXT,
    code TEXT,
    iflg TEXT,
    school_id TEXT,
    boys TEXT,
    girls TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT
);

-- Table: mst_class_2025_2026
CREATE TABLE mst_class_2025_2026 (
    mst_class_2025_2026_id TEXT,
    name TEXT,
    grade_id TEXT,
    section_id TEXT,
    medium_id TEXT,
    type_id TEXT,
    code TEXT,
    iflg TEXT,
    school_id TEXT,
    boys TEXT,
    girls TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT
);

-- Table: mst_class_grade
CREATE TABLE mst_class_grade (
    mst_class_grade_id TEXT,
    code TEXT,
    name TEXT,
    display_order TEXT
);

-- Table: mst_class_medium
CREATE TABLE mst_class_medium (
    class_medium_id TEXT,
    code TEXT,
    name TEXT,
    display_order TEXT
);

-- Table: mst_class_section
CREATE TABLE mst_class_section (
    mst_class_section_id TEXT,
    code TEXT,
    name TEXT,
    display_order TEXT
);

-- Table: mst_class_type
CREATE TABLE mst_class_type (
    mst_class_type_id TEXT,
    code TEXT,
    name TEXT,
    display_order TEXT
);

-- Table: mst_donor
CREATE TABLE mst_donor (
    mst_donor_id TEXT,
    name TEXT,
    code TEXT,
    iflg TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT
);

-- Table: mst_is_category
CREATE TABLE mst_is_category (
    mst_is_category_id TEXT,
    code TEXT,
    name TEXT,
    order_no TEXT
);

-- Table: mst_is_languages
CREATE TABLE mst_is_languages (
    mst_is_languages_id TEXT,
    language_code TEXT,
    language_name TEXT,
    order_no TEXT,
    is_deleted TEXT
);

-- Table: mst_is_program_type_question_mapping
CREATE TABLE mst_is_program_type_question_mapping (
    mst_is_program_type_question_mapping_id TEXT,
    version_num TEXT,
    question_order_no TEXT,
    is_deleted TEXT,
    program_type_id TEXT,
    question_id TEXT
);

-- Table: mst_is_questions
CREATE TABLE mst_is_questions (
    mst_is_questions_id TEXT,
    version_num TEXT,
    question_code TEXT,
    question_text TEXT,
    question_order_no TEXT,
    question_info TEXT,
    is_deleted TEXT,
    is_category_id TEXT
);

-- Table: mst_is_rejected_reason
CREATE TABLE mst_is_rejected_reason (
    mst_is_rejected_reason_id TEXT,
    reason_code TEXT,
    reason_text TEXT,
    order_no TEXT,
    is_deleted TEXT
);

-- Table: mst_is_status
CREATE TABLE mst_is_status (
    mst_is_status_id TEXT,
    code TEXT,
    name TEXT,
    order_no TEXT
);

-- Table: mst_languages
CREATE TABLE mst_languages (
    mst_languages_id TEXT,
    language_code TEXT,
    language_name TEXT,
    order_no TEXT,
    is_deleted TEXT
);

-- Table: mst_modules
CREATE TABLE mst_modules (
    mst_modules_id TEXT,
    name TEXT,
    code TEXT,
    is_webapp TEXT,
    iflg TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT
);

-- Table: mst_month
CREATE TABLE mst_month (
    mst_month_id TEXT,
    month_no TEXT,
    year TEXT,
    start_date TEXT,
    end_date TEXT
);

-- Table: mst_oppurtunity_category
CREATE TABLE mst_oppurtunity_category (
    mst_oppurtunity_category_id TEXT,
    name TEXT
);

-- Table: mst_oppurtunity_type
CREATE TABLE mst_oppurtunity_type (
    mst_oppurtunity_type_id TEXT,
    name TEXT
);

-- Table: mst_periodicity
CREATE TABLE mst_periodicity (
    mst_periodicity_id TEXT,
    code TEXT,
    name TEXT,
    order_no TEXT
);

-- Table: mst_program_type
CREATE TABLE mst_program_type (
    mst_program_type_id TEXT,
    name TEXT,
    code TEXT,
    iflg TEXT,
    activity_flg TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT,
    rank_program_type TEXT
);

-- Table: mst_quarter
CREATE TABLE mst_quarter (
    mst_quarter_id TEXT,
    quarter_no TEXT,
    year TEXT,
    start_date TEXT,
    end_date TEXT
);

-- Table: mst_questions
CREATE TABLE mst_questions (
    mst_questions_id TEXT,
    code TEXT,
    iflg TEXT,
    description TEXT,
    topic_id TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT
);

-- Table: mst_region
CREATE TABLE mst_region (
    mst_region_id TEXT,
    name TEXT,
    code TEXT,
    iflg TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT,
    rank_region TEXT
);

-- Table: mst_role
CREATE TABLE mst_role (
    mst_role_id TEXT,
    name TEXT,
    code TEXT,
    iflg TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT
);

-- Table: mst_school
CREATE TABLE mst_school (
    mst_school_id TEXT,
    name TEXT,
    code TEXT,
    udise_code TEXT,
    udise_name TEXT,
    iflg TEXT,
    contact_name TEXT,
    address TEXT,
    pincode TEXT,
    phone_1 TEXT,
    phone_2 TEXT,
    phone_3 TEXT,
    email_1 TEXT,
    email_2 TEXT,
    latitude TEXT,
    area_id TEXT,
    state_management TEXT,
    national_management TEXT,
    school_category TEXT,
    school_type TEXT,
    location TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT,
    longitude TEXT,
    "Unnamed: 27" TEXT,
    "Unnamed: 28" TEXT
);

-- Table: mst_school_2017_2018
CREATE TABLE mst_school_2017_2018 (
    mst_school_2017_2018_id TEXT,
    name TEXT,
    code TEXT,
    udise_code TEXT,
    udise_name TEXT,
    iflg TEXT,
    contact_name TEXT,
    address TEXT,
    pincode TEXT,
    phone_1 TEXT,
    phone_2 TEXT,
    phone_3 TEXT,
    email_1 TEXT,
    email_2 TEXT,
    area_id TEXT,
    state_management TEXT,
    national_management TEXT,
    school_category TEXT,
    school_type TEXT,
    location TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT
);

-- Table: mst_school_2018_2019
CREATE TABLE mst_school_2018_2019 (
    mst_school_2018_2019_id TEXT,
    name TEXT,
    code TEXT,
    udise_code TEXT,
    udise_name TEXT,
    iflg TEXT,
    contact_name TEXT,
    address TEXT,
    pincode TEXT,
    phone_1 TEXT,
    phone_2 TEXT,
    phone_3 TEXT,
    email_1 TEXT,
    email_2 TEXT,
    area_id TEXT,
    state_management TEXT,
    national_management TEXT,
    school_category TEXT,
    school_type TEXT,
    location TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT
);

-- Table: mst_school_2019_2020
CREATE TABLE mst_school_2019_2020 (
    mst_school_2019_2020_id TEXT,
    name TEXT,
    code TEXT,
    udise_code TEXT,
    udise_name TEXT,
    iflg TEXT,
    contact_name TEXT,
    address TEXT,
    pincode TEXT,
    phone_1 TEXT,
    phone_2 TEXT,
    phone_3 TEXT,
    email_1 TEXT,
    email_2 TEXT,
    area_id TEXT,
    state_management TEXT,
    national_management TEXT,
    school_category TEXT,
    school_type TEXT,
    location TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT
);

-- Table: mst_school_2020_2021
CREATE TABLE mst_school_2020_2021 (
    mst_school_2020_2021_id TEXT,
    name TEXT,
    code TEXT,
    udise_code TEXT,
    udise_name TEXT,
    iflg TEXT,
    contact_name TEXT,
    address TEXT,
    pincode TEXT,
    phone_1 TEXT,
    phone_2 TEXT,
    phone_3 TEXT,
    email_1 TEXT,
    email_2 TEXT,
    area_id TEXT,
    state_management TEXT,
    national_management TEXT,
    school_category TEXT,
    school_type TEXT,
    location TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT
);

-- Table: mst_school_2021_2022
CREATE TABLE mst_school_2021_2022 (
    mst_school_2021_2022_id TEXT,
    name TEXT,
    code TEXT,
    udise_code TEXT,
    udise_name TEXT,
    iflg TEXT,
    contact_name TEXT,
    address TEXT,
    pincode TEXT,
    phone_1 TEXT,
    phone_2 TEXT,
    phone_3 TEXT,
    email_1 TEXT,
    email_2 TEXT,
    area_id TEXT,
    state_management TEXT,
    national_management TEXT,
    school_category TEXT,
    school_type TEXT,
    location TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT
);

-- Table: mst_school_2022_2023
CREATE TABLE mst_school_2022_2023 (
    mst_school_2022_2023_id TEXT,
    name TEXT,
    code TEXT,
    udise_code TEXT,
    udise_name TEXT,
    iflg TEXT,
    contact_name TEXT,
    address TEXT,
    pincode TEXT,
    phone_1 TEXT,
    phone_2 TEXT,
    phone_3 TEXT,
    email_1 TEXT,
    email_2 TEXT,
    area_id TEXT,
    state_management TEXT,
    national_management TEXT,
    school_category TEXT,
    school_type TEXT,
    location TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT
);

-- Table: mst_school_2023_2024
CREATE TABLE mst_school_2023_2024 (
    mst_school_2023_2024_id TEXT,
    name TEXT,
    code TEXT,
    udise_code TEXT,
    udise_name TEXT,
    iflg TEXT,
    contact_name TEXT,
    address TEXT,
    pincode TEXT,
    phone_1 TEXT,
    phone_2 TEXT,
    phone_3 TEXT,
    email_1 TEXT,
    email_2 TEXT,
    area_id TEXT,
    state_management TEXT,
    national_management TEXT,
    school_category TEXT,
    school_type TEXT,
    location TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT
);

-- Table: mst_school_2024_2025
CREATE TABLE mst_school_2024_2025 (
    mst_school_2024_2025_id TEXT,
    name TEXT,
    code TEXT,
    udise_code TEXT,
    udise_name TEXT,
    iflg TEXT,
    contact_name TEXT,
    address TEXT,
    pincode TEXT,
    phone_1 TEXT,
    phone_2 TEXT,
    phone_3 TEXT,
    email_1 TEXT,
    email_2 TEXT,
    latitude TEXT,
    area_id TEXT,
    state_management TEXT,
    national_management TEXT,
    school_category TEXT,
    school_type TEXT,
    location TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT,
    longitude TEXT
);

-- Table: mst_school_2025_2026
CREATE TABLE mst_school_2025_2026 (
    mst_school_2025_2026_id TEXT,
    name TEXT,
    code TEXT,
    udise_code TEXT,
    udise_name TEXT,
    iflg TEXT,
    contact_name TEXT,
    address TEXT,
    pincode TEXT,
    phone_1 TEXT,
    phone_2 TEXT,
    phone_3 TEXT,
    email_1 TEXT,
    email_2 TEXT,
    latitude TEXT,
    area_id TEXT,
    state_management TEXT,
    national_management TEXT,
    school_category TEXT,
    school_type TEXT,
    location TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT,
    longitude TEXT
);

-- Table: mst_school_type
CREATE TABLE mst_school_type (
    mst_school_type_id TEXT,
    code TEXT,
    name TEXT,
    display_order TEXT
);

-- Table: mst_section
CREATE TABLE mst_section (
    mst_section_id TEXT,
    name TEXT,
    code TEXT,
    iflg TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT
);

-- Table: mst_shift
CREATE TABLE mst_shift (
    mst_shift_id TEXT,
    name TEXT,
    code TEXT,
    additional_info TEXT,
    iflg TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT
);

-- Table: mst_state
CREATE TABLE mst_state (
    mst_state_id TEXT,
    name TEXT,
    code TEXT,
    iflg TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT,
    state_manager TEXT
);

-- Table: mst_subject
CREATE TABLE mst_subject (
    mst_subject_id TEXT,
    name TEXT,
    code TEXT,
    iflg TEXT,
    description TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT
);

-- Table: mst_topic
CREATE TABLE mst_topic (
    mst_topic_id TEXT,
    iflg TEXT,
    description TEXT,
    subject_id TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT
);

-- Table: mst_user
CREATE TABLE mst_user (
    mst_user_id TEXT,
    name TEXT,
    code TEXT,
    iflg TEXT,
    role_id TEXT,
    report_id TEXT,
    contact_number TEXT,
    address TEXT,
    pass TEXT,
    email TEXT,
    region_id TEXT,
    area_id TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT,
    base_program_id TEXT,
    donor_id TEXT,
    circle_id TEXT,
    has_b_ed_degree TEXT,
    has_d_ed_degree TEXT,
    joining_date TEXT,
    pg_degree TEXT,
    ug_degree TEXT
);

-- Table: mst_vehicle
CREATE TABLE mst_vehicle (
    mst_vehicle_id TEXT,
    vehicle_name TEXT,
    vehicle_number TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT,
    program_id TEXT,
    area_id TEXT
);

-- Table: mst_volunteer_assignment
CREATE TABLE mst_volunteer_assignment (
    mst_volunteer_assignment_id TEXT,
    engagement_no TEXT,
    start_date TEXT,
    end_date TEXT,
    no_of_sessions TEXT,
    no_of_hours_commited TEXT,
    status_date TEXT,
    class_id TEXT,
    lms_status_id TEXT,
    opportunity_id TEXT,
    school_id TEXT,
    status_id TEXT,
    subject_id TEXT,
    volunteer_id TEXT
);

-- Table: mst_volunteer_assignment_lms_status
CREATE TABLE mst_volunteer_assignment_lms_status (
    mst_volunteer_assignment_lms_status_id TEXT,
    name TEXT
);

-- Table: mst_volunteer_assignment_status
CREATE TABLE mst_volunteer_assignment_status (
    mst_volunteer_assignment_status_id TEXT,
    name TEXT,
    order_no TEXT
);

-- Table: mst_volunteer_assignment_status_history
CREATE TABLE mst_volunteer_assignment_status_history (
    mst_volunteer_assignment_status_history_id TEXT,
    status_date TEXT,
    volunteer_assignment_id TEXT,
    volunteer_assignment_status_id TEXT
);

-- Table: mst_volunteer_docs
CREATE TABLE mst_volunteer_docs (
    mst_volunteer_docs_id TEXT,
    name TEXT,
    display_name TEXT,
    doc_no TEXT,
    description TEXT,
    verification_required TEXT,
    relevant_for_teaching TEXT,
    relevant_for_nonteaching TEXT,
    link TEXT,
    communication_group TEXT
);

-- Table: mst_volunteer_feedback_options
CREATE TABLE mst_volunteer_feedback_options (
    mst_volunteer_feedback_options_id TEXT,
    option_order TEXT,
    option_text TEXT,
    option_info TEXT,
    is_deleted TEXT,
    volunteer_feedback_question_id TEXT
);

-- Table: mst_volunteer_feedback_questions
CREATE TABLE mst_volunteer_feedback_questions (
    mst_volunteer_feedback_questions_id TEXT,
    feedback_version TEXT,
    question_order TEXT,
    question_text TEXT,
    question_info TEXT,
    is_deleted TEXT
);

-- Table: mst_volunteer_occupation_types
CREATE TABLE mst_volunteer_occupation_types (
    mst_volunteer_occupation_types_id TEXT,
    name TEXT
);

-- Table: mst_week
CREATE TABLE mst_week (
    mst_week_id TEXT,
    week_no TEXT,
    year TEXT,
    start_date TEXT,
    end_date TEXT
);

-- Table: rpt_adhoc_feedback
CREATE TABLE rpt_adhoc_feedback (
    location_id TEXT,
    topic_id TEXT,
    instructor_id TEXT,
    program_id TEXT,
    activity_type_id TEXT,
    date TEXT,
    session_duration_id TEXT,
    no_of_men TEXT,
    no_of_women TEXT,
    no_of_model_demonstrated TEXT,
    no_of_girls TEXT,
    no_of_boys TEXT,
    details TEXT,
    village TEXT,
    id TEXT,
    adhoc_id TEXT
);

-- Table: rpt_class
CREATE TABLE rpt_class (
    rpt_class_id TEXT,
    session_id TEXT,
    class_id TEXT,
    section_id TEXT,
    boys TEXT,
    girls TEXT,
    name TEXT,
    section_name TEXT
);

-- Table: rpt_feedback
CREATE TABLE rpt_feedback (
    rpt_feedback_id TEXT,
    session_id TEXT,
    subject_id TEXT,
    subject_name TEXT,
    topic_id TEXT,
    topic_name TEXT,
    demo_session TEXT,
    hands_on_session TEXT,
    no_of_guest__others TEXT,
    session_duration TEXT,
    no_of_teachers TEXT,
    concept_id TEXT,
    concept_name TEXT,
    location TEXT,
    no_of_girls TEXT,
    no_of_boys TEXT,
    no_of_participating_school TEXT,
    school_id TEXT,
    school_name TEXT,
    no_of_young_instructor TEXT,
    no_of_model_displayed TEXT,
    details TEXT,
    no_of_teacher_visited TEXT,
    no_of_school_visited TEXT,
    village TEXT,
    location_name TEXT,
    no_of_men TEXT,
    no_of_women TEXT,
    mode_of_engagement TEXT
);

-- Table: rpt_feedback_activity
CREATE TABLE rpt_feedback_activity (
    rpt_feedback_activity_id TEXT,
    session_id TEXT,
    activity_id TEXT,
    name TEXT
);

-- Table: rpt_feedback_covered_topics
CREATE TABLE rpt_feedback_covered_topics (
    rpt_feedback_covered_topics_id TEXT,
    session_id TEXT,
    covered_topic_id TEXT,
    name TEXT
);

-- Table: rpt_feedback_digital_literacy
CREATE TABLE rpt_feedback_digital_literacy (
    rpt_feedback_digital_literacy_id TEXT,
    session_id TEXT,
    digital_literacy_id TEXT,
    name TEXT
);

-- Table: rpt_feedback_leadership_activity
CREATE TABLE rpt_feedback_leadership_activity (
    rpt_feedback_leadership_activity_id TEXT,
    session_id TEXT,
    leadership_activity_id TEXT,
    name TEXT
);

-- Table: rpt_feedback_science_concept
CREATE TABLE rpt_feedback_science_concept (
    rpt_feedback_science_concept_id TEXT,
    session_id TEXT,
    science_concept_id TEXT,
    name TEXT
);

-- Table: rpt_feedback_topics
CREATE TABLE rpt_feedback_topics (
    rpt_feedback_topics_id TEXT,
    session_id TEXT,
    topic_id TEXT,
    name TEXT
);

-- Table: rpt_portal_arealead_summary
CREATE TABLE rpt_portal_arealead_summary (
    rpt_portal_arealead_summary_id TEXT,
    region_id TEXT,
    region_name TEXT,
    area_id TEXT,
    area_name TEXT,
    area_lead TEXT,
    school_session_exposure_target TEXT,
    school_session_exposures_covered TEXT,
    science_fair_target TEXT,
    no_of_young_instructors TEXT,
    science_fair_count TEXT,
    community_visit_target TEXT,
    community_visit_covered TEXT,
    ttp_target TEXT,
    ttp_covered TEXT,
    year TEXT,
    month TEXT
);

-- Table: rpt_portal_attendance_report
CREATE TABLE rpt_portal_attendance_report (
    rpt_portal_attendance_report_id TEXT,
    region_id TEXT,
    region_name TEXT,
    area_id TEXT,
    area_name TEXT,
    instructor_id TEXT,
    instructor_code TEXT,
    instructor_name TEXT,
    program_name TEXT,
    no_of_days_worked TEXT,
    year TEXT,
    month TEXT
);

-- Table: rpt_portal_instructor_details
CREATE TABLE rpt_portal_instructor_details (
    rpt_portal_instructor_details_id TEXT,
    instructor_id TEXT,
    instructor_name TEXT,
    date TEXT,
    activity_name TEXT,
    school_name TEXT,
    class_name TEXT,
    topic_name TEXT,
    boys TEXT,
    girls TEXT,
    teachers TEXT,
    others TEXT,
    total TEXT
);

-- Table: rpt_portal_instructor_summary
CREATE TABLE rpt_portal_instructor_summary (
    rpt_portal_instructor_summary_id TEXT,
    area_id TEXT,
    area_name TEXT,
    instructor_id TEXT,
    instructor_name TEXT,
    days_count TEXT,
    school_session_count TEXT,
    school_session_exposure TEXT,
    science_fair_count TEXT,
    science_fair_exposure TEXT,
    young_instructor_count TEXT,
    young_instructor_exposure TEXT,
    community_visit_count TEXT,
    community_visit_exposure TEXT,
    teacher_training_program_count TEXT,
    training_meeting_count TEXT,
    year TEXT,
    month TEXT,
    yi_exposure_training TEXT,
    teacher_training_exposure TEXT,
    special_program_count TEXT,
    special_program_exposure TEXT,
    is_deleted TEXT,
    summer_winter_camp_exposure TEXT
);

-- Table: rpt_portal_overview
CREATE TABLE rpt_portal_overview (
    rpt_portal_overview_id TEXT,
    region_id TEXT,
    region_name TEXT,
    instructor_count TEXT,
    driver_count TEXT,
    ml_count TEXT,
    lob_count TEXT,
    sc_count TEXT,
    yil_count TEXT,
    lib_count TEXT
);

-- Table: rpt_portal_program_wise
CREATE TABLE rpt_portal_program_wise (
    rpt_portal_program_wise_id TEXT,
    region_id TEXT,
    region_name TEXT,
    area_id TEXT,
    area_name TEXT,
    program_id TEXT,
    program_name TEXT,
    total_no_of_days_worked TEXT,
    school_sessions TEXT,
    average_session_duration TEXT,
    target_exposures TEXT,
    school_visit_exposures TEXT,
    sf_session_target TEXT,
    sf_count TEXT,
    sf_exposures TEXT,
    yi_training_target TEXT,
    yi_training_session TEXT,
    yi_training_exposures TEXT,
    cv_target TEXT,
    cv_sessions TEXT,
    cv_exposures TEXT,
    ttp_sessions TEXT,
    training_meeting TEXT,
    total_exposure TEXT,
    total_school TEXT,
    no_of_schools TEXT,
    program_type_name TEXT,
    year TEXT,
    month TEXT,
    donor_id TEXT,
    donor_name TEXT,
    donor_exposure_target TEXT,
    sp_target TEXT,
    sp_sessions TEXT,
    sp_exposures TEXT,
    ttp_days_target TEXT,
    summer_winter_camp_exposures TEXT
);

-- Table: rpt_portal_program_wise_summary
CREATE TABLE rpt_portal_program_wise_summary (
    rpt_portal_program_wise_summary_id TEXT,
    school_id TEXT,
    school_name TEXT,
    class_id TEXT,
    class_name TEXT,
    section_id TEXT,
    section_name TEXT,
    program_id TEXT,
    program_name TEXT,
    school_session_count TEXT,
    school_session_exposure_count TEXT,
    full_year TEXT,
    month_number TEXT
);

-- Table: rpt_portal_region_summary
CREATE TABLE rpt_portal_region_summary (
    rpt_portal_region_summary_id TEXT,
    region_id TEXT,
    region_name TEXT,
    school_visit_target TEXT,
    school_visit_exposures TEXT,
    science_fair_target TEXT,
    science_fair__count TEXT,
    young_instructor_count TEXT,
    community_visist_target TEXT,
    community_visist_count TEXT,
    teacher_training_program_target TEXT,
    teacher_training_program_count TEXT,
    year TEXT,
    month TEXT,
    program_type_id TEXT,
    program_type TEXT
);

-- Table: rpt_portal_vehicle_log
CREATE TABLE rpt_portal_vehicle_log (
    rpt_portal_vehicle_log_id TEXT,
    region_id TEXT,
    region_name TEXT,
    area_id TEXT,
    area_name TEXT,
    program_id TEXT,
    program_name TEXT,
    vehicle_number TEXT,
    driver_name TEXT,
    opening_log TEXT,
    closing_log TEXT,
    total_fuel TEXT,
    year TEXT,
    month TEXT,
    user_id TEXT,
    vehicle_id TEXT,
    km_runs TEXT,
    milage TEXT,
    donor_id TEXT,
    donor_name TEXT
);

-- Table: rpt_portal_workdays
CREATE TABLE rpt_portal_workdays (
    rpt_portal_workdays_id TEXT,
    region_id TEXT,
    region_name TEXT,
    area_name TEXT,
    instructor_name TEXT,
    program_name TEXT,
    program_id TEXT,
    school_session TEXT,
    science_fair TEXT,
    young_instructor_training TEXT,
    summer_winter_camp TEXT,
    community_visit TEXT,
    meeting_training TEXT,
    teacher_training_program TEXT,
    special_program TEXT,
    lib_rotation TEXT,
    total TEXT,
    instructor_id TEXT,
    year TEXT,
    month TEXT,
    area_id TEXT,
    psm_date TEXT,
    is_deleted TEXT
);

-- Table: txn_daily_data
CREATE TABLE txn_daily_data (
    txn_daily_data_id TEXT,
    vehicle_id TEXT,
    psm_id TEXT,
    assigned_driver TEXT,
    driver_contact_no TEXT,
    vehicle_used_flag TEXT,
    vehicle_not_used_reason TEXT,
    open_reading TEXT,
    closed_reading TEXT,
    fuel_price TEXT,
    instructor_id TEXT,
    date TEXT,
    fuel_quantity TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT
);

-- Table: txn_feedback_answer
CREATE TABLE txn_feedback_answer (
    txn_feedback_answer_id TEXT,
    session_id TEXT,
    answer_obj TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT,
    is_overdue TEXT
);

-- Table: txn_feedback_exposure
CREATE TABLE txn_feedback_exposure (
    txn_feedback_exposure_id TEXT,
    session_id TEXT,
    class_id TEXT,
    section TEXT,
    boys TEXT,
    girls TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT
);

-- Table: txn_interviewer_header
CREATE TABLE txn_interviewer_header (
    txn_interviewer_header_id TEXT,
    student_name TEXT,
    student_rollno TEXT,
    date_of_interview TEXT,
    created_date TEXT,
    submitted_date TEXT,
    assigned_date TEXT,
    refined_date TEXT,
    accepted_rejected_date TEXT,
    published_date TEXT,
    status TEXT,
    rejected_reason TEXT,
    area_id TEXT,
    class_id TEXT,
    donor_id TEXT,
    author_id TEXT,
    program_id TEXT,
    region_id TEXT,
    school_id TEXT,
    writer_id TEXT,
    interview_language TEXT,
    sessions_conducted_count TEXT,
    uploaded_docs TEXT,
    student_gender TEXT
);

-- Table: txn_is_interview_response
CREATE TABLE txn_is_interview_response (
    txn_is_interview_response_id TEXT,
    version_num TEXT,
    original_response TEXT,
    refined_response TEXT,
    header_id TEXT,
    is_question_id TEXT,
    refine_status TEXT
);

-- Table: txn_ovv_assignments
CREATE TABLE txn_ovv_assignments (
    txn_ovv_assignments_id TEXT,
    user_id TEXT,
    school_id TEXT,
    start_date TEXT,
    end_date TEXT,
    is_deleted TEXT,
    created_on TEXT,
    modified_on TEXT
);

-- Table: txn_program
CREATE TABLE txn_program (
    txn_program_id TEXT,
    donor_id TEXT,
    area_id TEXT,
    program_type_id TEXT,
    start_date TEXT,
    end_date TEXT,
    name TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT,
    donor_exposure_target TEXT,
    operational_exposure_target TEXT,
    total_workdays_target TEXT,
    school_session_days_target TEXT,
    school_session_exposure_target TEXT,
    community_visit_days_target TEXT,
    community_visit_exposure_target TEXT,
    sciece_fair_days_target TEXT,
    science_fair_exposure_target TEXT,
    ttp_days_target TEXT,
    ttp_exposure_target TEXT,
    sp_days_target TEXT,
    sp_exposure_target TEXT,
    ov_days_target TEXT,
    ov_exposure_target TEXT,
    yil_days_target TEXT,
    yil_exposure_target TEXT,
    instructor_capacity TEXT,
    location TEXT,
    periodicity_id TEXT
);

-- Table: txn_session
CREATE TABLE txn_session (
    txn_session_id TEXT,
    instructor_id TEXT,
    program_school_mapped_id TEXT,
    shift_id TEXT,
    date TEXT,
    additional_info TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT,
    is_overdue TEXT
);

-- Table: txn_sols_observations_detail
CREATE TABLE txn_sols_observations_detail (
    txn_sols_observations_detail_id TEXT,
    version_num TEXT,
    rating TEXT,
    text_answer TEXT,
    remarks_text TEXT,
    header_id TEXT,
    sols_parameter_id TEXT,
    sols_option_id TEXT,
    sols_question_id TEXT
);

-- Table: txn_sols_observations_header
CREATE TABLE txn_sols_observations_header (
    txn_sols_observations_header_id TEXT,
    date_of_observation TEXT,
    time_of_session TEXT,
    boys TEXT,
    girls TEXT,
    guest_1 TEXT,
    guest_2 TEXT,
    guest_3 TEXT,
    experience_on_date TEXT,
    observation_start_date TEXT,
    observation_submission_date TEXT,
    score TEXT,
    grade TEXT,
    visit_no TEXT,
    score_data TEXT,
    is_submitted TEXT,
    certificate_id TEXT,
    area_id TEXT,
    instructor_id TEXT,
    observation_round TEXT,
    observer_1_id TEXT,
    observer_2_id TEXT,
    program_id TEXT,
    region_id TEXT,
    school_id TEXT,
    school_session_id TEXT,
    visit_type TEXT,
    program_category_id TEXT,
    circle_id TEXT
);

-- Table: txn_subject_lesson_plan
CREATE TABLE txn_subject_lesson_plan (
    txn_subject_lesson_plan_id TEXT,
    description TEXT,
    subject_id TEXT,
    url TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT
);

-- Table: txn_vehicle_checklist
CREATE TABLE txn_vehicle_checklist (
    txn_vehicle_checklist_id TEXT,
    vehicle_id TEXT,
    vehicle_event TEXT,
    renewed_flag TEXT,
    renewed_on TEXT,
    next_renewal_date TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT
);

-- Table: txn_vehicle_log
CREATE TABLE txn_vehicle_log (
    txn_vehicle_log_id TEXT,
    vehicle_id TEXT,
    driver_id TEXT,
    program_id TEXT,
    instructor_id TEXT,
    date TEXT,
    vehicle_used_flag TEXT,
    vehicle_not_used_reason TEXT,
    open_reading TEXT,
    closed_reading TEXT,
    fuel_price TEXT,
    fuel_quantity TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT,
    is_deleted TEXT
);

-- Table: txn_volunteer_communication_log
CREATE TABLE txn_volunteer_communication_log (
    txn_volunteer_communication_log_id TEXT,
    link TEXT,
    comm_timestamp TEXT,
    status TEXT,
    status_timestamp TEXT,
    volunteer_auth_key TEXT,
    volunteer_assignment_id TEXT,
    volunteer_doc_id TEXT
);

-- Table: txn_volunteer_documents_uploaded
CREATE TABLE txn_volunteer_documents_uploaded (
    txn_volunteer_documents_uploaded_id TEXT,
    verification_status TEXT,
    verification_timestamp TEXT,
    volunteer_assignment_id TEXT,
    volunteer_communication_id TEXT,
    volunteer_doc_id TEXT,
    document_number TEXT,
    document_year TEXT
);

-- Table: txn_volunteer_feedback_answers
CREATE TABLE txn_volunteer_feedback_answers (
    txn_volunteer_feedback_answers_id TEXT,
    submission_date TEXT,
    feedback_version TEXT,
    answer_text TEXT,
    volunteer_assignment_id TEXT,
    volunteer_feedback_option_id TEXT,
    volunteer_feedback_question_id TEXT
);

-- Table: txn_volunteer_mentor
CREATE TABLE txn_volunteer_mentor (
    txn_volunteer_mentor_id TEXT,
    name TEXT,
    mobile TEXT,
    email TEXT,
    start_date TEXT,
    end_date TEXT,
    is_active TEXT,
    volunteer_assignment_id TEXT
);

-- Table: txn_volunteer_oppurtunity
CREATE TABLE txn_volunteer_oppurtunity (
    txn_volunteer_oppurtunity_id TEXT,
    opportunity_id TEXT,
    rvc_id TEXT,
    volunteer_id TEXT,
    volunteer_assignment_id TEXT
);

-- Table: txn_volunteer_periodic_data
CREATE TABLE txn_volunteer_periodic_data (
    txn_volunteer_periodic_data_id TEXT,
    link_url TEXT,
    week_end_date TEXT,
    link_sent_date TEXT,
    response_status TEXT,
    response_date TEXT,
    boys TEXT,
    girls TEXT,
    no_of_sessions TEXT,
    preparation_hours TEXT,
    training_hours TEXT,
    session_hours TEXT,
    exposure TEXT,
    details TEXT,
    volunteer_auth_key TEXT,
    class TEXT,
    topic_name TEXT,
    mens TEXT,
    womens TEXT,
    verification_comments TEXT,
    verification_status TEXT,
    verification_timestamp TEXT,
    subject_id TEXT,
    topic_id TEXT,
    volunteer_assignment_id TEXT,
    volunteer_mentor_id TEXT,
    week_id TEXT
);


-- Table: conf_program_school_mapping
CREATE TABLE conf_program_school_mapping (
    conf_program_school_mapping_id TEXT,
    school_id TEXT,
    program_id TEXT,
    date DATE,
    activity_flg TEXT,
    activity_type_id TEXT,
    created_by TEXT,
    created_on TEXT,
    modified_on TEXT,
    modified_by TEXT
);
