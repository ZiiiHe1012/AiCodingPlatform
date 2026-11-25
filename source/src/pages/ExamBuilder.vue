<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { state } from "../store";
import { api } from "../services/api";
import { validateWeights } from "../domain";
import type { Exam } from "../types";
import { taskTypes, stacks } from "../data";
import Icon from "../components/Icon.vue";
const route = useRoute(),
  router = useRouter(),
  personal = computed(() => route.path === "/mock");
const step = ref(0),
  title = ref(""),
  classId = ref(state.classes.find((c) => !c.archived)?.id || ""),
  range = ref<[Date, Date]>([
    new Date(Date.now() + 3600000),
    new Date(Date.now() + 9000000),
  ]),
  immediate = ref(false),
  limitRoster = ref(false),
  selectedStudents = ref<string[]>([]),
  duration = ref(90),
  bank = ref(""),
  difficulty = ref(""),
  selection = ref<string[]>([]),
  weights = ref<Record<string, number>>({}),
  count = ref(1),
  taskType = ref(""),
  stack = ref(""),
  aiContext = ref<Exam["aiContext"]>("项目文件"),
  aiMode = ref<Exam["aiMode"]>("对话与代码建议"),
  deliverables = ref(["项目代码与测试", "变更说明", "AI 协作与验证记录"]),
  model = ref("course-coder-v1"),
  requests = ref(40),
  tokens = ref(60000),
  board = ref(false),
  publicBoard = ref(false),
  release = ref("manual"),
  busy = ref(false),
  mode = ref("手动选题");
const classroom = computed(() => state.classes.find(c => c.id === classId.value));
watch(classId, () => { selectedStudents.value = []; });
const available = computed(() =>
  state.problems.filter(
    (p) =>
      p.status === "已发布" &&
      (!bank.value || p.bank === bank.value) &&
      (!difficulty.value || p.difficulty === difficulty.value) &&
      (!taskType.value || p.type === taskType.value) &&
      (!stack.value || p.stack === stack.value) &&
      (!personal.value || p.bank !== "内置题库"),
  ),
);
const chosen = computed(() =>
  selection.value.map((id) => state.problems.find((p) => p.id === id)!),
);
const totalWeight = computed(() =>
  selection.value.reduce((s, id) => s + (weights.value[id] || 0), 0),
);
function toggle(id: string) {
  if (selection.value.includes(id)) {
    selection.value = selection.value.filter((x) => x !== id);
  } else selection.value.push(id);
  balance();
}
function balance() {
  const n = selection.value.length;
  selection.value.forEach(
    (id, i) =>
      (weights.value[id] =
        i === n - 1
          ? 100 - Math.floor(100 / n) * (n - 1)
          : Math.floor(100 / n)),
  );
}
function draw() {
  if (available.value.length < count.value)
    return ElMessage.warning(
      `符合条件的题目仅 ${available.value.length} 道，无法抽取 ${count.value} 道`,
    );
  selection.value = [...available.value]
    .sort(() => Math.random() - 0.5)
    .slice(0, count.value)
    .map((p) => p.id);
  balance();
  ElMessage.success("已重新抽取不重复题目");
}
function next() {
  if (step.value === 0) {
    if (!title.value.trim()) return ElMessage.warning("请填写考试名称");
    if (!personal.value && !classId.value)
      return ElMessage.warning("请选择未归档班级");
    if (!personal.value && limitRoster.value && !selectedStudents.value.length)
      return ElMessage.warning("请选择参加考试的学生");
    if (
      !personal.value &&
      (!range.value ||
        range.value[1].getTime() <= Date.now() ||
        (!immediate.value && range.value[1] <= range.value[0]))
    )
      return ElMessage.warning("请选择未来有效的起止时间");
    if (duration.value < 1 || duration.value > 300)
      return ElMessage.warning("模拟时长须为 1–300 分钟");
  }
  if (
    step.value === 1 &&
    (!selection.value.length ||
      !validateWeights(selection.value.map((id) => weights.value[id])))
  )
    return ElMessage.warning("请选择题目，每题权重大于 0 且合计 100%");
  step.value++;
}
async function publish() {
  if (!validateWeights(selection.value.map((id) => weights.value[id])))
    return ElMessage.warning("请检查题目权重");
  busy.value = true;
  try {
    const start = personal.value || immediate.value ? new Date() : range.value[0],
      end = personal.value
        ? new Date(Date.now() + duration.value * 60000)
        : range.value[1];
    const exam: Exam = {
      id: "exam-" + Date.now(),
      title: title.value.trim(),
      className: personal.value
        ? "个人模拟 · 仅自己可见"
        : state.classes.find((c) => c.id === classId.value)!.name,
      start: start.toISOString(),
      end: end.toISOString(),
      status: personal.value ? "进行中" : "已发布",
      problemIds: [...selection.value],
      weights: selection.value.map((id) => weights.value[id]),
      model: model.value,
      aiContext: aiContext.value,
      aiMode: aiMode.value,
      deliverables: [...deliverables.value],
      requests: requests.value,
      tokens: tokens.value,
      personal: personal.value,
      leaderboard: !personal.value && board.value,
      publicLeaderboard: !personal.value && board.value && publicBoard.value,
      published: false,
      snapshots: JSON.parse(JSON.stringify(chosen.value)),
      ...(!personal.value && limitRoster.value ? {selectedParticipants:[...selectedStudents.value]} : {}),
      participantIds: personal.value
        ? ["u-student"]
        : state.classes
            .find((c) => c.id === classId.value)!
            .members.map((m) => m.id),
    };
    await api.createExam(exam);
    ElMessage.success("考试已创建，题目版本与规则已冻结");
    router.push("/exams/" + exam.id);
  } catch (e) {
    ElMessage.error((e as Error).message);
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <div class="page-heading">
    <div>
      <h1>{{ personal ? "创建个人模拟" : "组卷与考试发布" }}</h1>
    </div>
    <el-button @click="router.push('/exams')">取消</el-button>
  </div>
  <section class="panel builder-panel">
    <el-steps :active="step" finish-status="success" align-center
      ><el-step title="基本信息" description="范围与时间" /><el-step
        title="选题与 AI 规则"
        description="任务与统一条件" /><el-step
        title="预览与发布"
        description="冻结规则快照"
    /></el-steps>
    <div class="builder-body">
      <template v-if="step === 0"
        ><div class="section-intro">
          <h2>设置{{ personal ? "模拟" : "考试" }}基本信息</h2>
        </div>
        <el-form label-position="top" class="builder-form"
          ><el-form-item label="考试名称 *"
            ><el-input
              v-model="title"
              maxlength="80"
              placeholder="例如：AI Coding · 项目迭代测评" /></el-form-item
          ><el-form-item v-if="!personal" label="目标班级 *"
            ><el-select v-model="classId" placeholder="选择班级"
              ><el-option
                v-for="c in state.classes.filter((c) => !c.archived)"
                :key="c.id"
                :label="c.name"
                :value="c.id" /></el-select></el-form-item
          ><el-form-item v-if="!personal" label="参加考生">
            <el-checkbox v-model="limitRoster">仅指定学生参加</el-checkbox>
            <el-select v-if="limitRoster" v-model="selectedStudents" multiple filterable placeholder="选择班级成员">
              <el-option v-for="member in classroom?.members" :key="member.id" :value="member.id" :label="member.name" />
            </el-select>
          </el-form-item><el-form-item v-if="!personal" label="考试时间（北京时间） *"
            ><el-checkbox v-model="immediate">发布后立即开始</el-checkbox>
            <el-date-picker v-if="immediate" v-model="range[1]" type="datetime" placeholder="截止时间" />
            <el-date-picker v-else
              v-model="range"
              type="datetimerange"
              start-placeholder="开始时间"
              end-placeholder="截止时间"
              format="YYYY-MM-DD HH:mm" /></el-form-item
          ><el-form-item v-else label="模拟时长（分钟）"
            ><el-input-number v-model="duration" :min="1" :max="300" :step="15"
          /></el-form-item> </el-form
      ></template>
      <template v-if="step === 1"
        ><div class="section-intro">
          <h2>选择题目，设定统一规则</h2>
          <p>
            已选择 {{ selection.length }} 道题目 · 总权重
            <b :class="totalWeight === 100 ? 'positive' : 'danger'"
              >{{ totalWeight }}%</b
            >
          </p>
        </div>
        <div class="filter-row">
          <el-select v-model="bank" placeholder="全部可用题库" clearable
            ><el-option
              v-if="!personal"
              label="内置题库"
              value="内置题库" /><el-option
              v-for="b in state.banks"
              :key="b"
              :value="b" /></el-select
          ><el-select v-model="difficulty" placeholder="全部难度" clearable
            ><el-option
              v-for="d in ['简单', '中等', '困难']"
              :key="d"
              :value="d" /></el-select
          ><el-select v-model="taskType" placeholder="任务类型" clearable
            ><el-option v-for="t in taskTypes" :key="t" :value="t" /></el-select
          ><el-select v-model="stack" placeholder="技术栈" clearable
            ><el-option v-for="s in stacks" :key="s" :value="s" /></el-select
          ><el-radio-group v-model="mode"
            ><el-radio-button value="手动选题">手动选题</el-radio-button
            ><el-radio-button value="随机抽题"
              >随机抽题</el-radio-button
            ></el-radio-group
          ><template v-if="mode === '随机抽题'"
            ><el-input-number
              v-model="count"
              :min="1"
              :max="12"
              style="width: 120px"
            /><el-button @click="draw">重新抽题</el-button></template
          >
        </div>
        <div class="selection-table">
          <table>
            <thead>
              <tr>
                <th>选择</th>
                <th>题目 / 版本</th>
                <th>题型</th>
                <th>难度</th>
                <th>题目权重</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in available" :key="p.id">
                <td>
                  <el-checkbox
                    :model-value="selection.includes(p.id)"
                    :aria-label="'选择' + p.title"
                    @change="toggle(p.id)"
                  />
                </td>
                <td>
                  <b>{{ p.title }}</b
                  ><small class="table-sub"
                    >{{ p.stack }} · {{ p.duration }} 分钟</small
                  >
                </td>
                <td>{{ p.type }}</td>
                <td>{{ p.difficulty }}</td>
                <td>
                  <el-input-number
                    v-if="selection.includes(p.id)"
                    v-model="weights[p.id]"
                    :min="1"
                    :max="100"
                    size="small"
                  />
                  <span v-if="selection.includes(p.id)">%</span
                  ><span v-else>—</span>
                </td>
              </tr>
            </tbody>
          </table>
          <el-empty
            v-if="!available.length"
            description="暂无符合条件的已发布私有题目"
            ><el-button @click="router.push('/banks')"
              >前往题库管理创建</el-button
            ></el-empty
          >
        </div>
        <div class="divider" />
        <div class="selection-duration">
          已选项目建议用时：{{ chosen.reduce((n, p) => n + p.duration, 0) }}
          分钟
        </div>
        <h3>统一 AI 条件</h3>
        <div class="form-three-columns">
          <label
            >固定模型<el-select v-model="model"
              ><el-option
                label="course-coder-v1"
                value="course-coder-v1" /></el-select></label
          ><label
            >成功请求上限<el-input-number
              v-model="requests"
              :min="1"
              :max="100" /></label
          ><label
            >累计 Token 上限<el-input-number
              v-model="tokens"
              :min="1000"
              :max="100000"
              :step="1000"
          /></label>
        </div>
        <div class="form-two-columns project-field">
          <label
            >AI 上下文范围<el-select v-model="aiContext"
              ><el-option value="项目文件" /><el-option
                value="当前文件" /></el-select></label
          ><label
            >AI 协作方式<el-select v-model="aiMode"
              ><el-option value="对话与代码建议" /><el-option
                value="仅分析建议" /></el-select
          ></label>
        </div>
        <h3 class="project-field">交付要求</h3>
        <el-checkbox-group v-model="deliverables"
          ><el-checkbox value="项目代码与测试" disabled
            >项目代码与测试</el-checkbox
          ><el-checkbox value="变更说明">变更说明</el-checkbox
          ><el-checkbox value="AI 协作与验证记录"
            >AI 协作与验证记录</el-checkbox
          ></el-checkbox-group
        >
      </template>
      <template v-if="step === 2"
        ><div class="section-intro">
          <h2>确认后，准备开始</h2>
        </div>
        <div class="publish-summary">
          <h2>{{ title }}</h2>
          <p>
            {{
              personal
                ? "个人模拟 · 仅自己可见"
                : state.classes.find((c) => c.id === classId)?.name
            }}
          </p>
          <div v-for="(p, i) in chosen" :key="p.id" class="publish-problem">
            <span>{{ String(i + 1).padStart(2, "0") }}</span
            ><b>{{ p.title }}</b
            ><small>{{ p.version }}</small
            ><strong>{{ weights[p.id] }}%</strong>
          </div>
          <div class="summary-rule">
            <Icon name="sparkles" />{{ model }} · {{ requests }} 次请求 ·
            {{ tokens.toLocaleString() }} token · {{ aiContext }} · {{ aiMode }}
          </div>
          <p>交付物：{{ deliverables.join("、") }}</p>
        </div>
        <template v-if="!personal"
          ><el-form label-position="top"
            ><el-form-item label="成绩发布策略"
              ><el-radio-group v-model="release"
                ><el-radio value="manual"
                  >教师复核后手动发布</el-radio
                ></el-radio-group
              ></el-form-item
            ><el-form-item label="班级排行榜"
              ><el-switch v-model="board" /><span class="muted switch-label"
                >仅在考试结束且成绩发布后开放</span
              ></el-form-item>
              <el-form-item v-if="board"><el-checkbox v-model="publicBoard">平台公开匿名榜</el-checkbox>
                <span class="muted switch-label">允许平台用户查看匿名排名和分数</span>
              </el-form-item></el-form
          ></template
        >
      </template>
    </div>
    <div class="builder-footer">
      <el-button :disabled="step === 0" @click="step--">上一步</el-button
      ><span class="muted tiny">{{ step + 1 }} / 3</span
      ><el-button v-if="step < 2" type="primary" @click="next"
        >下一步 <Icon name="arrow" :size="16" /></el-button
      ><el-button v-else type="primary" :loading="busy" @click="publish">{{
        personal ? "创建模拟考试" : "确认发布考试"
      }}</el-button>
    </div>
  </section>
</template>
