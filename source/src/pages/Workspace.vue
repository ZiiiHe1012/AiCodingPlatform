<script setup lang="ts">
import {
  ref,
  computed,
  watch,
  nextTick,
  onMounted,
  onBeforeUnmount,
  defineAsyncComponent,
} from "vue";
import { useRoute, useRouter, onBeforeRouteLeave, onBeforeRouteUpdate } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import Icon from "../components/Icon.vue";
import ResizableWorkspace from "../components/ResizableWorkspace.vue";
import ProjectExplorer from "../components/ProjectFiles.vue";
import { state, userId } from "../store";
import { platform, type JobProgress } from "../services/platform";
import { api, isMock, ApiError } from "../services/api";
import { dimensionNames, validatePackagePath } from "../domain";
import { downloadProject, upgradeDraft } from "../project";
import type { Draft, ProjectFiles } from "../types";
const CodeEditor = defineAsyncComponent(
  () => import("../components/CodeEditor.vue"),
);
const route = useRoute(),
  router = useRouter();
const exam = computed(() => state.exams.find((e) => e.id === route.query.exam));
const problem = computed(
  () =>
    exam.value?.snapshots?.find((p) => p.id === route.params.id) ||
    state.problems.find((p) => p.id === route.params.id),
);
const scope = exam.value?.id || "practice-" + route.params.id;
const key = userId() + ":" + scope + ":" + route.params.id;
const draftStore = platform?.live ? sessionStorage : localStorage;
const rawInitial = (
  exam.value?.receipt
    ? exam.value.finalDrafts?.[String(route.params.id)]
    : JSON.parse(draftStore.getItem("codelab-draft-" + key) || "null")
) as Draft | null;
const initial = rawInitial ? upgradeDraft(rawInitial) : null;
const files = ref<ProjectFiles>({
  ...(initial?.files || problem.value?.files || {}),
});
const historyRows = ref<{version:number; updatedAt:string}[]>([]);
interface ChatMessage {
  role: string;
  text: string;
  time?: string;
  requestId?: string;
}
const runTask = ref<JobProgress | null>(null);
const explanation = ref(initial?.explanation || ""),
  version = ref(initial?.version || 0),
  file = ref(initial?.activeFile || problem.value?.entryFile || "README.md"),
  leftTab = ref("项目任务"),
  bottomTab = ref("项目检查"),
  saveState = ref(initial ? "已恢复草稿" : "尚未保存"),
  readOnly = ref(false),
  offline = ref(!navigator.onLine),
  conflict = ref(false),
  busy = ref(false),
  running = ref(false),
  output = ref(""),
  runShown = ref(false),
  chat = ref<ChatMessage[]>(JSON.parse(draftStore.getItem("codelab-chat-" + key) || "[]")),
  receipt = ref(exam.value?.receipt || "");
const explorerOpen = ref(true);
const openedFiles = ref([file.value]);
watch(file, (path) => {
  if (!openedFiles.value.includes(path)) openedFiles.value.push(path);
});
function closeFile(path: string) {
  if (openedFiles.value.length === 1) return;
  const index = openedFiles.value.indexOf(path);
  openedFiles.value = openedFiles.value.filter((p) => p !== path);
  if (file.value === path)
    file.value = openedFiles.value[Math.max(0, index - 1)];
}
async function resetFile() {
  try {
    await ElMessageBox.confirm("恢复当前文件的初始内容？", file.value);
    currentFile.value = problem.value!.files[file.value];
  } catch {}
}
const session = crypto.randomUUID(),
  lockKey = "codelab-lock-" + userId() + ":" + scope;
let saveTimer: ReturnType<typeof setTimeout>;
let tick: ReturnType<typeof setInterval>;
let heartbeat: ReturnType<typeof setInterval>;
let periodicSave: ReturnType<typeof setInterval>;
let savePromise: Promise<boolean> | null = null;
const baseNow = () => {
  if (isMock && exam.value?.id === "exam-1") {
    const k = "codelab-demo-clock";
    let origin = Number(sessionStorage.getItem(k));
    if (!origin) {
      origin = Date.now();
      sessionStorage.setItem(k, String(origin));
    }
    return Date.parse("2026-10-31T14:29:00+08:00") + Date.now() - origin;
  }
  return Date.now();
};
const now = ref(baseNow());
const remaining = computed(() =>
  exam.value
    ? Math.max(
        0,
        Math.floor((new Date(exam.value.end).getTime() - now.value) / 1000),
      )
    : 0,
);
const timeText = computed(() =>
  [
    Math.floor(remaining.value / 3600),
    Math.floor(remaining.value / 60) % 60,
    remaining.value % 60,
  ]
    .map((v) => String(v).padStart(2, "0"))
    .join(":"),
);
const frozen = computed(
  () =>
    readOnly.value || !!receipt.value || (!!exam.value && remaining.value <= 0),
);
const currentFile = computed({
  get: () => files.value[file.value] || "",
  set: (value: string) => {
    files.value[file.value] = value;
  },
});
async function addFile() {
  try {
    const { value } = await ElMessageBox.prompt(
      "输入相对项目根目录的路径",
      "新建文件",
      {
        inputPlaceholder: "tests/acceptance.test.ts",
        inputValidator: (v) =>
          (!!v &&
            validatePackagePath(v) &&
            !v.endsWith("/") &&
            !(v in files.value)) ||
          "路径无效或文件已存在",
      },
    );
    files.value[value] = "";
    file.value = value;
  } catch {}
}
function exportProject() {
  downloadProject(
    problem.value!.repository,
    files.value,
    explanation.value,
    chat.value,
  );
}
watch(
  chat,
  () => draftStore.setItem("codelab-chat-" + key, JSON.stringify(chat.value)),
  { deep: true },
);
function acquire() {
  if (platform?.live && exam.value) { readOnly.value = platform.examReadOnly; return; }
  const l = JSON.parse(localStorage.getItem(lockKey) || "null");
  if (l && l.session !== session && Date.now() - l.time < 8000) {
    readOnly.value = true;
    return;
  }
  readOnly.value = false;
  localStorage.setItem(lockKey, JSON.stringify({ session, time: Date.now() }));
}
async function saveDraft(): Promise<boolean> {
  saveState.value = "保存中…";
  const draft: Draft = {
    files: { ...files.value }, activeFile: file.value, aiHistory: JSON.parse(JSON.stringify(chat.value)),
    explanation: explanation.value, version: version.value, updatedAt: "",
  };
  try {
    const result = await api.saveDraft(key, draft);
    version.value = result.version;
    saveState.value = platform?.live || !isMock ? "已同步到服务器" : "已保存";
    draftStore.removeItem("codelab-unsynced-" + key);
    return true;
  } catch (e) {
    saveState.value = (e as Error).message;
    if (e instanceof ApiError && e.status === 409) conflict.value = true;
    try { draftStore.setItem("codelab-unsynced-" + key, JSON.stringify(draft)); }
    catch { ElMessage.error("本地存储已满，请立即下载草稿"); }
    return false;
  }
}
async function save(): Promise<boolean> {
  if (savePromise && !(await savePromise)) return false;
  if (frozen.value || conflict.value || offline.value) return false;
  if (!savePromise) {
    savePromise = saveDraft().finally(() => { savePromise = null; });
  }
  return savePromise;
}
async function saveCurrent(): Promise<boolean> {
  // Drain edits made while the preceding revision was being acknowledged.
  for (;;) {
    const before = JSON.stringify([files.value, explanation.value, chat.value, file.value]);
    if (!await save()) return false;
    if (before === JSON.stringify([files.value, explanation.value, chat.value, file.value])) return true;
  }
}
watch(
  [files, explanation, chat],
  () => {
    if (frozen.value) return;
    saveState.value = "有未保存修改";
    clearTimeout(saveTimer);
    saveTimer = setTimeout(save, 800);
  },
  { deep: true },
);
async function restore() {
  const d = JSON.parse(
    draftStore.getItem("codelab-draft-" + key) || "null",
  ) as Draft | null;
  if (d) {
    files.value = { ...upgradeDraft(d).files };
    file.value = upgradeDraft(d).activeFile;
    explanation.value = d.explanation;
    version.value = d.version;
    conflict.value = false;
    saveState.value = "已恢复确认版本";
  }
}
async function refreshHistory() {
  bottomTab.value = "草稿历史";
  if (!platform?.live) return;
  try { historyRows.value = await platform.versions(key); }
  catch (e) { ElMessage.error((e as Error).message); }
}
async function restoreVersion(target: number) {
  if (!platform?.live || frozen.value) return;
  try {
    await ElMessageBox.confirm("当前内容会先保存，恢复后仍可在历史中找到。", "恢复草稿版本");
  } catch { return; }
  if (!await saveCurrent()) return ElMessage.warning("当前内容尚未保存，无法恢复。");
  try {
    const restored = await platform.restoreDraft(key, target, version.value);
    files.value = { ...restored.files }; file.value = restored.activeFile;
    explanation.value = restored.explanation; version.value = restored.version;
    chat.value = restored.aiHistory || [];
    await refreshHistory();
  } catch (e) { ElMessage.error((e as Error).message); }
}
async function stopJob(task: JobProgress | null) {
  if (!task || !platform?.live) return;
  try { await platform.cancelJob(task.id); }
  catch (e) { ElMessage.error((e as Error).message); }
}
async function run(command = "", inSandbox = false) {
  if (!problem.value || frozen.value || running.value) return;
  running.value = true;
  if (!inSandbox) bottomTab.value = "项目检查";
  runTask.value = null;
  try {
    const r = platform?.live
      ? await platform.runCommand(problem.value.id, files.value, command, task => { runTask.value = task; })
      : await api.run(problem.value.id, files.value);
    output.value = r.message;
    runShown.value = true;
  } catch (e) {
    output.value = (e as Error).message;
    runShown.value = true;
  } finally {
    running.value = false;
  }
}
async function submit() {
  if (!problem.value || frozen.value || busy.value) return;
  if (!Object.values(files.value).some((text) => text.trim()))
    return ElMessage.warning("请先编写项目文件");
  busy.value = true;
  try {
    if (!await saveCurrent()) return ElMessage.warning("草稿尚未同步，暂不能提交项目。");
    const frozenFiles = { ...files.value };
    const history = chat.value.map(({role, text}) => ({role, text}));
    const retryStore = "codelab-submit-" + key;
    const previous = JSON.parse(sessionStorage.getItem(retryStore) || "null");
    const token = previous?.version === version.value ? previous.token : crypto.randomUUID();
    sessionStorage.setItem(retryStore, JSON.stringify({version: version.value, token}));
    const s = await api.submit(
      problem.value.id,
      frozenFiles,
      explanation.value,
      token,
      exam.value?.id,
      history,
    );
    sessionStorage.removeItem(retryStore);
    if (exam.value) {
      ElMessage.success(`过程提交 ${s.id} 已接收；最终成绩以交卷快照为准`);
    } else ElMessage.success("项目已提交，编号 " + s.id);
  } catch (e) {
    ElMessage.error((e as Error).message);
  } finally {
    busy.value = false;
  }
}
async function handIn(auto = false) {
  if (!exam.value || receipt.value || busy.value || readOnly.value) return;
  if (!auto) {
    try {
      await ElMessageBox.confirm(
        "交卷后无法继续修改，确认提交最终答卷？",
        "确认交卷",
        {
          confirmButtonText: "确认交卷",
          cancelButtonText: "继续作答",
          type: "warning",
        },
      );
    } catch {
      return;
    }
    if (!await saveCurrent())
      return ElMessage.warning("草稿尚未同步，请处理冲突或恢复网络后交卷");
  }
  busy.value = true;
  try {
    const drafts: Record<string, Draft> = {};
    drafts[problem.value!.id] = {
      files: JSON.parse(JSON.stringify(files.value)),
      activeFile: file.value,
      explanation: explanation.value,
      aiHistory: JSON.parse(JSON.stringify(chat.value)),
      version: version.value,
      updatedAt: new Date().toISOString(),
    };
    for (const id of exam.value.problemIds) {
      const raw = draftStore.getItem(
        "codelab-draft-" + userId() + ":" + scope + ":" + id,
      );
      if (raw && id !== problem.value!.id)
        drafts[id] = upgradeDraft(JSON.parse(raw));
    }
    const r = await api.handIn(exam.value.id, drafts);
    receipt.value = r.receipt;
    ElMessage.success(auto ? "考试已结束，答卷已提交" : "交卷成功");
  } catch (e) {
    ElMessage.error((e as Error).message);
  } finally {
    busy.value = false;
  }
}
async function beforeChange() {
  clearTimeout(saveTimer);
  if (!frozen.value) {
    if (!await saveCurrent()) {
      try {
        await ElMessageBox.confirm(
          "有尚未同步的草稿。建议先下载保留，是否仍要离开？",
          "草稿未同步",
        );
      } catch {
        return false;
      }
    }
  }
}
onBeforeRouteLeave(beforeChange);
onBeforeRouteUpdate(beforeChange);
function online() {
  offline.value = !navigator.onLine;
  if (!offline.value) save();
}
function storage(e: StorageEvent) {
  if (e.key === lockKey) acquire();
}
function leave(e: BeforeUnloadEvent) {
  if (saveState.value === "有未保存修改" || offline.value) {
    e.preventDefault();
    e.returnValue = "";
  }
}
onMounted(() => {
  acquire();
  periodicSave = setInterval(save, 15000);
  heartbeat = setInterval(acquire, 3000);
  tick = setInterval(() => {
    now.value = baseNow();
    if (exam.value && remaining.value === 0 && !receipt.value) handIn(true);
  }, 1000);
  window.addEventListener("online", online);
  window.addEventListener("offline", online);
  window.addEventListener("storage", storage);
  window.addEventListener("beforeunload", leave);
  if (!initial && !frozen.value) save();
  const unsynced = draftStore.getItem("codelab-unsynced-" + key);
  if (unsynced) ElMessage.warning("检测到未同步的本地草稿，可在下方下载保留。");
});
onBeforeUnmount(() => {
  clearInterval(periodicSave);
  clearInterval(tick);
  clearInterval(heartbeat);
  clearTimeout(saveTimer);
  const l = JSON.parse(localStorage.getItem(lockKey) || "null");
  if (l?.session === session) localStorage.removeItem(lockKey);
  window.removeEventListener("online", online);
  window.removeEventListener("offline", online);
  window.removeEventListener("storage", storage);
  window.removeEventListener("beforeunload", leave);
});
</script>
<template>
  <el-empty v-if="!problem" description="题目不存在或无权访问" /><template
    v-else
    ><div class="work-toolbar">
      <div>
        <button
          class="icon-btn"
          aria-label="返回题库"
          @click="router.push(exam ? '/exams/' + exam.id : '/problems')"
        >
          <Icon name="back" /></button
        ><b>{{ problem.title }}</b
        ><span class="tag blue">{{ exam ? "考试模式" : "自由练习" }}</span
        ><el-select
          v-if="exam"
          :model-value="problem.id"
          style="width: 150px"
          aria-label="切换考试题目"
          @change="
            (v: string) => router.push('/workspace/' + v + '?exam=' + exam!.id)
          "
          ><el-option
            v-for="(id, i) in exam.problemIds"
            :key="id"
            :label="'第 ' + (i + 1) + ' 题 · ' + id"
            :value="id"
        /></el-select>
      </div>
      <div>
        <span v-if="exam" class="countdown"
          ><Icon name="clock" :size="16" />{{ timeText }} </span
        ><el-button :loading="running" :disabled="frozen" @click="run()"
          ><Icon name="play" :size="15" />检查项目</el-button
        ><el-button
          type="primary"
          :loading="busy"
          :disabled="frozen"
          @click="submit"
          ><Icon name="send" :size="15" />提交项目</el-button
        ><el-button
          v-if="exam"
          type="primary"
          plain
          :disabled="frozen"
          @click="handIn(false)"
          >交卷</el-button
        >
      </div>
    </div>
    <div v-if="offline || conflict || readOnly || receipt" class="work-notice">
      <Icon name="warning" :size="16" />{{
        receipt
          ? "交卷完成 · 最终答卷 " + receipt + " · 当前为只读快照"
          : readOnly
            ? "另一页面正在编辑，本页面只读"
            : conflict
              ? "草稿版本冲突，请选择要保留的版本"
              : "网络已断开，本地修改尚未同步"
      }}<button v-if="conflict" class="text-link" @click="restore">
        恢复确认版本</button
      ><button class="text-link" @click="exportProject">下载当前草稿</button>
    </div>

    <ResizableWorkspace
      ><template #statement>
        <section class="work-statement">
          <div class="work-tabs">
            <button
              v-for="t in ['项目任务', '验收标准', '评分量规']"
              :key="t"
              :class="{ active: leftTab === t }"
              @click="leftTab = t"
            >
              {{ t }}
            </button>
          </div>
          <div v-if="leftTab === '项目任务'" class="statement-body">
            <div class="inline-tags">
              <span class="tag blue">{{ problem.type }}</span
              ><span class="tag gray">{{ problem.difficulty }}</span
              ><span class="muted tiny"
                >{{ problem.id }} · {{ problem.version }}</span
              >
            </div>
            <h2>{{ problem.title }}</h2>
            <p>{{ problem.description }}</p>
            <h3>需求清单</h3>
            <ol class="project-requirements">
              <li v-for="r in problem.requirements" :key="r">{{ r }}</li>
            </ol>
            <h3>交付物</h3>
            <ul class="constraint-list">
              <li v-for="d in problem.deliverables" :key="d">{{ d }}</li>
            </ul>
            <h3>工程约束</h3>
            <ul class="constraint-list">
              <li v-for="c in problem.constraints" :key="c">{{ c }}</li>
            </ul>
            <h3>开发环境</h3>
            <p>{{ problem.stack }} · 建议 {{ problem.duration }} 分钟</p>
            <div class="code-sample">
              <code>{{
                [
                  problem.commands.setup,
                  problem.commands.test,
                  problem.commands.start,
                ]
                  .filter(Boolean)
                  .join("\n")
              }}</code>
            </div>
            <details class="source-details">
              <summary>题目来源</summary>
              <p>{{ problem.source }}</p>
            </details>
          </div>
          <div v-else-if="leftTab === '验收标准'" class="statement-body">
            <h2>验收场景</h2>
            <article
              v-for="a in problem.acceptance"
              :key="a.id"
              class="acceptance-card"
            >
              <span class="tag blue">{{ a.id }}</span>
              <h3>{{ a.scenario }}</h3>
              <p>{{ a.expected }}</p>
            </article>
          </div>
          <div v-else class="statement-body">
            <h2>六维评分量规</h2>

            <div v-for="(d, i) in dimensionNames" :key="d" class="rubric-row">
              <span>D{{ i + 1 }} {{ d }}</span
              ><b>{{ problem.weights[i] }}%</b>
            </div>
          </div>
        </section></template
      ><template #editor>
        <section class="work-code">
          <div class="editor-top">
            <span
              ><button
                class="icon-btn"
                aria-label="切换文件资源管理器"
                :aria-pressed="explorerOpen"
                @click="explorerOpen = !explorerOpen"
              >
                <Icon name="folder" :size="16" /></button
              >工作区</span
            ><button class="text-link" @click="exportProject">
              <Icon name="download" :size="14" />导出项目
            </button>
          </div>
          <div
            class="project-editor-layout"
            :class="{ 'explorer-hidden': !explorerOpen }"
          >
            <ProjectExplorer
              v-if="explorerOpen"
              :paths="Object.keys(files)"
              v-model="file"
              :repository="problem.repository"
              :read-only="frozen"
              @create="addFile"
            />
            <div class="project-editor-main">
              <div
                class="editor-open-tabs"
                role="tablist"
                aria-label="已打开文件"
              >
                <div
                  v-for="path in openedFiles"
                  :key="path"
                  class="editor-file-tab"
                  :class="{ active: file === path }"
                >
                  <button
                    role="tab"
                    :aria-selected="file === path"
                    :title="path"
                    @click="file = path"
                  >
                    <Icon name="file" :size="13" />{{
                      path.split("/").pop()
                    }}</button
                  ><button
                    :aria-label="'关闭 ' + path"
                    :disabled="openedFiles.length === 1"
                    @click="closeFile(path)"
                  >
                    <Icon name="close" :size="12" />
                  </button>
                </div>
              </div>
              <div class="editor-breadcrumb">
                <span>{{ file }}</span
                ><button
                  class="icon-btn"
                  aria-label="恢复当前文件"
                  :disabled="frozen || !(file in problem.files)"
                  @click="resetFile"
                >
                  <Icon name="refresh" :size="14" />
                </button>
              </div>
              <CodeEditor
                v-model="currentFile"
                :file-name="file"
                :read-only="frozen"
              />
              <div class="editor-status">
                <span
                  ><Icon
                    :name="conflict || offline ? 'warning' : 'success'"
                    :size="12"
                  />{{ saveState }}</span
                ><span
                  >UTF-8 · v{{ version }}
                  <button class="text-link tiny" @click="save">
                    保存
                  </button></span
                >
              </div>
              <div class="results-panel">
                <div class="work-tabs">
                  <button
                    v-for="t in platform?.live ? ['项目检查', '验证说明', '草稿历史'] : ['项目检查', '验证说明']"
                    :key="t"
                    :class="{ active: bottomTab === t }"
                    @click="t === '草稿历史' ? refreshHistory() : bottomTab = t"
                  >
                    {{ t }}
                  </button>
                </div>
                <div v-if="bottomTab === '项目检查'" class="run-output">
                  <div v-if="!runShown && !running" class="empty-console">
                    <Icon name="terminal" :size="25" /><span
                      >检查项目文件，查看测试命令</span
                    >
                  </div>
                  <p v-else-if="running">正在请求运行服务…
                    <button v-if="runTask" class="text-link" @click="stopJob(runTask)">停止运行</button>
                  </p>
                  <template v-else>
                    <pre>{{ output }}</pre>
                  </template>
                </div>
                <div v-else-if="bottomTab === '草稿历史'" class="run-output">
                  <p v-if="!historyRows.length">暂无已保存的版本</p>
                  <p v-for="row in historyRows" :key="row.version">v{{ row.version }} · {{ new Date(row.updatedAt).toLocaleTimeString() }}
                    <button class="text-link" v-if="row.version !== version" :disabled="frozen" @click="restoreVersion(row.version)">恢复此版本</button>
                  </p>
                </div>
                <div v-else class="explanation-editor">
                  <el-input
                    v-model="explanation"
                    type="textarea"
                    :rows="5"
                    :disabled="frozen"
                    placeholder="记录需求拆解、设计取舍、测试结果，以及采纳或拒绝 AI 建议的依据。"
                  />
                </div>
              </div>
            </div>
          </div></section></template
      ><template #assistant><aside class="work-ai"><h3>本题交付要求</h3><ul><li v-for="item in problem.deliverables" :key="item">{{ item }}</li></ul></aside></template>
    </ResizableWorkspace>
  </template>
</template>
