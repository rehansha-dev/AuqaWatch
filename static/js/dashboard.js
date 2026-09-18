(function () {
  const STATUS_COLOR = { alert: "#dc2626", watch: "#d97706", normal: "#16a34a" };
  const STATUS_LABEL = { alert: "Outbreak Alert", watch: "Watch", normal: "Normal" };

  let map, markersLayer, timeseriesChart, symptomChart, sourceChart;

  function initMap() {
    map = L.map("map", { scrollWheelZoom: false }).setView([16.45, 80.55], 10);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap contributors",
      maxZoom: 18,
    }).addTo(map);
    markersLayer = L.layerGroup().addTo(map);
  }

  function renderMarkers(statuses) {
    markersLayer.clearLayers();
    statuses.forEach((s) => {
      const color = STATUS_COLOR[s.status];
      const radius = 8 + Math.min(s.window_count, 20) * 1.4;
      const circle = L.circleMarker([s.area.lat, s.area.lng], {
        radius,
        color,
        weight: 2,
        fillColor: color,
        fillOpacity: 0.35,
      }).addTo(markersLayer);
      circle.bindPopup(
        `<strong>${s.area.name}</strong><br/>` +
        `Status: <strong style="color:${color}">${STATUS_LABEL[s.status]}</strong><br/>` +
        `Reports (last 7d): ${s.window_count} (expected ~${s.expected})<br/>` +
        `Trend: ${s.trend}` +
        (s.dominant_water_source ? `<br/>Likely source: ${s.dominant_water_source}` : "")
      );
    });
  }

  function renderAlertList(statuses) {
    const el = document.getElementById("alertList");
    el.innerHTML = "";
    statuses.forEach((s) => {
      const div = document.createElement("div");
      div.className = `alert-item status-${s.status}`;
      div.innerHTML = `
        <div>
          <div class="area-name">${s.area.name}</div>
          <div class="area-meta">${s.window_count} reports / 7d · expected ~${s.expected} · trend: ${s.trend}${s.dominant_water_source ? " · " + s.dominant_water_source : ""}</div>
        </div>
        <span class="alert-badge badge-${s.status}">${STATUS_LABEL[s.status]}</span>
      `;
      el.appendChild(div);
    });
  }

  function populateAreaFilter(statuses) {
    const sel = document.getElementById("areaFilter");
    const existing = new Set(Array.from(sel.options).map((o) => o.value));
    statuses.forEach((s) => {
      const id = String(s.area.id);
      if (!existing.has(id)) {
        const opt = document.createElement("option");
        opt.value = id;
        opt.textContent = s.area.name;
        sel.appendChild(opt);
      }
    });
  }

  async function loadSummary() {
    const res = await fetch("/api/summary");
    const data = await res.json();
    document.getElementById("statTotal").textContent = data.total_reports;
    document.getElementById("statToday").textContent = data.today_reports;
    document.getElementById("statAreas").textContent = data.areas_monitored;
    document.getElementById("statAlerts").textContent = data.active_alerts;
    document.getElementById("statWatch").textContent = data.active_watches;
    renderMarkers(data.statuses);
    renderAlertList(data.statuses);
    populateAreaFilter(data.statuses);
  }

  async function loadTimeseries() {
    const res = await fetch("/api/timeseries?days=14");
    const data = await res.json();
    const ctx = document.getElementById("timeseriesChart").getContext("2d");
    if (timeseriesChart) timeseriesChart.destroy();
    timeseriesChart = new Chart(ctx, {
      type: "line",
      data: {
        labels: data.labels.map((d) => d.slice(5)),
        datasets: [{
          label: "Reports",
          data: data.values,
          borderColor: "#0284c7",
          backgroundColor: "rgba(2,132,199,0.12)",
          fill: true,
          tension: 0.35,
          pointRadius: 3,
        }],
      },
      options: {
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
      },
    });
  }

  async function loadSymptomChart() {
    const res = await fetch("/api/symptom-distribution");
    const data = await res.json();
    const ctx = document.getElementById("symptomChart").getContext("2d");
    if (symptomChart) symptomChart.destroy();
    symptomChart = new Chart(ctx, {
      type: "bar",
      data: {
        labels: data.labels,
        datasets: [{
          data: data.values,
          backgroundColor: "#0369a1",
          borderRadius: 6,
        }],
      },
      options: {
        indexAxis: "y",
        plugins: { legend: { display: false } },
        scales: { x: { beginAtZero: true, ticks: { precision: 0 } } },
      },
    });
  }

  async function loadSourceChart() {
    const res = await fetch("/api/water-source-breakdown");
    const data = await res.json();
    const ctx = document.getElementById("sourceChart").getContext("2d");
    if (sourceChart) sourceChart.destroy();
    const palette = ["#0284c7", "#0ea5e9", "#38bdf8", "#7dd3fc", "#d97706", "#dc2626", "#16a34a", "#64748b"];
    sourceChart = new Chart(ctx, {
      type: "doughnut",
      data: {
        labels: data.labels,
        datasets: [{ data: data.values, backgroundColor: palette }],
      },
      options: { plugins: { legend: { position: "bottom", labels: { boxWidth: 10, font: { size: 11 } } } } },
    });
  }

  function severityPillClass(sev) {
    return `sev-pill sev-${sev}`;
  }

  async function loadReports(areaId) {
    const url = areaId ? `/api/reports?area_id=${areaId}` : "/api/reports";
    const res = await fetch(url);
    const rows = await res.json();
    const tbody = document.querySelector("#reportsTable tbody");
    tbody.innerHTML = "";
    rows.slice(0, 100).forEach((r) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${r.onset_date || "—"}</td>
        <td>${r.area}</td>
        <td>${r.reporter_type}</td>
        <td>${r.age ?? "—"}</td>
        <td>${r.symptoms.join(", ") || "—"}</td>
        <td>${r.water_source || "—"}</td>
        <td><span class="${severityPillClass(r.severity)}">${r.severity}</span></td>
      `;
      tbody.appendChild(tr);
    });
  }

  async function refreshAll() {
    await Promise.all([loadSummary(), loadTimeseries(), loadSymptomChart(), loadSourceChart(), loadReports()]);
  }

  document.addEventListener("DOMContentLoaded", () => {
    initMap();
    refreshAll();
    setInterval(refreshAll, 30000);
    document.getElementById("refreshBtn").addEventListener("click", refreshAll);
    document.getElementById("areaFilter").addEventListener("change", (e) => loadReports(e.target.value));
  });
})();
