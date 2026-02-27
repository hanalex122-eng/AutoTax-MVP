export function filterInvoices(invoices, filters) {
  return invoices.filter(inv => {
    if (filters.dateFrom && inv.date && inv.date < filters.dateFrom) return false;
    if (filters.dateTo   && inv.date && inv.date > filters.dateTo)   return false;

    if (filters.vendor && filters.vendor !== "ALL") {
      if (!(inv.vendor || "").toLowerCase().includes(filters.vendor.toLowerCase())) return false;
    }

    if (filters.category && inv.category !== filters.category) return false;

    const amount = inv.total || 0;
    if (filters.minAmount !== null && amount < filters.minAmount) return false;
    if (filters.maxAmount !== null && amount > filters.maxAmount) return false;

    return true;
  });
}
