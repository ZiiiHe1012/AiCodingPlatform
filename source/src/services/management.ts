import { ElMessage } from "element-plus";
import { request } from "./api";

export async function allPages<T>(path: string): Promise<T[]> {
  const items: T[] = [];
  const separator = path.includes("?") ? "&" : "?";
  for (let page = 1; ; page++) {
    const result = await request<{ items: T[]; total: number }>(
      "GET", path + separator + "page=" + page + "&page_size=100",
    );
    items.push(...result.items);
    if (!result.items.length || items.length >= result.total) return items;
  }
}

export function showError(error: unknown) {
  if (error === "cancel" || error === "close") return;
  ElMessage.error(error instanceof Error ? error.message : "请求失败，请重试");
}

