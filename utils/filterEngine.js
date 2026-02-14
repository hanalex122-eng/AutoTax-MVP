export function filterInvoices(invoices, filters) {
  return invoices.filter(inv => {

    const primary = inv.date_primary ? new Date(inv.date_primary) : null;
    const rangeStart = inv.date_range?.start ? new Date(inv.date_range.start) : null;
    const rangeEnd = inv.date_range?.end ? new Date(inv.date_range.end) : null;

    if (filters.dateFrom || filters.dateTo) {
      const from = filters.dateFrom ? new Date(filters.dateFrom) : null;
      const to = filters.dateTo ? new Date(filters.dateTo) : null;

      const compareStart = rangeStart || primary;
      const compareEnd = rangeEnd || primary;

      if (from && compareEnd < from) return false;
      if (to && compareStart > to) return false;
    }

    if (filters.vendor && filters.vendor !== "ALL") {
      if (!inv.vendor_name || inv.vendor_name !== filters.vendor) {
        return false;
      }
    }

    const amount = inv.total_amount ? parseFloat(inv.total_amount) : 0;

    if (filters.minAmount !== null && amount < filters.minAmount) return false;
    if (filters.maxAmount !== null && amount > filters.maxAmount) return false;

    return true;
  });
}