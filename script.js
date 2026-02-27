const API = "http://127.0.0.1:8000";

let allInvoices = [];     // yüklenen tüm faturalar
let filtered    = [];     // filtre uygulanmış liste
let sortCol     = "date";
let sortAsc     = false;

// ============================================================
// INIT
// ============================================================
document.addEventListener("DOMContentLoaded", () => {
  loadFromServer();
  bindUpload();
  bindFilters();
  bindExports();
  bindModal();
  bindSelectAll();
  bindColumnSort();
});

// ============================================================
// SUNUCUDAN MEVCUT FATURALARI YÜKlE
// ============================================================
async function loadFromServer() {
  try {
    setStatus("loading", "Yükleniyor…");
    const res = await fetch(`${API}/stats/summary`);
    if (!res.ok) throw new Error("API hatası");
    const body = await res.json();
    allInvoices = (body.invoices || []).map(normalizeInvoice);
    applyFilters();
    setStatus("ok", "Bağlandı");
  } catch (e) {
    setStatus("error", "API bağlantısı yok");
  }
}

// DB kaydının alanlarını tutarlı hale getir
function normalizeInvoice(inv) {
  const d = inv.data || inv.parsed || inv || {};
  return {
    _id:            inv.id       || inv.invoice_id || "",
    _ts:            inv.timestamp || "",
    filename:       inv.filename || d.filename || "",
    vendor:         d.vendor    || "",
    date:           d.date      || "",
    time:           d.time      || "",
    total:          parseFloat(d.total)      || 0,
    vat_amount:     parseFloat(d.vat_amount) || 0,
    vat_rate:       d.vat_rate  || "",
    invoice_no:     d.invoice_number || d.invoice_no || "",
    category:       d.category  || "",
    payment_method: d.payment_method || "",
    qr_raw:         d.qr_raw    || inv.qr_raw || "",
    qr_parsed:      d.qr_parsed || inv.qr_parsed || null,
    raw_text:       d.raw_text  || inv.raw_text  || "",
    needs_review:   inv.needs_review || false,
  };
}

// ============================================================
// UPLOAD
// ============================================================
function bindUpload() {
  const input   = document.getElementById("fileInput");
  const btn     = document.getElementById("uploadBtn");
  const zone    = document.getElementById("dropZone");

  input.addEventListener("change", () => {
    btn.disabled = input.files.length === 0;
  });

  zone.addEventListener("dragover", e => { e.preventDefault(); zone.classList.add("drag-over"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
  zone.addEventListener("drop", e => {
    e.preventDefault();
    zone.classList.remove("drag-over");
    input.files = e.dataTransfer.files;
    btn.disabled = input.files.length === 0;
  });

  btn.addEventListener("click", uploadFiles);
}

async function uploadFiles() {
  const input = document.getElementById("fileInput");
  const files = [...input.files];
  if (!files.length) return;

  const bar  = document.getElementById("uploadProgress");
  const fill = document.getElementById("progressFill");
  bar.style.display = "block";
  setStatus("loading", `${files.length} dosya işleniyor…`);

  for (let i = 0; i < files.length; i++) {
    fill.style.width = Math.round(((i) / files.length) * 100) + "%";
    const fd = new FormData();
    fd.append("file", files[i]);

    try {
      const res  = await fetch(`${API}/ocr/upload`, { method: "POST", body: fd });
      const data = await res.json();
      const norm = normalizeInvoice(data);
      // Varsa güncelle, yoksa ekle
      const idx = allInvoices.findIndex(x => x._id === norm._id);
      if (idx >= 0) allInvoices[idx] = norm; else allInvoices.unshift(norm);
    } catch (e) {
      console.error("Upload hata:", e);
    }

    fill.style.width = Math.round(((i + 1) / files.length) * 100) + "%";
  }

  bar.style.display = "none";
  input.value = "";
  document.getElementById("uploadBtn").disabled = true;
  setStatus("ok", "Yükleme tamamlandı");
  applyFilters();
}

// ============================================================
// FİLTRELEME
// ============================================================
function bindFilters() {
  document.getElementById("applyFilters").addEventListener("click", applyFilters);
  document.getElementById("resetFilters").addEventListener("click", () => {
    ["dateFrom","dateTo","vendorInput","minAmount","maxAmount"].forEach(id => {
      document.getElementById(id).value = "";
    });
    document.getElementById("categorySelect").value = "";
    applyFilters();
  });
  // Canlı arama (firma)
  document.getElementById("vendorInput").addEventListener("input", applyFilters);
}

function applyFilters() {
  const dateFrom  = document.getElementById("dateFrom").value;
  const dateTo    = document.getElementById("dateTo").value;
  const vendor    = document.getElementById("vendorInput").value.trim().toLowerCase();
  const category  = document.getElementById("categorySelect").value;
  const minAmount = parseFloat(document.getElementById("minAmount").value) || null;
  const maxAmount = parseFloat(document.getElementById("maxAmount").value) || null;

  filtered = allInvoices.filter(inv => {
    if (dateFrom && inv.date && inv.date < dateFrom) return false;
    if (dateTo   && inv.date && inv.date > dateTo)   return false;
    if (vendor   && !inv.vendor.toLowerCase().includes(vendor)) return false;
    if (category && inv.category !== category) return false;
    if (minAmount !== null && inv.total < minAmount) return false;
    if (maxAmount !== null && inv.total > maxAmount) return false;
    return true;
  });

  sortData();
  renderTable(filtered);
  renderSummary(filtered);
  renderVendorTotals(filtered);
}

// ============================================================
// SIRALAMA
// ============================================================
function bindColumnSort() {
  document.querySelectorAll("#invoiceTable th[data-col]").forEach(th => {
    th.addEventListener("click", () => {
      const col = th.dataset.col;
      if (sortCol === col) sortAsc = !sortAsc;
      else { sortCol = col; sortAsc = true; }
      sortData();
      renderTable(filtered);
    });
  });
}

function sortData() {
  filtered.sort((a, b) => {
    let av = a[sortCol] ?? "";
    let bv = b[sortCol] ?? "";
    if (typeof av === "number") return sortAsc ? av - bv : bv - av;
    return sortAsc
      ? String(av).localeCompare(String(bv))
      : String(bv).localeCompare(String(av));
  });
}

// ============================================================
// TABLO RENDER
// ============================================================
function renderTable(data) {
  const tbody = document.getElementById("tableBody");
  tbody.innerHTML = "";

  if (!data.length) {
    tbody.innerHTML = `<tr class="empty-row"><td colspan="13">Sonuç bulunamadı.</td></tr>`;
    return;
  }

  data.forEach((inv, i) => {
    const tr = document.createElement("tr");

    const catBadge = inv.category
      ? `<span class="cat-badge cat-${inv.category}">${catLabel(inv.category)}</span>`
      : "—";

    const qrBadge = inv.qr_raw
      ? `<span class="qr-badge">QR</span>`
      : "—";

    tr.innerHTML = `
      <td class="col-check"><input type="checkbox" class="row-check" data-i="${i}"></td>
      <td title="${esc(inv.filename)}">${esc(shortName(inv.filename))}</td>
      <td title="${esc(inv.vendor)}">${esc(inv.vendor) || "—"}</td>
      <td>${inv.date || "—"}</td>
      <td>${inv.time || "—"}</td>
      <td class="num">${inv.total ? inv.total.toFixed(2) : "—"}</td>
      <td class="num">${inv.vat_rate ? inv.vat_rate + "%" : "—"}</td>
      <td class="num">${inv.vat_amount ? inv.vat_amount.toFixed(2) : "—"}</td>
      <td title="${esc(inv.invoice_no)}">${esc(inv.invoice_no) || "—"}</td>
      <td>${catBadge}</td>
      <td>${esc(inv.payment_method) || "—"}</td>
      <td>${qrBadge}</td>
      <td class="col-action">
        <button class="btn btn-ghost detail-btn" data-i="${i}" style="padding:0 8px;height:26px;font-size:11px;">Detay</button>
      </td>
    `;
    tbody.appendChild(tr);
  });

  // Detay butonları
  tbody.querySelectorAll(".detail-btn").forEach(btn => {
    btn.addEventListener("click", () => openModal(filtered[+btn.dataset.i]));
  });
}

// ============================================================
// ÖZET BAR
// ============================================================
function renderSummary(data) {
  const total = data.reduce((s, inv) => s + (inv.total || 0), 0);
  const vat   = data.reduce((s, inv) => s + (inv.vat_amount || 0), 0);
  document.getElementById("countBadge").textContent = data.length;
  document.getElementById("totalSum").textContent   = fmtMoney(total);
  document.getElementById("vatSum").textContent     = fmtMoney(vat);
}

// ============================================================
// FİRMA TOPLAMLAR
// ============================================================
function renderVendorTotals(data) {
  const map = {};
  data.forEach(inv => {
    const v = inv.vendor || "Bilinmiyor";
    map[v] = (map[v] || 0) + (inv.total || 0);
  });

  const panel = document.getElementById("vendorTotalsPanel");
  const grid  = document.getElementById("vendorTotalsGrid");

  const entries = Object.entries(map).sort((a, b) => b[1] - a[1]);
  if (!entries.length) { panel.style.display = "none"; return; }

  panel.style.display = "block";
  grid.innerHTML = entries.map(([name, amt]) =>
    `<div class="vendor-chip"><span class="vc-name">${esc(name)}</span><span class="vc-amt">${fmtMoney(amt)}</span></div>`
  ).join("");
}

// ============================================================
// MODAL
// ============================================================
function bindModal() {
  document.getElementById("modalClose").addEventListener("click", closeModal);
  document.getElementById("modal").addEventListener("click", e => {
    if (e.target === document.getElementById("modal")) closeModal();
  });
}

function openModal(inv) {
  document.getElementById("modalTitle").textContent = inv.filename || "Fatura";
  document.getElementById("detailQR").textContent =
    inv.qr_raw
      ? (typeof inv.qr_parsed === "object"
          ? JSON.stringify(inv.qr_parsed, null, 2)
          : inv.qr_raw)
      : "QR / Barkod bulunamadı";
  document.getElementById("detailRaw").textContent = inv.raw_text || "—";

  const fields = [
    ["Firma",        inv.vendor],
    ["Tarih",        inv.date],
    ["Saat",         inv.time],
    ["Tutar",        inv.total ? fmtMoney(inv.total) : null],
    ["KDV %",        inv.vat_rate],
    ["KDV Tutarı",   inv.vat_amount ? fmtMoney(inv.vat_amount) : null],
    ["Fatura No",    inv.invoice_no],
    ["Kategori",     inv.category],
    ["Ödeme",        inv.payment_method],
    ["Dosya",        inv.filename],
    ["Tarih/Saat",   inv._ts],
    ["ID",           inv._id],
  ];

  document.getElementById("detailGrid").innerHTML = fields.map(([label, val]) => `
    <div class="detail-item">
      <div class="di-label">${esc(label)}</div>
      <div class="di-value">${esc(val) || "—"}</div>
    </div>
  `).join("");

  document.getElementById("modal").style.display = "flex";
}

function closeModal() {
  document.getElementById("modal").style.display = "none";
}

// ============================================================
// SEÇİM (checkbox)
// ============================================================
function bindSelectAll() {
  document.getElementById("selectAll").addEventListener("change", e => {
    document.querySelectorAll(".row-check").forEach(cb => cb.checked = e.target.checked);
  });
}

function getSelected() {
  const selected = [];
  document.querySelectorAll(".row-check:checked").forEach(cb => {
    selected.push(filtered[+cb.dataset.i]);
  });
  return selected.length ? selected : filtered;
}

// ============================================================
// EXPORT
// ============================================================
function bindExports() {
  document.getElementById("exportExcel").addEventListener("click", exportExcel);
  document.getElementById("exportJSON").addEventListener("click",  exportJSON);
  document.getElementById("exportAllFile").addEventListener("click", exportFullReport);
}

function exportExcel() {
  const rows = getSelected().map(inv => ({
    "Dosya":       inv.filename,
    "Firma":       inv.vendor,
    "Tarih":       inv.date,
    "Saat":        inv.time,
    "Tutar":       inv.total,
    "KDV %":       inv.vat_rate,
    "KDV Tutarı":  inv.vat_amount,
    "Fatura No":   inv.invoice_no,
    "Kategori":    inv.category,
    "Ödeme":       inv.payment_method,
    "QR Verisi":   inv.qr_raw,
    "İnceleme?":   inv.needs_review ? "Evet" : "Hayır",
    "Timestamp":   inv._ts,
    "ID":          inv._id,
  }));

  const ws = XLSX.utils.json_to_sheet(rows);

  // Sütun genişlikleri
  const wscols = [
    {wch:28},{wch:20},{wch:12},{wch:8},{wch:10},{wch:7},{wch:12},
    {wch:18},{wch:12},{wch:14},{wch:30},{wch:8},{wch:22},{wch:36}
  ];
  ws["!cols"] = wscols;

  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, "Faturalar");
  XLSX.writeFile(wb, `autotax_faturalar_${today()}.xlsx`);
}

function exportJSON() {
  const rows = getSelected();
  download(JSON.stringify(rows, null, 2), `autotax_faturalar_${today()}.json`, "application/json");
}

function exportFullReport() {
  const report = {
    export_date: new Date().toISOString(),
    total_invoices: allInvoices.length,
    filtered_count: filtered.length,
    total_sum: filtered.reduce((s, i) => s + (i.total || 0), 0),
    vat_sum:   filtered.reduce((s, i) => s + (i.vat_amount || 0), 0),
    by_vendor: buildVendorMap(filtered),
    by_category: buildCategoryMap(filtered),
    invoices: filtered.map(inv => ({
      ...inv,
      // OCR ham metin de dahil
      raw_text: inv.raw_text || "",
      qr_raw:   inv.qr_raw   || "",
      qr_parsed: inv.qr_parsed || null,
    })),
  };
  download(JSON.stringify(report, null, 2), `autotax_tam_rapor_${today()}.json`, "application/json");
}

function buildVendorMap(data) {
  const m = {};
  data.forEach(i => { const v = i.vendor || "bilinmiyor"; m[v] = (m[v]||0) + (i.total||0); });
  return m;
}

function buildCategoryMap(data) {
  const m = {};
  data.forEach(i => { const c = i.category || "bilinmiyor"; m[c] = (m[c]||0) + (i.total||0); });
  return m;
}

// ============================================================
// YARDIMCI
// ============================================================
function setStatus(type, text) {
  const dot  = document.getElementById("statusDot");
  const span = document.getElementById("statusText");
  dot.className = `dot dot-${type}`;
  span.textContent = text;
}

function esc(s) {
  if (s == null) return "";
  return String(s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function fmtMoney(v) {
  return Number(v).toLocaleString("tr-TR", {minimumFractionDigits:2, maximumFractionDigits:2}) + " €";
}

function shortName(s) {
  if (!s) return "";
  return s.length > 22 ? s.slice(0, 20) + "…" : s;
}

function today() {
  return new Date().toISOString().slice(0, 10);
}

function download(content, filename, mime) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([content], {type: mime}));
  a.download = filename;
  a.click();
}

function catLabel(c) {
  const map = {
    food:"Yemek", grocery:"Market", transport:"Ulaşım",
    fuel:"Akaryakıt", hotel:"Otel", health:"Sağlık",
    electronics:"Elektronik", clothing:"Giyim",
  };
  return map[c] || c;
}
