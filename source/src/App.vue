<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import Icon from "./components/Icon.vue";
import { state, resetDemo, applyAccount } from "./store";
import { isMock } from "./services/api";
import { enterDemo } from "./services/accounts";
import ProfileAvatar from "./components/ProfileAvatar.vue";
import type { Role } from "./types";
const route = useRoute(),
  router = useRouter(),
  mobileNavOpen = ref(false),
  sidebarCollapsed = ref(localStorage.getItem("codelab-sidebar-collapsed") === "1"),
  viewportWidth = ref(window.innerWidth),
  help = ref(false),
  notifications = ref(false),
  search = ref("");
const drawerMode = computed(() => viewportWidth.value <= 760 || (route.path.startsWith("/workspace") && viewportWidth.value <= 1024));
const navigationVisible = computed(() => drawerMode.value ? mobileNavOpen.value : !sidebarCollapsed.value);
function toggleNavigation() {
  if (drawerMode.value) mobileNavOpen.value = !mobileNavOpen.value;
  else {
    sidebarCollapsed.value = !sidebarCollapsed.value;
    localStorage.setItem("codelab-sidebar-collapsed", sidebarCollapsed.value ? "1" : "0");
  }
}
const updateViewport = () => { viewportWidth.value = window.innerWidth; };
const nav = [
  {
    label: "工作空间",
    items: [
      { path: "/", text: "个人主页", icon: "dashboard" },
      { path: "/problems", text: "探索题库", icon: "book", badge: "12" },
      { path: "/exams", text: "考试中心", icon: "calendar" },
      { path: "/reports", text: "学习记录", icon: "chart" },
      { path: "/leaderboard", text: "排行榜", icon: "trophy" },
    ],
  },
  {
    label: "我的资源",
    items: [
      { path: "/classes", text: "我的班级", icon: "users" },
      { path: "/banks", text: "我的题库", icon: "folder" },
      { path: "/mock", text: "个人模拟", icon: "code" },
      { path: "/developer", text: "开放 API", icon: "key" },
    ],
  },
];
const management = computed(() =>
  state.role === "student"
    ? []
    : [
        { path: "/exams/new", text: "组卷与发布", icon: "list" },
        { path: "/grades", text: "成绩与复核", icon: "graduation" },
        ...(state.role === "admin"
          ? [
              { path: "/admin", text: "用户与权限", icon: "shield" },
              { path: "/monitor", text: "运行监控", icon: "activity" },
            ]
          : []),
      ],
);
const roleName = computed(
  () => ({ student: "学生", teacher: "教师", admin: "管理员" })[state.role],
);
const displayName = computed(() => state.name);
function roleChange(value: Role) {
  applyAccount(enterDemo(value));
  router.push("/");
  ElMessage.success(`已切换为${roleName.value}`);
}
function globalSearch() {
  router.push({ path: "/problems", query: { q: search.value } });
  search.value = "";
}
async function reset() {
  await ElMessageBox.confirm(
    "将清除本浏览器的演示操作和草稿，恢复初始展示数据。",
    "重置演示",
    { type: "warning" },
  )
    .then(resetDemo)
    .catch(() => {});
}
const storageError = () =>
  ElMessage.error("浏览器存储空间不足，请下载草稿后清理演示数据");
onMounted(() => {
  window.addEventListener("storage-error", storageError);
  window.addEventListener("resize", updateViewport);
});
onBeforeUnmount(() => {
  window.removeEventListener("storage-error", storageError);
  window.removeEventListener("resize", updateViewport);
});
</script>
<template>
  <div v-if="route.path === '/login'" class="login-shell"><RouterView /></div>
  <div
    v-else
    class="app-shell"
    :class="{
      'sidebar-open': drawerMode && mobileNavOpen,
      'sidebar-collapsed': !drawerMode && sidebarCollapsed,
      'workspace-shell': route.path.startsWith('/workspace'),
    }"
  >
    <div v-if="drawerMode && mobileNavOpen" class="nav-backdrop" @click="mobileNavOpen = false" />
    <aside id="primary-navigation" class="sidebar" :inert="!navigationVisible" :aria-hidden="!navigationVisible">
      <RouterLink to="/" class="brand" @click="mobileNavOpen = false"
        ><span class="brand-mark"><Icon name="code" :size="23" /></span
        ><span>CodeLab</span><span class="brand-dot"
      /></RouterLink>
      <nav>
        <div v-for="group in nav" :key="group.label" class="nav-group">
          <span class="nav-label">{{ group.label }}</span
          ><RouterLink
            v-for="item in group.items"
            :key="item.path"
            :to="item.path"
            class="nav-link"
            :class="{
              selected:
                route.path === item.path ||
                (item.path === '/reports' &&
                  route.path.startsWith('/reports/')),
            }"
            @click="mobileNavOpen = false"
            ><Icon :name="item.icon" /><span>{{ item.text }}</span
            ><small v-if="item.badge" class="nav-badge">{{
              state.problems.filter((p) => p.bank === "内置题库").length
            }}</small></RouterLink
          >
        </div>
        <div v-if="management.length" class="nav-group">
          <span class="nav-label">教学与平台管理</span
          ><RouterLink
            v-for="item in management"
            :key="item.path"
            :to="item.path"
            class="nav-link"
            :class="{ selected: route.path === item.path }"
            @click="mobileNavOpen = false"
            ><Icon :name="item.icon" /><span>{{ item.text }}</span></RouterLink
          >
        </div>
      </nav>
      <div class="sidebar-bottom">
        <button class="nav-link guide-button" @click="help = true">
          <Icon name="help" /><span>使用指南</span>
        </button>
        <RouterLink to="/settings" class="profile-link" @click="mobileNavOpen = false"
          ><ProfileAvatar
            :name="displayName"
            :color="state.profile?.avatar"
            :size="34" />
          ><span
            ><b>{{ displayName }}</b
            ><small
              >{{ roleName }} ·
              {{ state.profile?.demo ? "体验账户" : "个人账户" }}</small
            ></span
          ><Icon name="settings" :size="18"
        /></RouterLink>
      </div>
    </aside>
    <div class="main-shell">
      <header class="topbar">
        <div class="breadcrumb">
          <button
            class="icon-btn sidebar-toggle"
            :aria-label="navigationVisible ? '收起左侧导航' : '展开左侧导航'"
            :title="navigationVisible ? '收起左侧导航' : '展开左侧导航'"
            :aria-expanded="navigationVisible"
            aria-controls="primary-navigation"
            @click="toggleNavigation"
          >
            <Icon :name="navigationVisible ? 'sidebar-close' : 'sidebar-open'" /></button
          ><span>工作空间</span><Icon name="right" :size="14" /><b>{{
            route.meta.title
          }}</b>
        </div>
        <div class="topbar-actions">
          <form class="global-search" @submit.prevent="globalSearch">
            <Icon name="search" :size="16" /><input
              v-model="search"
              aria-label="全局搜索题目"
              placeholder="搜索题目、关键词…"
            /><kbd>↵</kbd>
          </form>
          <el-select
            v-if="isMock && state.profile?.demo"
            :model-value="state.role"
            class="role-select"
            aria-label="演示角色"
            @change="roleChange"
            ><el-option label="学生视角" value="student" /><el-option
              label="教师视角"
              value="teacher" /><el-option
              label="管理员视角"
              value="admin" /></el-select
          ><button
            class="icon-btn notification-btn"
            aria-label="查看通知"
            @click="notifications = true"
          >
            <Icon name="bell" /><i /></button
          ><RouterLink to="/" aria-label="个人主页"
            ><ProfileAvatar
              :name="displayName"
              :color="state.profile?.avatar"
              :size="32"
          /></RouterLink>
        </div>
      </header>
      <main
        :class="
          route.path.startsWith('/workspace') ? 'workspace-main' : 'page-main'
        "
      >
        <RouterView :key="route.fullPath" />
      </main>
    </div>
  </div>
  <el-dialog v-model="help" title="开始使用 CodeLab" width="560px">
    <div class="guide-steps">
      <p>
        <b>01　个人练习</b><br />探索题库 → 点击题目 → 编辑项目文件 → 检查项目 →
        提交 → 六维报告。
      </p>
      <p>
        <b>02　课堂考试</b><br />教师创建考试 → 学生考前确认 → 限时作答与交卷 →
        教师复核和发布。
      </p>
      <p>
        <b>03　内容与平台</b
        ><br />建立私有题库、配置模拟考试；管理员可维护权限和查看模拟队列。
      </p>
    </div>
    <template #footer
      ><el-button v-if="state.profile?.demo" @click="reset"
        >重置演示数据</el-button
      ><el-button type="primary" @click="help = false"
        >开始探索</el-button
      ></template
    ></el-dialog
  >
  <el-drawer v-model="notifications" title="消息通知" size="380px"
    ><div class="notification-item">
      <span class="icon-tile"><Icon name="calendar" /></span>
      <div>
        <b>阶段测评已发布</b>
        <p>请提前阅读 AI 使用规则与考前确认信息。</p>
        <RouterLink to="/exams" @click="notifications = false"
          >查看考试 →</RouterLink
        >
      </div>
    </div>
    <div class="notification-item">
      <span class="icon-tile"><Icon name="chart" /></span>
      <div>
        <b>基础能力报告已就绪</b>
        <p>查看六维表现与具体改进建议。</p>
        <RouterLink to="/reports" @click="notifications = false"
          >查看报告 →</RouterLink
        >
      </div>
    </div>
  </el-drawer>
</template>
