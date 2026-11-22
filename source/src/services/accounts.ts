import type { Role } from "../types";

export interface Profile {
  id: string;
  username: string;
  nickname: string;
  role: Role;
  bio: string;
  className: string;
  avatar: string;
  skills: string[];
  joinedAt: string;
  demo: boolean;
}
interface LocalAccount extends Profile {
  credential?: { salt: string; digest: string };
  revision: number;
}
const accountKey = "codelab-accounts-v1";
const sessionKey = "codelab-session-v1";
const demoNames = { student: "林同学", teacher: "陈老师", admin: "平台管理员" };
const storage = () =>
  typeof sessionStorage === "undefined" ? localStorage : sessionStorage;
function readAccounts(): LocalAccount[] {
  const accounts: (LocalAccount & { school?: string })[] = JSON.parse(localStorage.getItem(accountKey) || "[]");
  let migrated = false;
  const updated = accounts.map(({ school, ...account }) => {
    if (account.className !== undefined) return account;
    migrated = true;
    return { ...account, className: school && school !== "软件工程 · C7 小组" ? school : "" };
  });
  if (migrated) localStorage.setItem(accountKey, JSON.stringify(updated));
  return updated;
}
const writeAccounts = (accounts: LocalAccount[]) =>
  localStorage.setItem(accountKey, JSON.stringify(accounts));
const publicProfile = ({
  credential: _credential,
  revision: _revision,
  ...profile
}: LocalAccount): Profile => profile;

export const avatarColors = [
  "blue",
  "mint",
  "violet",
  "amber",
  "rose",
  "slate",
];
export function validateCredentials(username: string, password: string) {
  if (!/^[a-zA-Z0-9_]{4,32}$/.test(username))
    throw new Error("用户名须为 4–32 位字母、数字或下划线");
  if (password.length < 8 || password.length > 64)
    throw new Error("密码须为 8–64 位");
}
const hex = (bytes: ArrayBuffer | Uint8Array) =>
  Array.from(new Uint8Array(bytes))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
async function digest(password: string, salt: string) {
  const material = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(password),
    "PBKDF2",
    false,
    ["deriveBits"],
  );
  return hex(
    await crypto.subtle.deriveBits(
      {
        name: "PBKDF2",
        salt: new TextEncoder().encode(salt),
        iterations: 100000,
        hash: "SHA-256",
      },
      material,
      256,
    ),
  );
}
function setSession(account: LocalAccount, remember: boolean) {
  localStorage.removeItem(sessionKey);
  storage().removeItem(sessionKey);
  (remember ? localStorage : storage()).setItem(
    sessionKey,
    JSON.stringify({ id: account.id, revision: account.revision }),
  );
  return publicProfile(account);
}
export function currentProfile(): Profile | null {
  const raw = storage().getItem(sessionKey) || localStorage.getItem(sessionKey);
  if (!raw) return null;
  const session = JSON.parse(raw);
  const account = readAccounts().find(
    (a) => a.id === session.id && a.revision === session.revision,
  );
  return account ? publicProfile(account) : null;
}
export function signOut() {
  localStorage.removeItem(sessionKey);
  storage().removeItem(sessionKey);
}
export async function registerAccount(
  username: string,
  password: string,
  nickname: string,
  remember = false,
) {
  username = username.trim().toLowerCase();
  nickname = nickname.trim();
  validateCredentials(username, password);
  if (!nickname || nickname.length > 24)
    throw new Error("昵称须为 1–24 个字符");
  if (readAccounts().some((a) => a.username === username))
    throw new Error("这个用户名已经被使用");
  const salt = hex(crypto.getRandomValues(new Uint8Array(16)));
  const credential = { salt, digest: await digest(password, salt) };
  const accounts = readAccounts();
  if (accounts.some((a) => a.username === username))
    throw new Error("这个用户名已经被使用");
  const account: LocalAccount = {
    id: crypto.randomUUID(),
    username,
    nickname,
    role: "student",
    bio: "",
    className: "",
    avatar: "blue",
    skills: [],
    joinedAt: new Date().toISOString(),
    demo: false,
    revision: 1,
    credential,
  };
  writeAccounts([...accounts, account]);
  return setSession(account, remember);
}
export async function signIn(
  username: string,
  password: string,
  remember = false,
) {
  validateCredentials(username.trim(), password);
  const account = readAccounts().find(
    (a) => a.username === username.trim().toLowerCase(),
  );
  if (
    !account?.credential ||
    (await digest(password, account.credential.salt)) !==
      account.credential.digest
  )
    throw new Error("用户名或密码不正确");
  return setSession(account, remember);
}
export function enterDemo(role: Role = "student") {
  const accounts = readAccounts();
  let account = accounts.find((a) => a.id === "u-" + role);
  if (!account) {
    account = {
      id: "u-" + role,
      username: "codelab_" + role,
      nickname: demoNames[role],
      role,
      bio: role === "student" ? "在真实项目里，把想法写成代码。" : "",
      className: "",
      avatar: role === "teacher" ? "mint" : role === "admin" ? "slate" : "blue",
      skills: role === "student" ? ["Vue", "TypeScript", "Python"] : [],
      joinedAt: "2026-09-01T00:00:00+08:00",
      demo: true,
      revision: 1,
    };
    writeAccounts([...accounts, account]);
  }
  return setSession(account, true);
}
export function updateProfile(
  changes: Pick<Profile, "nickname" | "bio" | "className" | "avatar" | "skills">,
) {
  const active = currentProfile();
  if (!active) throw new Error("请先登录");
  if (!changes.nickname.trim() || changes.nickname.trim().length > 24)
    throw new Error("昵称须为 1–24 个字符");
  if (
    changes.bio.length > 120 ||
    changes.className.length > 40 ||
    changes.skills.length > 5
  )
    throw new Error("个人资料超过长度限制");
  const accounts = readAccounts();
  const index = accounts.findIndex((a) => a.id === active.id);
  accounts[index] = {
    ...accounts[index],
    ...changes,
    nickname: changes.nickname.trim(),
  };
  writeAccounts(accounts);
  return publicProfile(accounts[index]);
}
export async function changeLocalPassword(
  oldPassword: string,
  newPassword: string,
) {
  const profile = currentProfile();
  if (!profile) throw new Error("请先登录");
  validateCredentials(profile.username, newPassword);
  const accounts = readAccounts();
  const account = accounts.find((a) => a.id === profile.id)!;
  if (!account.credential)
    throw new Error("体验账户没有密码，请注册自己的账户");
  if (
    (await digest(oldPassword, account.credential.salt)) !==
    account.credential.digest
  )
    throw new Error("原密码不正确");
  if (oldPassword === newPassword) throw new Error("新密码不能与原密码相同");
  const salt = hex(crypto.getRandomValues(new Uint8Array(16)));
  account.credential = { salt, digest: await digest(newPassword, salt) };
  account.revision++;
  writeAccounts(accounts);
  signOut();
}
