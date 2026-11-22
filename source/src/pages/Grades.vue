<script setup lang="ts">
import { ref, computed } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { state, audit } from "../store";
import { weightedScore, dimensionNames, csvExport, download } from "../domain";
import Icon from "../components/Icon.vue";
import { gradeRows } from "../services/gradeStore";
const examId = ref("exam-3"),
  filter = ref("全部状态"),
  dialog = ref(false),
  reason = ref(""),
  scores = ref([90, 80, 80, 70, 60, 80]),
  selectedId = ref("");
const rows = ref(gradeRows);
const allRows = computed(() => rows.value[examId.value] || []);
const shown = computed(() =>
  allRows.value.filter(
    (s) => filter.value === "全部状态" || s.status === filter.value,
  ),
);
const graded = computed(() =>
  allRows.value.filter((s) => s.status === "已评分" && s.scores),
);
const average = computed(() =>
  graded.value.length
    ? (
        graded.value.reduce((a, s) => a + weightedScore(s.scores!), 0) /
        graded.value.length
      ).toFixed(2)
    : "—",
);
const exam = computed(() => state.exams.find((e) => e.id === examId.value));
const unresolved = computed(() =>
  allRows.value.some((s) => ["待评分", "待复核"].includes(s.status)),
);
function edit(id: string) {
  selectedId.value = id;
  const row = allRows.value.find((r) => r.id === id)!;
  scores.value = [...(row.scores || [0, 0, 0, 0, 0, 0])];
  reason.value = "";
  dialog.value = true;
}
function confirm() {
  if (!reason.value.trim()) return ElMessage.warning("调分必须填写理由");
  try {
    weightedScore(scores.value);
  } catch (e) {
    return ElMessage.warning((e as Error).message);
  }
  const row = allRows.value.find((r) => r.id === selectedId.value)!;
  audit(
    "人工复核调整",
    `${row.name} 原分 ${row.scores ? weightedScore(row.scores).toFixed(2) : "待评"} → ${weightedScore(scores.value).toFixed(2)}；${reason.value}`,
  );
  const s = state.submissions.find(
    (s) => s.userId === row.id && s.examId === examId.value,
  );
  if (s) {
    s.adjustment = {
      oldScores: [...(s.scores || [0, 0, 0, 0, 0, 0])],
      reason: reason.value,
      operator: "陈老师",
      time: new Date().toISOString(),
    };
    s.scores = [...scores.value];
    s.version++;
    s.status = "COMPLETED";
  }
  row.scores = [...scores.value];
  row.status = "已评分";
  localStorage.setItem("codelab-grades", JSON.stringify(rows.value));
  dialog.value = false;
  ElMessage.success("复核已保存，原始分数与理由已保留在审计中");
}
async function publish() {
  if (!allRows.value.length || unresolved.value)
    return ElMessage.warning("请先完成全部评分和复核");
  try {
    await ElMessageBox.confirm(
      "成绩将对本场考生开放，已启用的班级榜单将同步更新。",
      "确认发布成绩",
    );
    exam.value!.published = true;
    exam.value!.publishedAt = new Date().toISOString();
    exam.value!.status = "成绩已发布";
    audit("发布考试成绩", exam.value!.title);
    ElMessage.success("成绩已发布");
  } catch {}
}
function exportCSV() {
  const data = [
    ["考试", "用户编号", "昵称", ...dimensionNames, "总分", "状态"],
    ...allRows.value.map((r) => [
      exam.value?.title,
      r.id,
      r.name,
      ...(r.scores || Array(6).fill("")),
      r.scores ? weightedScore(r.scores).toFixed(2) : "",
      r.status,
    ]),
  ];
  download("班级成绩.csv", csvExport(data), "text/csv;charset=utf-8");
  audit("导出班级成绩", exam.value?.title || "");
}
</script>
<template>
  <div class="page-heading">
    <div>
      <h1>班级成绩与复核</h1>
    </div>
    <div class="button-row">
      <el-button @click="exportCSV"
        ><Icon name="download" :size="16" />导出 CSV</el-button
      ><el-button
        type="primary"
        :disabled="!allRows.length || unresolved"
        @click="publish"
        >{{ exam?.published ? "重新发布成绩" : "发布成绩" }}</el-button
      >
    </div>
  </div>
  <section class="panel filter-panel">
    <div class="filter-row">
      <el-select v-model="examId" style="width: 350px"
        ><el-option
          v-for="e in state.exams.filter((e) => !e.personal)"
          :key="e.id"
          :label="e.title"
          :value="e.id" /></el-select
      ><span class="tag blue">{{
        exam?.published ? "成绩已发布" : "成绩未发布"
      }}</span>
    </div>
  </section>
  <div class="stats-grid">
    <div
      v-for="s in [
        { title: '已交卷', value: allRows.length, icon: 'file' },
        {
          title: '待评分',
          value: allRows.filter((r) => r.status === '待评分').length,
          icon: 'clock',
        },
        {
          title: '待复核',
          value: allRows.filter((r) => r.status === '待复核').length,
          icon: 'list',
        },
        { title: '已评分平均分', value: average, icon: 'chart' },
      ]"
      :key="s.title"
      class="stat-card"
    >
      <div class="stat-top">
        <span>{{ s.title }}</span
        ><Icon :name="s.icon" />
      </div>
      <div class="stat-number">{{ s.value }}</div>
    </div>
  </div>
  <section class="panel">
    <div class="panel-heading">
      <h2>学生成绩</h2>
      <el-select v-model="filter" style="width: 160px"
        ><el-option
          v-for="s in ['全部状态', '已评分', '待评分', '待复核']"
          :key="s"
          :value="s"
      /></el-select>
    </div>
    <div class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>学生</th>
            <th>用户编号</th>
            <th>需求达成</th>
            <th>综合得分</th>
            <th>成绩状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in shown" :key="r.id">
            <td>
              <span class="person-cell"
                ><span class="avatar small">{{ r.name[0] }}</span
                >{{ r.name }}</span
              >
            </td>
            <td class="mono">{{ r.id }}</td>
            <td>{{ r.scores?.[0] ?? "—" }}</td>
            <td>
              <b class="score-text">{{
                r.scores ? weightedScore(r.scores).toFixed(2) : "—"
              }}</b>
            </td>
            <td>
              <span
                class="tag"
                :class="
                  r.status === '已评分'
                    ? 'green'
                    : r.status === '待评分'
                      ? 'gray'
                      : 'orange'
                "
                >{{ r.status }}</span
              >
            </td>
            <td>
              <button class="text-link" @click="edit(r.id)">
                {{ r.status === "待评分" ? "人工处理" : "查看与复核" }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <el-empty v-if="!shown.length" description="暂无符合条件的成绩" />
    </div>
  </section>
  <el-dialog v-model="dialog" title="评分复核与调整" width="630px">
    <div class="grade-adjustments">
      <label v-for="(d, i) in dimensionNames" :key="d"
        >{{ d }}<el-input-number v-model="scores[i]" :min="0" :max="100"
      /></label>
    </div>
    <p>
      调整后综合得分：<b>{{ weightedScore(scores).toFixed(2) }}</b>
    </p>
    <el-input
      v-model="reason"
      type="textarea"
      :rows="3"
      placeholder="填写调整理由、对应代码或测试证据（必填）"
    /><template #footer
      ><el-button @click="dialog = false">取消</el-button
      ><el-button type="primary" @click="confirm"
        >保存复核记录</el-button
      ></template
    ></el-dialog
  >
</template>
