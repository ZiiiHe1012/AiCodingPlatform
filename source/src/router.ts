import { createRouter, createWebHistory } from "vue-router";
import { state, applyAccount } from "./store";
import { currentProfile } from "./services/accounts";
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
  {
    path: "/problems",
    component: () => import("./pages/Problems.vue"),
    meta: { title: "探索题库" },
  },
  {
    path: "/workspace/:id",
    component: () => import("./pages/Workspace.vue"),
    meta: { title: "编程工作台" },
  },
  {
    path: "/reports/:id?",
    component: () => import("./pages/Report.vue"),
    meta: { title: "成绩报告" },
  },
  {
    path: "/classes",
    component: () => import("./pages/Classes.vue"),
    meta: { title: "我的班级" },
  },
  {
    path: "/exams",
    component: () => import("./pages/Exams.vue"),
    meta: { title: "考试中心" },
  },
  {
    path: "/exams/new",
    component: () => import("./pages/ExamBuilder.vue"),
    meta: { title: "创建考试", roles: ["teacher", "admin"] },
  },
  {
    path: "/exams/:id",
    component: () => import("./pages/ExamDetail.vue"),
    meta: { title: "考试详情" },
  },
  {
    path: "/grades",
    component: () => import("./pages/Grades.vue"),
    meta: { title: "班级成绩", roles: ["teacher", "admin"] },
  },
  {
    path: "/banks",
    component: () => import("./pages/Banks.vue"),
    meta: { title: "我的题库" },
  },
  {
    path: "/problem-edit/:id?",
    component: () => import("./pages/ProblemEditor.vue"),
    meta: { title: "题目编辑" },
  },
  {
    path: "/mock",
    component: () => import("./pages/ExamBuilder.vue"),
    meta: { title: "个人模拟" },
  },
  {
    path: "/leaderboard",
    component: () => import("./pages/Leaderboard.vue"),
    meta: { title: "排行榜" },
  },
  {
    path: "/admin",
    component: () => import("./pages/Admin.vue"),
    meta: { title: "用户与权限", roles: ["admin"] },
  },
  {
    path: "/developer",
    component: () => import("./pages/Developer.vue"),
    meta: { title: "开放 API" },
  },
  {
    path: "/monitor",
    component: () => import("./pages/Monitor.vue"),
    meta: { title: "运行监控", roles: ["admin"] },
  },
  { path: "/profile", redirect: "/" },
  { path: "/:pathMatch(.*)*", redirect: "/" },
];
export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
});
router.beforeEach((to) => {
  applyAccount(currentProfile());
  if (!state.loggedIn && to.path !== "/login")
    return { path: "/login", query: { redirect: to.fullPath } };
  if (state.loggedIn && to.path === "/login") return "/";
  const roles = to.meta.roles as string[] | undefined;
  if (roles && !roles.includes(state.role)) return "/";
  document.title = `${to.meta.title || "个人主页"} · CodeLab`;
});
