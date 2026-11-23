import type { RouteLocationNormalized } from "vue-router";
import type { Profile } from "./accounts";
import type { api, ApiError } from "./api";
import type { state } from "../store";
interface PlatformClient {
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
