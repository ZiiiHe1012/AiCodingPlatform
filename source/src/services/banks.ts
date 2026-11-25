import type { Problem } from "../types";
import { state, userId } from "../store";

export interface Bank {
  id: string;
  name: string;
  owner_id: string | null;
  class_id: string | null;
  visibility: "private" | "class" | "public";
}
export type BankProblem = Problem & { bank_id: string; problem_version_id: string };
export interface CheckResult {
  valid: boolean;
  validation_id: string;
  items: {file: string; field: string; severity: string; message: string}[];
  titles?: string[];
}
export function canManageBank(bank?: Bank) {
  return !!bank && (bank.owner_id === userId() || (bank.id === "builtin" && state.role === "admin"));
}
export function issueText(item: CheckResult["items"][number]) {
  return [item.file, item.field, item.message].filter(Boolean).join(" · ");
}
