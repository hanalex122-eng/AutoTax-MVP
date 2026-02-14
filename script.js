import { filterInvoices } from "./utils/filterEngine.js";

let allInvoices = []; // Tüm OCR sonuçları burada tutulacak

// ------------------------------
// 1) OCR Upload
// ------------------------------
document.getElementById("uploadBtn").addEventListener("click", async () => {
    const fileInput = document.getElementById("fileInput");
    if (!fileInput.files.length) {
        alert("Lütfen bir dosya seçin.");
        return;
    }

    const file = fileInput.files[0];
    const formData = new FormData();
    formData.append("file", file);

    const res = await fetch("http://127.0.0.1:8000/invoice", {
    method: "POST",
    body: formData
});

    const data = await res.json();

    // Sonucu ekrana yaz
    document.getElementById("result").textContent = JSON.stringify(data, null, 2);

    // Listeye ekle
    allInvoices.push(data);

    // Firma dropdown güncelle
    updateVendorDropdown();

    // Tabloyu güncelle
    renderTable(allInvoices);
});

// ------------------------------
// TOPLAM HESAPLAMA
// ------------------------------
function updateTotal(data) {
    const total = data.reduce((sum, inv) => {
        const amount = inv.total_amount ? parseFloat(inv.total_amount) : 0;
        return sum + amount;
    }, 0);

    document.getElementById("totalBox").textContent =
        "Toplam: " + total.toFixed(2) + " €";
}

// ------------------------------
// 2) Firma Dropdown Güncelleme
// ------------------------------
function updateVendorDropdown() {
    const vendorSelect = document.getElementById("vendorSelect");

    vendorSelect.innerHTML = `<option value="ALL">Tümü</option>`;

    const vendors = [...new Set(allInvoices.map(inv => inv.vendor_name))];

    vendors.forEach(v => {
        if (v) {
            const opt = document.createElement("option");
            opt.value = v;
            opt.textContent = v;
            vendorSelect.appendChild(opt);
        }
    });
}

// ------------------------------
// 3) Tabloyu Güncelleme
// ------------------------------
function renderTable(data) {
    const tbody = document.querySelector("#invoiceTable tbody");
    tbody.innerHTML = "";

    data.forEach(inv => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${inv.vendor_name || "-"}</td>
            <td>${inv.date_primary || "-"}</td>
            <td>${inv.total_amount || "-"}</td>
            <td>${inv.filename}</td>
        `;
        tbody.appendChild(tr);
    });

    // ⭐ TOPLAM HESAPLAMAYI BURADA ÇAĞIRIYORUZ
    updateTotal(data);
}

// ------------------------------
// 4) Filtreleme Butonu
// ------------------------------
document.getElementById("applyFilters").addEventListener("click", () => {
    const filters = {
        dateFrom: document.getElementById("dateFrom").value || null,
        dateTo: document.getElementById("dateTo").value || null,
        vendor: document.getElementById("vendorSelect").value,
        minAmount: document.getElementById("minAmount").value ? parseFloat(document.getElementById("minAmount").value) : null,
        maxAmount: document.getElementById("maxAmount").value ? parseFloat(document.getElementById("maxAmount").value) : null
    };

    const filtered = filterInvoices(allInvoices, filters);
    renderTable(filtered);
});