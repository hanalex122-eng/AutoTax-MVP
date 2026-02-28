/* =========================================================
   AutoTax â€” app.js  v4.1
   + Review Queue, Manuel DÃ¼zeltme, Excel-like Footer
   ========================================================= */
const API      = "";
const PER_PAGE = 100;

let allInvoices  = [];
let filtered     = [];
let currentPage  = 1;
let totalPages   = 1;
let serverTotal  = 0;
let sortCol      = "date";
let sortAsc      = false;
let chartMonthly   = null;
let chartCategory  = null;

// â”€â”€ AUTH HELPERS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function getToken() { return localStorage.getItem('at_token'); }

async function authFetch(url, opts = {}) {
  const tok = getToken();
  if (!tok) { window.location.replace('/login.html'); return null; }
  opts.headers = { ...(opts.headers || {}), Authorization: `Bearer ${tok}` };
  opts.credentials = 'include';
  let res = await fetch(url, opts);
  if (res.status === 401) {
    const rr = await fetch(`${API}/api/auth/refresh`, { method: 'POST', credentials: 'include' });
    if (rr.ok) {
      const rd = await rr.json();
      localStorage.setItem('at_token', rd.access_token);
      opts.headers.Authorization = `Bearer ${rd.access_token}`;
      res = await fetch(url, opts);
    } else {
      localStorage.removeItem('at_token');
      localStorage.removeItem('at_user');
      window.location.replace('/login.html');
      return null;
    }
  }
  return res;
}

async function setupAuth() {
  try {
    const res  = await authFetch(`${API}/api/auth/me`);
    if (!res) return;
    const user = await res.json();
    localStorage.setItem('at_user', JSON.stringify(user));

    const bar  = document.getElementById('topbar-user');
    const used = user.usage?.used  ?? 0;
    const lim  = user.usage?.limit ?? 50;
    const pct  = Math.min(100, Math.round(used / lim * 100));

    document.getElementById('tb-name').textContent  = user.full_name || user.email;
    const chip = document.getElementById('tb-plan');
    chip.textContent  = user.plan_label || user.plan;
    chip.className    = `plan-chip ${user.plan}`;

    const qbar = document.getElementById('tb-quota-bar');
    qbar.style.width  = pct + '%';
    qbar.className    = 'quota-bar' + (pct >= 90 ? ' over' : pct >= 70 ? ' warn' : '');
    document.getElementById('tb-usage').textContent = `${used}/${lim === 999999999 ? 'âˆž' : lim}`;
    bar.style.display = 'flex';

    document.getElementById('btn-logout').addEventListener('click', async () => {
      await authFetch(`${API}/api/auth/logout`, { method: 'POST' });
      localStorage.removeItem('at_token');
      localStorage.removeItem('at_user');
      window.location.replace('/login.html');
    });
  } catch(e) {
    console.warn('Auth setup failed', e);
  }
}

// â”€â”€ INIT â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
document.addEventListener("DOMContentLoaded", async () => {
  await setupAuth();
  setupNav();
  setupTheme();
  setupUpload();
  setupTableSort();
  setupFilters();
  setupExports();
  setupModal();
  setupEditModal();
  setupSelectAll();
  setupStats();
  setupExcelFooter();
  await loadPage(1);
});

// â”€â”€ NAVIGATION â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function setupNav() {
  document.querySelectorAll(".nav-links li").forEach(li => {
    li.addEventListener("click", () => {
      document.querySelectorAll(".nav-links li").forEach(x => x.classList.remove("active"));
      document.querySelectorAll(".view").forEach(x => x.classList.remove("active"));
      li.classList.add("active");
      const view = li.dataset.view;
      document.getElementById("view-" + view).classList.add("active");
      if (view === "review") loadReviewQueue(1);
      if (view === "ledger") { initLedger(); loadLedger(); }
    });
  });
  loadPlanWidget();
}

// â”€â”€ THEME â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function setupTheme() {
  document.documentElement.dataset.theme = localStorage.getItem("theme") || "light";
  document.getElementById("themeToggle").addEventListener("click", () => {
    const t = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = t;
    localStorage.setItem("theme", t);
    rebuildCharts();
  });
}

// â”€â”€ SERVER-SIDE SAYFALAMA â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async function loadPage(page, params = buildFilterParams()) {
  setStatus("load", "YÃ¼kleniyorâ€¦");
  try {
    params.set("page",     page);
    params.set("per_page", PER_PAGE);
    const r    = await authFetch(`${API}/api/stats/summary?${params}`);
    if (!r.ok) throw new Error(r.status);
    const body = await r.json();

    allInvoices = (body.invoices || []).map(norm);
    filtered    = [...allInvoices];
    currentPage = body.page  || page;
    totalPages  = body.pages || 1;
    serverTotal = body.count || allInvoices.length;

    renderTable(filtered);
    renderSummary(body);
    renderPagination();
    renderDashboard(body);
    updateExcelFooter();
    updateReviewBadge(allInvoices.filter(i => i.needs_review).length);
    setStatus("ok", "BaÄŸlÄ±");
  } catch (e) {
    setStatus("error", "API baÄŸlantÄ±sÄ± yok");
    console.error("loadPage hata:", e);
  }
}

function buildFilterParams() {
  const p = new URLSearchParams();
  const df  = (document.getElementById("fDateFrom") || {}).value;
  const dt  = (document.getElementById("fDateTo")   || {}).value;
  const ven = ((document.getElementById("fVendor")  || {}).value || "").trim();
  const cat = (document.getElementById("fCategory") || {}).value;
  const mn  = (document.getElementById("fMin")      || {}).value;
  const mx  = (document.getElementById("fMax")      || {}).value;
  if (df)  p.set("start",      df);
  if (dt)  p.set("end",        dt);
  if (ven) p.set("vendor",     ven);
  if (cat) p.set("category",   cat);
  if (mn)  p.set("min_amount", mn);
  if (mx)  p.set("max_amount", mx);
  return p;
}

function norm(inv) {
  const d = inv.data || inv.parsed || inv || {};
  return {
    _id:            inv.id       || inv.invoice_id || "",
    _ts:            inv.timestamp || "",
    filename:       inv.filename  || d.filename || "",
    vendor:         d.vendor      || "",
    date:           d.date        || "",
    time:           d.time        || "",
    total:          toF(d.total),
    vat_amount:     toF(d.vat_amount),
    vat_rate:       d.vat_rate    || "",
    invoice_no:     d.invoice_number || d.invoice_no || "",
    category:       d.category    || "",
    payment_method: d.payment_method || "",
    qr_raw:         (d.qr_raw     || inv.qr_raw  || "").slice(0, 500),
    qr_parsed:      d.qr_parsed   || inv.qr_parsed || null,
    raw_text:       (d.raw_text   || inv.raw_text || "").slice(0, 5000),
    needs_review:   !!inv.needs_review,
    review_reason:  inv.review_reason || d.review_reason || "",
  };
}
const toF = v => { const n = parseFloat(v); return isNaN(n) ? 0 : n; };

// â”€â”€ UPLOAD â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function setupUpload() {
  const input = document.getElementById("fileInput");
  const btn   = document.getElementById("uploadBtn");
  const zone  = document.getElementById("dropZone");
  const fList = document.getElementById("fileList");

  const refresh = () => {
    btn.disabled = !input.files.length;
    fList.innerHTML = [...input.files].map(f =>
      `<div class="file-item">
        <span class="fi-name">${esc(f.name)}</span>
        <span class="fi-size">${fmtSize(f.size)}</span>
      </div>`
    ).join("");
  };

  input.addEventListener("change", refresh);
  zone.addEventListener("dragover",  e => { e.preventDefault(); zone.classList.add("drag-over"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
  zone.addEventListener("drop", e => {
    e.preventDefault(); zone.classList.remove("drag-over");
    input.files = e.dataTransfer.files; refresh();
  });
  btn.addEventListener("click", doUpload);
}

async function doUpload() {
  const input = document.getElementById("fileInput");
  const files = [...input.files];
  if (!files.length) return;

  const wrap  = document.getElementById("uploadProgressWrap");
  const fill  = document.getElementById("progressFill");
  const label = document.getElementById("progressLabel");
  const log   = document.getElementById("uploadLog");

  wrap.style.display = "block";
  log.innerHTML = "";
  setStatus("load", "OCR iÅŸleniyorâ€¦");

  let reviewCount = 0;

  for (let i = 0; i < files.length; i++) {
    fill.style.width = Math.round((i / files.length) * 100) + "%";
    label.textContent = `${i + 1} / ${files.length} â€” ${files[i].name}`;

    const fd = new FormData();
    fd.append("file", files[i]);
    try {
      const res  = await authFetch(`${API}/api/ocr/upload`, { method: "POST", body: fd });
      const data = await res.json();

      // Duplikasyon uyarısı
      if (data.duplicate_warning) {
        const dw = data.duplicate_warning;
        const msg = `⚠️ Duplik Fatura Tespit Edildi!\n\nBu fatura daha önce sisteme eklenmiş olabilir:\n• Tarih: ${dw.existing_date || "-"}\n• Tutar: €${(dw.existing_total||0).toFixed(2)}\n• Yüklenme: ${(dw.existing_timestamp||"").slice(0,10)}\n\nYine de kaydetmek istiyor musunuz?`;
        if (!confirm(msg)) {
          showToast("Fatura iptal edildi.", "warn");
          uploadBtn.disabled = false;
          uploadBtn.textContent = "Yükle";
          return;
        }
      }
      if (!res.ok) throw new Error(data.message || res.status);

      if (data.needs_review) {
        reviewCount++;
        // UyarÄ±: hangi bilgiler eksik?
        const missing = buildMissingList(data);
        log.innerHTML += logItem("warn",
          `âš  ${esc(files[i].name)} â€” <strong>Manuel giriÅŸ gerekli!</strong> Eksik: ${esc(missing.join(", "))} &nbsp;
          <button class="btn btn-sm btn-primary" onclick="openEditModalById('${esc(data.id)}')">
            Åžimdi DÃ¼zenle
          </button>`
        );
      } else {
        const parts = [
          data.vendor  ? `Firma: ${data.vendor}` : "",
          data.total   ? `Tutar: ${fmtMoney(data.total)}` : "",
          data.date    ? `Tarih: ${data.date}` : "",
          data.qr_raw  ? "QR: âœ“" : "",
        ].filter(Boolean).join(" Â· ");
        log.innerHTML += logItem("ok",  `âœ“ ${esc(files[i].name)} â€” ${esc(parts) || "Ä°ÅŸlendi"}`);
      }
    } catch (e) {
      log.innerHTML += logItem("error", `âœ— ${esc(files[i].name)} â€” ${esc(e.message)}`);
    }
  }

  fill.style.width = "100%";
  label.textContent = "TamamlandÄ±";

  // Eksik fatura uyarÄ±sÄ±
  if (reviewCount > 0) {
    log.innerHTML = `
      <div class="review-alert-bar">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
          <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
        </svg>
        <strong>${reviewCount} faturada bilgiler okunamadÄ±.</strong>
        TutarÄ± onaylayÄ±n veya elle girin.
        <button class="btn btn-sm btn-warning" onclick="goToReview()">Ä°nceleme KuyruÄŸuna Git â†’</button>
      </div>` + log.innerHTML;
  }

  setTimeout(() => { wrap.style.display = "none"; fill.style.width = "0%"; }, 3000);
  input.value = "";
  document.getElementById("uploadBtn").disabled = true;
  document.getElementById("fileList").innerHTML = "";
  setStatus("ok", "HazÄ±r");
  await loadPage(1);
}

function buildMissingList(data) {
  const missing = [];
  if (!data.total)          missing.push("Tutar");
  if (!data.vendor)         missing.push("Firma");
  if (!data.date)           missing.push("Tarih");
  if (!data.invoice_number) missing.push("Fatura No");
  return missing.length ? missing : ["Kontrol gerekli"];
}

function goToReview() {
  document.querySelectorAll(".nav-links li[data-view='review']")[0]?.click();
}

const logItem = (type, msg) => `<div class="log-item log-${type}">${msg}</div>`;

// â”€â”€ FÄ°LTRELER â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function setupFilters() {
  document.getElementById("applyFilter").addEventListener("click", () => loadPage(1));
  document.getElementById("resetFilter").addEventListener("click", () => {
    ["fDateFrom","fDateTo","fVendor","fMin","fMax"].forEach(id => {
      document.getElementById(id).value = "";
    });
    document.getElementById("fCategory").value = "";
    loadPage(1);
  });
  document.getElementById("fVendor").addEventListener("input",
    debounce(() => loadPage(1), 400));
}

function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

// â”€â”€ SIRALAMA â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function setupTableSort() {
  document.querySelectorAll("#invoiceTable th[data-col]").forEach(th => {
    th.addEventListener("click", () => {
      const col = th.dataset.col;
      sortAsc = sortCol === col ? !sortAsc : true;
      sortCol = col;
      filtered.sort((a, b) => {
        let av = a[col] ?? ""; let bv = b[col] ?? "";
        return typeof av === "number"
          ? (sortAsc ? av - bv : bv - av)
          : (sortAsc ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av)));
      });
      renderTable(filtered);
      updateExcelFooter();
    });
  });
}

// â”€â”€ TABLO â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
const CAT_LABELS = {
  food:"Yemek", grocery:"Market", transport:"UlaÅŸÄ±m",
  fuel:"AkaryakÄ±t", hotel:"Otel", health:"SaÄŸlÄ±k",
  electronics:"Elektronik", clothing:"Giyim",
};

function renderTable(data) {
  const tbody = document.getElementById("tBody");
  if (!data.length) {
    tbody.innerHTML = `<tr class="empty-row"><td colspan="13">Fatura bulunamadÄ±.</td></tr>`;
    return;
  }
  tbody.innerHTML = data.map((inv, i) => `
    <tr class="${inv.needs_review ? 'row-review' : ''}">
      <td class="th-chk"><input type="checkbox" class="row-chk" data-i="${i}"></td>
      <td title="${esc(inv.filename)}">${esc(short(inv.filename, 22))}${inv.needs_review ? ' <span class="review-dot" title="Ä°nceleme bekliyor">!</span>' : ''}</td>
      <td title="${esc(inv.vendor)}">${esc(inv.vendor) || '<span class="missing">â€”</span>'}</td>
      <td>${formatDate(inv.date) || '<span class="missing">—</span>'}</td>
      <td>${esc(inv.time) || "â€”"}</td>
      <td class="num ${!inv.total ? 'missing' : ''}">${inv.total ? inv.total.toFixed(2) : 'âš  Yok'}</td>
      <td class="num">${inv.vat_rate ? esc(String(inv.vat_rate)) + "%" : "â€”"}</td>
      <td class="num">${inv.vat_amount ? inv.vat_amount.toFixed(2) : "â€”"}</td>
      <td title="${esc(inv.invoice_no)}">${esc(short(inv.invoice_no, 18)) || "â€”"}</td>
      <td>${inv.category
        ? `<span class="cat-badge cat-${esc(inv.category)}">${esc(CAT_LABELS[inv.category] || inv.category)}</span>`
        : "â€”"}</td>
      <td>${esc(inv.payment_method) || "â€”"}</td>
      <td>${inv.qr_raw ? '<span class="qr-badge">QR</span>' : "â€”"}</td>
      <td style="display:flex;gap:4px">
        <button class="btn btn-ghost detail-btn" style="height:26px;padding:0 8px;font-size:11px" data-i="${i}">Detay</button>
        <button class="btn btn-sm ${inv.needs_review ? 'btn-warning' : 'btn-outline'} edit-btn" style="height:26px;padding:0 8px;font-size:11px" data-id="${esc(inv._id)}" title="${inv.needs_review ? 'Manuel giriÅŸ gerekli!' : 'DÃ¼zenle'}">
          ${inv.needs_review ? 'âœ Gir' : 'âœ'}
        </button>
      </td>
    </tr>`).join("");

  tbody.querySelectorAll(".detail-btn").forEach(b =>
    b.addEventListener("click", () => openModal(filtered[+b.dataset.i])));
  tbody.querySelectorAll(".edit-btn").forEach(b =>
    b.addEventListener("click", () => openEditModalById(b.dataset.id)));
}

// â”€â”€ Ã–ZET â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function renderSummary(body) {
  const t = body.total_sum ?? filtered.reduce((s, i) => s + i.total, 0);
  const v = body.vat_sum   ?? filtered.reduce((s, i) => s + i.vat_amount, 0);
  const c = body.count     ?? filtered.length;
  document.getElementById("fCount").textContent = `${c.toLocaleString("tr-TR")} fatura`;
  document.getElementById("fTotal").textContent = fmtMoney(t);
  document.getElementById("fVat").textContent   = fmtMoney(v);
}

// â”€â”€ PAGÄ°NATION â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function renderPagination() {
  const el = document.getElementById("pagination");
  if (totalPages <= 1) { el.innerHTML = ""; return; }
  const range = [];
  for (let p = Math.max(1, currentPage - 2); p <= Math.min(totalPages, currentPage + 2); p++) range.push(p);
  el.innerHTML = `
    <button class="pg-btn" ${currentPage <= 1 ? "disabled" : ""} data-p="1">Â«</button>
    <button class="pg-btn" ${currentPage <= 1 ? "disabled" : ""} data-p="${currentPage - 1}">â€¹</button>
    ${range.map(p => `<button class="pg-btn ${p === currentPage ? "pg-active" : ""}" data-p="${p}">${p}</button>`).join("")}
    <button class="pg-btn" ${currentPage >= totalPages ? "disabled" : ""} data-p="${currentPage + 1}">â€º</button>
    <button class="pg-btn" ${currentPage >= totalPages ? "disabled" : ""} data-p="${totalPages}">Â»</button>
    <span class="pg-info">${currentPage} / ${totalPages} Â· ${serverTotal.toLocaleString("tr-TR")} kayÄ±t</span>`;
  el.querySelectorAll(".pg-btn:not([disabled])").forEach(b =>
    b.addEventListener("click", () => loadPage(+b.dataset.p)));
}

// â”€â”€ EXCEL-LIKE FOOTER â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function setupExcelFooter() {
  document.getElementById("efFunc").addEventListener("change", updateExcelFooter);
}

function updateExcelFooter() {
  const fn    = (document.getElementById("efFunc") || {}).value || "SUM";
  const data  = filtered;
  if (!data.length) return;

  const totals = data.map(i => i.total || 0);
  const vats   = data.map(i => i.vat_amount || 0);
  const rates  = data.filter(i => i.vat_rate).map(i => parseFloat(i.vat_rate) || 0);

  const calc = (arr, f) => {
    if (!arr.length) return 0;
    switch (f) {
      case "SUM":   return arr.reduce((s, v) => s + v, 0);
      case "AVG":   return arr.reduce((s, v) => s + v, 0) / arr.length;
      case "MIN":   return Math.min(...arr);
      case "MAX":   return Math.max(...arr);
      case "COUNT": return arr.length;
      case "POS":   return arr.filter(v => v > 0).reduce((s, v) => s + v, 0);
      case "NEG":   return arr.filter(v => v < 0).reduce((s, v) => s + v, 0);
      default:      return 0;
    }
  };

  const totalVal  = calc(totals, fn);
  const vatVal    = calc(vats, fn);
  const rateVal   = rates.length ? calc(rates, fn === "COUNT" ? "COUNT" : "AVG") : null;
  const count     = data.length;
  const missingN  = data.filter(i => !i.total).length;

  const fmt = fn === "COUNT" ? v => v.toLocaleString("tr-TR") : fmtMoney;

  document.getElementById("efTotal").textContent   = fmt(totalVal);
  document.getElementById("efVat").textContent     = fmt(vatVal);
  document.getElementById("efVatRate").textContent = rateVal !== null ? (fn === "COUNT" ? rateVal : rateVal.toFixed(1) + "%") : "â€”";

  // Pozitif / negatif net gÃ¶ster
  const net = totals.filter(v => v > 0).reduce((s,v) => s+v, 0)
            - Math.abs(totals.filter(v => v < 0).reduce((s,v) => s+v, 0));

  const infoEl = document.getElementById("efInfo");
  infoEl.innerHTML = `
    <span title="Toplam kayÄ±t sayÄ±sÄ±">n=${count}</span>
    <span class="ef-plus" title="Pozitif toplamÄ±">+${fmtMoney(totals.filter(v=>v>0).reduce((s,v)=>s+v,0))}</span>
    <span class="ef-minus" title="Negatif toplamÄ±">${fmtMoney(totals.filter(v=>v<0).reduce((s,v)=>s+v,0))}</span>
    <span class="ef-net" title="Net (pozitif âˆ’ negatif)">NET ${fmtMoney(net)}</span>
    ${missingN ? `<span class="ef-warn" title="TutarÄ± okunamamÄ±ÅŸ fatura sayÄ±sÄ±">âš  ${missingN} eksik</span>` : ""}
  `;
}

function updateReviewBadge(n) {
  const b = document.getElementById("reviewBadge");
  if (n > 0) { b.textContent = n; b.style.display = "inline"; }
  else        { b.style.display = "none"; }
}

// â”€â”€ DASHBOARD â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function renderDashboard(body = {}) {
  const reviewN = allInvoices.filter(i => i.needs_review).length;
  document.getElementById("kpiCount").textContent  = (body.count     ?? allInvoices.length).toLocaleString("tr-TR");
  document.getElementById("kpiTotal").textContent  = fmtMoney(body.total_sum ?? 0);
  document.getElementById("kpiReview").textContent = reviewN;
  document.getElementById("kpiVat").textContent    = fmtMoney(body.vat_sum ?? 0);

  // KDV kartÄ±na renk
  if (reviewN > 0) {
    document.getElementById("kpiReview").style.color = "#f59e0b";
  }

  renderVendorChips(body.by_vendor || {});
  rebuildCharts(body);
}

function rebuildCharts(body = {}) {
  if (chartMonthly)  { chartMonthly.destroy();  chartMonthly  = null; }
  if (chartCategory) { chartCategory.destroy(); chartCategory = null; }

  const monthly = {};
  allInvoices.forEach(inv => {
    if (!inv.date) return;
    const key = inv.date.slice(0, 7);
    monthly[key] = (monthly[key] || 0) + inv.total;
  });
  const mLabels = Object.keys(monthly).sort();
  chartMonthly = new Chart(
    document.getElementById("chartMonthly").getContext("2d"), {
      type: "bar",
      data: {
        labels: mLabels,
        datasets: [{ label: "Tutar (â‚¬)", data: mLabels.map(k => monthly[k]),
          backgroundColor: "rgba(37,99,235,.75)", borderRadius: 5 }]
      },
      options: { responsive: true, plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true } } }
    }
  );

  const cats  = body.by_category || {};
  const cKeys = Object.keys(cats);
  const COLORS = ["#2563eb","#16a34a","#d97706","#dc2626","#7c3aed","#0891b2","#db2777","#65a30d","#64748b"];
  chartCategory = new Chart(
    document.getElementById("chartCategory").getContext("2d"), {
      type: "doughnut",
      data: {
        labels: cKeys.map(l => CAT_LABELS[l] || l),
        datasets: [{ data: cKeys.map(k => cats[k]),
          backgroundColor: COLORS.slice(0, cKeys.length), borderWidth: 2 }]
      },
      options: { responsive: true, plugins: { legend: { position: "right" } } }
    }
  );
}

function renderVendorChips(byVendor) {
  const chips = Object.entries(byVendor).sort((a, b) => b[1] - a[1]).slice(0, 20);
  document.getElementById("vendorChips").innerHTML = chips.map(([name, amt]) =>
    `<div class="vendor-chip">
      <span class="vc-name">${esc(name)}</span>
      <span class="vc-amt">${fmtMoney(amt)}</span>
    </div>`
  ).join("") || "<span style='color:var(--muted)'>HenÃ¼z veri yok</span>";
}

// â”€â”€ SEÃ‡Ä°M â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function setupSelectAll() {
  document.getElementById("selAll").addEventListener("change", e => {
    document.querySelectorAll(".row-chk").forEach(cb => cb.checked = e.target.checked);
  });
}
function getSelected() {
  const sel = [];
  document.querySelectorAll(".row-chk:checked").forEach(cb => sel.push(filtered[+cb.dataset.i]));
  return sel.length ? sel : filtered;
}

// â”€â”€ EXPORT â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function setupExports() {
  document.getElementById("exportExcel").addEventListener("click", exportExcel);
  document.getElementById("exportJSON").addEventListener("click",  exportJSON);
  document.getElementById("exportFull").addEventListener("click",  exportFull);
}

function exportExcel() {
  const rows = getSelected().map(inv => ({
    "ID": inv._id, "Dosya": inv.filename, "Firma": inv.vendor,
    "Tarih": inv.date, "Saat": inv.time, "Tutar": inv.total,
    "KDV %": inv.vat_rate, "KDV TutarÄ±": inv.vat_amount,
    "Fatura No": inv.invoice_no,
    "Kategori": CAT_LABELS[inv.category] || inv.category,
    "Ã–deme": inv.payment_method,
    "QR": inv.qr_raw,
    "Ä°nceleme": inv.needs_review ? "Evet" : "HayÄ±r",
    "Timestamp": inv._ts,
  }));
  const ws = XLSX.utils.json_to_sheet(rows);
  ws["!cols"] = [36,28,20,12,8,10,7,12,20,12,14,30,8,22].map(w => ({ wch: w }));
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, "Faturalar");
  XLSX.writeFile(wb, `autotax_${today()}.xlsx`);
}

function exportJSON() {
  dl(JSON.stringify(getSelected(), null, 2), `autotax_${today()}.json`, "application/json");
}

function exportFull() {
  const data   = getSelected();
  const report = {
    export_date:    new Date().toISOString(),
    total_count:    serverTotal,
    exported_count: data.length,
    total_sum:      round2(data.reduce((s, i) => s + i.total, 0)),
    vat_sum:        round2(data.reduce((s, i) => s + i.vat_amount, 0)),
    by_vendor:      buildMap(data, "vendor"),
    by_category:    buildMap(data, "category"),
    invoices:       data,
  };
  dl(JSON.stringify(report, null, 2), `autotax_tam_rapor_${today()}.json`, "application/json");
}

function buildMap(data, field) {
  const m = {};
  data.forEach(i => {
    const k = i[field] || "bilinmiyor";
    m[k] = round2((m[k] || 0) + i.total);
  });
  return m;
}

// â”€â”€ DETAY MODAL â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function setupModal() {
  document.getElementById("modalClose").addEventListener("click", closeModal);
  document.getElementById("modal").addEventListener("click", e => {
    if (e.target.id === "modal") closeModal();
  });
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") { closeModal(); closeEditModal(); }
  });
}

function openModal(inv) {
  document.getElementById("modalTitle").textContent = inv.filename || "Fatura";
  let qrText = "QR / Barkod bulunamadÄ±";
  if (inv.qr_raw) {
    try { qrText = inv.qr_parsed ? JSON.stringify(inv.qr_parsed, null, 2) : inv.qr_raw; }
    catch { qrText = inv.qr_raw; }
  }
  document.getElementById("detailQR").textContent  = qrText;
  document.getElementById("detailRaw").textContent = inv.raw_text || "â€”";
  document.getElementById("detailGrid").innerHTML = [
    ["Firma",        inv.vendor],
    ["Tarih",        inv.date],
    ["Saat",         inv.time],
    ["Tutar",        inv.total ? fmtMoney(inv.total) : null],
    ["KDV %",        inv.vat_rate ? inv.vat_rate + "%" : null],
    ["KDV TutarÄ±",   inv.vat_amount ? fmtMoney(inv.vat_amount) : null],
    ["Fatura No",    inv.invoice_no],
    ["Kategori",     CAT_LABELS[inv.category] || inv.category],
    ["Ã–deme",        inv.payment_method],
    ["Ä°nceleme?",    inv.needs_review ? "âš  Evet â€” " + (inv.review_reason || "") : "âœ“ HayÄ±r"],
    ["Dosya",        inv.filename],
    ["YÃ¼klenme",     inv._ts],
    ["ID",           inv._id],
  ].map(([l, v]) =>
    `<div class="detail-item">
      <div class="di-label">${esc(l)}</div>
      <div class="di-value">${esc(v) || "â€”"}</div>
    </div>`
  ).join("");
  document.getElementById("modal").style.display = "flex";
}

function closeModal() {
  document.getElementById("modal").style.display = "none";
}

// â”€â”€ MANUEL DÃœZELTME MODAL â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function setupEditModal() {
  document.getElementById("editModalClose").addEventListener("click", closeEditModal);
  document.getElementById("editModal").addEventListener("click", e => {
    if (e.target.id === "editModal") closeEditModal();
  });

  // KDV otomatik hesap
  const autoCalc = () => {
    if (!document.getElementById("eVatAuto").checked) return;
    const total = parseFloat(document.getElementById("eTotal").value) || 0;
    const rate  = parseFloat(document.getElementById("eVatRate").value) || 0;
    if (total && rate) {
      document.getElementById("eVatAmount").value =
        (total - total / (1 + rate / 100)).toFixed(2);
    }
  };
  document.getElementById("eTotal").addEventListener("input",   autoCalc);
  document.getElementById("eVatRate").addEventListener("input", autoCalc);

  document.getElementById("editSaveBtn").addEventListener("click",  saveEdit);
  document.getElementById("editSkipBtn").addEventListener("click",  skipReview);

  // Refresh buton
  document.getElementById("rqRefresh") && 
    document.getElementById("rqRefresh").addEventListener("click", () => loadReviewQueue(1));
}

async function openEditModalById(invId) {
  const res = await authFetch(`${API}/api/ocr/invoice/${invId}`);
  if (!res || !res.ok) { alert("Fatura yÃ¼klenemedi."); return; }
  const inv = await res.json();
  const d   = inv.data || {};

  document.getElementById("editInvId").value  = inv.id || invId;
  document.getElementById("editModalTitle").textContent = inv.filename || "Fatura DÃ¼zenle";
  document.getElementById("editModalSub").textContent   = inv.id || "";

  // UyarÄ± ÅŸeridi
  const warn = document.getElementById("editWarning");
  if (inv.needs_review) {
    document.getElementById("editWarningMsg").textContent =
      buildMissingList(d).join(", ") + " okunamadÄ±. LÃ¼tfen elle girin veya geÃ§in.";
    warn.style.display = "flex";
  } else {
    warn.style.display = "none";
  }

  document.getElementById("eVendor").value    = d.vendor || "";
  document.getElementById("eInvoiceNo").value = d.invoice_number || "";
  document.getElementById("eDate").value      = d.date || "";
  document.getElementById("eTime").value      = d.time || "";
  document.getElementById("eTotal").value     = d.total || "";
  document.getElementById("eVatRate").value   = d.vat_rate || "";
  document.getElementById("eVatAmount").value = d.vat_amount || "";
  document.getElementById("ePayment").value   = d.payment_method || "";
  setSelectVal("eCategory", d.category || "");

  document.getElementById("editFeedback").style.display = "none";
  document.getElementById("editModal").style.display    = "flex";
}

function setSelectVal(id, val) {
  const sel = document.getElementById(id);
  for (const opt of sel.options) if (opt.value === val) { sel.value = val; return; }
  sel.value = "";
}

async function saveEdit() {
  const invId   = document.getElementById("editInvId").value;
  const totalV  = parseFloat(document.getElementById("eTotal").value);
  const fb      = document.getElementById("editFeedback");

  if (!invId)      { showEditFeedback("error", "Fatura ID bulunamadÄ±."); return; }
  if (isNaN(totalV) || totalV <= 0) {
    showEditFeedback("error", "Tutar girilmedi veya geÃ§ersiz. LÃ¼tfen toplam tutarÄ± girin.");
    document.getElementById("eTotal").focus();
    return;
  }

  const payload = {
    vendor:         document.getElementById("eVendor").value.trim() || null,
    invoice_number: document.getElementById("eInvoiceNo").value.trim() || null,
    date:           document.getElementById("eDate").value || null,
    time:           document.getElementById("eTime").value || null,
    total:          totalV,
    vat_rate:       parseFloat(document.getElementById("eVatRate").value) || null,
    vat_amount:     parseFloat(document.getElementById("eVatAmount").value) || null,
    category:       document.getElementById("eCategory").value || null,
    payment_method: document.getElementById("ePayment").value || null,
    needs_review:   0,
    review_reason:  null,
  };

  const btn = document.getElementById("editSaveBtn");
  btn.disabled   = true;
  btn.textContent = "Kaydediliyorâ€¦";

  try {
    const res = await authFetch(`${API}/api/ocr/invoice/${invId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error((await res.json()).detail || res.status);
    showEditFeedback("ok", "âœ“ Kaydedildi. Fatura inceleme kuyruÄŸundan kaldÄ±rÄ±ldÄ±.");
    setTimeout(() => { closeEditModal(); loadPage(currentPage); loadReviewQueue(1); }, 1200);
  } catch (e) {
    showEditFeedback("error", "Hata: " + e.message);
  } finally {
    btn.disabled   = false;
    btn.textContent = "Kaydet";
  }
}

async function skipReview() {
  const invId = document.getElementById("editInvId").value;
  if (!invId) return;
  await authFetch(`${API}/api/ocr/invoice/${invId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ needs_review: 0, review_reason: "KullanÄ±cÄ± tarafÄ±ndan geÃ§ildi" }),
  });
  closeEditModal();
  loadPage(currentPage);
  loadReviewQueue(1);
}

function showEditFeedback(type, msg) {
  const el = document.getElementById("editFeedback");
  el.style.display     = "block";
  el.style.background  = type === "ok" ? "#f0fdf4" : "#fef2f2";
  el.style.color       = type === "ok" ? "#166534" : "#991b1b";
  el.style.border      = `1px solid ${type === "ok" ? "#bbf7d0" : "#fecaca"}`;
  el.style.padding     = "10px 14px";
  el.style.borderRadius = "8px";
  el.style.fontSize    = "13px";
  el.textContent       = msg;
}

function closeEditModal() {
  document.getElementById("editModal").style.display = "none";
}

// â”€â”€ Ä°NCELEME KUYRUÄžU â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async function loadReviewQueue(page = 1) {
  try {
    const r    = await authFetch(`${API}/api/ocr/review-queue?page=${page}&per_page=20`);
    const body = await r.json();
    const count = body.count || 0;

    document.getElementById("rqCount").textContent = `${count} bekliyor`;
    updateReviewBadge(count);

    const banner = document.getElementById("rqBanner");
    if (count > 0) {
      banner.style.display = "flex";
      document.getElementById("rqBannerMsg").textContent =
        `${count} faturada bilgiler okunamadÄ± ya da bulanÄ±k. ` +
        `TutarÄ± onaylayÄ±n, dÃ¼zeltin veya "GeÃ§" seÃ§in.`;
    } else {
      banner.style.display = "none";
    }

    renderReviewList(body.invoices || []);
    renderRQPagination(body);
  } catch (e) {
    console.error("review queue error:", e);
  }
}

function renderReviewList(invs) {
  const el = document.getElementById("reviewList");
  if (!invs.length) {
    el.innerHTML = `<div class="rq-empty">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="1.5">
        <polyline points="20 6 9 17 4 12"/>
      </svg>
      <p>TÃ¼m faturalar onaylandÄ±!</p>
    </div>`;
    return;
  }
  el.innerHTML = invs.map(inv => {
    const d       = inv.data || {};
    const missing = buildMissingList(d);
    const reason  = inv.review_reason || "Bilgi eksik";
    return `
      <div class="rq-card" id="rqc-${esc(inv.id)}">
        <div class="rqc-top">
          <div>
            <div class="rqc-filename">${esc(inv.filename || "â€”")}</div>
            <div class="rqc-reason">
              <span class="warn-icon">âš </span>
              ${esc(reason)} Â· Eksik: <strong>${esc(missing.join(", "))}</strong>
            </div>
          </div>
          <div class="rqc-ts">${esc((inv.timestamp || "").slice(0,16))}</div>
        </div>
        <div class="rqc-fields">
          ${rqField("Firma",    d.vendor)}
          ${rqField("Tarih",    d.date)}
          ${rqField("Tutar",    d.total  ? fmtMoney(d.total)  : null, true)}
          ${rqField("KDV%",     d.vat_rate ? d.vat_rate + "%" : null)}
          ${rqField("Fatura No",d.invoice_number)}
        </div>
        <div class="rqc-raw">${esc((d.raw_text || "").slice(0, 200))}${(d.raw_text||"").length > 200 ? "â€¦" : ""}</div>
        <div class="rqc-actions">
          <button class="btn btn-primary" onclick="openEditModalById('${esc(inv.id)}')">
            âœ DÃ¼zenle / Gir
          </button>
          <button class="btn btn-ghost" onclick="skipFromQueue('${esc(inv.id)}')">
            â†’ GeÃ§
          </button>
        </div>
      </div>`;
  }).join("");
}

function rqField(label, val, highlight = false) {
  const missing = !val;
  return `<div class="rqf ${missing ? 'rqf-missing' : ''} ${highlight && missing ? 'rqf-critical' : ''}">
    <span class="rqf-label">${esc(label)}</span>
    <span class="rqf-val">${missing ? (highlight ? 'âš  YOK' : 'â€”') : esc(String(val))}</span>
  </div>`;
}

async function skipFromQueue(invId) {
  await authFetch(`${API}/api/ocr/invoice/${invId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ needs_review: 0, review_reason: "KullanÄ±cÄ± tarafÄ±ndan geÃ§ildi" }),
  });
  document.getElementById(`rqc-${invId}`)?.remove();
  const cur = parseInt(document.getElementById("rqCount").textContent) || 0;
  const newN = Math.max(0, cur - 1);
  document.getElementById("rqCount").textContent = `${newN} bekliyor`;
  updateReviewBadge(newN);
}

function renderRQPagination(body) {
  const el = document.getElementById("rqPagination");
  if (!el || body.pages <= 1) { if (el) el.innerHTML = ""; return; }
  el.innerHTML = Array.from({length: body.pages}, (_, i) => i + 1).map(p =>
    `<button class="pg-btn ${p === body.page ? 'pg-active' : ''}" data-p="${p}">${p}</button>`
  ).join("") + `<span class="pg-info">${body.page}/${body.pages} Â· ${body.count} bekliyor</span>`;
  el.querySelectorAll(".pg-btn").forEach(b =>
    b.addEventListener("click", () => loadReviewQueue(+b.dataset.p)));
}

// â”€â”€ Ä°STATÄ°STÄ°K â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function setupStats() {
  document.getElementById("runStats").addEventListener("click", runStats);
}

async function runStats() {
  const p = new URLSearchParams();
  const df  = document.getElementById("sDateFrom").value;
  const dt  = document.getElementById("sDateTo").value;
  const ven = document.getElementById("sVendor").value.trim();
  const cat = document.getElementById("sCategory").value;
  const mn  = document.getElementById("sMin").value;
  const mx  = document.getElementById("sMax").value;
  if (df)  p.set("start", df);
  if (dt)  p.set("end",   dt);
  if (ven) p.set("vendor",     ven);
  if (cat) p.set("category",   cat);
  if (mn)  p.set("min_amount", mn);
  if (mx)  p.set("max_amount", mx);
  p.set("per_page", "1");

  const el = document.getElementById("statsResult");
  el.innerHTML = `<div class="log-item log-info">SorgulanÄ±yorâ€¦</div>`;
  try {
    const r    = await authFetch(`${API}/api/stats/summary?${p}`);
    const body = await r.json();
    el.innerHTML = `
      <div class="stats-card">
        <h3>Ã–zet</h3>
        <div class="stats-kpi-row">
          <div class="stats-kpi"><span class="sk-label">Fatura SayÄ±sÄ±</span><span class="sk-value">${(body.count||0).toLocaleString("tr-TR")}</span></div>
          <div class="stats-kpi"><span class="sk-label">Toplam Tutar</span><span class="sk-value">${fmtMoney(body.total_sum||0)}</span></div>
          <div class="stats-kpi"><span class="sk-label">Toplam KDV</span><span class="sk-value">${fmtMoney(body.vat_sum||0)}</span></div>
        </div>
      </div>
      <div class="stats-card"><h3>Firma BazlÄ± Toplamlar</h3><div id="sVendorChips"></div></div>
      <div class="stats-card"><h3>Kategori BazlÄ± Toplamlar</h3><div id="sCatChips"></div></div>
      <div style="margin-top:8px;display:flex;gap:8px">
        <a href="/api/stats/export/excel?${p}" class="btn btn-success" target="_blank">Excel Ä°ndir</a>
        <a href="/api/stats/export/csv?${p}"   class="btn btn-outline"  target="_blank">CSV Ä°ndir</a>
      </div>`;
    document.getElementById("sVendorChips").innerHTML =
      Object.entries(body.by_vendor || {}).sort((a,b)=>b[1]-a[1]).map(([k,v]) =>
        `<div class="vendor-chip"><span class="vc-name">${esc(k)}</span><span class="vc-amt">${fmtMoney(v)}</span></div>`
      ).join("") || "â€”";
    document.getElementById("sCatChips").innerHTML =
      Object.entries(body.by_category || {}).sort((a,b)=>b[1]-a[1]).map(([k,v]) =>
        `<div class="vendor-chip"><span class="vc-name">${esc(CAT_LABELS[k]||k)}</span><span class="vc-amt">${fmtMoney(v)}</span></div>`
      ).join("") || "â€”";
  } catch (err) {
    el.innerHTML = logItem("error", "API hatasÄ±: " + esc(err.message));
  }
}

// â”€â”€ STATUS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function setStatus(type, text) {
  const el = document.getElementById("apiStatus");
  el.className  = `status-badge status-${type}`;
  el.textContent = text;
}

// â”€â”€ YARDIMCILAR â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function esc(s) {
  if (s == null) return "";
  return String(s)
    .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
    .replace(/"/g,"&quot;").replace(/'/g,"&#39;");
}
function fmtMoney(v) {
  return Number(v).toLocaleString("tr-TR", { minimumFractionDigits:2, maximumFractionDigits:2 }) + " â‚¬";
}
function fmtSize(b) {
  return b > 1024*1024 ? (b/1024/1024).toFixed(1)+" MB" : (b/1024).toFixed(0)+" KB";
}
function short(s, n) { return s && s.length > n ? s.slice(0,n-1)+"â€¦" : (s||""); }
function today()     { return new Date().toISOString().slice(0,10); }

// Kullanıcının bölgesine göre tarih formatı (DB'de YYYY-MM-DD, gösterimde yerel format)
const USER_LOCALE = navigator.language || "de-DE";
function formatDate(isoStr) {
  if (!isoStr) return "";
  try {
    const [y, m, d] = isoStr.split("-");
    const dt = new Date(Number(y), Number(m) - 1, Number(d));
    return dt.toLocaleDateString(USER_LOCALE, { year:"numeric", month:"2-digit", day:"2-digit" });
  } catch { return isoStr; }
}
// Yerel tarih → ISO (filtreler için)
function localToISO(localStr) {
  if (!localStr) return "";
  // Zaten ISO formatındaysa direkt döndür
  if (/^\d{4}-\d{2}-\d{2}$/.test(localStr)) return localStr;
  try {
    const dt = new Date(localStr);
    if (isNaN(dt)) return localStr;
    return dt.toISOString().slice(0, 10);
  } catch { return localStr; }
}
function round2(v)   { return Math.round(v*100)/100; }
function dl(content, filename, mime) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([content], { type:mime }));
  a.download = filename; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 10000);
}

// ── Muhasebe Defteri ─────────────────────────────────────────────────────────
let _ldgPage = 1;
const _ldgPerPage = 50;

function initLedger() {
  document.getElementById("ldgFilter")?.addEventListener("click", () => { _ldgPage = 1; loadLedger(); });
  document.getElementById("ldgReset")?.addEventListener("click", () => {
    document.getElementById("ldgStart").value = "";
    document.getElementById("ldgEnd").value = "";
    document.getElementById("ldgVendor").value = "";
    _ldgPage = 1; loadLedger();
  });
}

async function loadLedger() {
  const start  = document.getElementById("ldgStart")?.value  || "";
  const end    = document.getElementById("ldgEnd")?.value    || "";
  const vendor = document.getElementById("ldgVendor")?.value || "";

  let url = `/api/stats/ledger?page=${_ldgPage}&per_page=${_ldgPerPage}`;
  if (start)  url += `&start=${start}`;
  if (end)    url += `&end=${end}`;
  if (vendor) url += `&vendor=${encodeURIComponent(vendor)}`;

  // Export link güncelle
  let xlsUrl = `/api/stats/export/ledger-excel?`;
  if (start)  xlsUrl += `&start=${start}`;
  if (end)    xlsUrl += `&end=${end}`;
  if (vendor) xlsUrl += `&vendor=${encodeURIComponent(vendor)}`;
  const ldgExcel = document.getElementById("ldgExcel");
  if (ldgExcel) ldgExcel.href = xlsUrl;

  const res = await authFetch(url);
  if (!res || !res.ok) return;
  const d = await res.json();

  // Boş veri kontrolü
  const tbody = document.getElementById("ldgTbody");
  if (!d || (d.count_income === 0 && d.count_expense === 0)) {
    if (tbody) tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:40px;color:#888">
      <div style="font-size:48px">📭</div>
      <div style="margin-top:8px;font-size:15px">Henüz fatura yüklenmedi.</div>
      <div style="margin-top:4px;font-size:13px;color:#aaa">OCR ile fatura yükleyin, muhasebe defteri otomatik oluşur.</div>
    </td></tr>`;
    ["ldgIncome","ldgExpense","ldgNet"].forEach(id => { const el=document.getElementById(id); if(el) el.textContent="0,00"; });
    return;
  }

  const fmt = v => (v !== null && v !== undefined) ? v.toLocaleString(USER_LOCALE, {minimumFractionDigits:2, maximumFractionDigits:2}) : "—";

  // KPI kartlar
  document.getElementById("ldgIncome").textContent       = fmt(d.total_income);
  document.getElementById("ldgExpense").textContent      = fmt(d.total_expense);
  document.getElementById("ldgNet").textContent          = fmt(d.net);
  document.getElementById("ldgNetLabel").textContent     = d.net_label;
  document.getElementById("ldgIncomeCount").textContent  = `${d.count_income} fatura`;
  document.getElementById("ldgExpenseCount").textContent = `${d.count_expense} fatura`;
  document.getElementById("ldgVatIncome").textContent    = fmt(d.vat_income);
  document.getElementById("ldgVatExpense").textContent   = `Ödenen: ${fmt(d.vat_expense)}`;
  const netCard = document.getElementById("ldgNetCard");
  if (netCard) {
    netCard.classList.toggle("profit", d.net >= 0);
    netCard.classList.toggle("loss",   d.net < 0);
  }

  // Aylık özet
  const mb = document.getElementById("ldgMonthlyBody");
  if (mb) {
    mb.innerHTML = d.monthly.map(m => `
      <tr>
        <td>${m.month}</td>
        <td class="num" style="color:#16a34a">${fmt(m.income)}</td>
        <td class="num" style="color:#dc2626">${fmt(m.expense)}</td>
        <td class="num" style="font-weight:700;color:${m.net>=0?'#16a34a':'#dc2626'}">${fmt(m.net)}</td>
        <td class="num">${m.count}</td>
      </tr>`).join("");
    document.getElementById("ldgFtIncome").textContent  = fmt(d.total_income);
    document.getElementById("ldgFtExpense").textContent = fmt(d.total_expense);
    document.getElementById("ldgFtNet").textContent     = fmt(d.net);
    document.getElementById("ldgFtCount").textContent   = d.count;
  }

  // Fatura listesi
  const lb = document.getElementById("ldgBody");
  if (lb) {
    lb.innerHTML = d.invoices.map(inv => {
      const isIncome = inv.invoice_type === "income";
      return `<tr class="${isIncome ? 'row-income' : 'row-expense'}">
        <td><span class="${isIncome ? 'badge-income' : 'badge-expense'}">${isIncome ? 'GELİR' : 'GİDER'}</span></td>
        <td>${formatDate(inv.date) || "—"}</td>
        <td>${esc(inv.vendor) || "—"}</td>
        <td class="num">${inv.total !== null ? fmt(inv.total) : "—"}</td>
        <td class="num">${inv.vat_amount !== null ? fmt(inv.vat_amount) : "—"}</td>
        <td>${esc(inv.category) || "—"}</td>
        <td>${esc(inv.payment_method) || "—"}</td>
      </tr>`;
    }).join("");
  }

  // Sayfa bilgisi
  const pi = document.getElementById("ldgPageInfo");
  if (pi) pi.textContent = `Sayfa ${d.page}/${d.pages} — ${d.count} kayıt`;

  // Pagination
  const pg = document.getElementById("ldgPagination");
  if (pg) {
    let html = "";
    if (_ldgPage > 1)       html += `<button class="btn btn-ghost btn-sm" onclick="ldgGoPage(${_ldgPage-1})">← Önceki</button>`;
    if (_ldgPage < d.pages) html += `<button class="btn btn-ghost btn-sm" onclick="ldgGoPage(${_ldgPage+1})">Sonraki →</button>`;
    pg.innerHTML = html;
  }
}

window.ldgGoPage = (p) => { _ldgPage = p; loadLedger(); };

// ── Plan widget ──────────────────────────────────────────────────────────────
async function loadPlanWidget() {
  try {
    const res = await authFetch("/api/stripe/plan");
    if (!res || !res.ok) return;
    const d = await res.json();
    const plan    = d.plan || "free";
    const limits  = d.limits || {};
    const display = d.display || plan;
    const used    = d.used || 0;
    const limit   = limits.invoices ?? 50;

    const badge = document.getElementById("planBadge");
    if (badge) { badge.textContent = display; badge.className = "plan-badge " + plan; }

    const upgrade = document.getElementById("planUpgrade");
    if (upgrade) upgrade.style.display = plan === "business" ? "none" : "inline";

    if (limit !== -1) {
      const barWrap = document.getElementById("planBarWrap");
      const barFill = document.getElementById("planBarFill");
      const barLabel = document.getElementById("planBarLabel");
      if (barWrap) barWrap.style.display = "flex";
      const pct = Math.min(100, Math.round((used / limit) * 100));
      if (barFill) {
        barFill.style.width = pct + "%";
        barFill.className = "plan-bar-fill" + (pct >= 90 ? " full" : pct >= 70 ? " warn" : "");
      }
      if (barLabel) barLabel.textContent = used + " / " + limit;
    }
  } catch (e) { /* sessiz hata */ }
}

// ── PWA: Service Worker kaydı ────────────────────────────────────────────────
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js", { scope: "/" })
      .then(() => console.log("SW registered"))
      .catch(() => {});
  });
}

// ── PWA: "Ana Ekrana Ekle" prompt ────────────────────────────────────────────
let _deferredInstall = null;
window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  _deferredInstall = e;
  const btn = document.getElementById("btnInstallApp");
  if (btn) btn.style.display = "flex";
});

window.addEventListener("appinstalled", () => {
  _deferredInstall = null;
  const btn = document.getElementById("btnInstallApp");
  if (btn) btn.style.display = "none";
});

window.installApp = async () => {
  if (!_deferredInstall) return;
  _deferredInstall.prompt();
  const { outcome } = await _deferredInstall.userChoice;
  if (outcome === "accepted") _deferredInstall = null;
};

// ── Plan: Kilitli özellik overlay ────────────────────────────────────────────
window.showUpgradePrompt = (feature) => {
  const msg = {
    qr:       "QR Kod okuma Kişisel plan ve üzerinde kullanılabilir.",
    api:      "API erişimi İşletme planında kullanılabilir.",
    members:  "Aile paylaşımı Aile planı ve üzerinde kullanılabilir.",
    export:   "Gelişmiş export Kişisel plan ve üzerinde kullanılabilir.",
  };
  const text = msg[feature] || "Bu özellik üst planda kullanılabilir.";
  const overlay = document.createElement("div");
  overlay.className = "upgrade-overlay";
  overlay.innerHTML = `
    <div class="upgrade-box">
      <div class="upgrade-icon">🔒</div>
      <h3>Plan Yükseltmesi Gerekiyor</h3>
      <p>${text}</p>
      <div class="upgrade-actions">
        <a href="/landing.html#pricing" class="btn btn-primary">Planları Gör</a>
        <button class="btn btn-ghost" onclick="this.closest('.upgrade-overlay').remove()">Kapat</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) overlay.remove(); });
};

/* ── Dil & Para Birimi Ayarları ── */
window.saveLangSetting = function() {
  const lang = document.querySelector('input[name="appLang"]:checked')?.value || "tr";
  localStorage.setItem("autotax_lang", lang);
  const msg = document.getElementById("langSaveMsg");
  if (msg) { msg.style.display = "block"; setTimeout(() => msg.style.display = "none", 2500); }
};

window.saveCurrencySetting = function() {
  const cur = document.getElementById("currencySelect")?.value || "EUR";
  localStorage.setItem("autotax_currency", cur);
  showToast("Para birimi kaydedildi: " + cur);
};

/* Sayfa yüklenince kayıtlı dil/para birimi uygula */
(function initSettings() {
  const lang = localStorage.getItem("autotax_lang") || "tr";
  const cur  = localStorage.getItem("autotax_currency") || "EUR";
  const langRadio = document.querySelector(`input[name="appLang"][value="${lang}"]`);
  if (langRadio) langRadio.checked = true;
  const curSel = document.getElementById("currencySelect");
  if (curSel) curSel.value = cur;
})();

/* ─── KAMERA / EKRAN YAKALAMA ───────────────────────────────── */
let _cameraStream   = null;
let _qrScanInterval = null;  // FIX: interval sızıntısını önlemek için modül düzeyinde

async function _uploadBlob(blob, filename) {
  const fd = new FormData();
  fd.append("file", blob, filename);
  showToast("📤 Yükleniyor…");
  try {
    const res = await authFetch("/api/ocr/upload", { method: "POST", body: fd });
    if (!res) return;
    const d = await res.json();
    if (res.ok) {
      showToast("✅ " + (d.vendor || "Fatura") + " — " + (d.total ?? "") + " OCR tamam");
      loadInvoices();
    } else {
      showToast("❌ " + (d.detail || "Yükleme hatası"));
    }
  } catch(e) {
    showToast("❌ Bağlantı hatası");
  }
}

function _stopCamera() {
  // FIX: interval'i burada da temizle (QR modu için)
  if (_qrScanInterval) { clearInterval(_qrScanInterval); _qrScanInterval = null; }
  if (_cameraStream)   { _cameraStream.getTracks().forEach(t => t.stop()); _cameraStream = null; }
  const modal = document.getElementById("cameraModal");
  if (modal) modal.style.display = "none";
}

document.addEventListener("DOMContentLoaded", () => {

  /* Kamera */
  document.getElementById("btnCamera")?.addEventListener("click", async () => {
    const modal = document.getElementById("cameraModal");  // FIX: yerel referans
    const video = document.getElementById("cameraVideo");  // FIX: yerel referans
    if (!modal || !video) return;
    try {
      _cameraStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
      video.srcObject = _cameraStream;
      modal.style.display = "flex";
    } catch(e) {
      _stopCamera();
      showToast("❌ Kamera erişimi reddedildi: " + e.message);  // FIX: try/catch
    }
  });

  document.getElementById("btnCapture")?.addEventListener("click", () => {
    const video  = document.getElementById("cameraVideo");   // FIX: yerel referans
    const canvas = document.getElementById("cameraCanvas");  // FIX: yerel referans
    if (!video || !canvas) return;
    canvas.width  = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    _stopCamera();
    canvas.toBlob(blob => {
      if (blob) _uploadBlob(blob, "kamera_" + Date.now() + ".jpg");
    }, "image/jpeg", 0.92);
  });

  document.getElementById("btnCameraClose")?.addEventListener("click", _stopCamera);

  /* Ekran görüntüsü — FIX: ImageCapture yerine video+canvas (Firefox/Safari uyumlu) */
  document.getElementById("btnScreen")?.addEventListener("click", async () => {
    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({ video: true });
      const tmpVideo = document.createElement("video");
      tmpVideo.srcObject = stream;
      tmpVideo.muted = true;
      await tmpVideo.play();
      const canvas = document.createElement("canvas");
      canvas.width  = tmpVideo.videoWidth;
      canvas.height = tmpVideo.videoHeight;
      canvas.getContext("2d").drawImage(tmpVideo, 0, 0);
      stream.getTracks().forEach(t => t.stop());
      tmpVideo.srcObject = null;
      canvas.toBlob(blob => {
        if (blob) _uploadBlob(blob, "ekran_" + Date.now() + ".png");
      }, "image/png");
    } catch(e) {
      showToast("❌ Ekran yakalama iptal edildi: " + e.message);  // FIX: try/catch
    }
  });

  /* QR kod — FIX: JSON blob değil, kamera çerçevesini JPEG olarak gönder */
  document.getElementById("btnQR")?.addEventListener("click", async () => {
    if (!("BarcodeDetector" in window)) {
      showToast("⚠️ Tarayıcınız QR okumayı desteklemiyor. Faturayı fotoğraf olarak yükleyin.");
      return;
    }
    const modal = document.getElementById("cameraModal");
    const video = document.getElementById("cameraVideo");
    if (!modal || !video) return;
    try {
      _cameraStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
      video.srcObject = _cameraStream;
      modal.style.display = "flex";
      showToast("🔲 QR kodu kameraya gösterin, otomatik algılanacak…");
      const detector = new BarcodeDetector({ formats: ["qr_code"] });
      // FIX: interval ID modül değişkeninde saklanıyor → _stopCamera() onu da temizler
      _qrScanInterval = setInterval(async () => {
        try {
          const codes = await detector.detect(video);
          if (codes.length > 0) {
            const qrValue = codes[0].rawValue;
            // FIX: QR okunduktan sonra kamera çerçevesini JPEG olarak yükle (JSON değil)
            const canvas = document.createElement("canvas");
            canvas.width  = video.videoWidth;
            canvas.height = video.videoHeight;
            canvas.getContext("2d").drawImage(video, 0, 0);
            _stopCamera();  // interval + stream birlikte temizlenir
            showToast("✅ QR okundu: " + qrValue.substring(0, 60));
            canvas.toBlob(blob => {
              if (blob) _uploadBlob(blob, "qr_" + Date.now() + ".jpg");
            }, "image/jpeg", 0.92);
          }
        } catch(_) {}
      }, 500);
      setTimeout(() => { if (_qrScanInterval) _stopCamera(); }, 30000);
    } catch(e) {
      _stopCamera();
      showToast("❌ Kamera erişimi reddedildi: " + e.message);  // FIX: try/catch
    }
  });

  /* ── TARAYICI (Scanner) ────────────────────────────────────── */
  document.getElementById("btnScanner")?.addEventListener("click", () => {
    const modal = document.getElementById("scannerModal");
    if (modal) modal.style.display = "flex";
  });

  document.getElementById("btnScannerClose")?.addEventListener("click", () => {
    const modal = document.getElementById("scannerModal");
    if (modal) modal.style.display = "none";
  });

  // Windows Faks ve Tarama uygulamasını açmaya yönlendir
  document.getElementById("btnScannerWinScan")?.addEventListener("click", () => {
    showToast("🪟 Windows Tarama açılıyor… (wfs:// protokolü)");
    const a = document.createElement("a");
    a.href = "ms-photos:";   // MS Photos'un import from scanner özelliği
    a.click();
    setTimeout(() => {
      const st = document.getElementById("scannerUploadStatus");
      if (st) st.textContent = "Taramayı tamamladıktan sonra 'Tarama Dosyası Seç' ile yükleyin.";
    }, 1500);
  });

  // Tarayıcı dosya seçme input'u — seçilince otomatik OCR'a gönder
  document.getElementById("scannerFileInput")?.addEventListener("change", async (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    const st = document.getElementById("scannerUploadStatus");
    if (st) st.textContent = `${files.length} dosya OCR'a gönderiliyor…`;

    let ok = 0, fail = 0;
    for (const f of files) {
      const fd = new FormData();
      fd.append("file", f, f.name);
      try {
        const res = await authFetch("/api/ocr/upload", { method: "POST", body: fd });
        if (res && res.ok) { ok++; } else { fail++; }
      } catch(_) { fail++; }
    }

    if (st) st.textContent = `✅ ${ok} fatura işlendi${fail ? ` | ❌ ${fail} hata` : ""}.`;
    showToast(`📠 Tarayıcı: ${ok} fatura OCR'a aktarıldı`);
    e.target.value = "";   // input'u sıfırla (aynı dosya tekrar seçilebilsin)
    loadInvoices();

    // Modal'ı 2 saniye sonra kapat
    setTimeout(() => {
      const modal = document.getElementById("scannerModal");
      if (modal) modal.style.display = "none";
    }, 2000);
  });

});

