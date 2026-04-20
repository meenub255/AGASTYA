(function () {
    const charts = {};
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

    document.addEventListener("DOMContentLoaded", async () => {
        syncRangeLabels();
        bindFilters();
        try {
            await loadFilterOptions();
            await refreshPage();
        } catch (error) {
            console.error(error);
        }
        
        // Auto-load data for new pages
        const seeReportBtn = document.getElementById("seeReport");
        if (seeReportBtn) {
            setTimeout(() => { seeReportBtn.click(); }, 300);
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
        const params = new URLSearchParams();
        const start = document.getElementById("startYear")?.value;
        const end = document.getElementById("endYear")?.value;
        const region = document.getElementById("regionFilter")?.value;
        const program = document.getElementById("programFilter")?.value;
        const instructor = document.getElementById("instructorTypeFilter")?.value;

        if (start) {
            params.set("start", start);
        }
        if (end) {
            params.set("end", end);
        }
        if (region) {
            params.set("region", region);
        }
        if (program) {
            params.set("program", program);
        }
        if (instructor) {
            params.set("instructor", instructor);
        }

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
        const canvas = document.getElementById(id);
        if (!canvas) {
            return;
        }

        if (charts[id]) {
            charts[id].destroy();
        }

        // Custom plugin to draw data labels inside doughnut/pie charts
        const dataLabelPlugin = {
            id: "datalabels",
            afterDatasetsDraw(chart, args, options) {
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

        const chartConfig = {
            type,
            data: {
                labels: points.map((point) => point.label),
                datasets: [{
                    label,
                    data: points.map((point) => point.value),
                    ...datasetOptions,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: datasetOptions && datasetOptions.showLegend === true ? true : false,
                        position: datasetOptions && datasetOptions.legendPosition ? datasetOptions.legendPosition : 'top',
                        labels: datasetOptions && datasetOptions.legendSmall
                            ? { color: datasetOptions.legendTextColor || '#1f2937', boxWidth: 12, padding: 8, usePointStyle: true, pointStyle: 'rectRounded' }
                            : { color: datasetOptions && datasetOptions.legendTextColor ? datasetOptions.legendTextColor : COLORS.tick },
                        // disable default click behavior (toggling datasets)
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
                                const dataset = context.dataset || (context.chart && context.chart.data && context.chart.data.datasets && context.chart.data.datasets[0]);
                                const data = dataset && dataset.data ? dataset.data : [];
                                const value = data[context.dataIndex] ?? context.parsed ?? 0;
                                const total = data.reduce((s, v) => s + (Number(v) || 0), 0) || 0;
                                const pct = total ? Math.round((Number(value) / total) * 100) : 0;
                                return `${context.label || ''}: ${Number(value).toLocaleString()} (${pct}%)`;
                            }
                        }
                    },
                },
            },
        };

        // Only include Cartesian scales for bar/line charts
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

        // Register the datalabels plugin only for pie/doughnut charts
        if (type === "doughnut" || type === "pie") {
            charts[id] = new Chart(canvas, { ...chartConfig, plugins: [dataLabelPlugin] });
        } else {
            charts[id] = new Chart(canvas, chartConfig);
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
                const firstVal = $(this).find('option:first').val();
                $(this).val(firstVal).trigger('change.select2');
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
        }
    };
})();
