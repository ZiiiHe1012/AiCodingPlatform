import { createRouter, createWebHistory } from "vue-router";
import { state, applyAccount } from "./store";
import { currentProfile } from "./services/accounts";
import { platform } from "./services/platform";
const routes = [
  {
    path: "/",
    name: "dashboard",
    component: () => import("./pages/Dashboard.vue"),
    meta: { title: "个人主页" },
  },
  {
    path: "/login",
    name: "login",
    component: () => import("./pages/Account.vue"),
    meta: { title: "账户登录" },
  },
  {
    path: "/settings",
    component: () => import("./pages/Account.vue"),
    meta: { title: "个人设置" },
  },
  { path: "/profile", redirect: "/" },
  { path: "/:pathMatch(.*)*", redirect: "/" },
];
export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
});
router.beforeEach(async (to) => {
  const local = currentProfile();
  applyAccount(platform ? await platform.route(to, local) : local);
  if (!state.loggedIn && to.path !== "/login")
    return { path: "/login", query: { redirect: to.fullPath } };
  if (state.loggedIn && to.path === "/login") return "/";
  const roles = to.meta.roles as string[] | undefined;
  if (roles && !roles.includes(state.role)) return "/";
  document.title = `${to.meta.title || "个人主页"} · CodeLab`;
});
