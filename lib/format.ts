export function formatNumber(
  value: number | null | undefined,
  digits = 2,
): string {
  if (value === null || value === undefined) {
    return "—";
  }
  return value.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function formatPrice(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "—";
  }
  return `¥${value.toLocaleString("en-US", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 1,
  })}`;
}

export function formatPercent(
  value: number | null | undefined,
  options?: { signed?: boolean; digits?: number },
): string {
  if (value === null || value === undefined) {
    return "—";
  }
  const digits = options?.signed ? 1 : (options?.digits ?? 1);
  const pct = value * 100;
  const body = `${pct.toFixed(digits)}%`;
  if (options?.signed && pct > 0) {
    return `+${body}`;
  }
  return body;
}

export function formatScore(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "—";
  }
  return value.toFixed(1);
}

export function formatBeta(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "—";
  }
  return value.toFixed(2);
}
