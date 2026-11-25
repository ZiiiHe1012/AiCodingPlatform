export type Role = "student" | "teacher" | "admin";
export type TaskType = "需求实现" | "代码理解" | "缺陷修复" | "工程重构";
export type ProjectFiles = Record<string, string>;
export interface Acceptance {
  id: string;
  scenario: string;
  expected: string;
}
export type SubmissionStatus =
  | "ACCEPTED"
  | "QUEUED"
  | "TESTING"
  | "AI_SCORING"
  | "PENDING_REVIEW"
  | "COMPLETED"
  | "SYSTEM_FAILED";
export interface Problem {
  id: string;
  title: string;
  type: TaskType;
  difficulty: "简单" | "中等" | "困难";
  tags: string[];
  solved: boolean;
  attempts: number;
  passRate: number;
  description: string;
  stack: string;
  duration: number;
  repository: string;
  entryFile: string;
  files: ProjectFiles;
  requirements: string[];
  acceptance: Acceptance[];
  constraints: string[];
  deliverables: string[];
  commands: { setup: string; test: string; start: string };
  evaluation: {
    timeout: number;
    memory: number;
    network: "禁用" | "依赖白名单";
  };
  version: string;
  bank: string;
  status: "已发布" | "草稿" | "预检通过" | "已下架";
  source: string;
  weights: number[];
}
export interface Exam {
  id: string;
  title: string;
  className: string;
  start: string;
  end: string;
  status: "草稿" | "已发布" | "进行中" | "已结束" | "成绩已发布" | "已归档";
  problemIds: string[];
  problemCount?: number;
  weights: number[];
  model: string;
  requests: number;
  tokens: number;
  personal: boolean;
  leaderboard: boolean;
  publicLeaderboard?: boolean;
  published: boolean;
  receipt?: string;
  snapshots?: Problem[];
  finalDrafts?: Record<string, Draft>;
  participantIds?: string[];
  publishedAt?: string;
  aiContext: "项目文件" | "当前文件";
  aiMode: "对话与代码建议" | "仅分析建议";
  deliverables: string[];
}
export interface Submission {
  id: string;
  problemId: string;
  userId: string;
  files: ProjectFiles;
  problemSnapshot?: Problem;
  aiHistory?: { role: string; text: string }[];
  explanation: string;
  status: SubmissionStatus;
  createdAt: string;
  scores: number[] | null;
  version: number;
  examId?: string;
  idempotencyKey: string;
  review?: string;
  adjustment?: {
    oldScores: number[];
    reason: string;
    operator: string;
    time: string;
  };
}
export interface ClassRoom {
  memberCount?: number;
  id: string;
  name: string;
  teacher: string;
  code: string;
  members: { id: string; name: string; joined: string }[];
  archived: boolean;
}
export interface ApiKey {
  id: string;
  name: string;
  prefix: string;
  scopes: string[];
  expires: string;
  revoked: boolean;
}
export interface Audit {
  id: string;
  action: string;
  reason: string;
  time: string;
  actor: string;
}
export interface Envelope<T> {
  code: string;
  message: string;
  data: T;
  request_id: string;
}
export interface Draft {
  files: ProjectFiles;
  activeFile: string;
  explanation: string;
  aiHistory?: { role: string; text: string }[];
  version: number;
  updatedAt: string;
}
