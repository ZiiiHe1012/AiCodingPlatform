export interface PaneSizes {
  statement: number;
  assistant: number;
}
export const defaultPaneSizes: PaneSizes = { statement: 23, assistant: 26 };
export function resizePane(
  sizes: PaneSizes,
  side: keyof PaneSizes,
  desired: number,
  width: number,
): PaneSizes {
  const available = Math.max(1, width - 12);
  const minimum = {
    statement: Math.min((210 / available) * 100, 24),
    assistant: Math.min((230 / available) * 100, 26),
  };
  const editorMinimum = Math.min((350 / available) * 100, 42);
  const other = side === "statement" ? "assistant" : "statement";
  const next = Math.max(
    minimum[side],
    Math.min(100 - sizes[other] - editorMinimum, desired),
  );
  return { ...sizes, [side]: next };
}
