<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { downloadProject } from "../project";
import Icon from "../components/Icon.vue";
import { state, userId } from "../store";
import {
  dimensionNames,
  defaultWeights,
  weightedScore,
  formatTime,
  download,
} from "../domain";
import { api, isMock } from "../services/api";
const route = useRoute(),
  router = useRouter();
const selected = computed(
  () =>
    state.submissions.find((s) => s.id === route.params.id) ||
    (!route.params.id
      ? state.submissions.find((s) => s.userId === userId())
      : undefined),
);
const problem = computed(
  () =>
    selected.value?.problemSnapshot ||
    state.problems.find((p) => p.id === selected.value?.problemId),
);
const exam = computed(() =>
  state.exams.find((e) => e.id === selected.value?.examId),
);
const allowed = computed(
  () =>
    selected.value &&
    (selected.value.userId === userId() || state.role !== "student"),
);
const released = computed(
  () => !exam.value || exam.value.published || state.role !== "student",
);
const score = computed(() =>
  selected.value?.scores
    ? weightedScore(
        selected.value.scores,
        problem.value?.weights || defaultWeights,
      ).toFixed(2)
    : "—",
);
const reviewDialog = ref(false),
  reason = ref(""),
  busy = ref(false);
let poll: ReturnType<typeof setInterval>;
const reviewExpired = computed(
  () =>
    !!selected.value &&
    Date.now() - Date.parse(selected.value.createdAt) > 48 * 3600000,
);
const statusNames: Record<string, string> = {
  ACCEPTED: "已接收",
  QUEUED: "排队中",
  TESTING: "客观测试中",
  AI_SCORING: "AI 评分中",
  PENDING_REVIEW: "等待人工复核",
  COMPLETED: "评分完成",
  SYSTEM_FAILED: "系统故障 · 不记零分",
};
const vertices = (scale: number) =>
  Array.from({ length: 6 }, (_, i) => {
    const a = (i * Math.PI) / 3 - Math.PI / 2;
    return `${150 + Math.cos(a) * scale},${135 + Math.sin(a) * scale}`;
  }).join(" ");
const radar = computed(() =>
  selected.value?.scores
    ?.map((s, i) => {
      const a = (i * Math.PI) / 3 - Math.PI / 2;
      return `${150 + Math.cos(a) * s * 0.88},${135 + Math.sin(a) * s * 0.88}`;
    })
    .join(" "),
);
async function refresh() {
  if (!selected.value) return;
  if (
    isMock &&
    ["QUEUED", "TESTING", "AI_SCORING"].includes(selected.value.status)
  ) {
    const age = Date.now() - Date.parse(selected.value.createdAt);
    selected.value.status =
      age > 7000
        ? "COMPLETED"
        : age > 3500
          ? "AI_SCORING"
          : age > 1500
            ? "TESTING"
            : "QUEUED";
    if (selected.value.status === "COMPLETED")
      selected.value.scores = [90, 80, 80, 70, 60, 80];
  } else if (!isMock) {
    try {
      const updated = await api.submission(selected.value.id);
      Object.assign(selected.value, updated);
    } catch (e) {
      ElMessage.error((e as Error).message);
      clearInterval(poll);
    }
  }
}
async function review() {
  if (!reason.value.trim())
    return ElMessage.warning("请填写复核理由和对应维度");
  busy.value = true;
  try {
    await api.review(selected.value!.id, reason.value.trim());
    reviewDialog.value = false;
    ElMessage.success("复核申请已记录，处理目标为 2 个工作日");
  } catch (e) {
    ElMessage.error((e as Error).message);
  } finally {
    busy.value = false;
  }
}
onMounted(() => {
  refresh();
  poll = setInterval(refresh, 1500);
});
onBeforeUnmount(() => clearInterval(poll));
</script>
<template>
  <div class="page-heading">
    <div>
      <h1>成绩与学习报告</h1>
    </div>
    <el-button @click="router.push('/problems')"
      ><Icon name="book" :size="16" />继续练习</el-button
    >
  </div>
  <div class="report-layout">
    <aside class="panel report-history">
      <div class="panel-heading">
        <h2>提交记录</h2>
        <span class="count-badge">{{
          state.submissions.filter(
            (s) => s.userId === userId() || state.role !== "student",
          ).length
        }}</span>
      </div>
      <button
        v-for="s in state.submissions.filter(
          (s) => s.userId === userId() || state.role !== 'student',
        )"
        :key="s.id"
        class="history-row"
        :class="{ active: s.id === selected?.id }"
        @click="router.push('/reports/' + s.id)"
      >
        <b>{{
          (
            s.problemSnapshot ||
            state.problems.find((p) => p.id === s.problemId)
          )?.title
        }}</b
        ><span>{{ formatTime(s.createdAt) }}</span
        ><span
          class="tag"
          :class="s.status === 'COMPLETED' ? 'green' : 'orange'"
          >{{ statusNames[s.status] }}</span
        >
      </button>
    </aside>
    <div v-if="selected && allowed" class="report-content">
      <section class="panel report-overview">
        <div>
          <code class="submission-id">{{ selected.id }}</code>
          <h2>{{ problem?.title }}</h2>
          <div class="inline-tags">
            <span class="tag green">{{ statusNames[selected.status] }}</span
            ><span class="tag gray">成绩 v{{ selected.version }}</span
            ><span class="muted tiny"
              >{{ formatTime(selected.createdAt) }} · 北京时间</span
            >
          </div>
        </div>
        <div class="report-score">
          <b>{{ released ? score : "—" }}</b
          ><span>{{ released ? "综合得分 / 100" : "成绩尚未发布" }}</span>
        </div>
      </section>
      <template v-if="selected.scores && released"
        ><div class="report-score-grid">
          <section class="panel radar-panel">
            <div class="panel-heading">
              <h2>六维能力画像</h2>
            </div>
            <svg
              viewBox="0 0 300 285"
              class="radar"
              role="img"
              aria-label="六维评分雷达图"
            >
              <polygon
                v-for="scale in [22, 44, 66, 88]"
                :key="scale"
                :points="vertices(scale)"
                fill="none"
                stroke="#e2e8f0"
              />
              <line
                v-for="(_, i) in dimensionNames"
                :key="i"
                x1="150"
                y1="135"
                :x2="150 + Math.cos((i * Math.PI) / 3 - Math.PI / 2) * 88"
                :y2="135 + Math.sin((i * Math.PI) / 3 - Math.PI / 2) * 88"
                stroke="#e2e8f0"
              />
              <polygon
                :points="radar"
                fill="#3b82f6"
                fill-opacity=".15"
                stroke="#3977df"
                stroke-width="2"
              />
              <text x="150" y="25" text-anchor="middle">需求达成</text>
              <text x="248" y="85" text-anchor="middle">健壮性</text>
              <text x="248" y="192" text-anchor="middle">代码质量</text>
              <text x="150" y="252" text-anchor="middle">工程设计</text>
              <text x="50" y="192" text-anchor="middle">验证与测试</text>
              <text x="50" y="85" text-anchor="middle">AI 协作</text>
            </svg>
          </section>
          <section class="panel dimension-panel">
            <div class="panel-heading">
              <h2>得分明细</h2>
            </div>
            <div
              v-for="(d, i) in dimensionNames"
              :key="d"
              class="dimension-item"
            >
              <div>
                <span
                  ><small>D{{ i + 1 }}</small> {{ d }}</span
                ><b
                  >{{ selected.scores[i] }}
                  <small
                    >/ 100 ·
                    {{ problem?.weights[i] || defaultWeights[i] }}%</small
                  ></b
                >
              </div>
              <el-progress
                :percentage="selected.scores[i]"
                :show-text="false"
                :stroke-width="5"
                :color="i < 2 ? '#3a79e0' : '#8ba7d7'"
              />
            </div>
            <div class="dimension-note">
              <span class="legend-dot" />客观测试 D1–D2
              <span class="legend-dot light" /> AI 建议 D3–D6
            </div>
          </section>
        </div>
        <section class="panel evidence-panel">
          <div class="panel-heading">
            <h2>评分依据与改进建议</h2>
            <span class="tag gray">rubric-v1.0</span>
          </div>
          <div class="evidence-item">
            <span class="evidence-icon"><Icon name="success" /></span>
            <div>
              <h3>需求达成 · 验收测试</h3>
              <p>
                {{ problem?.acceptance[0]?.scenario }}：{{
                  problem?.acceptance[0]?.expected
                }}
              </p>

              <span class="tag blue">测试结果证据</span>
            </div>
            <b>{{ selected.scores[0] }}</b>
          </div>
          <div class="evidence-item">
            <span class="evidence-icon"><Icon name="shield" /></span>
            <div>
              <h3>健壮性与安全 · 回归测试</h3>
              <p>
                {{ problem?.acceptance[1]?.scenario }}：{{
                  problem?.acceptance[1]?.expected
                }}
              </p>

              <span class="tag blue">边界测试摘要</span>
            </div>
            <b>{{ selected.scores[1] }}</b>
          </div>
          <div
            v-for="(d, i) in dimensionNames.slice(2)"
            :key="d"
            class="evidence-item"
          >
            <span class="evidence-icon gray-icon"
              ><Icon name="sparkles"
            /></span>
            <div>
              <h3>{{ d }} · AI 建议</h3>
              <p>
                {{
                  [
                    "将业务规则与界面或存储分开，检查接口兼容性和副作用。",
                    "说明模块边界、状态一致性与失败处理的设计取舍。",
                    "把验收场景转为回归测试，保留故障复现和复测证据。",
                    "记录关键设计选择、AI 建议核验过程和已知限制。",
                  ][i]
                }}
              </p>
              <span class="tag gray">{{
                i === 3 ? "验证说明" : problem?.entryFile
              }}</span>
            </div>
            <b>{{ selected.scores[i + 2] }}</b>
          </div>
        </section>
        <section v-if="selected.adjustment" class="notice">
          <b
            >人工复核已调整 · 原始得分
            {{ weightedScore(selected.adjustment.oldScores).toFixed(2) }}</b
          >
          <p>
            {{ selected.adjustment.reason }} ·
            {{ selected.adjustment.operator }} ·
            {{ formatTime(selected.adjustment.time) }}
          </p>
        </section>
        <section class="panel report-meta">
          <div>
            <h3>成绩版本与复核</h3>
            <p>
              题目 {{ problem?.version }} · 测试 test-v1 · 模型 course-coder-v1
              · 提示模板 scoring-v1
            </p>
            <p class="tiny muted">
              正式成绩公布后 48 小时内可申请复核，每个成绩版本仅能申请一次。
            </p>
          </div>
          <div class="button-row">
            <el-button
              @click="
                downloadProject(
                  selected!.id,
                  selected!.files,
                  selected!.explanation,
                  selected!.aiHistory,
                )
              "
              ><Icon name="download" :size="15" />项目快照</el-button
            ><el-button
              :disabled="!!selected.review || reviewExpired"
              @click="reviewDialog = true"
              >{{
                selected.review
                  ? "已申请复核"
                  : reviewExpired
                    ? "复核期限已结束"
                    : "申请复核"
              }}</el-button
            >
          </div>
        </section></template
      >
      <section v-else class="panel pending-report">
        <Icon
          :name="selected.status === 'SYSTEM_FAILED' ? 'warning' : 'clock'"
          :size="38"
        />
        <h2>
          {{
            !released ? "教师尚未公布本场成绩" : statusNames[selected.status]
          }}
        </h2>

        <div class="pipeline">
          <span
            v-for="s in ['QUEUED', 'TESTING', 'AI_SCORING', 'COMPLETED']"
            :key="s"
            :class="{ current: selected.status === s }"
            >{{ statusNames[s] }}</span
          >
        </div>
      </section>
    </div>
    <el-empty v-else description="暂无可查看的提交报告"
      ><el-button type="primary" @click="router.push('/problems')"
        >开始第一次练习</el-button
      ></el-empty
    >
  </div>
  <el-dialog v-model="reviewDialog" title="申请成绩复核" width="540px"
    ><p class="muted">
      请指出具体维度、证据或疑问。教师处理目标为 2 个工作日。
    </p>
    <el-input
      v-model="reason"
      type="textarea"
      :rows="5"
      maxlength="1000"
      show-word-limit
      placeholder="例如：D5 验证与测试中，已提交的边界测试未被计入…"
    /><template #footer
      ><el-button @click="reviewDialog = false">取消</el-button
      ><el-button type="primary" :loading="busy" @click="review"
        >提交复核申请</el-button
      ></template
    ></el-dialog
  >
</template>
