<script setup lang="ts">
import { ref, computed } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useRouter } from "vue-router";
import { state, audit } from "../store";
import { formatTime } from "../domain";
import Icon from "../components/Icon.vue";
const router = useRouter(),
  tab = ref("用户管理"),
  search = ref("");
const users = computed(() =>
  state.users.filter((u) => `${u.id}${u.name}`.includes(search.value)),
);
async function change(id: string, mode: string) {
  const u = state.users.find((u) => u.id === id)!;
  if (
    u.role === "admin" &&
    state.users.filter((v) => v.role === "admin" && v.enabled).length === 1
  )
    return ElMessage.warning("禁止禁用或降级最后一个有效管理员");
  try {
    const { value } = await ElMessageBox.prompt(
      mode === "role"
        ? "请输入授予或撤销教师角色的原因"
        : "请输入修改账户状态的原因",
      "操作原因",
      { inputValidator: (v) => !!v.trim() || "必须填写原因" },
    );
    if (mode === "role") u.role = u.role === "teacher" ? "student" : "teacher";
    else u.enabled = !u.enabled;
    audit(
      mode === "role" ? "变更用户角色" : "变更账户状态",
      `${u.id}：${value}`,
    );
    ElMessage.success("变更已保存");
  } catch {}
}
</script>
<template>
  <div class="page-heading">
    <div>
      <h1>用户权限与内容审核</h1>
    </div>
    <span class="tag blue"><Icon name="shield" :size="14" />管理员工作区</span>
  </div>
  <section class="panel">
    <div class="panel-heading">
      <div class="tab-row flush">
        <button
          v-for="t in ['用户管理', '内置题审核', '操作审计']"
          :key="t"
          :class="{ active: tab === t }"
          @click="tab = t"
        >
          {{ t }}
        </button>
      </div>
      <el-input
        v-if="tab === '用户管理'"
        v-model="search"
        placeholder="搜索用户编号或昵称"
        style="width: 260px"
        clearable
      />
    </div>
    <template v-if="tab === '用户管理'"
      ><div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>用户</th>
              <th>用户编号</th>
              <th>当前角色</th>
              <th>账户状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="u in users" :key="u.id">
              <td>
                <span class="person-cell"
                  ><span class="avatar small">{{ u.name[0] }}</span
                  >{{ u.name }}</span
                >
              </td>
              <td class="mono">{{ u.id }}</td>
              <td>
                <span
                  class="tag"
                  :class="
                    u.role === 'admin'
                      ? 'orange'
                      : u.role === 'teacher'
                        ? 'blue'
                        : 'gray'
                  "
                  >{{
                    { student: "普通用户", teacher: "教师", admin: "管理员" }[
                      u.role
                    ]
                  }}</span
                >
              </td>
              <td>
                <span class="tag" :class="u.enabled ? 'green' : 'gray'">{{
                  u.enabled ? "已启用" : "已禁用"
                }}</span>
              </td>
              <td>
                <div class="button-row">
                  <button class="text-link" @click="change(u.id, 'role')">
                    {{ u.role === "teacher" ? "撤销教师" : "授予教师" }}</button
                  ><button
                    class="text-link"
                    :class="u.enabled ? 'danger' : ''"
                    @click="change(u.id, 'status')"
                  >
                    {{ u.enabled ? "禁用" : "启用" }}
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div> </template
    ><template v-if="tab === '内置题审核'"
      ><table>
        <thead>
          <tr>
            <th>题目</th>
            <th>版本</th>
            <th>来源</th>
            <th>状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="p in state.problems.filter((p) => p.bank === '内置题库')"
            :key="p.id"
          >
            <td>{{ p.title }}</td>
            <td>{{ p.version }}</td>
            <td>{{ p.source }}</td>
            <td>
              <span class="tag green">{{ p.status }}</span>
            </td>
            <td>
              <button
                class="text-link"
                @click="router.push('/problem-edit/' + p.id)"
              >
                查看与维护
              </button>
            </td>
          </tr>
        </tbody>
      </table></template
    ><template v-if="tab === '操作审计'"
      ><table>
        <thead>
          <tr>
            <th>操作时间</th>
            <th>操作人</th>
            <th>动作</th>
            <th>原因与变更记录</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="a in state.audits" :key="a.id">
            <td>{{ formatTime(a.time) }}</td>
            <td>{{ a.actor }}</td>
            <td>{{ a.action }}</td>
            <td>{{ a.reason }}</td>
          </tr>
        </tbody>
      </table>
      <el-empty
        v-if="!state.audits.length"
        description="还没有管理操作，变更后将在这里留下记录"
    /></template>
  </section>
</template>
