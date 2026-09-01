/**
 * Formatting Utility Functions for REVIVE Dashboard
 */

export function formatINR(val: number | null | undefined): string {
  if (val === null || val === undefined) return "₹0.00";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(val);
}
