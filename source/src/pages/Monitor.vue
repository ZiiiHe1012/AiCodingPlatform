<script setup lang="ts">
import { ref, computed } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { audit, state } from "../store";
import { formatTime } from "../domain";
import Icon from "../components/Icon.vue";
const tasks = ref(
  JSON.parse(localStorage.getItem("codelab-tasks") || "null") || [
    {
      id: "JOB-1092",
      stage: "TESTING",
      wait: 22,
      status: "运行中",
      reason: "—",
      retries: 0,
      type: "normal",
    },
    {
      id: "JOB-1093",
      stage: "AI_SCORING",
      wait: 75,
      status: "排队中",
      reason: "模型配额繁忙",
      retries: 0,
      type: "normal",
    },
    {
      id: "JOB-1094",
      stage: "TESTING",
      wait: 186,
      status: "SYSTEM_FAILED",
      reason: "执行进程心跳丢失",
      retries: 0,
      type: "system",
    },
    {
      id: "JOB-1095",
      stage: "AI_SCORING",
      wait: 192,
      status: "SYSTEM_FAILED",
      reason: "模型响应格式不合格",
      retries: 2,
      type: "system",
    },
    {
      id: "JOB-1096",
      stage: "TESTING",
      wait: 8,
      status: "运行错误",
      reason: "用户代码：IndexError",
      retries: 0,
      type: "code",
    },
  ],
);
const updated = ref(new Date().toISOString()),
  tab = ref("全部任务");
const filtered = computed(() =>
  tasks.value.filter(
    (t: any) => tab.value === "全部任务" || t.stage === tab.value,
  ),
);
async function retry(t: any) {
  try {
    const { value } = await ElMessageBox.prompt(
      t.retries >= 2
        ? "已达到重试上限，请填写转人工处理说明"
        : "重试沿用原题目、模型与量规版本，请填写原因",
      "处理失败任务",
      { inputValidator: (v) => !!v.trim() || "必须填写原因" },
    );
    if (t.retries >= 2) t.status = "PENDING_REVIEW";
    else {
      t.retries++;
      t.status = "排队中";
      t.wait = 0;
    }
    audit(
      t.status === "PENDING_REVIEW" ? "任务转人工" : "重试测评任务",
      `${t.id}：${value}`,
    );
    localStorage.setItem("codelab-tasks", JSON.stringify(tasks.value));
    updated.value = new Date().toISOString();
    ElMessage.success("任务已更新");
  } catch {}
}
</script>
<template>
  <div class="page-heading">
    <div>
      <h1>队列与测评服务</h1>
    </div>
    <el-button
      @click="
        updated = new Date().toISOString();
        ElMessage.success('已刷新');
      "
      ><Icon name="refresh" :size="16" />刷新快照</el-button
    >
  </div>
  <div class="monitor-notice">
    <Icon name="warning" /><span>2 个任务等待超过 180 秒</span
    ><span class="tag orange">队列告警</span>
  </div>
  <div class="stats-grid">
    <div
      v-for="s in [
        { label: '测试队列', value: 8, unit: '个任务', icon: 'terminal' },
        { label: 'AI 评分队列', value: 12, unit: '个任务', icon: 'sparkles' },
        { label: '执行槽位', value: '6 / 8', unit: '已使用', icon: 'activity' },
        {
          label: '系统失败',
          value: tasks.filter((t: any) => t.status === 'SYSTEM_FAILED').length,
          unit: '待处理',
          icon: 'warning',
        },
      ]"
      :key="s.label"
      class="stat-card"
    >
      <div class="stat-top">
        <span>{{ s.label }}</span
        ><span class="icon-tile"><Icon :name="s.icon" /></span>
      </div>
      <div class="stat-number">
        {{ s.value }} <small>{{ s.unit }}</small>
      </div>
    </div>
  </div>
  <div class="monitor-service-grid">
    <section class="panel form-panel">
      <div class="panel-heading no-padding">
        <h2>执行资源</h2>
        <span class="tag green">在线</span>
      </div>
      <div class="resource-bar"><span>CPU 使用率</span><b>62%</b></div>
      <el-progress :percentage="62" :show-text="false" :stroke-width="7" />
      <div class="resource-bar"><span>内存使用率</span><b>48%</b></div>
      <el-progress :percentage="48" :show-text="false" :stroke-width="7" />
    </section>
    <section class="panel form-panel">
      <div class="panel-heading no-padding">
        <h2>模型服务</h2>
        <span class="tag orange">繁忙</span>
      </div>
      <div class="model-meta">
        <b>course-coder-v1</b><span>固定模型 · 禁止静默切换</span>
      </div>
      <div class="resource-bar"><span>共享预算使用</span><b>68%</b></div>
      <el-progress
        :percentage="68"
        :show-text="false"
        :stroke-width="7"
        color="#d69b43"
      />
    </section>
  </div>
  <section class="panel">
    <div class="panel-heading">
      <h2>任务队列</h2>
      <el-radio-group v-model="tab" size="small"
        ><el-radio-button value="全部任务" /><el-radio-button value="TESTING"
          >代码测试</el-radio-button
        ><el-radio-button value="AI_SCORING"
          >AI 评分</el-radio-button
        ></el-radio-group
      >
    </div>
    <div class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>任务编号</th>
            <th>阶段</th>
            <th>耗时 / 等待</th>
            <th>状态</th>
            <th>异常原因</th>
            <th>重试次数</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="t in filtered" :key="t.id">
            <td class="mono">{{ t.id }}</td>
            <td>
              <span class="tag gray">{{ t.stage }}</span>
            </td>
            <td
              :class="
                t.wait > 180 ? 'danger' : t.wait > 60 ? 'warning-text' : ''
              "
            >
              {{ t.wait }} 秒{{
                t.wait > 180 ? " · 告警" : t.wait > 60 ? " · 繁忙" : ""
              }}
            </td>
            <td>{{ t.status }}</td>
            <td>{{ t.reason }}</td>
            <td>{{ t.retries }} / 2</td>
            <td>
              <button
                v-if="t.status === 'SYSTEM_FAILED'"
                class="text-link"
                @click="retry(t)"
              >
                {{ t.retries >= 2 ? "转人工" : "重试" }}</button
              ><span v-else class="muted tiny">{{
                t.type === "code" ? "代码错误不重试" : "—"
              }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="table-footer">
      <span>更新于 {{ formatTime(updated) }}</span>
    </div>
  </section>
  <section
    v-if="state.audits.some((a) => /任务/.test(a.action))"
    class="panel form-panel"
  >
    <h2>处理审计</h2>
    <div
      v-for="a in state.audits.filter((a) => /任务/.test(a.action))"
      :key="a.id"
      class="audit-line"
    >
      <span>{{ formatTime(a.time) }}</span
      ><b>{{ a.action }}</b
      ><span>{{ a.reason }}</span>
    </div>
  </section>
</template>
