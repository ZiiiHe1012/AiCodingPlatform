<script setup lang="ts">
import { ref, computed } from "vue";
import { state } from "../store";
import { rankEntries, weightedScore } from "../domain";
import Icon from "../components/Icon.vue";
import { gradeRows } from "../services/gradeStore";
const examId = ref("exam-3"),
  mine = ref(false);
const exam = computed(() => state.exams.find((e) => e.id === examId.value));
const entries = computed(() =>
  rankEntries(
    (gradeRows[examId.value] || [])
      .filter((r) => r.status === "已评分" && r.scores)
      .map((r) => ({
        id: r.id,
        name: r.name,
        score: weightedScore(r.scores!),
        functional: r.scores![0],
      })),
  ),
);
const pending = computed(() =>
  (gradeRows[examId.value] || []).filter((r) =>
    ["待评分", "待复核"].includes(r.status),
  ),
);
const visible = computed(
  () =>
    exam.value?.published && exam.value?.leaderboard && !exam.value?.personal,
);
</script>
<template>
  <div class="page-heading">
    <div>
      <h1>排行榜</h1>
    </div>
    <el-select v-model="examId" style="width: 300px"
      ><el-option
        v-for="e in state.exams.filter((e) => !e.personal)"
        :key="e.id"
        :label="e.title"
        :value="e.id"
    /></el-select>
  </div>
  <section class="leaderboard-banner">
    <div>
      <span class="tag">CLASS LEADERBOARD</span>
      <h2>{{ exam?.title }}</h2>
      <p>{{ exam?.className }}</p>
    </div>
    <Icon name="trophy" :size="80" />
  </section>
  <template v-if="visible"
    ><div class="podium">
      <section
        v-for="(p, i) in entries.slice(0, 3)"
        :key="p.id"
        class="panel podium-card"
        :class="{ 'first-place': i === 0 }"
      >
        <span class="podium-rank">{{ String(p.rank).padStart(2, "0") }}</span
        ><span class="avatar podium-avatar">{{ p.name[0] }}</span>
        <h3>{{ p.name }}</h3>
        <b>{{ p.score.toFixed(2) }}<small>分</small></b>
        <p>需求达成 {{ p.functional }} / 100</p>
      </section>
    </div>
    <section class="panel">
      <div class="panel-heading">
        <div>
          <h2>
            班级排行榜 <span class="count-badge">{{ entries.length }}</span>
          </h2>
          <p>更新于 2026-10-31 14:00（北京时间）</p>
        </div>
        <el-button @click="mine = !mine"
          ><Icon name="users" :size="15" />{{
            mine ? "显示全部" : "定位我的排名"
          }}</el-button
        >
      </div>
      <table>
        <thead>
          <tr>
            <th>名次</th>
            <th>参赛者</th>
            <th>总分</th>
            <th>需求达成</th>
            <th>状态</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="r in entries.filter((e) => !mine || e.id === 'u-student')"
            :key="r.id"
            :class="{ 'my-rank': r.id === 'u-student' }"
          >
            <td>
              <span class="rank-number" :class="{ 'top-rank': r.rank < 4 }">{{
                String(r.rank).padStart(2, "0")
              }}</span>
            </td>
            <td>
              <span class="person-cell"
                ><span class="avatar small">{{ r.name[0] }}</span
                >{{ r.name
                }}<span v-if="r.id === 'u-student'" class="tag blue"
                  >我</span
                ></span
              >
            </td>
            <td class="score-text">{{ r.score.toFixed(2) }}</td>
            <td>{{ r.functional.toFixed(2) }}</td>
            <td>
              <span class="status-label positive"
                ><Icon name="success" :size="14" />有效最终成绩</span
              >
            </td>
          </tr>
        </tbody>
      </table>
      <div class="table-footer">
        按总分、需求达成降序排序；完全同分并列，例如
        1、2、2、4。排队或模型响应时间不作为惩罚。
      </div>
    </section>
    <section class="panel waiting-rank">
      <Icon name="clock" />
      <div>
        <h3>待评记录单列</h3>
        <p>
          {{ pending.length }}
          份记录等待评分或复核，完成并满足公布条件后才会计入有效名次。
        </p>
      </div>
      <span class="tag orange">{{ pending.length }} 人待处理</span>
    </section></template
  ><el-empty
    v-else
    description="本场榜单尚未开放，须考试结束、成绩公布且启用榜单"
  />
</template>
