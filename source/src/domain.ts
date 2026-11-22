export const dimensionNames = [
  "需求达成",
  "健壮性与安全",
  "代码质量",
  "工程设计",
  "验证与测试",
  "分析与 AI 协作",
];
export const defaultWeights = [40, 15, 15, 10, 10, 10];
export function weightedScore(scores: number[], weights = defaultWeights) {
  if (
    scores.length !== 6 ||
    weights.length !== 6 ||
    weights.some((w) => !Number.isFinite(w) || w < 0) ||
    Math.abs(weights.reduce((a, b) => a + b, 0) - 100) > 1e-8 ||
    scores.some((s) => !Number.isFinite(s) || s < 0 || s > 100)
  )
    throw new Error("六维分值须为 0–100，权重之和须为 100%");
  return scores.reduce((s, v, i) => s + (v * weights[i]) / 100, 0);
}
export function rankEntries<
  T extends { score: number; functional: number; id: string },
>(entries: T[]) {
  const sorted = [...entries].sort(
    (a, b) =>
      b.score - a.score ||
      b.functional - a.functional ||
      a.id.localeCompare(b.id),
  );
  let rank = 0;
  return sorted.map((entry, i) => {
    if (
      !i ||
      entry.score !== sorted[i - 1].score ||
      entry.functional !== sorted[i - 1].functional
    )
      rank = i + 1;
    return { ...entry, rank };
  });
}
export function csvCell(value: unknown) {
  let s = String(value ?? "");
  if (/^[\s]*[=+@-]/.test(s)) s = "'" + s;
  return '"' + s.replaceAll('"', '""') + '"';
}
export function csvExport(rows: unknown[][]) {
  return "\uFEFF" + rows.map((r) => r.map(csvCell).join(",")).join("\r\n");
}
export function validateWeights(weights: number[]) {
  return (
    weights.length > 0 &&
    weights.every((w) => Number.isFinite(w) && w > 0) &&
    Math.abs(weights.reduce((a, b) => a + b, 0) - 100) < 1e-8
  );
}
export function canUseAI(
  requests: number,
  tokens: number,
  requestLimit = 30,
  tokenLimit = 30000,
) {
  return requests < requestLimit && tokens < tokenLimit;
}
export function validatePackagePath(path: string) {
  return (
    !/(^[\\/]|^[a-z]:|(^|[\\/])\.\.([\\/]|$))/i.test(path) &&
    !/\.(exe|dll|sh|bat|cmd|ps1|msi)$/i.test(path)
  );
}
export function formatTime(value: string) {
  return new Date(value).toLocaleString("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}
export function download(
  name: string,
  content: string,
  type = "text/plain;charset=utf-8",
) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
