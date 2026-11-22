import type { Envelope, Submission, Draft, Exam, ProjectFiles } from "../types";
import { state, userId, audit } from "../store";
import { gradeRows } from "./gradeStore";
import { sameFiles } from "../project";
import { signIn, registerAccount, type Profile } from "./accounts";
export const isMock = import.meta.env.VITE_USE_MOCK !== "false";
export const baseURL = import.meta.env.VITE_API_BASE_URL || "/api/v1";
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public requestId = "",
  ) {
    super(message);
  }
}
export async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  headers: Record<string, string> = {},
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    const res = await fetch(baseURL + path, {
      method,
      credentials: "include",
      signal: controller.signal,
      headers: { "Content-Type": "application/json", ...headers },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (res.status === 204) return undefined as T;
    const data: Envelope<T> = await res.json();
    if (!res.ok) throw new ApiError(res.status, data.message, data.request_id);
    return data.data;
  } finally {
    clearTimeout(timer);
  }
}
const delay = () => new Promise((r) => setTimeout(r, 400));
export const api = {
  async login(
    username: string,
    password: string,
    remember = false,
  ): Promise<Profile> {
    if (!isMock) return request("POST", "/auth/login", { username, password });
    return signIn(username, password, remember);
  },
  async register(
    username: string,
    password: string,
    nickname: string,
    remember = false,
  ): Promise<Profile> {
    if (!isMock)
      return request("POST", "/auth/register", {
        username,
        password,
        nickname,
      });
    return registerAccount(username, password, nickname, remember);
  },
  async saveDraft(key: string, draft: Draft): Promise<Draft> {
    if (!isMock)
      return request("PUT", `/drafts/${encodeURIComponent(key)}`, draft);
    await delay();
    if (!navigator.onLine)
      throw new ApiError(503, "网络已断开，本地草稿未同步");
    const current = JSON.parse(
      localStorage.getItem("codelab-draft-" + key) || "null",
    ) as Draft | null;
    if (current && current.version > draft.version)
      throw new ApiError(409, "草稿版本冲突，请下载本地草稿后恢复已保存版本");
    const saved = {
      ...draft,
      version: draft.version + 1,
      updatedAt: new Date().toISOString(),
    };
    localStorage.setItem("codelab-draft-" + key, JSON.stringify(saved));
    return saved;
  },
  async submit(
    problemId: string,
    files: ProjectFiles,
    explanation: string,
    idempotencyKey: string,
    examId?: string,
    aiHistory: { role: string; text: string }[] = [],
  ): Promise<Submission> {
    const problem =
      state.exams
        .find((e) => e.id === examId)
        ?.snapshots?.find((p) => p.id === problemId) ||
      state.problems.find((p) => p.id === problemId);
    const snapshot = JSON.parse(JSON.stringify(files));
    const payload = {
      problem_version_id:
        problemId +
        "@" +
        (state.problems.find((p) => p.id === problemId)?.version || "v1.0"),
      stack: problem?.stack,
      files: snapshot,
      ai_history: aiHistory,
      explanation,
      exam_id: examId,
    };
    if (!isMock)
      return request("POST", "/submissions", payload, {
        "Idempotency-Key": idempotencyKey,
      });
    await delay();
    const existing = state.submissions.find(
      (s) => s.idempotencyKey === idempotencyKey,
    );
    if (existing) {
      if (
        !sameFiles(existing.files, snapshot) ||
        existing.problemId !== problemId ||
        existing.explanation !== explanation ||
        existing.examId !== examId ||
        JSON.stringify(existing.aiHistory || []) !== JSON.stringify(aiHistory)
      )
        throw new ApiError(409, "幂等键已用于不同内容");
      return existing;
    }
    const s: Submission = {
      id: "SUB-" + Date.now(),
      problemId,
      files: snapshot,
      problemSnapshot: problem
        ? JSON.parse(JSON.stringify(problem))
        : undefined,
      aiHistory: JSON.parse(JSON.stringify(aiHistory)),
      explanation,
      userId: userId(),
      examId,
      idempotencyKey,
      status: "QUEUED",
      createdAt: new Date().toISOString(),
      scores: null,
      version: 1,
    };
    state.submissions.unshift(s);
    return s;
  },
  async submission(id: string): Promise<Submission> {
    if (!isMock) return request("GET", `/submissions/${id}`);
    const s = state.submissions.find((s) => s.id === id);
    if (!s) throw new ApiError(404, "未找到提交");
    return s;
  },
  async createExam(exam: Exam) {
    if (!isMock) return request<Exam>("POST", "/exams", exam);
    await delay();
    state.exams.unshift(exam);
    audit("创建考试", exam.title);
    return exam;
  },
  async handIn(
    examId: string,
    snapshots: Record<string, Draft>,
  ): Promise<{ receipt: string }> {
    if (!isMock)
      return request(
        "POST",
        `/exams/${examId}/answer-sheet`,
        { drafts: snapshots },
        { "Idempotency-Key": `${examId}:${userId()}` },
      );
    await delay();
    const exam = state.exams.find((e) => e.id === examId);
    if (!exam) throw new ApiError(404, "考试不存在");
    if (!exam.receipt) {
      exam.receipt = "ANS-" + Date.now();
      exam.finalDrafts = JSON.parse(JSON.stringify(snapshots));
      for (const [pid, draft] of Object.entries(snapshots)) {
        state.submissions.unshift({
          id: "SUB-" + Date.now() + "-" + pid,
          problemId: pid,
          userId: userId(),
          files: JSON.parse(JSON.stringify(draft.files)),
          problemSnapshot: JSON.parse(
            JSON.stringify(
              exam.snapshots?.find((p) => p.id === pid) ||
                state.problems.find((p) => p.id === pid),
            ),
          ),
          aiHistory: draft.aiHistory || [],
          explanation: draft.explanation,
          status: "QUEUED",
          createdAt: new Date().toISOString(),
          scores: null,
          version: 1,
          examId,
          idempotencyKey: "final-" + examId + "-" + pid,
        });
      }
      gradeRows[examId] = gradeRows[examId] || [];
      if (!gradeRows[examId].some((r) => r.id === userId()))
        gradeRows[examId].push({
          id: userId(),
          name: state.name,
          scores: null,
          status: "待评分",
        });
      if (exam.personal) exam.published = true;
    }
    audit("交卷回执", exam.receipt);
    return { receipt: exam.receipt };
  },
  async review(id: string, reason: string) {
    if (!isMock)
      return request("POST", `/submissions/${id}/reviews`, { reason });
    await delay();
    const s = state.submissions.find((s) => s.id === id)!;
    if (!s || s.status !== "COMPLETED")
      throw new ApiError(409, "当前成绩尚未完成");
    if (Date.now() - Date.parse(s.createdAt) > 48 * 3600000)
      throw new ApiError(409, "已超过 48 小时复核期限");
    if (s.review) throw new ApiError(409, "该成绩版本已申请复核");
    s.review = reason;
    audit("申请成绩复核", reason);
  },
  async ai(
    message: string,
    files: ProjectFiles,
    scope: string,
    problemId: string,
    activeFile: string,
  ) {
    const exam = state.exams.find((e) => e.id === scope);
    const problem =
      exam?.snapshots?.find((p) => p.id === problemId) ||
      state.problems.find((p) => p.id === problemId);
    if (!problem) throw new ApiError(404, "项目不存在");
    const contextFiles =
      exam?.aiContext === "当前文件"
        ? { [activeFile]: files[activeFile] || "" }
        : files;
    if (!isMock)
      return request<{
        text: string;
        suggestion: string;
        file: string;
        tokens: number;
      }>("POST", "/ai/messages", {
        message,
        scope,
        problem_version_id: problem.id + "@" + problem.version,
        requirements: problem.requirements,
        acceptance: problem.acceptance,
        files: contextFiles,
        active_file: activeFile,
        mode: exam?.aiMode || "对话与代码建议",
      });
    await delay();
    const usage = state.aiUsage[userId() + ":" + scope] || {
      requests: 0,
      tokens: 0,
    };
    if (
      usage.requests >= (exam?.requests || 40) ||
      usage.tokens >= (exam?.tokens || 60000)
    )
      throw new ApiError(429, "本场 AI 额度已用尽");
    const analysis = /阅读|理解|链路|结构|分析/.test(message);
    const testing = /测试|验证|验收/.test(message);
    const text = testing
      ? `将验收标准转为回归测试：\n${problem.acceptance.map((a) => `${a.id}：${a.scenario} → ${a.expected}`).join("\n")}\n执行 ${problem.commands.test}，记录失败复现、修改内容与复测结果。`
      : analysis
        ? `从 ${activeFile} 开始阅读，定位业务入口与状态修改点。\n需要核对的需求：\n${problem.requirements.map((r, i) => `${i + 1}. ${r}`).join("\n")}\n先追踪依赖和调用方，再提出改动，保留公开接口。`
        : `针对 ${problem.title}，先建立失败复现，再修改业务逻辑。\n优先核对：${problem.acceptance[1]?.scenario || problem.acceptance[0]?.scenario}。\n检查 ${activeFile} 的调用方、异常路径及副作用；把实际验证过程写入 CHANGELOG.md。`;
    const suggestion =
      exam?.aiMode === "仅分析建议" || !contextFiles["CHANGELOG.md"]
        ? ""
        : `# 变更说明\n\n## 需求拆解\n${problem.requirements.map((r) => "- " + r).join("\n")}\n\n## 设计与取舍\n\n## 验证计划\n${problem.acceptance.map((a) => `- [ ] ${a.id} ${a.scenario}：${a.expected}`).join("\n")}\n\n执行命令：${problem.commands.test}\n\n## 实际验证结果\n\n## AI 建议的采纳与核验\n`;
    return {
      text,
      suggestion,
      file: "CHANGELOG.md",
      tokens: Math.min(600, (exam?.tokens || 60000) - usage.tokens),
    };
  },
  async run(problemId: string, files: Record<string, string>) {
    if (!isMock)
      return request<{ message: string }>("POST", "/runs", {
        problem_version_id:
          problemId +
          "@" +
          (state.problems.find((p) => p.id === problemId)?.version || "v1.0"),
        stack: state.problems.find((p) => p.id === problemId)?.stack,
        files,
      });
    await delay();
    const problem = state.problems.find((p) => p.id === problemId);
    if (!problem) throw new ApiError(404, "项目不存在");
    const missing = Object.keys(problem.files).filter(
      (path) => !(path in files),
    );
    return {
      message: missing.length
        ? "缺少项目文件：" + missing.join("、")
        : `项目文件检查完成：${Object.keys(files).length} 个文件\n入口：${problem.entryFile}\n测试命令：${problem.commands.test}\n测试执行状态：未连接运行环境`,
    };
  },
};
