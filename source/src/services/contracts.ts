/** 后端接入契约。所有路径统一加 /api/v1 前缀；实现只在服务端。 */
import { request } from "./api";
import type {
  Problem,
  Exam,
  ClassRoom,
  ApiKey,
  Audit,
  Submission,
  Draft,
  Role,
} from "../types";
export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
export interface AssessmentReport {
  submission_id: string;
  report_status: "pending" | "completed";
  score: number | null;
  dimensions: {
    id: string;
    score: number;
    weight: number;
    evidence: { file?: string; line?: number; description: string }[];
  }[];
  scoring_version: string;
  published_at: string | null;
  review_deadline: string | null;
}
export interface TeacherGrade {
  user_id: string;
  status: string;
  score: number | null;
  dimensions: number[] | null;
  grade_version: number;
}
export interface PackageCheck {
  validation_id: string;
  valid: boolean;
  items: {
    file: string;
    field: string;
    message: string;
    severity: "error" | "warning";
  }[];
}
export const backend = {
  auth: {
    me: () => request("GET", "/users/me"),
    logout: () => request("POST", "/auth/logout"),
    updateProfile: (nickname: string) =>
      request("PATCH", "/users/me", { nickname }),
  },
  problems: {
    list: (query: URLSearchParams) =>
      request<Page<Problem>>("GET", "/problems?" + query.toString()),
    detail: (id: string) => request<Problem>("GET", `/problems/${id}`),
    create: (data: Partial<Problem>) =>
      request<Problem>("POST", "/problems", data),
    newVersion: (id: string, data: Partial<Problem>) =>
      request<Problem>("POST", `/problems/${id}/versions`, data),
    precheck: (id: string) =>
      request<PackageCheck>("POST", `/problem-versions/${id}/precheck`),
    publish: (id: string) => request("POST", `/problem-versions/${id}/publish`),
    unpublish: (id: string, reason: string) =>
      request("POST", `/problem-versions/${id}/unpublish`, { reason }),
  },
  banks: {
    list: () => request("GET", "/banks"),
    create: (name: string) =>
      request("POST", "/banks", { name, visibility: "private" }),
    uploadURL: (
      bankId: string,
      file: { name: string; size: number; type: string },
    ) =>
      request<{ upload_url: string; object_id: string }>(
        "POST",
        `/banks/${bankId}/imports/upload-url`,
        file,
      ),
    validate: (bankId: string, objectId: string) =>
      request<PackageCheck>("POST", `/banks/${bankId}/imports/validate`, {
        object_id: objectId,
      }),
    confirm: (bankId: string, validationId: string) =>
      request("POST", `/banks/${bankId}/imports`, {
        validation_id: validationId,
      }),
  },
  classes: {
    list: () => request<ClassRoom[]>("GET", "/classes"),
    create: (name: string) => request<ClassRoom>("POST", "/classes", { name }),
    joinPreview: (code: string) =>
      request<{ class_name: string; teacher_nickname: string }>(
        "POST",
        "/classes/invitations/preview",
        { code },
      ),
    join: (code: string) => request("POST", "/classes/join", { code }),
    update: (id: string, data: Partial<ClassRoom>) =>
      request("PATCH", `/classes/${id}`, data),
    resetCode: (id: string) =>
      request("POST", `/classes/${id}/invitation/reset`),
    importMembers: (id: string, members: string[]) =>
      request("POST", `/classes/${id}/members/import`, { members }),
    removeMember: (id: string, userId: string) =>
      request("DELETE", `/classes/${id}/members/${userId}`),
  },
  exams: {
    list: () => request<Exam[]>("GET", "/exams"),
    detail: (id: string) => request<Exam>("GET", `/exams/${id}`),
    checkIn: (id: string) =>
      request<{
        server_time: string;
        end_time: string;
        session_id: string;
        read_only: boolean;
        rules_version: string;
      }>("POST", `/exams/${id}/sessions`),
    publish: (id: string) => request("POST", `/exams/${id}/publish`),
    cancel: (id: string, reason: string) =>
      request("POST", `/exams/${id}/cancel`, { reason }),
    clock: (id: string) =>
      request<{ server_time: string; deadline: string }>(
        "GET",
        `/exams/${id}/clock`,
      ),
    draft: (id: string, problemId: string) =>
      request<Draft>("GET", `/exams/${id}/drafts/${problemId}`),
    receipt: (id: string) => request("GET", `/exams/${id}/answer-sheet`),
    createMock: (data: Partial<Exam>) =>
      request<Exam>("POST", "/mock-exams", data),
  },
  grades: {
    list: (examId: string) =>
      request<Page<TeacherGrade>>("GET", `/exams/${examId}/grades`),
    report: (submissionId: string) =>
      request<AssessmentReport>("GET", `/submissions/${submissionId}/report`),
    review: (
      submissionId: string,
      gradeVersion: number,
      reason: string,
      dimensions: number[],
    ) =>
      request("POST", `/submissions/${submissionId}/adjustments`, {
        grade_version: gradeVersion,
        reason,
        dimensions,
      }),
    publish: (examId: string) =>
      request("POST", `/exams/${examId}/grades/publish`),
    exportURL: (examId: string) =>
      request<{ download_url: string }>(
        "POST",
        `/exams/${examId}/grades/exports`,
      ),
  },
  leaderboards: {
    get: (examId: string) =>
      request<{
        updated_at: string;
        rules_version: string;
        frozen: boolean;
        entries: {
          rank: number;
          anonymous_id: string;
          nickname: string;
          score: number;
          functional_score: number;
        }[];
        pending: Submission[];
      }>("GET", `/exams/${examId}/leaderboard`),
  },
  admin: {
    users: (query: string) =>
      request("GET", "/admin/users?q=" + encodeURIComponent(query)),
    updateRole: (id: string, role: Role, reason: string) =>
      request("PATCH", `/admin/users/${id}/role`, { role, reason }),
    updateStatus: (id: string, enabled: boolean, reason: string) =>
      request("PATCH", `/admin/users/${id}/status`, { enabled, reason }),
    audits: () => request<Page<Audit>>("GET", "/admin/audits"),
  },
  keys: { list: () => request<ApiKey[]>("GET", "/api-keys") },
  monitoring: {
    summary: () => request("GET", "/admin/monitoring/summary"),
    tasks: () => request("GET", "/admin/tasks"),
    retry: (id: string, reason: string) =>
      request("POST", `/admin/tasks/${id}/retry`, { reason }),
    manual: (id: string, reason: string) =>
      request("POST", `/admin/tasks/${id}/manual-review`, { reason }),
  },
};
