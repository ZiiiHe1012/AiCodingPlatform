import type { RouteLocationNormalized } from "vue-router";
import type { Profile } from "./accounts";
import type { api, ApiError } from "./api";
import type { state } from "../store";
import type { Draft, ProjectFiles } from "../types";

export interface JobProgress {
  id: string; status: string; events: {at:string; event:string; detail:string}[];
}
type UpdateJob = (job: JobProgress) => void;

interface PlatformClient {
  readonly examReadOnly: boolean;
  versions(key:string): Promise<{version:number; updatedAt:string}[]>;
  restoreDraft(key:string, version:number, expected:number): Promise<Draft>;
  runCommand(pid:string, files:ProjectFiles, command:string, update:UpdateJob): Promise<{message:string}>;
  cancelJob(id:string): Promise<unknown>;
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
