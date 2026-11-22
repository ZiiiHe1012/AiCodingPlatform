import { reactive, watch } from "vue";
import { currentProfile, type Profile } from "./services/accounts";
import { upgradeProblem } from "./project";
import { problems, seedExams, seedSubmissions, seedClasses } from "./data";
import type {
  Role,
  Problem,
  Exam,
  Submission,
  ClassRoom,
  ApiKey,
  Audit,
} from "./types";
interface State {
  profile: Profile | null;
  contentVersion: number;
  role: Role;
  name: string;
  loggedIn: boolean;
  problems: Problem[];
  exams: Exam[];
  submissions: Submission[];
  classes: ClassRoom[];
  keys: ApiKey[];
  audits: Audit[];
  aiUsage: Record<string, { requests: number; tokens: number }>;
  banks: string[];
  users: { id: string; name: string; role: Role; enabled: boolean }[];
}
const initial: State = {
  profile: null,
  contentVersion: 2,
  role: "student",
  name: "林同学",
  loggedIn: false,
  problems: [
    ...problems,
    ...problems.slice(0, 3).map((p, i) => ({
      ...p,
      id: "E" + (2001 + i),
      title: [
        "工单协作台 · 团队练习",
        "订单回调 · 团队练习",
        "知识库权限 · 团队练习",
      ][i],
      bank: "我的工程实践题库",
      solved: false,
    })),
  ],
  exams: seedExams,
  submissions: seedSubmissions,
  classes: seedClasses,
  keys: [],
  audits: [],
  aiUsage: {},
  banks: ["我的工程实践题库"],
  users: [
    { id: "u-student", name: "林同学", role: "student", enabled: true },
    { id: "u-teacher", name: "陈老师", role: "teacher", enabled: true },
    { id: "u-admin", name: "平台管理员", role: "admin", enabled: true },
  ],
};
let saved: Partial<State> = {};
try {
  saved = JSON.parse(localStorage.getItem("codelab-demo-v1") || "{}");
} catch {
  /* damaged cache uses seed */
}
if (saved.contentVersion !== 2 && saved.problems) {
  const legacyProblems = saved.problems.map(upgradeProblem);
  const oldSeeds = new Set([
    ...Array.from({ length: 12 }, (_, i) => `P${1001 + i}`),
    "P2001",
    "P2002",
    "P2003",
  ]);
  const oldExamIds = new Set(["exam-1", "exam-2", "exam-3"]);
  saved.submissions = [
    ...seedSubmissions,
    ...(saved.submissions || []).map((s) => {
      const legacy = s as unknown as { code?: string };
      return {
        ...s,
        files: s.files || { "main.py": legacy.code || "" },
        problemSnapshot:
          s.problemSnapshot || legacyProblems.find((p) => p.id === s.problemId),
        examId:
          s.examId && oldExamIds.has(s.examId)
            ? "archive-" + s.examId
            : s.examId,
      };
    }),
  ];
  saved.exams = [
    ...seedExams,
    ...(saved.exams || []).map((e) => ({
      ...e,
      id: oldExamIds.has(e.id) ? "archive-" + e.id : e.id,
      status: oldExamIds.has(e.id) ? ("已归档" as const) : e.status,
      snapshots: (
        e.snapshots || legacyProblems.filter((p) => e.problemIds.includes(p.id))
      ).map(upgradeProblem),
      aiContext: "项目文件" as const,
      aiMode: "对话与代码建议" as const,
      deliverables: ["项目代码与测试", "验证说明"],
    })),
  ];
  saved.problems = [
    ...initial.problems,
    ...legacyProblems.filter((p) => !oldSeeds.has(p.id)),
  ];
  saved.banks = [
    ...new Set([
      "我的工程实践题库",
      ...(saved.banks || []).filter((b) => b !== "我的 Python 专项题库"),
    ]),
  ];
  saved.contentVersion = 2;
}
for (const classroom of saved.classes || []) {
  if (classroom.id === "class-1" && classroom.name === "软件工程 2023 级 1 班") classroom.name = "示例班级";
}
for (const exam of saved.exams || []) {
  if (exam.className === "软件工程 2023 级 1 班") exam.className = "示例班级";
}
const session = currentProfile();
export const state = reactive<State>({
  ...initial,
  ...saved,
  profile: session,
  loggedIn: !!session,
  ...(session ? { name: session.nickname, role: session.role } : {}),
});
export function applyAccount(profile: Profile | null) {
  state.profile = profile;
  state.loggedIn = !!profile;
  if (profile) {
    state.name = profile.nickname;
    state.role = profile.role;
  }
}
localStorage.setItem("codelab-demo-v1", JSON.stringify(state));
watch(
  state,
  () => {
    try {
      localStorage.setItem("codelab-demo-v1", JSON.stringify(state));
    } catch {
      window.dispatchEvent(new CustomEvent("storage-error"));
    }
  },
  { deep: true },
);
export const userId = () => state.profile?.id || `u-${state.role}`;
export function audit(action: string, reason: string) {
  state.audits.unshift({
    id: crypto.randomUUID(),
    action,
    reason,
    time: new Date().toISOString(),
    actor:
      state.role === "teacher"
        ? "陈老师"
        : state.role === "admin"
          ? "管理员"
          : state.name,
  });
}
export function resetDemo() {
  localStorage.removeItem("codelab-demo-v1");
  Object.keys(localStorage)
    .filter(
      (k) =>
        k.startsWith("codelab-") &&
        !["codelab-accounts-v1", "codelab-session-v1"].includes(k),
    )
    .forEach((k) => localStorage.removeItem(k));
  location.href = "/";
  location.reload();
}
