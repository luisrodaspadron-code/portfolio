export function money(value: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);
}

export function signedMoney(value: number) {
  const formatted = money(Math.abs(value));
  return `${value >= 0 ? "+" : "-"}${formatted}`;
}

export function pct(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

export function signedPct(value: number) {
  return `${value >= 0 ? "+" : ""}${pct(value)}`;
}

export function number(value: number) {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(value);
}

export function titleCase(value?: string | null) {
  if (!value) return "";
  return value
    .replace(/[_-]+/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function shortDateTime(value?: string | null) {
  if (!value) return "";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit"
  }).format(new Date(value));
}

export function textValue(value: unknown, fallback = "") {
  if (typeof value === "string") return value;
  if (typeof value === "number") return number(value);
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return fallback;
}
