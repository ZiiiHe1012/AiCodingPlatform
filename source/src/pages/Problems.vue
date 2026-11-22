<script setup lang="ts">
import { ref, computed } from "vue";
import { useRouter, useRoute } from "vue-router";
import { state, userId } from "../store";
import { taskTypes, stacks } from "../data";
import Icon from "../components/Icon.vue";
const route = useRoute(),
  router = useRouter();
const query = ref(String(route.query.q || "")),
  difficulty = ref(""),
  type = ref(""),
  stack = ref(""),
  status = ref(""),
  tag = ref(""),
  page = ref(1);
const completed = computed(
  () =>
    new Set(
      state.submissions
        .filter((s) => s.userId === userId() && s.status === "COMPLETED")
        .map((s) => s.problemId),
    ),
);
const filtered = computed(() =>
  state.problems.filter(
    (p) =>
      p.status === "已发布" &&
      (!query.value ||
        `${p.title}${p.id}${p.tags.join("")}`
          .toLowerCase()
          .includes(query.value.toLowerCase())) &&
      (!difficulty.value || p.difficulty === difficulty.value) &&
      (!type.value || p.type === type.value) &&
      (!stack.value || p.stack === stack.value) &&
      (!tag.value || p.tags.includes(tag.value)) &&
      (!status.value ||
        (status.value === "已完成") === completed.value.has(p.id)),
  ),
);
const tags = computed(() => [
  ...new Set(state.problems.flatMap((p) => p.tags)),
]);
function clear() {
  query.value =
    difficulty.value =
    type.value =
    stack.value =
    status.value =
    tag.value =
      "";
  page.value = 1;
}
</script>
<template>
  <div class="page-heading">
    <div>
      <h1>探索题库</h1>
    </div>
    <el-button @click="router.push('/banks')"
      ><Icon name="folder" :size="16" />管理我的题库</el-button
    >
  </div>
  <div class="problem-type-grid">
    <button
      v-for="(t, i) in taskTypes"
      :key="t"
      :class="{ active: type === t }"
      @click="type = type === t ? '' : t"
    >
      <span class="icon-tile"
        ><Icon :name="['code', 'settings', 'list', 'shield'][i]" :size="21"
      /></span>
      <div>
        <b>{{ t }}</b
        ><small
          >{{ state.problems.filter((p) => p.type === t).length }} 道题目</small
        >
      </div>
      <Icon name="diagonal" :size="16" />
    </button>
  </div>
  <section class="panel filter-panel">
    <div class="filter-row">
      <el-input
        v-model="query"
        placeholder="搜索题号、题目或关键词"
        clearable
        class="search-input"
        ><template #prefix
          ><Icon name="search" :size="16" /></template></el-input
      ><el-select
        v-model="difficulty"
        placeholder="全部难度"
        clearable
        aria-label="题目难度"
        ><el-option
          v-for="d in ['简单', '中等', '困难']"
          :key="d"
          :value="d" /></el-select
      ><el-select
        v-model="status"
        placeholder="完成状态"
        clearable
        aria-label="完成状态"
        ><el-option label="已完成" value="已完成" /><el-option
          label="未开始"
          value="未开始" /></el-select
      ><el-select
        v-model="tag"
        placeholder="能力标签"
        clearable
        aria-label="能力标签"
        ><el-option v-for="t in tags" :key="t" :value="t" /></el-select
      ><el-select
        v-model="stack"
        placeholder="技术栈"
        clearable
        aria-label="技术栈"
        ><el-option v-for="s in stacks" :key="s" :value="s" /></el-select
      ><button class="text-link" @click="clear">重置筛选</button>
    </div>
  </section>
  <div class="all-problems">
    <section class="panel problem-list">
      <div class="panel-heading">
        <h2>
          全部题目 <span class="count-badge">{{ filtered.length }}</span>
        </h2>
      </div>
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>题目名称</th>
              <th>难度</th>
              <th>题型</th>
              <th>完成状态</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="p in filtered.slice((page - 1) * 20, page * 20)"
              :key="p.id"
              class="clickable-row"
              @click="router.push('/workspace/' + p.id)"
            >
              <td>
                <RouterLink
                  class="table-title"
                  :to="'/workspace/' + p.id"
                  @click.stop
                  >{{ p.title }}</RouterLink
                >
                <div class="table-sub">
                  {{ p.id }} <span>· {{ p.tags.join(" / ") }}</span>
                </div>
              </td>
              <td>
                <span
                  class="tag"
                  :class="
                    p.difficulty === '简单'
                      ? 'green'
                      : p.difficulty === '困难'
                        ? 'orange'
                        : 'blue'
                  "
                  >{{ p.difficulty }}</span
                >
              </td>
              <td>{{ p.type }}</td>
              <td>
                <span
                  class="status-label"
                  :class="completed.has(p.id) ? 'positive' : 'muted'"
                  ><Icon
                    :name="completed.has(p.id) ? 'success' : 'circle'"
                    :size="14"
                  />{{ completed.has(p.id) ? "已完成" : "未开始" }}</span
                >
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <el-empty
        v-if="!filtered.length"
        description="没有匹配的题目，试试调整筛选条件"
        ><el-button @click="clear">清除筛选</el-button></el-empty
      >
      <div class="table-footer">
        <span>共 {{ filtered.length }} 道题目 · 每页 20 条</span
        ><el-pagination
          v-model:current-page="page"
          :total="filtered.length"
          :page-size="20"
          layout="prev,pager,next"
        />
      </div>
    </section>
  </div>
</template>
