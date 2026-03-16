/* ═══════════════════════════════════════════════════════════════
   app.js  —  FlakyScan Dashboard JavaScript
   ═══════════════════════════════════════════════════════════════ */

"use strict";

// ─── State ────────────────────────────────────────────────────
let allTestData = [];
let barChart = null;
let pieChart = null;
let trendChart = null;
let sortKey = 'failure_rate';
let sortAsc = false;

// ─── DOM refs ─────────────────────────────────────────────────
const $id = id => document.getElementById(id);

// ─── Initialise ───────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  fetchData();
  initCharts();
  initUploadArea();
  initLabUploadArea();
});

// ─── Tab Navigation ───────────────────────────────────────────
function switchTab(tabId) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

  event.target.classList.add('active');
  $id('tab-' + tabId).classList.add('active');

  // Lazy-load trend data when switching to trends tab
  if (tabId === 'trends') {
    fetchTrends();
    fetchTrendSummary();
  }
  if (tabId === 'webhooks') {
    fetchWebhooks();
  }
}

// ─── Chart initialisation ─────────────────────────────────────
function initCharts() {
  const chartDefaults = {
    color: '#8b949e',
    font: { family: 'Inter, system-ui', size: 12 },
  };
  Chart.defaults.color = chartDefaults.color;
  Chart.defaults.font  = chartDefaults.font;

  // Bar chart — Failure rate per test
  barChart = new Chart($id('failureBarChart'), {
    type: 'bar',
    data: { labels: [], datasets: [{ label: 'Failure Rate (%)', data: [], borderRadius: 6, borderSkipped: false }] },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => ` ${(ctx.raw * 100).toFixed(1)} %`,
          },
        },
      },
      scales: {
        x: {
          grid: { color: 'rgba(48,54,61,.6)' },
          ticks: { maxRotation: 40, font: { size: 10 } },
        },
        y: {
          grid: { color: 'rgba(48,54,61,.6)' },
          min: 0,
          max: 1,
          ticks: { callback: v => (v * 100) + '%' },
        },
      },
    },
  });

  // Pie chart — Flaky vs Stable
  pieChart = new Chart($id('distributionPieChart'), {
    type: 'doughnut',
    data: {
      labels: ['Flaky', 'Stable'],
      datasets: [{
        data: [0, 0],
        backgroundColor: ['rgba(210,153,34,.8)', 'rgba(63,185,80,.8)'],
        borderColor: ['#d29922', '#3fb950'],
        borderWidth: 2,
        hoverOffset: 8,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '68%',
      plugins: {
        legend: { position: 'bottom', labels: { padding: 18, usePointStyle: true } },
        tooltip: {
          callbacks: {
            label: ctx => ` ${ctx.label}: ${ctx.raw} tests`,
          },
        },
      },
    },
  });

  // Trend line chart
  trendChart = new Chart($id('trendLineChart'), {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        {
          label: 'Flaky Tests',
          data: [],
          borderColor: '#d29922',
          backgroundColor: 'rgba(210,153,34,.15)',
          fill: true,
          tension: 0.3,
          pointRadius: 4,
        },
        {
          label: 'Total Tests',
          data: [],
          borderColor: '#58a6ff',
          backgroundColor: 'rgba(88,166,255,.08)',
          fill: true,
          tension: 0.3,
          pointRadius: 4,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: 'bottom', labels: { padding: 18, usePointStyle: true } } },
      scales: {
        x: { grid: { color: 'rgba(48,54,61,.6)' } },
        y: { grid: { color: 'rgba(48,54,61,.6)' }, beginAtZero: true },
      },
    },
  });
}

// ─── Fetch & Render ───────────────────────────────────────────
async function fetchData() {
  try {
    const res = await fetch('/flaky-tests');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const json = await res.json();
    allTestData = json.flaky_tests || [];
    renderAll();
    $id('lastUpdated').textContent = 'Updated ' + new Date().toLocaleTimeString();
    showBanner('Data refreshed successfully.', 'success', 3000);
  } catch (err) {
    showBanner('Failed to load data: ' + err.message, 'error');
    console.error(err);
  }
}

function renderAll() {
  updateKPIs(allTestData);
  updateCharts(allTestData);
  renderTable(filteredSortedData());
}

// ─── Run Tests ────────────────────────────────────────────────
async function runTests() {
  const btn = $id('runTestsBtn');
  btn.disabled = true;
  showLoading('Running test suite (x5)…');

  try {
    const res = await fetch('/run-tests', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ runs: 5 }) });
    const json = await res.json();

    if (!res.ok) throw new Error(json.message || `HTTP ${res.status}`);

    hideLoading();
    showBanner(
      `Tests complete — ${json.total_tests} tests, ${json.flaky_count} flaky detected.`,
      'success',
      5000,
    );
    await fetchData();
  } catch (err) {
    hideLoading();
    showBanner('Test run failed: ' + err.message, 'error');
    console.error(err);
  } finally {
    btn.disabled = false;
  }
}

// ─── KPIs ─────────────────────────────────────────────────────
function updateKPIs(data) {
  const total   = data.length;
  const flaky   = data.filter(d => d.failure_rate > 0 && d.failure_rate < 1).length;
  const stable  = total - flaky;
  const avgRate = total ? data.reduce((s, d) => s + d.failure_rate, 0) / total : 0;

  animateNumber($id('totalTests'),  total);
  animateNumber($id('flakyCount'),  flaky);
  $id('avgRate').textContent    = (avgRate * 100).toFixed(1) + '%';
  animateNumber($id('stableCount'), stable);
}

function animateNumber(el, target) {
  const start  = parseInt(el.textContent) || 0;
  const frames = 20;
  let frame    = 0;
  const step   = () => {
    frame++;
    el.textContent = Math.round(start + (target - start) * frame / frames);
    if (frame < frames) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

// ─── Charts ───────────────────────────────────────────────────
function updateCharts(data) {
  // Bar chart
  const sorted = [...data].sort((a, b) => b.failure_rate - a.failure_rate).slice(0, 12);
  barChart.data.labels   = sorted.map(d => shortName(d.test_name));
  barChart.data.datasets[0].data = sorted.map(d => d.failure_rate);
  barChart.data.datasets[0].backgroundColor = sorted.map(d => rateColor(d.failure_rate));
  barChart.update('active');

  // Pie chart
  const flakyCount  = data.filter(d => d.failure_rate > 0 && d.failure_rate < 1).length;
  const stableCount = data.length - flakyCount;
  pieChart.data.datasets[0].data = [flakyCount, stableCount];
  pieChart.update('active');
}

function rateColor(rate) {
  if (rate >= 0.6) return 'rgba(248,81,73,.8)';
  if (rate >= 0.3) return 'rgba(210,153,34,.8)';
  return 'rgba(88,166,255,.8)';
}

function shortName(name) {
  const parts = name.split('::');
  return parts[parts.length - 1] || name;
}

// ─── Table ────────────────────────────────────────────────────
function filteredSortedData() {
  const query  = ($id('searchInput').value || '').toLowerCase();
  const filter = $id('filterSelect').value;

  return allTestData
    .filter(d => {
      if (filter === 'flaky'  && !(d.failure_rate > 0 && d.failure_rate < 1)) return false;
      if (filter === 'stable' &&   (d.failure_rate > 0 && d.failure_rate < 1)) return false;
      return d.test_name.toLowerCase().includes(query);
    })
    .sort((a, b) => {
      const av = a[sortKey] ?? '';
      const bv = b[sortKey] ?? '';
      const cmp = typeof av === 'number' ? av - bv : String(av).localeCompare(String(bv));
      return sortAsc ? cmp : -cmp;
    });
}

function renderTable(data) {
  const tbody = $id('tableBody');

  if (!data.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-state">No tests match the current filter.</td></tr>`;
    return;
  }

  tbody.innerHTML = data.map(row => {
    const isFlaky   = row.failure_rate > 0 && row.failure_rate < 1;
    const badge     = isFlaky ? '<span class="badge badge-flaky">⚠ Flaky</span>' : '<span class="badge badge-stable">✓ Stable</span>';
    const pct       = (row.failure_rate * 100).toFixed(1);
    const barColor  = rateColor(row.failure_rate);
    const fix       = row.suggested_fix ? escHtml(row.suggested_fix) : '—';

    return `
      <tr>
        <td><code style="font-size:.8rem;color:var(--accent)">${escHtml(shortName(row.test_name))}</code>
            <br><small style="color:var(--text-muted);font-size:.7rem">${escHtml(row.test_name)}</small></td>
        <td>${row.total_runs}</td>
        <td>${row.failures}</td>
        <td>
          <div class="rate-bar-wrap">
            <div class="rate-bar-bg">
              <div class="rate-bar" style="width:${pct}%;background:${barColor}"></div>
            </div>
            <span class="rate-text">${pct}%</span>
          </div>
        </td>
        <td>${badge}</td>
        <td><p class="suggestion-text">${fix}</p></td>
      </tr>`;
  }).join('');
}

function sortTable(key) {
  if (sortKey === key) sortAsc = !sortAsc;
  else { sortKey = key; sortAsc = false; }
  renderTable(filteredSortedData());
}

function filterTable() {
  renderTable(filteredSortedData());
}

// ─── Trends ───────────────────────────────────────────────────
async function fetchTrends() {
  try {
    const res = await fetch('/trends?days=30');
    if (!res.ok) return;
    const json = await res.json();
    const trends = json.trends || [];

    trendChart.data.labels = trends.map(t => {
      const d = new Date(t.recorded_at);
      return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    });
    trendChart.data.datasets[0].data = trends.map(t => t.flaky_count);
    trendChart.data.datasets[1].data = trends.map(t => t.total_tests);
    trendChart.update('active');
  } catch (err) {
    console.error('Failed to fetch trends:', err);
  }
}

async function fetchTrendSummary() {
  try {
    const res = await fetch('/trends/summary');
    if (!res.ok) return;
    const data = await res.json();

    renderTrendCard('trendNewly', 'trendNewlyList', data.newly_flaky);
    renderTrendCard('trendResolved', 'trendResolvedList', data.resolved);
    renderTrendCard('trendWorsened', 'trendWorsenedList', data.worsened);
    renderTrendCard('trendImproved', 'trendImprovedList', data.improved);
  } catch (err) {
    console.error('Failed to fetch trend summary:', err);
  }
}

function renderTrendCard(countId, listId, items) {
  $id(countId).textContent = items.length;
  const ul = $id(listId);
  if (!items.length) {
    ul.innerHTML = '<li style="color:var(--text-muted);font-size:.8rem">None</li>';
    return;
  }
  ul.innerHTML = items.map(n => `<li><code style="font-size:.75rem">${escHtml(shortName(n))}</code></li>`).join('');
}

// ─── CI Integration — JUnit Upload ───────────────────────────
function initUploadArea() {
  const area = $id('uploadArea');
  const input = $id('junitFiles');

  area.addEventListener('dragover', e => { e.preventDefault(); area.classList.add('drag-over'); });
  area.addEventListener('dragleave', () => area.classList.remove('drag-over'));
  area.addEventListener('drop', e => {
    e.preventDefault();
    area.classList.remove('drag-over');
    input.files = e.dataTransfer.files;
    showSelectedFiles(input.files);
  });

  input.addEventListener('change', () => showSelectedFiles(input.files));
}

function showSelectedFiles(files) {
  const container = $id('uploadedFiles');
  const btn = $id('ingestBtn');
  if (!files.length) { container.style.display = 'none'; btn.style.display = 'none'; return; }

  container.style.display = 'block';
  btn.style.display = 'inline-flex';
  container.innerHTML = Array.from(files).map(f =>
    `<span class="file-chip">📄 ${escHtml(f.name)} <small>(${(f.size/1024).toFixed(1)} KB)</small></span>`
  ).join('');
}

async function ingestJUnit() {
  const input = $id('junitFiles');
  if (!input.files.length) { showBanner('No files selected.', 'error', 3000); return; }

  const formData = new FormData();
  Array.from(input.files).forEach(f => formData.append('files', f));

  showLoading('Ingesting JUnit reports…');

  try {
    const res = await fetch('/ingest-junit', { method: 'POST', body: formData });
    const json = await res.json();
    hideLoading();

    if (!res.ok) throw new Error(json.message || `HTTP ${res.status}`);

    $id('ingestResult').innerHTML = `
      <div class="status-banner success">
        Ingested ${json.files_parsed} report(s): ${json.total_tests} tests, ${json.flaky_count} flaky detected. Batch: <code>${json.batch_id.slice(0,8)}</code>
      </div>`;

    input.value = '';
    $id('uploadedFiles').style.display = 'none';
    $id('ingestBtn').style.display = 'none';
    await fetchData();
  } catch (err) {
    hideLoading();
    showBanner('Ingestion failed: ' + err.message, 'error');
    console.error(err);
  }
}

// ─── Webhooks ─────────────────────────────────────────────────
async function fetchWebhooks() {
  try {
    const res = await fetch('/webhooks');
    if (!res.ok) return;
    const json = await res.json();
    renderWebhookTable(json.webhooks || []);
  } catch (err) {
    console.error('Failed to fetch webhooks:', err);
  }
}

function renderWebhookTable(webhooks) {
  const tbody = $id('webhookTableBody');
  if (!webhooks.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No webhooks configured.</td></tr>';
    return;
  }

  tbody.innerHTML = webhooks.map(w => {
    const urlDisplay = escHtml(w.url.length > 50 ? w.url.slice(0, 50) + '…' : w.url);
    const created = new Date(w.created_at).toLocaleDateString();
    const typeBadge = w.type === 'slack'
      ? '<span class="badge" style="background:rgba(88,166,255,.2);color:var(--accent);border:1px solid rgba(88,166,255,.4)">Slack</span>'
      : '<span class="badge" style="background:rgba(139,148,158,.2);color:var(--text-muted);border:1px solid var(--border)">Generic</span>';

    return `<tr>
      <td><strong>${escHtml(w.name)}</strong></td>
      <td><code style="font-size:.75rem">${urlDisplay}</code></td>
      <td>${typeBadge}</td>
      <td>${created}</td>
      <td><button class="btn btn-secondary" style="padding:.3rem .6rem;font-size:.75rem" onclick="deleteWebhook(${w.id})">Delete</button></td>
    </tr>`;
  }).join('');
}

async function addWebhook() {
  const name = $id('whName').value.trim();
  const url = $id('whUrl').value.trim();
  const type = $id('whType').value;

  if (!name || !url) { showBanner('Name and URL are required.', 'error', 3000); return; }

  try {
    const res = await fetch('/webhooks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, url, type }),
    });
    const json = await res.json();
    if (!res.ok) throw new Error(json.message || `HTTP ${res.status}`);

    showBanner('Webhook added.', 'success', 3000);
    $id('whName').value = '';
    $id('whUrl').value = '';
    fetchWebhooks();
  } catch (err) {
    showBanner('Failed to add webhook: ' + err.message, 'error');
  }
}

async function deleteWebhook(id) {
  try {
    const res = await fetch(`/webhooks/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    showBanner('Webhook deleted.', 'success', 3000);
    fetchWebhooks();
  } catch (err) {
    showBanner('Failed to delete webhook: ' + err.message, 'error');
  }
}

async function testWebhookForm() {
  const url = $id('whUrl').value.trim();
  const type = $id('whType').value;
  if (!url) { showBanner('Enter a webhook URL first.', 'error', 3000); return; }

  try {
    const res = await fetch('/webhooks/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, type }),
    });
    const json = await res.json();
    if (json.success) {
      showBanner('Test notification sent successfully.', 'success', 3000);
    } else {
      showBanner('Webhook test failed: ' + (json.error || 'Unknown error'), 'error');
    }
  } catch (err) {
    showBanner('Webhook test failed: ' + err.message, 'error');
  }
}

// ─── Test Laboratory — Python Upload ───────────────────────────
function handleLabFileSelection(input) {
  const container = $id('labFilePreview');
  const btn = $id('labExecuteBtn');
  const files = input.files;

  if (!files.length) {
    container.style.display = 'none';
    btn.style.display = 'none';
    return;
  }

  container.style.display = 'block';
  btn.style.display = 'inline-flex';
  container.innerHTML = `<span class="file-chip">🐍 ${escHtml(files[0].name)} <small>(${(files[0].size/1024).toFixed(1)} KB)</small></span>`;
}

async function executeLabTest() {
  const input = $id('labFile');
  const runs = $id('labRuns').value || 3;
  if (!input.files.length) { showBanner('No file selected.', 'error', 3000); return; }

  const formData = new FormData();
  formData.append('file', input.files[0]);
  formData.append('runs', runs);

  showLoading(`Executing uploaded tests (${runs} runs)…`);

  try {
    const res = await fetch('/upload-tests', { method: 'POST', body: formData });
    const json = await res.json();
    hideLoading();

    if (!res.ok) throw new Error(json.message || `HTTP ${res.status}`);

    $id('labResult').innerHTML = `
      <div class="status-banner success">
        Success: ${json.total_tests} tests executed, ${json.flaky_count} flaky detected. 
        Batch ID: <code>${json.batch_id.slice(0,8)}</code>
      </div>
      <div style="margin-top: 1rem; color: var(--text-muted); font-size: 0.85rem;">
        The results have been merged into your global dashboard and trends.
      </div>`;

    input.value = '';
    $id('labFilePreview').style.display = 'none';
    $id('labExecuteBtn').style.display = 'none';
    await fetchData();
  } catch (err) {
    hideLoading();
    showBanner('Upload execution failed: ' + err.message, 'error');
    console.error(err);
  }
}

function initLabUploadArea() {
  const area = $id('labUploadArea');
  const input = $id('labFile');
  if (!area || !input) return;

  area.addEventListener('dragover', e => { e.preventDefault(); area.classList.add('drag-over'); });
  area.addEventListener('dragleave', () => area.classList.remove('drag-over'));
  area.addEventListener('drop', e => {
    e.preventDefault();
    area.classList.remove('drag-over');
    if (e.dataTransfer.files.length) {
      input.files = e.dataTransfer.files;
      handleLabFileSelection(input);
    }
  });
}

// ─── UI helpers ───────────────────────────────────────────────
function showBanner(msg, type = 'info', autoHideMs = 0) {
  const el = $id('statusBanner');
  el.textContent = msg;
  el.className   = `status-banner ${type}`;
  if (autoHideMs) setTimeout(() => el.classList.add('hidden'), autoHideMs);
}

function showLoading(msg = 'Loading…') {
  $id('loadingMsg').textContent = msg;
  $id('loadingOverlay').classList.remove('hidden');
}

function hideLoading() {
  $id('loadingOverlay').classList.add('hidden');
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
