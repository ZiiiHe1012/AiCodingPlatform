<script setup lang="ts">
import { ref, computed } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { state, audit } from "../store";
import Icon from "../components/Icon.vue";
const router = useRouter(),
  dialog = ref(false),
  name = ref(""),
  invite = ref(""),
  selectedId = ref(state.classes[0]?.id || ""),
  memberSearch = ref(""),
  importDialog = ref(false),
  csv = ref(""),
  importErrors = ref<string[]>([]);
const navigator = window.navigator;
const teacher = computed(() => state.role !== "student"),
  selected = computed(() =>
    state.classes.find((c) => c.id === selectedId.value),
  ),
  members = computed(
    () =>
      selected.value?.members.filter((m) =>
        `${m.id}${m.name}`.includes(memberSearch.value),
      ) || [],
  );
function create() {
  if (!name.value.trim()) return ElMessage.warning("请输入班级名称");
  const id = "class-" + Date.now();
  state.classes.push({
    id,
    name: name.value.trim(),
    teacher: "陈老师",
    code: Math.random().toString(36).slice(2, 8).toUpperCase(),
    members: [],
    archived: false,
  });
  selectedId.value = id;
  dialog.value = false;
  audit("创建班级", name.value);
  name.value = "";
  ElMessage.success("班级已创建");
}
async function join() {
  const room = state.classes.find(
    (c) => c.code === invite.value.trim().toUpperCase() && !c.archived,
  );
  if (!room) return ElMessage.warning("邀请码无效或班级已归档");
  try {
    await ElMessageBox.confirm(
      `班级：${room.name}；教师：${room.teacher}。确认加入？`,
      "确认班级",
    );
    if (room.members.some((m) => m.id === "u-student"))
      ElMessage.info("你已加入该班级，无需重复加入");
    else {
      room.members.push({
        id: "u-student",
        name: state.name,
        joined: "2026-10-31",
      });
      ElMessage.success("加入成功");
    }
    dialog.value = false;
    selectedId.value = room.id;
  } catch {}
}
async function resetCode() {
  try {
    await ElMessageBox.confirm(
      "旧邀请码将失效，已加入成员及已冻结考试名单不受影响。",
      "重置邀请码",
    );
    selected.value!.code = Math.random().toString(36).slice(2, 8).toUpperCase();
    audit("重置邀请码", selected.value!.name);
  } catch {}
}
async function remove(id: string) {
  try {
    await ElMessageBox.confirm("确认将此成员移出班级？", "移除成员", {
      type: "warning",
    });
    selected.value!.members = selected.value!.members.filter(
      (m) => m.id !== id,
    );
    audit("移除班级成员", id);
  } catch {}
}
function importMembers() {
  const lines = csv.value.trim().split(/\r?\n/);
  const errors: string[] = [];
  const parsed = lines.map((l, i) => {
    const fields = l.split(",").map((s) => s.trim());
    if (fields.length !== 2 || !fields.every(Boolean))
      errors.push(`第 ${i + 1} 行：应为“用户编号,昵称”`);
    return { id: fields[0], name: fields[1], joined: "2026-10-31" };
  });
  importErrors.value = errors;
  if (errors.length || !csv.value.trim()) return;
  let count = 0;
  for (const m of parsed)
    if (!selected.value!.members.some((x) => x.id === m.id)) {
      selected.value!.members.push(m);
      count++;
    }
  audit("导入班级成员", `${count} 人`);
  ElMessage.success(`导入 ${count} 人，重复记录已跳过`);
  importDialog.value = false;
  csv.value = "";
}
</script>
<template>
  <div class="page-heading">
    <div>
      <h1>{{ teacher ? "班级管理" : "我的班级" }}</h1>
    </div>
    <el-button type="primary" @click="dialog = true"
      ><Icon name="plus" :size="16" />{{
        teacher ? "创建班级" : "通过邀请码加入"
      }}</el-button
    >
  </div>
  <div class="class-cards">
    <button
      v-for="c in state.classes"
      :key="c.id"
      class="panel class-card"
      :class="{ active: c.id === selectedId }"
      @click="selectedId = c.id"
    >
      <div class="class-cover">
        <span>SE</span><Icon name="graduation" :size="32" />
      </div>
      <div>
        <span class="tag" :class="c.archived ? 'gray' : 'blue'">{{
          c.archived ? "已归档" : "进行中"
        }}</span>
        <h2>{{ c.name }}</h2>
        <p>{{ c.teacher }} · 2026 秋季</p>
        <div class="class-counts">
          <span
            ><Icon name="users" :size="15" />{{ c.members.length }} 位成员</span
          ><span
            ><Icon name="calendar" :size="15" />{{
              state.exams.filter((e) => e.className === c.name).length
            }}
            场考试</span
          >
        </div>
      </div>
    </button>
  </div>
  <section v-if="selected" class="panel">
    <div class="panel-heading">
      <div>
        <h2>{{ selected.name }}</h2>
        <p>成员与考试安排 · 名单变动不影响历史答卷</p>
      </div>
      <div v-if="teacher" class="button-row">
        <el-button :disabled="selected.archived" @click="importDialog = true"
          ><Icon name="upload" :size="15" />导入成员</el-button
        ><el-button
          type="primary"
          :disabled="selected.archived"
          @click="router.push('/exams/new')"
          >安排考试</el-button
        ><el-dropdown
          ><button class="icon-btn" aria-label="班级操作">
            <Icon name="more" /></button
          ><template #dropdown
            ><el-dropdown-menu
              ><el-dropdown-item
                @click="
                  ElMessageBox.prompt('请输入新的班级名称', '修改班级名称', {
                    inputValue: selected!.name,
                    inputValidator: (v) => !!v.trim() || '名称不能为空',
                  })
                    .then(({ value }) => {
                      selected!.name = value;
                      audit('修改班级名称', value);
                    })
                    .catch(() => {})
                "
                >修改名称</el-dropdown-item
              ><el-dropdown-item
                @click="
                  ElMessageBox.confirm(
                    '归档后将停用邀请码并停止新成员导入。',
                    '归档班级',
                  )
                    .then(() => {
                      selected!.archived = true;
                      audit('归档班级', selected!.name);
                    })
                    .catch(() => {})
                "
                >归档班级</el-dropdown-item
              ></el-dropdown-menu
            ></template
          ></el-dropdown
        >
      </div>
    </div>
    <div v-if="teacher" class="invite-strip">
      <Icon name="key" :size="19" /><span>班级邀请码</span
      ><b>{{ selected.code }}</b
      ><button
        class="text-link"
        @click="
          navigator.clipboard
            .writeText(selected.code)
            .then(() => ElMessage.success('邀请码已复制'))
        "
      >
        <Icon name="copy" :size="14" />复制</button
      ><button
        class="text-link"
        :disabled="selected.archived"
        @click="resetCode"
      >
        重置邀请码
      </button>
    </div>
    <div class="table-toolbar">
      <h3>{{ teacher ? "班级成员" : "班级信息" }}</h3>
      <el-input
        v-if="teacher"
        v-model="memberSearch"
        placeholder="搜索成员编号或昵称"
        style="width: 240px"
        clearable
        ><template #prefix><Icon name="search" :size="15" /></template
      ></el-input>
    </div>
    <div v-if="teacher" class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>成员</th>
            <th>用户编号</th>
            <th>加入时间</th>
            <th>状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="m in members" :key="m.id">
            <td>
              <span class="person-cell"
                ><span class="avatar small">{{ m.name[0] }}</span
                >{{ m.name }}</span
              >
            </td>
            <td class="mono">{{ m.id }}</td>
            <td>{{ m.joined }}</td>
            <td>
              <span class="status-label positive"
                ><Icon name="success" :size="14" />正常</span
              >
            </td>
            <td>
              <button class="text-link danger" @click="remove(m.id)">
                移除
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <el-empty v-if="!members.length" description="暂无成员" />
    </div>
    <div v-else class="form-panel">
      <p>任课教师：{{ selected.teacher }}</p>
      <p>成员数量：{{ selected.members.length }} 人</p>
      <el-button @click="router.push('/exams')"
        >查看本班考试安排 <Icon name="arrow" :size="16"
      /></el-button>
    </div>
  </section>
  <el-empty v-else description="尚未加入班级" /><el-dialog
    v-model="dialog"
    :title="teacher ? '创建班级' : '加入班级'"
    width="450px"
    ><el-form label-position="top"
      ><el-form-item v-if="teacher" label="班级名称"
        ><el-input
          v-model="name"
          placeholder="请输入班级名称"
          maxlength="60" /></el-form-item
      ><el-form-item v-else label="邀请码"
        ><el-input
          v-model="invite"
          placeholder="输入教师提供的邀请码，如 SE2026" /></el-form-item></el-form
    ><template #footer
      ><el-button @click="dialog = false">取消</el-button
      ><el-button type="primary" @click="teacher ? create() : join()">{{
        teacher ? "创建班级" : "确认邀请码"
      }}</el-button></template
    ></el-dialog
  ><el-dialog v-model="importDialog" title="导入班级成员" width="540px"
    ><p>每行一个成员，格式为“用户编号,昵称”，重复用户自动跳过。</p>
    <el-input
      v-model="csv"
      type="textarea"
      :rows="7"
      placeholder="20230005,王同学&#10;20230006,赵同学"
    />
    <p v-for="e in importErrors" :key="e" class="danger tiny">{{ e }}</p>
    <template #footer
      ><el-button @click="importDialog = false">取消</el-button
      ><el-button type="primary" @click="importMembers"
        >校验并导入</el-button
      ></template
    ></el-dialog
  >
</template>
