<script setup lang="ts">
import { ref, computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { state } from "../store";
import { formatTime } from "../domain";
import { isMock } from "../services/api";
import Icon from "../components/Icon.vue";
const route = useRoute(),
  router = useRouter(),
  agreed = ref(false);
const exam = computed(() => state.exams.find((e) => e.id === route.params.id));
const inWindow = computed(
  () =>
    exam.value &&
    ((exam.value.id === "exam-1" && isMock) ||
      (Date.now() >= Date.parse(exam.value.start) &&
        Date.now() < Date.parse(exam.value.end))),
);
const ready = computed(
  () => agreed.value && inWindow.value && !exam.value?.receipt,
);
</script>
<template>
  <el-empty v-if="!exam" description="考试不存在或无权访问" /><template v-else
    ><button class="text-link back-link" @click="router.push('/exams')">
      <Icon name="back" :size="16" />返回考试中心
    </button>
    <div class="page-heading">
      <div>
        <h1>{{ exam.title }}</h1>
      </div>
      <span class="tag" :class="exam.status === '进行中' ? 'green' : 'blue'">{{
        exam.receipt ? "已交卷" : exam.status
      }}</span>
    </div>
    <div class="exam-detail-grid">
      <div>
        <section class="panel briefing-panel">
          <div class="briefing-stats">
            <div>
              <span>题目数量</span
              ><b>{{ exam.problemIds.length }} <small>道</small></b>
            </div>
            <div>
              <span>考试时长</span
              ><b
                >{{
                  Math.round(
                    (Date.parse(exam.end) - Date.parse(exam.start)) / 60000,
                  )
                }}
                <small>分钟</small></b
              >
            </div>
            <div>
              <span>工程任务</span
              ><b class="language-label">{{
                [...new Set((exam.snapshots || []).map((p) => p.type))].join(
                  " / ",
                )
              }}</b>
            </div>
          </div>
          <div class="exam-time-row">
            <Icon name="calendar" />{{ formatTime(exam.start) }} —
            {{ formatTime(exam.end) }}<span class="tag gray">固定截止时间</span>
          </div>
        </section>
        <section class="panel form-panel">
          <h2>考试规则与注意事项</h2>
          <div class="rule-list">
            <div
              v-for="(r, i) in [
                [
                  '统一的 AI 辅助条件',
                  `本场使用 ${exam.model}，每人最多 ${exam.requests} 次成功请求、累计 ${exam.tokens} token，任一额度用尽将暂停 AI。`,
                ],
                [
                  '草稿保存与断线恢复',
                  '整个项目自动保存。离开前可导出项目，交卷后代码、测试和验证记录一并冻结。',
                ],
                [
                  '截止与最终答卷',
                  '窗口内可迟到进入，截止时间不顺延。交卷后不可修改；最终答卷采用每题最后确认的快照，未作答题记零。',
                ],
                [
                  '评分与成绩复核',
                  '评分由客观测试与六维评价构成。模型不可用时保持待评。公布后 48 小时内可申请复核。',
                ],
                [
                  'AI 协作与交付',
                  `上下文：${exam.aiContext}；协作方式：${exam.aiMode}。交付：${exam.deliverables.join('、')}。`,
                ],
              ]"
              :key="i"
            >
              <span>{{ String(i + 1).padStart(2, "0") }}</span>
              <div>
                <h3>{{ r[0] }}</h3>
                <p>{{ r[1] }}</p>
              </div>
            </div>
          </div>
        </section>
      </div>
      <aside>
        <section class="panel form-panel">
          <h2>考前确认</h2>
          <div class="environment-check">
            <div><Icon name="success" />浏览器已就绪</div>
            <div><Icon name="success" />项目编辑器已就绪</div>
          </div>

          <template v-if="exam.receipt"
            ><div class="success-box">
              <Icon name="success" />
              <h3>已成功交卷</h3>
              <code>{{ exam.receipt }}</code>
              <p>同一场次只生成一份最终答卷。</p>
            </div>
            <el-button
              class="full-width"
              @click="
                router.push(
                  '/workspace/' + exam.problemIds[0] + '?exam=' + exam.id,
                )
              "
              >查看只读工作台</el-button
            ></template
          ><template v-else
            ><el-checkbox v-model="agreed" class="rules-checkbox"
              >我已阅读并理解上述考试规则</el-checkbox
            ><el-button
              type="primary"
              class="full-width"
              :disabled="!ready"
              @click="
                router.push(
                  '/workspace/' + exam.problemIds[0] + '?exam=' + exam.id,
                )
              "
              ><Icon name="arrow" :size="16" />进入考试</el-button
            >
            <p v-if="!inWindow" class="muted">当前不在考试时段</p></template
          >
        </section>
        <section class="panel form-panel compact-panel">
          <h3>本场题目</h3>
          <div
            v-for="(id, i) in exam.problemIds"
            :key="id"
            class="exam-problem-row"
          >
            <span>{{ String(i + 1).padStart(2, "0") }}</span
            ><b>{{
              (
                exam.snapshots?.find((p) => p.id === id) ||
                state.problems.find((p) => p.id === id)
              )?.title
            }}</b
            ><small>{{ exam.weights[i] }}%</small>
          </div>
        </section>
      </aside>
    </div></template
  >
</template>
