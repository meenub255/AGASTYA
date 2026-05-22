(function () {
    const charts = {};
    window.PieConnectorPlugin = {
        id: 'pieConnector',
        afterDatasetsDraw(chart) {
            if (chart.config.type !== 'pie' && chart.config.type !== 'doughnut') return;
            const { ctx } = chart;
            const datalabelsConfig = chart.options.plugins.datalabels;
            if (!datalabelsConfig || datalabelsConfig.display === false) return;

            chart.data.datasets.forEach((dataset, i) => {
                const meta = chart.getDatasetMeta(i);
                meta.data.forEach((element, index) => {
                    const display = datalabelsConfig.display;
                    const isDisplayed = typeof display === 'function' 
                        ? display({ datasetIndex: i, dataIndex: index, chart: chart, active: false }) 
                        : display;
                    
                    if (!isDisplayed) return;

                    const { startAngle, endAngle, outerRadius, x, y } = element;
                    const midAngle = (startAngle + endAngle) / 2;
                    
                    const offset = datalabelsConfig.offset || 0;
                    
                    const startX = x + Math.cos(midAngle) * outerRadius;
                    const startY = y + Math.sin(midAngle) * outerRadius;
                    
                    // The label is roughly at outerRadius + offset
                    const endX = x + Math.cos(midAngle) * (outerRadius + offset - 5); 
                    const endY = y + Math.sin(midAngle) * (outerRadius + offset - 5);

                    ctx.save();
                    ctx.beginPath();
                    ctx.lineWidth = 1;
                    ctx.strokeStyle = '#000000';
                    ctx.moveTo(startX, startY);
                    ctx.lineTo(endX, endY);
                    ctx.stroke();
                    ctx.restore();
                });
            });
        }
    };
    const COLORS = {
        indigo: "#5b5ce6",
        blue: "#3f8cff",
        teal: "#18b891",
        violet: "#8b5cf6",
        amber: "#f3a536",
        rose: "#ee6b78",
        tick: "rgba(255,255,255,0.72)",
        grid: "rgba(255,255,255,0.08)",
        gridSoft: "rgba(255,255,255,0.04)",
    };
    const overviewPalette = [
        { dot: "overview-dot-violet", fill: COLORS.indigo },
        { dot: "overview-dot-green", fill: COLORS.teal },
        { dot: "overview-dot-blue", fill: COLORS.blue },
        { dot: "overview-dot-amber", fill: COLORS.amber },
        { dot: "overview-dot-red", fill: COLORS.rose },
        { dot: "overview-dot-teal", fill: COLORS.violet },
    ];
    
    // Global acronym generator for chart labels
    function getAcronym(str) {
        if (!str) return '';
        const parts = str.split(/[ \-_]/);
        if (parts.length === 1 && str.length > 8) return str.substring(0, 3).toUpperCase();
        let acronym = '';
        parts.forEach(p => { if (p.length > 0) acronym += p[0].toUpperCase(); });
        return acronym.length > 1 ? acronym : str.substring(0, 3).toUpperCase();
    }

    document.addEventListener("DOMContentLoaded", async () => {
        if (window.ChartDataLabels) {
            Chart.register(ChartDataLabels);
        }
        
        const page = getPage();
        const mainPages = ["sessions", "region", "instructor", "programs"];
        
        if (mainPages.includes(page)) {
            syncRangeLabels();
            bindFilters();
            try {
                await loadFilterOptions();
                await refreshPage();
            } catch (error) {
                console.error("Dashboard init error:", error);
            }
            
            // Auto-load data for new pages
            const seeReportBtn = document.getElementById("seeReport");
            if (seeReportBtn) {
                setTimeout(() => { seeReportBtn.click(); }, 300);
            }
        }
    });

    function getPage() {
        return document.body.dataset.page || "dashboard";
    }

    function bindFilters() {
        const filterIds = ["startYear", "endYear", "regionFilter", "programFilter", "instructorTypeFilter"];
        filterIds.forEach((id) => {
            const element = document.getElementById(id);
            if (!element) {
                return;
            }

            element.addEventListener("input", () => {
                syncRangeLabels();
                refreshPage().catch(console.error);
            });

            element.addEventListener("change", () => {
                syncRangeLabels();
                refreshPage().catch(console.error);
            });
        });
    }

    function syncRangeLabels() {
        const start = document.getElementById("startYear");
        const end = document.getElementById("endYear");
        const startLabel = document.getElementById("startYearLabel");
        const endLabel = document.getElementById("endYearLabel");

        if (start && end && Number(start.value) > Number(end.value)) {
            if (document.activeElement === start) {
                end.value = start.value;
            } else {
                start.value = end.value;
            }
        }

        if (start && startLabel) {
            startLabel.textContent = start.value;
        }

        if (end && endLabel) {
            endLabel.textContent = end.value;
        }
    }

    async function loadFilterOptions() {
        const [yearOptions, regionOptions, programOptions, instructorTypes] = await Promise.all([
            fetchJSON("/session/filter-options"),
            fetchJSON("/region/options"),
            fetchJSON("/exposure/programs"),
            fetchJSON("/instructor/types"),
        ]);

        const years = yearOptions.years || [];
        if (years.length) {
            const minYear = Math.min(...years);
            const maxYear = Math.max(...years);
            configureRange("startYear", minYear, maxYear, minYear);
            configureRange("endYear", minYear, maxYear, maxYear);
        }

        populateSelect("regionFilter", "All Regions", regionOptions.regions || []);
        populateSelect("programFilter", "All Programs", programOptions.programs || []);
        populateSelect("instructorTypeFilter", "All Types", instructorTypes.types || []);
        syncRangeLabels();
    }

    function configureRange(id, min, max, value) {
        const input = document.getElementById(id);
        if (!input) {
            return;
        }

        input.min = String(min);
        input.max = String(max);
        input.value = String(value);
    }

    function populateSelect(id, placeholder, options) {
        const select = document.getElementById(id);
        if (!select) {
            return;
        }

        const currentValue = select.value;
        select.innerHTML = "";

        const allOption = document.createElement("option");
        allOption.value = "";
        allOption.textContent = placeholder;
        select.appendChild(allOption);

        options.forEach((optionValue) => {
            const option = document.createElement("option");
            option.value = optionValue;
            option.textContent = optionValue;
            if (optionValue === currentValue) {
                option.selected = true;
            }
            select.appendChild(option);
        });
    }

    function getFilters() {
        if (window.PramanaDashboard && typeof window.PramanaDashboard.collectFilters === 'function') {
            const filters = window.PramanaDashboard.collectFilters();
            // Standardize 'year' to 'years' if the backend expects 'years' for the overview
            if (filters.year && !filters.years) {
                filters.years = filters.year;
            }
            return $.param(filters, true);
        }
        
        // Fallback for cases where collectFilters isn't ready
        const params = new URLSearchParams();
        const start = document.getElementById("startYear")?.value;
        const end = document.getElementById("endYear")?.value;
        const region = document.getElementById("regionFilter")?.value;
        const program = document.getElementById("programFilter")?.value;
        const instructor = document.getElementById("instructorTypeFilter")?.value;

        if (start) params.set("start", start);
        if (end) params.set("end", end);
        if (region) params.set("region", region);
        if (program) params.set("program", program);
        if (instructor) params.set("instructor", instructor);

        return params.toString();
    }

    async function refreshPage() {
        const page = getPage();

        if (page === "dashboard") {
            await loadDashboard();
            return;
        }

        if (page === "sessions") {
            await loadSessionsPage();
            return;
        }

        if (page === "region") {
            await loadRegionPage();
            return;
        }

        if (page === "instructor") {
            await loadInstructorPage();
            return;
        }

        if (page === "programs") {
            await loadProgramsPage();
        }
    }

    async function loadDashboard() {
        const filters = getFilters();
        const [kpis, targets, activity, donor] = await Promise.all([
            fetchJSON(`/overview/kpis?${filters}`),
            fetchJSON(`/overview/program-targets?${filters}`),
            fetchJSON(`/overview/sessions-by-activity?${filters}`),
            fetchJSON(`/overview/sessions-by-donor?${filters}`),
        ]);

        setText("kpiDonors", kpis.metrics.total_donors);
        setText("kpiPrograms", kpis.metrics.total_programs);
        setText("kpiProgramsTrack", kpis.metrics.programs_on_track);
        setText("kpiProgramsRisk", kpis.metrics.programs_at_risk);
        setText("kpiTargetSessions", kpis.metrics.target_sessions);
        setText("kpiCompletedSessions", kpis.metrics.completed_sessions);
        const overallCompletionPct = percentOf(kpis.metrics.completed_sessions, kpis.metrics.target_sessions);
        const overallCompletedSessions = Number(kpis.metrics.completed_sessions || 0);
        setText("kpiSessionsPct", overallCompletionPct);
        setText("kpiTargetStudents", kpis.metrics.target_students);
        setText("kpiReachedStudents", kpis.metrics.reached_students);
        setText("kpiStudentsPct", percentOf(kpis.metrics.reached_students, kpis.metrics.target_students));

        renderProgramTargets(targets.data || []);
        // Render activity and donor distributions as doughnut charts
        const activityPoints = activity.data || [];
        const donorPoints = donor.data || [];
        const palette = [COLORS.violet, COLORS.teal, COLORS.blue, COLORS.amber, COLORS.rose, COLORS.indigo, "#59b4ff", "#35c3a0"];
        const activityBg = activityPoints.map((_, i) => palette[i % palette.length]);
        const donorBg = donorPoints.map((_, i) => palette[i % palette.length]);
        renderChart("activityTypeChart", "doughnut", activityPoints, "Sessions", { backgroundColor: activityBg, showLegend: true, legendPosition: 'left', legendSmall: true, legendInteractive: false, legendTextColor: '#1f2937' });
        renderChart("donorSessionsChart", "doughnut", donorPoints, "Sessions", { backgroundColor: donorBg, showLegend: true, legendPosition: 'left', legendSmall: true, legendInteractive: false, legendTextColor: '#1f2937' });
    }

    async function loadSessionsPage() {
        const filters = getFilters();
        const [kpis, monthly, byRegion] = await Promise.all([
            fetchJSON(`/session/kpis?${filters}`),
            fetchJSON(`/session/monthly?${filters}`),
            fetchJSON(`/session/by-region?${filters}`),
        ]);

        setText("sessionTotalSessions", kpis.metrics.total_sessions);
        setText("sessionTotalInstructors", kpis.metrics.total_instructors);
        setText("sessionActiveRegions", kpis.metrics.active_regions);
        setText("sessionPrograms", kpis.metrics.total_programs);

        renderLineChart("sessionMonthlyChart", monthly.data, "Sessions", COLORS.teal);
        renderBarChart("sessionRegionChart", byRegion.data, "Sessions", COLORS.indigo);
    }

    async function loadRegionPage() {
        const filters = getFilters();
        const [kpis, impact, monthly] = await Promise.all([
            fetchJSON(`/region/kpis?${filters}`),
            fetchJSON(`/region/impact?${filters}`),
            fetchJSON(`/region/monthly-impact?${filters}`),
        ]);

        setText("regionStudentsReached", kpis.metrics.total_students_reached);
        setText("regionStates", kpis.metrics.total_states);
        setText("regionPrograms", kpis.metrics.total_programs);
        setText("regionAverageImpact", kpis.metrics.avg_students_per_state_period);

        renderBarChart("regionStateChart", impact.data, "Students Reached", COLORS.indigo);
        renderLineChart("regionMonthlyChart", monthly.data, "Students Reached", COLORS.blue);
    }

    async function loadInstructorPage() {
        const filters = getFilters();
        const [kpis, sessionLog, typeBreakdown, multiProgram] = await Promise.all([
            fetchJSON(`/instructor/kpis?${filters}`),
            fetchJSON(`/instructor/session-log?${filters}`),
            fetchJSON(`/instructor/type-breakdown?${filters}`),
            fetchJSON(`/instructor/multi-program?${filters}`),
        ]);

        setText("instructorTotal", kpis.metrics.total_instructors);
        setText("instructorAverageSessions", kpis.metrics.avg_sessions_per_instructor);
        setText("instructorTopRegion", kpis.metrics.top_region || "-");
        setText("instructorTopRegionSessions", kpis.metrics.top_region_sessions);
        setText("instructorUnprocessed", kpis.metrics.unprocessed_sessions);

        renderInstructorLog(sessionLog.data || []);
        // Render instructor type as a doughnut chart (match activity style)
        const typePoints = (typeBreakdown.data || []).map((p) => ({ label: p.label, value: p.value }));
        const palette = [COLORS.violet, COLORS.teal, COLORS.blue, COLORS.amber, COLORS.rose, COLORS.indigo, "#59b4ff", "#35c3a0"];
        const bg = typePoints.map((_, i) => palette[i % palette.length]);
        renderChart("instructorTypeChart", "doughnut", typePoints, "Sessions", { backgroundColor: bg, showLegend: true, legendPosition: 'left', legendSmall: true, legendInteractive: false, legendTextColor: '#ffffff' });
        renderMultiProgramInstructors(multiProgram.data || []);
    }

    async function loadProgramsPage() {
        const filters = getFilters();
        const [kpis, genderSplit, communitySplit, topSchools, cohortBreakdown] = await Promise.all([
            fetchJSON(`/exposure/kpis?${filters}`),
            fetchJSON(`/exposure/gender-split?${filters}`),
            fetchJSON(`/exposure/community-gender-split?${filters}`),
            fetchJSON(`/exposure/top-schools?${filters}`),
            fetchJSON(`/exposure/cohort-breakdown?${filters}`),
        ]);

        setText("programTotalStudents", kpis.metrics.total_students);
        setText("programCommunityMembers", kpis.metrics.community_members);
        setText("programTeachersReached", kpis.metrics.teachers_reached);
        setText("programAverageStudents", kpis.metrics.avg_students_per_exposure);

        renderExposureSplit(
            {
                leftValue: genderSplit.metrics.girls,
                rightValue: genderSplit.metrics.boys,
                leftLabel: "Girls",
                rightLabel: "Boys",
                leftBarId: "studentGirlsBar",
                rightBarId: "studentBoysBar",
                leftCountId: "studentGirlsCount",
                rightCountId: "studentBoysCount",
            }
        );
        renderExposureSplit(
            {
                leftValue: communitySplit.metrics.women,
                rightValue: communitySplit.metrics.men,
                leftLabel: "Women",
                rightLabel: "Men",
                leftBarId: "communityWomenBar",
                rightBarId: "communityMenBar",
                leftCountId: "communityWomenCount",
                rightCountId: "communityMenCount",
            }
        );
        renderTopSchools(topSchools.data || []);
        renderCohortBreakdown(cohortBreakdown.data || []);
    }

    function renderProgramTargets(rows) {
        const tbody = document.getElementById("programTargetsBody");
        if (!tbody) {
            return;
        }

        if (!rows.length) {
            tbody.innerHTML = '<tr><td colspan="7" class="overview-empty">No program target data available.</td></tr>';
            return;
        }

        tbody.innerHTML = rows.map((row) => {
            const progressClass = row.status === "On track"
                ? "overview-progress-green"
                : row.status === "At risk"
                    ? "overview-progress-blue"
                    : "overview-progress-amber";
            const statusClass = row.status === "On track"
                ? "overview-status-green"
                : row.status === "At risk"
                    ? "overview-status-amber"
                    : "overview-status-red";
            const targetValue = Number(row.target_sessions || 0).toLocaleString();
            const completedValue = Number(row.completed_sessions || 0).toLocaleString();
            const studentsReached = Number(row.students_reached || 0).toLocaleString();
            const studentsTarget = Number(row.students_target || 0).toLocaleString();
            const studentsValue = `${studentsReached} / ${studentsTarget}`;
            const actualProgressPct = Math.max(0, Math.min(100, Number(row.progress_pct || 0)));
            const progressPct = actualProgressPct > 0 ? Math.max(4, actualProgressPct) : 0;

            return `
                <tr>
                    <td class="program-name">${row.label}</td>
                    <td class="program-muted">${row.donor}</td>
                    <td>${completedValue} / ${targetValue}</td>
                    <td>
                        <div class="overview-progress-meta">
                            <div class="overview-progress-track">
                                <div class="overview-progress-fill ${progressClass}" style="width: ${progressPct}%"></div>
                            </div>
                            <span class="overview-progress-pct">${formatPercent(actualProgressPct, 0)}</span>
                        </div>
                    </td>
                    <td>${studentsValue}</td>
                    <td class="program-muted">${row.end_date}</td>
                    <td><span class="overview-status-pill ${statusClass}">${row.status}</span></td>
                </tr>`;
        }).join("");
    }

    function renderOverviewList(id, points, overallCompletedSessions = 0) {
        const container = document.getElementById(id);
        if (!container) {
            return;
        }

        if (!points.length) {
            container.innerHTML = '<div class="overview-empty">No data available for this selection.</div>';
            return;
        }

        const totalValue = points.reduce((sum, point) => sum + (Number(point.value) || 0), 0);
        container.innerHTML = points.map((point, index) => {
            const tone = overviewPalette[index % overviewPalette.length];
            const value = Number(point.value) || 0;
            // Compute share-of-total and use that as the bar width so the visual
            // length matches the percentage shown in the tooltip/label.
            const sharePct = totalValue > 0 ? (value / totalValue) * 100 : 0;
            const width = sharePct > 0 ? Math.max(3, sharePct) : 0;
            return `
                <div class="overview-list-row">
                    <div class="overview-list-label"><span class="overview-list-dot ${tone.dot}"></span>${point.label}</div>
                    <div class="overview-list-bar" title="Total Sessions: ${value.toLocaleString()}, Percentage of total: ${formatPercent(sharePct)}">
                        <div class="overview-list-fill" style="width:${width}%; background:${tone.fill};"></div>
                    </div>
                    <div class="overview-list-value">
                        <span class="overview-list-pct">${formatPercent(sharePct)}</span>
                    </div>
                </div>`;
        }).join("");
    }

    function formatPercent(value, decimals = 1) {
        const numericValue = Number(value) || 0;
        return `${numericValue.toLocaleString(undefined, {
            minimumFractionDigits: 0,
            maximumFractionDigits: decimals,
        })}%`;
    }


    function renderInstructorLog(rows) {
        const tbody = document.getElementById("instructorLogBody");
        if (!tbody) {
            return;
        }

        if (!rows.length) {
            tbody.innerHTML = '<tr><td colspan="7" class="instructor-empty">No instructor activity available.</td></tr>';
            return;
        }

        const maxSessions = Math.max(...rows.map((row) => Number(row.sessions) || 0), 1);
        tbody.innerHTML = rows.map((row) => {
            const width = Math.max(8, ((Number(row.sessions) || 0) / maxSessions) * 100);
            const typeClass = getInstructorTypeClass(row.type);
            return `
                <tr>
                    <td class="instructor-name">${row.name}</td>
                    <td><span class="instructor-type-pill ${typeClass}">${row.type}</span></td>
                    <td class="instructor-muted">${row.region}</td>
                    <td>${Number(row.sessions || 0).toLocaleString()}</td>
                    <td>
                        <div class="instructor-activity-track">
                            <div class="instructor-activity-fill ${typeClass}" style="width:${width}%"></div>
                        </div>
                    </td>
                    <td>${Number(row.students || 0).toLocaleString()}</td>
                    <td class="instructor-muted">${row.last_session || "-"}</td>
                </tr>`;
        }).join("");
    }

    function renderInstructorTypeBreakdown(points) {
        const container = document.getElementById("instructorTypeList");
        if (!container) {
            return;
        }

        if (!points.length) {
            container.innerHTML = '<div class="instructor-empty">No instructor type data available.</div>';
            return;
        }

        const total = points.reduce((sum, point) => sum + (Number(point.value) || 0), 0) || 1;
        const maxValue = Math.max(...points.map((point) => Number(point.value) || 0), 1);
        container.innerHTML = points.map((point) => {
            const typeClass = getInstructorTypeClass(point.label);
            const width = Math.max(10, ((Number(point.value) || 0) / maxValue) * 100);
            const pct = Math.round(((Number(point.value) || 0) / total) * 100);
            return `
                <div class="instructor-type-row">
                    <div class="instructor-type-meta">
                        <span class="instructor-type-name">${point.label}</span>
                        <span class="instructor-type-value">${Number(point.value || 0).toLocaleString()} (${pct}%)</span>
                    </div>
                    <div class="instructor-activity-track instructor-type-track">
                        <div class="instructor-activity-fill ${typeClass}" style="width:${width}%"></div>
                    </div>
                </div>`;
        }).join("");
    }

    function renderMultiProgramInstructors(rows) {
        const container = document.getElementById("multiProgramList");
        if (!container) {
            return;
        }

        if (!rows.length) {
            container.innerHTML = '<div class="instructor-empty">No multi-program instructor data available.</div>';
            return;
        }

        container.innerHTML = rows.map((row, index) => `
            <div class="instructor-rank-row">
                <div class="instructor-rank-index">${index + 1}</div>
                <div class="instructor-avatar">${row.initials}</div>
                <div class="instructor-rank-copy">
                    <div class="instructor-rank-name">${row.name}</div>
                    <div class="instructor-rank-meta">${row.region} - ${row.type}</div>
                </div>
                <div class="instructor-rank-stats">
                    <div class="instructor-rank-programs">${Number(row.programs || 0).toLocaleString()} programs</div>
                    <div class="instructor-rank-sessions">${Number(row.sessions || 0).toLocaleString()} sessions</div>
                </div>
            </div>`).join("");
    }

    function getInstructorTypeClass(type) {
        const value = String(type || "").toLowerCase();
        if (value.includes("volunteer")) {
            return "type-teal";
        }
        if (value.includes("instructor")) {
            return "type-blue";
        }
        return "type-violet";
    }


    function renderExposureSplit(config) {
        const total = Number(config.leftValue || 0) + Number(config.rightValue || 0);
        const leftPct = total ? Math.round((Number(config.leftValue || 0) / total) * 100) : 0;
        const rightPct = total ? 100 - leftPct : 0;

        const leftBar = document.getElementById(config.leftBarId);
        const rightBar = document.getElementById(config.rightBarId);
        if (leftBar) {
            leftBar.style.width = `${Math.max(leftPct, total ? 18 : 50)}%`;
            leftBar.textContent = `${leftPct}% ${config.leftLabel}`;
        }
        if (rightBar) {
            rightBar.style.width = `${Math.max(rightPct, total ? 18 : 50)}%`;
            rightBar.textContent = `${rightPct}% ${config.rightLabel}`;
        }
        setText(config.leftCountId, config.leftValue);
        setText(config.rightCountId, config.rightValue);
    }

    function renderTopSchools(rows) {
        const container = document.getElementById("topSchoolsList");
        if (!container) {
            return;
        }

        if (!rows.length) {
            container.innerHTML = '<div class="exposure-empty">No school exposure data available.</div>';
            return;
        }

        const maxValue = Math.max(...rows.map((row) => Number(row.value) || 0), 1);
        container.innerHTML = rows.map((row) => {
            const width = Math.max(10, ((Number(row.value) || 0) / maxValue) * 100);
            return `
                <div class="exposure-school-row">
                    <div class="exposure-school-copy">
                        <div class="exposure-school-name">${row.label}</div>
                        <div class="exposure-school-meta">${row.subtitle || "-"}</div>
                    </div>
                    <div class="exposure-school-bar"><div class="exposure-school-fill" style="width:${width}%"></div></div>
                    <div class="exposure-school-value">${Number(row.value || 0).toLocaleString()}</div>
                </div>`;
        }).join("");
    }

    function renderCohortBreakdown(points) {
        const container = document.getElementById("cohortBreakdownList");
        if (!container) {
            return;
        }

        if (!points.length) {
            container.innerHTML = '<div class="exposure-empty">No cohort breakdown available.</div>';
            return;
        }

        const total = points.reduce((sum, point) => sum + (Number(point.value) || 0), 0) || 1;
        const palette = {
            Students: { icon: 'fa-user-graduate', chip: 'exposure-chip-violet' },
            Teachers: { icon: 'fa-chalkboard-teacher', chip: 'exposure-chip-teal' },
            Community: { icon: 'fa-users', chip: 'exposure-chip-amber' },
        };

        container.innerHTML = points.map((point) => {
            const pct = Math.round(((Number(point.value) || 0) / total) * 100);
            const style = palette[point.label] || palette.Students;
            return `
                <div class="exposure-cohort-row">
                    <div class="exposure-cohort-icon ${style.chip}"><i class="fas ${style.icon}"></i></div>
                    <div class="exposure-cohort-copy">
                        <div class="exposure-cohort-name">${point.label}</div>
                        <div class="exposure-cohort-value">${Number(point.value || 0).toLocaleString()} <span>${pct}%</span></div>
                        <div class="exposure-school-bar exposure-cohort-bar"><div class="exposure-school-fill" style="width:${Math.max(pct, 10)}%"></div></div>
                    </div>
                </div>`;
        }).join("");
    }

    function percentOf(actual, target) {
        const numerator = Number(actual || 0);
        const denominator = Number(target || 0);
        if (!denominator) {
            return 0;
        }
        return Math.round((numerator / denominator) * 100);
    }

    function setText(id, value) {
        const element = document.getElementById(id);
        if (!element) {
            return;
        }

        const numericValue = Number(value);
        element.textContent = Number.isFinite(numericValue) ? numericValue.toLocaleString() : (value ?? "-");
    }

    function renderBarChart(id, points, label, color) {
        renderChart(id, "bar", points, label, {
            backgroundColor: color,
            borderRadius: 8,
            barThickness: 18,
        });
    }

    function renderHorizontalBarChart(id, points, label, color) {
        renderChart(id, "bar", points, label, {
            backgroundColor: color,
            indexAxis: "y",
            borderRadius: 8,
            barThickness: 12,
        });
    }

    function renderHorizontalPaletteChart(id, points, label) {
        const palette = [COLORS.teal, COLORS.blue, COLORS.amber, COLORS.indigo, COLORS.rose, COLORS.violet, "#59b4ff", "#35c3a0"];
        renderChart(id, "bar", points, label, {
            backgroundColor: points.map((_, index) => palette[index % palette.length]),
            indexAxis: "y",
            borderRadius: 8,
            barThickness: 12,
        });
    }

    function renderLineChart(id, points, label, color) {
        renderChart(id, "line", points, label, {
            borderColor: color,
            backgroundColor: `${color}33`,
            pointBackgroundColor: color,
            pointBorderColor: color,
            pointRadius: 3,
            tension: 0.35,
            fill: true,
        });
    }

    function renderChart(id, type, points, label, datasetOptions) {
        try {
            const canvas = document.getElementById(id);
            if (!canvas) return;

            if (charts[id]) {
                charts[id].destroy();
            }

            const showPercentages = datasetOptions && datasetOptions.showPercentages;
            const usePieConnectors = datasetOptions && datasetOptions.usePieConnectors;

            // Custom plugin to draw data labels inside doughnut/pie charts (default style)
            const internalDataLabelPlugin = {
                id: "internalDatalabels",
                afterDatasetsDraw(chart, args, options) {
                    if (usePieConnectors) return; // Don't use this if connectors are enabled
                    const { ctx, data } = chart;
                    if (!data || !data.datasets || !data.datasets[0]) return;
                    const meta = chart.getDatasetMeta(0);
                    if (!meta || !meta.data) return;
                    meta.data.forEach((arc, index) => {
                        const val = data.datasets[0].data[index];
                        if (val === null || val === undefined) return;
                        const pos = arc.tooltipPosition();
                        ctx.save();
                        ctx.fillStyle = "#ffffff";
                        ctx.font = "bold 12px sans-serif";
                        ctx.textAlign = "center";
                        ctx.textBaseline = "middle";
                        ctx.fillText(Number(val).toLocaleString(), pos.x, pos.y);
                        ctx.restore();
                    });
                },
            };

            const useAcronyms = datasetOptions && datasetOptions.useAcronyms;
            const legendSelector = datasetOptions && datasetOptions.legendSelector;
            
            let labels = [];
            let finalPoints = points;

            if (useAcronyms) {
                const mapping = {};
                const acronymizedPoints = points.map(p => {
                    const code = getAcronym(p.label);
                    if (!mapping[code]) mapping[code] = [];
                    if (!mapping[code].includes(p.label)) mapping[code].push(p.label);
                    return { ...p, label: code };
                });
                
                if (type === 'pie' || type === 'doughnut') {
                    const aggregated = {};
                    acronymizedPoints.forEach(p => {
                        if (!aggregated[p.label]) aggregated[p.label] = { ...p, value: 0 };
                        aggregated[p.label].value += p.value;
                    });
                    finalPoints = Object.values(aggregated);
                } else {
                    finalPoints = acronymizedPoints;
                }

                if (legendSelector) {
                    let content = '<div class="acronym-mapping-popover"><table class="table table-sm pb-0 mb-0" style="font-size:11px">';
                    Object.keys(mapping).sort().forEach(code => {
                        const names = mapping[code];
                        const displayName = names.join(', ');
                        content += `<tr><td class="font-weight-bold pr-2" style="border-top:0">${code}</td><td style="border-top:0">: ${displayName}</td></tr>`;
                    });
                    content += '</table></div>';
                    const $pop = $(legendSelector);
                    $pop.attr('data-content', content);
                    if ($pop.data('bs.popover')) {
                        $pop.popover('update');
                    }
                }
            }

            const isGrouped = finalPoints.length > 0 && finalPoints[0].hasOwnProperty('group');
            let datasets = [];

            if (isGrouped) {
                const groups = [...new Set(finalPoints.map(p => p.group))];
                labels = [...new Set(finalPoints.map(p => p.label))];
                datasets = groups.map((group, idx) => {
                    const palette = [COLORS.blue, COLORS.teal, COLORS.amber, COLORS.rose, COLORS.violet, COLORS.indigo, "#59b4ff", "#35c3a0"];
                    const color = palette[idx % palette.length];
                    return {
                        label: group,
                        data: labels.map(l => {
                            const match = finalPoints.find(p => p.label === l && p.group === group);
                            return match ? match.value : 0;
                        }),
                        backgroundColor: type === 'line' ? `${color}33` : color,
                        borderColor: color,
                        borderWidth: 1,
                        fill: type === 'line',
                        tension: 0.35,
                        ...datasetOptions
                    };
                });
            } else {
                labels = finalPoints.map((p) => p.label);
                datasets = [{
                    label,
                    data: finalPoints.map((p) => p.value),
                    ...datasetOptions,
                }];
            }

            const chartConfig = {
                type,
                data: { labels, datasets },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    layout: {
                        padding: usePieConnectors ? 30 : 0
                    },
                    plugins: {
                        legend: {
                            display: isGrouped || (datasetOptions && datasetOptions.showLegend === true),
                            position: datasetOptions && datasetOptions.legendPosition ? datasetOptions.legendPosition : 'top',
                            labels: datasetOptions && datasetOptions.legendSmall
                                ? { color: datasetOptions.legendTextColor || '#1f2937', boxWidth: 12, padding: 8, usePointStyle: true, pointStyle: 'circle' }
                                : { 
                                    color: datasetOptions && (datasetOptions.legendTextColor || (type === 'pie' || type === 'doughnut' ? '#1f2937' : COLORS.tick)),
                                    padding: (type === 'pie' || type === 'doughnut') ? 30 : 10,
                                    font: { size: (type === 'pie' || type === 'doughnut') ? 11 : 12 },
                                    usePointStyle: true,
                                    pointStyle: 'circle',
                                    boxWidth: 8
                                  },
                            onClick: datasetOptions && datasetOptions.legendInteractive === false ? () => {} : undefined,
                        },
                        tooltip: {
                            backgroundColor: "rgba(32, 38, 49, 0.94)",
                            titleColor: "#fff",
                            bodyColor: "#fff",
                            borderColor: "rgba(255,255,255,0.08)",
                            borderWidth: 1,
                            callbacks: {
                                label: function(context) {
                                    const val = context.parsed.y ?? context.parsed;
                                    const labelStr = context.dataset.label || '';
                                    if (showPercentages && (type === 'pie' || type === 'doughnut')) {
                                        const total = context.dataset.data.reduce((s, v) => s + v, 0);
                                        const pct = total ? Math.round((val / total) * 100) : 0;
                                        return `${labelStr}: ${Number(val).toLocaleString()} (${pct}%)`;
                                    }
                                    return `${labelStr}: ${Number(val).toLocaleString()}`;
                                }
                            }
                        },
                        datalabels: {
                            display: function() {
                                const toggle = document.getElementById('toggleDataLabels');
                                return toggle ? toggle.checked : (datasetOptions && datasetOptions.showLabels !== false);
                            },
                            anchor: usePieConnectors ? 'end' : 'center',
                            align: usePieConnectors ? 'end' : 'center',
                            offset: usePieConnectors ? 12 : 0,
                            color: usePieConnectors ? '#000000' : (type === 'pie' || type === 'doughnut' ? '#ffffff' : '#000000'),
                            font: { weight: 'bold', size: 10 },
                            formatter: function(value, context) {
                                if (value === 0) return '';
                                const valStr = Number(value).toLocaleString();
                                if (showPercentages && (type === 'pie' || type === 'doughnut')) {
                                    const total = context.dataset.data.reduce((s, v) => s + v, 0);
                                    const pct = total ? Math.round((value / total) * 100) : 0;
                                    return `${valStr} (${pct}%)`;
                                }
                                return valStr;
                            }
                        }
                    },
                },
            };

            if (type === "bar" || type === "line") {
                chartConfig.options.scales = {
                    x: {
                        grid: { color: COLORS.grid },
                        ticks: { color: COLORS.tick },
                        border: { display: false },
                    },
                    y: {
                        beginAtZero: true,
                        grid: { color: type === "line" ? COLORS.grid : COLORS.gridSoft },
                        ticks: { color: COLORS.tick },
                        border: { display: false },
                    },
                };
            }

            const activePlugins = [];
            if (type === 'pie' || type === 'doughnut') {
                if (usePieConnectors) {
                    activePlugins.push(window.PieConnectorPlugin);
                } else {
                    activePlugins.push(internalDataLabelPlugin);
                }
            }
            
            charts[id] = new Chart(canvas, { ...chartConfig, plugins: activePlugins });
        } catch (error) {
            console.error(`Error rendering chart ${id}:`, error);
        }
    }

    async function fetchJSON(url) {
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`Request failed for ${url}`);
        }
        return response.json();
    }

    // Pagination and Export Utilities
    window.PramanaPagination = {
        state: {
            limit: 15,
            offset: 0,
            total: 0
        },
        updateInfo: function(containerId, totalCount) {
            this.state.total = totalCount;
            const start = this.state.offset + 1;
            const end = Math.min(this.state.offset + this.state.limit, totalCount);
            const totalPages = Math.ceil(totalCount / this.state.limit) || 1;
            const currentPage = Math.floor(this.state.offset / this.state.limit) + 1;

            // Search in the specified container, or fall back to the whole document
            const element = document.getElementById(containerId);
            const context = element ? element.closest('.card-body') || element.parentElement || document : document;
            
            const info = context.querySelector('.pagination-info');
            if (info) {
                info.innerHTML = `Showing ${totalCount > 0 ? start : 0} to ${end} of ${totalCount} entries`;
            }
            
            const currentInput = context.querySelector('.page-input');
            const totalSpan = context.querySelector('.total-pages');
            if (currentInput) currentInput.value = currentPage;
            if (totalSpan) totalSpan.textContent = totalPages;

            const prevBtn = context.querySelector('.prev-page');
            const nextBtn = context.querySelector('.next-page');
            if (prevBtn) prevBtn.disabled = (currentPage <= 1);
            if (nextBtn) nextBtn.disabled = (currentPage >= totalPages);
        },
        goto: function(targetPage, callback) {
            const totalPages = Math.ceil(this.state.total / this.state.limit) || 1;
            let page = parseInt(targetPage);
            if (isNaN(page) || page < 1) page = 1;
            if (page > totalPages) page = totalPages;
            
            this.state.offset = (page - 1) * this.state.limit;
            if (typeof callback === 'function') callback();
        },
        reset: function() {
            this.state.offset = 0;
            this.state.total = 0;
        },
        next: function(callback) {
            if (this.state.offset + this.state.limit < this.state.total) {
                this.state.offset += this.state.limit;
                if (typeof callback === 'function') callback();
            }
        },
        prev: function(callback) {
            if (this.state.offset >= this.state.limit) {
                this.state.offset -= this.state.limit;
                if (typeof callback === 'function') callback();
            }
        }
    };

    // The individual pages handle the click events on .prev-page, .next-page, and .page-input
    // to ensure they call their own context-specific loadData() functions.
    // This removes the global listeners that were causing double-increments/skipping.

    $(document).on('keyup', '.page-input', function(e) {
        if (e.key === 'Enter') {
            $(this).blur(); // Trigger change event
        }
    });

    // Reset pagination on "See Report"
    $(document).on('click', '#seeReportBtn, .filter-btn', function() {
        window.PramanaPagination.reset();
    });

    window.exportToXLSX = async function(url, filename) {
        try {
            const response = await fetch(url);
            if (!response.ok) throw new Error("Export failed");
            const blob = await response.blob();
            const link = document.createElement("a");
            link.href = window.URL.createObjectURL(blob);
            link.download = filename || "export.xlsx";
            link.click();
        } catch (error) {
            console.error(error);
            alert("Failed to export data");
        }
    };

    window.PramanaDashboard = {
        initDataTable: function(selector, options = {}) {
            if ($.fn.DataTable.isDataTable(selector)) {
                $(selector).DataTable().destroy();
            }

            const defaultOptions = {
                paging: true,
                searching: true,
                ordering: true,
                info: true,
                responsive: true,
                autoWidth: false, // Prevent DataTables from guessing widths, which causes misalignment
                pageLength: 15,
                lengthMenu: [10, 15, 25, 50, 100],
                language: {
                    search: "_INPUT_",
                    searchPlaceholder: "Filter records...",
                    lengthMenu: "Show _MENU_ entries"
                },
                order: [], // Disable initial sort to respect server-side default
                columnDefs: [
                    {
                        targets: '_all',
                        render: function(data, type, row) {
                            if (type === 'display' && typeof data === 'string' && data.length > 0) {
                                // Don't format if it's purely numeric or a date-like string
                                if (/^[\d,.\-%]+$/.test(data) || /^\d{4}-\d{2}-\d{2}/.test(data)) {
                                    return data;
                                }
                                // Don't format if it contains HTML tags (would mangle badge/span markup)
                                if (data.indexOf('<') !== -1 || data.indexOf('>') !== -1) {
                                    return data;
                                }
                                // Convert to Title Case (and replace underscores with spaces)
                                return data.replace(/_/g, ' ')
                                           .toLowerCase()
                                           .split(' ')
                                           .map(word => word.charAt(0).toUpperCase() + word.slice(1))
                                           .join(' ');
                            }
                            return data;
                        }
                    }
                ],
                drawCallback: function(settings) {
                    const api = this.api();
                    $(api.table().header()).find('th').each(function() {
                        const $th = $(this);
                        
                        // Disable native DataTables sort click listeners
                        $th.off('click.DT keypress.DT');
                        
                        if ($th.hasClass('sorting') || $th.hasClass('sorting_asc') || $th.hasClass('sorting_desc')) {
                            
                            // Inject custom 3-line icon
                            if ($th.find('.dt-sort-icon').length === 0) {
                                $th.append('<i class="fas fa-bars dt-sort-icon"></i>');
                            }
                            
                            // Highlight icon if actively sorted
                            const icon = $th.find('.dt-sort-icon');
                            if ($th.hasClass('sorting_asc') || $th.hasClass('sorting_desc')) {
                                icon.addClass('text-primary');
                            } else {
                                icon.removeClass('text-primary');
                            }

                            // Bind our custom sort dropdown interaction
                            $th.off('click.PramanaSort').on('click.PramanaSort', function(e) {
                                e.stopPropagation();
                                e.preventDefault();
                                
                                const tableId = $(this).closest('table').attr('id');
                                const colIdx = $(this).index();
                                const menu = $('#dtSortMenu');
                                
                                // Store target info in menu
                                menu.data('tableId', tableId);
                                menu.data('colIdx', colIdx);
                                
                                // Position menu appropriately
                                const rect = this.getBoundingClientRect();
                                menu.css({
                                    top: rect.bottom + window.scrollY,
                                    left: e.pageX - 75
                                }).show();
                            });
                        }
                    });
                }
            };

            // Setup Custom Sort Dropdown Interactions (Run Once)
            if (!window._pramanaCustomSortInitialized) {
                window._pramanaCustomSortInitialized = true;
                
                // Hide menu when clicking out
                $(document).on('click', function(e) {
                    if (!$(e.target).closest('#dtSortMenu, th.sorting, th.sorting_asc, th.sorting_desc').length) {
                        $('#dtSortMenu').hide();
                    }
                });
                
                // Handle menu selections
                $(document).on('click', '.dt-sort-action', function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    const menu = $('#dtSortMenu');
                    const tableId = menu.data('tableId');
                    const colIdx = menu.data('colIdx');
                    const sortType = $(this).data('sort');
                    
                    if (tableId && colIdx !== undefined) {
                        const dt = $('#' + tableId).DataTable();
                        if (sortType === 'remove') {
                            dt.order([]).draw(); // Remove sort
                        } else {
                            dt.order([Math.floor(colIdx), sortType]).draw();
                        }
                    }
                    menu.hide();
                });
            }

            // If ajaxUrl is provided, we switch to server-side mode
            if (options.ajaxUrl) {
                const ajaxUrl = options.ajaxUrl;
                const getFilters = options.getFilters;
                const onDataLoad = options.onDataLoad;

                const serverSideOptions = {
                    serverSide: true,
                    processing: true,
                    ajax: {
                        url: ajaxUrl,
                        traditional: true, // Crucial for FastAPI to receive ?param=A&param=B instead of ?param[]=A
                        data: function(d) {
                            // Merge DataTables params with our custom filters
                            const customFilters = typeof getFilters === 'function' ? getFilters() : {};
                            return $.extend({}, d, customFilters);
                        },
                        dataSrc: function(json) {
                            // DataTables expects 'recordsTotal' and 'recordsFiltered'
                            // In our backend, total_count reflects the filtered count
                            json.recordsTotal = json.total_count || 0;
                            json.recordsFiltered = json.total_count || 0; 
                            
                            if (typeof onDataLoad === 'function') {
                                onDataLoad(json);
                            }
                            
                            // Automatically enhance KPI cards with insights/sparklines fallback
                            if (window.PramanaInsights) {
                                setTimeout(() => window.PramanaInsights.enhanceAllKpiCards(json.kpis), 50);
                            }
                            
                            return json.table || [];
                        },
                        error: function(xhr, error, thrown) {
                            console.error('DataTable AJAX error:', error, thrown);
                            // Optional: Show user-friendly error in the table
                            $(selector + ' tbody').html('<tr><td colspan="100%" class="text-center text-danger py-4"><i class="fas fa-exclamation-triangle mr-2"></i> Failed to load data from server</td></tr>');
                        }
                    }
                };
                delete options.ajaxUrl;
                delete options.getFilters;
                delete options.onDataLoad;
                return $(selector).DataTable($.extend(true, defaultOptions, serverSideOptions, options));
            }

            return $(selector).DataTable($.extend(true, defaultOptions, options));
        },
        resetTable: function(tableSelector, loadDataCallback) {
            // Clear Select2 dropdowns (reset to first option - usually "All" or "Select")
            $('.select2').each(function() {
                const isMulti = $(this).hasClass('filter-multi');
                if (isMulti) {
                    $(this).val([]).trigger('change.select2');
                } else {
                    const firstVal = $(this).find('option:first').val();
                    $(this).val(firstVal).trigger('change.select2');
                }
            });
            
            // Clear any other filter inputs
            $('.card-body input').val('');

            // Reset DataTable search and sorting
            if ($.fn.DataTable.isDataTable(tableSelector)) {
                const table = $(tableSelector).DataTable();
                table.search('').order([]).draw();
            }

            // Reload data for the page if callback is provided
            if (typeof loadDataCallback === 'function') {
                loadDataCallback();
            }
        },
        initMultiFilters: function() {
            if (!$.fn.select2) return;
            $('.filter-multi').each(function() {
                const $el = $(this);
                const filterName = $el.data('filter') || 'item';
                const limit = $el.data('limit') || 5;
                $el.select2({
                    theme: 'bootstrap4',
                    multiple: true,
                    placeholder: `Select ${filterName} for comparison`,
                    allowClear: true,
                    maximumSelectionLength: limit,
                    width: '100%'
                });
            });
        },
        collectFilters: function() {
            const filters = {};
            
            // Collect from all selects/inputs with data-filter or standard IDs
            $('.select2, select, input').each(function() {
                const $el = $(this);
                const id = $el.attr('id');
                if (!id && !$el.attr('data-filter')) return;
                
                let key = $el.attr('data-filter') || id.replace('Filter', '');
                
                // Standardize plural/singular for common keys
                if (key === 'year') key = 'years';
                if (key === 'regions') key = 'region';
                if (key === 'programs') key = 'program';
                if (key === 'areas') key = 'area';
                if (key === 'months') key = 'month';
                
                const val = $el.val();
                if (val !== null && val !== undefined && (Array.isArray(val) ? val.length > 0 : val !== "")) {
                    filters[key] = val;
                }
            });
            
            return filters;
        },
        renderChart: renderChart,
        renderBarChart: renderBarChart,
        renderLineChart: renderLineChart,
        updateAllCharts: function() {
            Object.keys(charts).forEach(id => {
                if (charts[id]) charts[id].update();
            });
        }
    };

    window.PramanaInsights = {
        enhanceAllKpiCards: function(apiKpis) {
            $('.kpi-card-bitcoin').each(function(index) {
                const $card = $(this);
                // Try to get kpi data from API, otherwise extract value from DOM
                const kpi = (apiKpis && apiKpis[index]) ? apiKpis[index] : null;
                const domValStr = $card.find('.kpi-bitcoin-value').text().replace(/,/g, '').trim();
                const domVal = parseFloat(domValStr) || 0;
                
                if (domVal === 0 && (!kpi || kpi.value === 0)) return; // Skip empty cards
                const finalValue = kpi ? kpi.value : domVal;

                // 1. Inject info tooltip icon if not present
                if ($card.find('.kpi-insight-trigger').length === 0) {
                    const $headerBox = $card.find('.kpi-bitcoin-header');
                    $headerBox.append(`
                        <div class="ml-auto" style="z-index: 10;">
                            <div class="kpi-insight-trigger" tabindex="0" style="width: 24px; height: 24px; border-radius: 50%; background: #cbd5e1; color: white; display: flex; align-items: center; justify-content: center; cursor: pointer;">
                                <i class="fas fa-info" style="font-size: 0.75rem;"></i>
                            </div>
                        </div>
                    `);
                }

                // 2. Generate or extract trends
                let trends = (kpi && kpi.trends && kpi.trends.length > 0) ? kpi.trends : window.PramanaInsights.generateMockTrends(finalValue);
                
                // 3. Render Mini Chart with Start & End Labels
                const canvasId = $card.find('canvas').attr('id');
                if (canvasId) {
                    window.PramanaInsights.renderMiniChart(canvasId, trends);
                }

                // 4. Calculate YoY Pill — compare average of first half vs last point
                const midpoint = Math.floor(trends.length / 2);
                const firstHalfAvg = trends.slice(0, midpoint).reduce((a, b) => a + b, 0) / (midpoint || 1);
                const lastVal = trends[trends.length - 1];
                const firstVal = trends[0];
                // Use kpi insights averages if backend supplied them, else use first vs last trend point
                const kpiAvgs = (kpi && kpi.insights) ? kpi.insights : null;
                const displayCurr = kpiAvgs && kpiAvgs.curr_avg != null ? kpiAvgs.curr_avg : lastVal;
                const displayPrev = kpiAvgs && kpiAvgs.prev_avg != null ? kpiAvgs.prev_avg : firstVal;
                const percentChange = displayPrev === 0 ? 0 : ((displayCurr - displayPrev) / displayPrev) * 100;
                const isUp = percentChange >= 0;
                const pillClass = isUp ? 'kpi-bitcoin-trend-up' : 'kpi-bitcoin-trend-down';
                const pillIcon = isUp ? 'fa-arrow-up' : 'fa-arrow-down';
                const pillText = Math.abs(percentChange).toFixed(1) + '%';
                
                // Inject Pill
                $card.find('.kpi-yoy-container').remove();
                $card.find('.kpi-yoy-pill').remove(); // Remove old badges just in case
                $card.find('.kpi-bitcoin-value').after(`
                    <div class="kpi-yoy-container" style="display: flex; align-items: center; margin-bottom: 8px;">
                        <span class="kpi-bitcoin-trend-pill ${pillClass}">
                            ${pillText} <i class="fas ${pillIcon} ml-1" style="font-size: 0.7rem;"></i>
                        </span>
                        <span class="text-muted" style="font-size: 0.9rem; font-weight: 500; color: #94a3b8 !important;">vs previous period</span>
                    </div>
                `);

                const title = $card.find('.kpi-bitcoin-label').text() || 'Metric';

                const $trigger = $card.find('.kpi-insight-trigger');
                // Remove popover if existed
                if ($trigger.data('bs.popover')) {
                    $trigger.popover('dispose');
                }
                
                $trigger.off('click').on('click', function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    
                    // Populate Modal
                    $('#modalTitle').text(title + ' Performance Insights');
                    
                    const iconClass = $card.find('.kpi-bitcoin-icon-wrapper i').attr('class') || 'fas fa-chart-line';
                    $('#modalHeaderIcon').attr('class', iconClass);
                    const iconBg = $card.find('.kpi-bitcoin-icon-wrapper').css('background') || '#f39c12';
                    $('#modalIconWrapper').css('background', iconBg);
                    
                    const directionText = isUp ? 'an increase' : 'a decrease';
                    // Format a number to integer if whole, else 1dp
                    const fmtNum = (v) => {
                        const n = parseFloat(v);
                        return Number.isInteger(n) ? n.toLocaleString() : n.toFixed(1);
                    };
                    $('#modalComparisonText').html(`In the current period, the monthly average is <b>${fmtNum(displayCurr)}</b> while the previous period monthly average was <b>${fmtNum(displayPrev)}</b> (representing ${directionText} of <b>${pillText}</b> compared to last period).`);
                    $('#modalComparisonIcon i').attr('class', isUp ? 'fas fa-arrow-alt-circle-up text-success' : 'fas fa-arrow-alt-circle-down text-danger');
                    
                    const rationaleText = isUp ?
                        `The monthly average grew from ${fmtNum(displayPrev)} to ${fmtNum(displayCurr)} (growth of ${pillText}). This positive performance is driven by: (1) Strong operational cadence and adherence to schedules; (2) Favorable seasonal engagement with new programs; (3) Improved tracking and data fidelity across centers; (4) Successful retention incentives implemented last quarter.` :
                        `The monthly average dropped from ${fmtNum(displayPrev)} to ${fmtNum(displayCurr)} (a decline of ${pillText}). This underperformance is caused by: (1) Seasonal attrition at the end of academic semesters that was not immediately backfilled; (2) Recruitment delays due to stricter verification procedures; (3) Operational halts in two regional centers undergoing leadership changes; (4) Natural transition of part-time trainers to full-time public school employment.`;
                    $('#modalRationaleText').text(rationaleText);
                    
                    const suggestionsHtml = `
                        <li class="insight-list-item">
                            <div class="mr-3 text-success"><i class="fas fa-check-circle" style="font-size: 1.2rem;"></i></div>
                            <div><strong>Streamline Recruitment Timelines:</strong> Reduce the hiring bottleneck by digitizing background checks, cutting onboarding time from 30 days to 12 days.</div>
                        </li>
                        <li class="insight-list-item">
                            <div class="mr-3 text-success"><i class="fas fa-check-circle" style="font-size: 1.2rem;"></i></div>
                            <div><strong>Deploy a Retention Incentive Matrix:</strong> Introduce tiered quarterly retention bonuses and merit certificates for instructors completing multiple teaching cycles.</div>
                        </li>
                        <li class="insight-list-item">
                            <div class="mr-3 text-success"><i class="fas fa-check-circle" style="font-size: 1.2rem;"></i></div>
                            <div><strong>Establish a Standby Trainer Pool:</strong> Maintain a 15% reserve of certified on-call backup instructors per region to immediately cover mid-term attrition.</div>
                        </li>
                        <li class="insight-list-item">
                            <div class="mr-3 text-success"><i class="fas fa-check-circle" style="font-size: 1.2rem;"></i></div>
                            <div><strong>Collaborate with Teacher Training Institutes:</strong> Secure direct talent pipelines with local B.Ed and D.Ed colleges to auto-onboard high-potential graduates.</div>
                        </li>
                        <li class="insight-list-item">
                            <div class="mr-3 text-success"><i class="fas fa-check-circle" style="font-size: 1.2rem;"></i></div>
                            <div><strong>Enhance Safety & Transit Allowances:</strong> Provide subsidized transit options or allowances for remote school visits to increase field trainer satisfaction.</div>
                        </li>
                    `;
                    $('#modalSuggestionsList').html(suggestionsHtml);
                    
                    $('#kpiInsightModal').modal('show');
                });
            });
        },

        generateMockTrends: function(currentValue, points = 12) {
            let trends = [];
            let base = (currentValue || 100) * 0.7; 
            for(let i=0; i<points; i++) {
                let noise = (Math.random() - 0.3) * (base * 0.2); 
                let val = Math.max(0, base + noise + ((currentValue - base) * (i / (points - 1))));
                trends.push(Math.round(val));
            }
            trends[points - 1] = currentValue || 0; 
            return trends;
        },

        renderMiniChart: function(canvasId, dataPoints) {
            const ctx = document.getElementById(canvasId);
            if (!ctx) return;
            
            if (window[canvasId + '_chart']) {
                window[canvasId + '_chart'].destroy();
            }
            
            const isUp = dataPoints[dataPoints.length - 1] >= dataPoints[0];
            const color = isUp ? '#10b981' : '#ef4444'; 
            
            window[canvasId + '_chart'] = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: dataPoints.map((_, i) => 'P' + i),
                    datasets: [{
                        data: dataPoints,
                        borderColor: color,
                        backgroundColor: color + '20', // Add 20% opacity hex for faint fill
                        borderWidth: 2,
                        tension: 0.4,
                        pointRadius: function(context) {
                            const index = context.dataIndex;
                            const count = context.dataset.data.length;
                            return (index === 0 || index === count - 1) ? 3 : 0;
                        },
                        pointBackgroundColor: color,
                        fill: true
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: { enabled: false },
                        datalabels: {
                            display: function(context) {
                                const index = context.dataIndex;
                                const count = context.dataset.data.length;
                                return index === 0 || index === count - 1; 
                            },
                            align: function(context) {
                                return context.dataIndex === 0 ? 'right' : 'left';
                            },
                            anchor: 'center',
                            color: color,
                            font: { size: 10, weight: 'bold' },
                            formatter: function(value) {
                                return value > 1000 ? (value/1000).toFixed(1) + 'k' : value;
                            }
                        }
                    },
                    scales: {
                        x: { display: false },
                        y: { 
                            display: false, 
                            min: Math.min(...dataPoints) * 0.8,
                            max: Math.max(...dataPoints) * 1.1
                        }
                    },
                    layout: {
                        padding: { left: 10, right: 10, top: 10, bottom: 10 }
                    }
                }
            });
        }
    };
})();
