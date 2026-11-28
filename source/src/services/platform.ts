import type { RouteLocationNormalized } from "vue-router";
import type { Profile } from "./accounts";
import type { api, ApiError } from "./api";
import type { state } from "../store";
import type { Draft, ProjectFiles } from "../types";

export interface WorkspaceInfo {
  runner_status: "on_demand" | "closed" | "ready" | "unavailable" | "preparing"; runner_note: string;
  id: string; problem_id: string; version: number; preview_available: boolean; stack: string; model: string;
}
export interface SandboxAction { index: number; kind: "click" | "fill"; value?: string }
export interface SandboxPreview {
  version: number; width: number; height: number; image: string; text: string;
  controls: { index: number; label: string; kind: "button" | "input" | "select"; value: string;
              inputType: string; options: {value:string; label:string}[] }[];
}
export interface JobProgress {
  id: string; status: string; events: {at:string; event:string; detail:string}[];
}
type UpdateJob = (job: JobProgress) => void;

interface PlatformClient {
  readonly examReadOnly: boolean;
  workspace(scope:string, pid:string): Promise<WorkspaceInfo>;
  preview(scope:string, pid:string, version:number, actions:SandboxAction[]): Promise<SandboxPreview>;
  versions(key:string): Promise<{version:number; updatedAt:string}[]>;
  restoreDraft(key:string, version:number, expected:number): Promise<Draft>;
  runCommand(pid:string, files:ProjectFiles, command:string, update:UpdateJob): Promise<{message:string}>;
  askProject(pid:string, files:ProjectFiles, message:string, file:string, update:UpdateJob):
    Promise<{text:string; changes?:ProjectFiles; suggestion:string; file:string; tokens:number}>;
  cancelJob(id:string): Promise<unknown>;
  usage(scope:string): Promise<{requests:number; tokens:number}>;
  readonly live: boolean;
  route(to: RouteLocationNormalized, local: Profile | null): Promise<Profile | null>;
  logout(): Promise<void>;
  changePassword(oldPassword: string, newPassword: string): Promise<void>;
  updateProfile(data: Pick<Profile, "nickname" | "bio" | "className" | "avatar" | "skills">): Promise<Profile>;
}

export let platform: PlatformClient | undefined;

export async function connectPlatform(services: typeof api, store: typeof state, error: typeof ApiError) {
  const url = "/assets/codelab-backend.js";
  const { connectBackend } = await import(/* @vite-ignore */ url);
  platform = connectBackend(services, store, error);
}
