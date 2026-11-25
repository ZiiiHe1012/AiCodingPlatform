<script setup lang="ts">
import { ref, computed } from "vue";
import { useRouter } from "vue-router";
import { state } from "../store";
import { formatTime } from "../domain";
import Icon from "../components/Icon.vue";
const router = useRouter(),
  filter = ref("全部考试");
const exams = computed(() =>
  state.exams.filter(
    (e) =>
      filter.value === "全部考试" ||
      (filter.value === "个人模拟"
        ? e.personal
        : filter.value === "待参加"
          ? ["进行中", "已发布"].includes(e.status) && !e.receipt
          : !!e.receipt || ["成绩已发布", "已结束"].includes(e.status)),
  ),
);
</script>
<template>
  <div class="page-heading">
    <div>
      <h1>考试中心</h1>
    </div>
    <el-button
      v-if="state.role !== 'student'"
      type="primary"
      @click="router.push('/exams/new')"
      ><Icon name="plus" :size="16" />创建班级考试</el-button
    ><el-button v-else @click="router.push('/mock')"
      ><Icon name="plus" :size="16" />创建个人模拟</el-button
    >
  </div>
  <div class="tab-row">
    <button
      v-for="t in ['全部考试', '待参加', '已结束', '个人模拟']"
      :key="t"
      :class="{ active: filter === t }"
      @click="filter = t"
    >
      {{ t }}
    </button>
  </div>
  <div class="exam-grid">
    <section v-for="exam in exams" :key="exam.id" class="panel exam-card">
      <div class="exam-card-top">
        <span class="exam-icon"
          ><Icon
            :name="exam.personal ? 'code' : 'graduation'"
            :size="25" /></span
        ><span
          class="tag"
          :class="
            exam.receipt ? 'gray' : exam.status === '进行中' ? 'green' : 'blue'
          "
          >{{ exam.receipt ? "已交卷" : exam.status }}</span
        >
      </div>

      <h2>{{ exam.title }}</h2>
      <p>{{ exam.className }}</p>
      <div class="exam-info">
        <span
          ><Icon name="calendar" :size="15" />{{ formatTime(exam.start) }} —
          {{ formatTime(exam.end) }}</span
        ><span
          ><Icon name="file" :size="15" />{{ exam.problemCount ?? exam.problemIds.length }} 道题目
          <i /> AI Coding</span
        ><span
          ><Icon name="sparkles" :size="15" />{{ exam.model }} ·
          {{ exam.requests }} 次 /
          {{ exam.tokens.toLocaleString() }} token</span
        >
      </div>
      <div class="exam-card-footer">
        <span
          ><Icon :name="exam.personal ? 'lock' : 'users'" :size="14" />{{
            exam.personal ? "仅自己可见" : "班级考试"
          }}
          · 北京时间</span
        ><el-button
          :type="
            exam.status === '进行中' && !exam.receipt ? 'primary' : 'default'
          "
          @click="router.push('/exams/' + exam.id)"
          >{{ exam.receipt ? "查看回执" : "查看详情" }}
          <Icon name="arrow" :size="14"
        /></el-button>
      </div>
    </section>
  </div>
  <el-empty v-if="!exams.length" description="暂无符合条件的考试" />
</template>
