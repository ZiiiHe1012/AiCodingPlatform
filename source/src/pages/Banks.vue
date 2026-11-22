<script setup lang="ts">
import { ref, computed } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { unzipSync, strFromU8, zipSync, strToU8 } from "fflate";
import { state, audit } from "../store";
import { validatePackagePath } from "../domain";
import { validateProject } from "../project";
import { taskTypes } from "../data";
import type { Problem } from "../types";
import Icon from "../components/Icon.vue";
const router = useRouter(),
  tab = ref("个人题库"),
  query = ref(""),
  dialog = ref(false),
  errors = ref<string[]>([]),
  preview = ref<Problem[]>([]),
  filename = ref(""),
  busy = ref(false),
  fileInput = ref<HTMLInputElement>();
const list = computed(() =>
  state.problems.filter(
    (p) =>
      (tab.value === "内置题库"
        ? p.bank === "内置题库"
        : tab.value === "授权班级题库"
          ? p.bank === "班级共享题库"
          : p.bank !== "内置题库" && p.bank !== "班级共享题库") &&
      p.title.includes(query.value),
  ),
);
async function createBank() {
  try {
    const { value } = await ElMessageBox.prompt(
      "题库默认仅本人可见",
      "新建题库",
      {
        inputPlaceholder: "题库名称",
        inputValidator: (v) =>
          (!!v.trim() && !state.banks.includes(v.trim())) ||
          "请输入不重复的题库名称",
      },
    );
    state.banks.push(value.trim());
    ElMessage.success("私有题库已创建");
  } catch {}
}
async function importFile(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0];
  if (!file) return;
  filename.value = file.name;
  errors.value = [];
  preview.value = [];
  busy.value = true;
  dialog.value = true;
  try {
    if (file.size > 20 * 1024 * 1024) throw new Error("题包超过 20 MB 限制");
    if (!file.name.toLowerCase().endsWith(".zip"))
      throw new Error("请选择 ZIP 题包");
    let count = 0,
      size = 0;
    const archive = unzipSync(new Uint8Array(await file.arrayBuffer()), {
      filter: (f) => {
        count++;
        size += f.originalSize;
        if (count > 1000 || size > 100 * 1024 * 1024)
          throw new Error("解压大小或文件数量超过限制");
        if (!validatePackagePath(f.name))
          throw new Error("不允许的文件路径：" + f.name);
        if (
          !/\/$|\.(json|md|py|txt|ts|js|vue|html|css|toml|yaml|yml|log)$/i.test(
            f.name,
          )
        )
          throw new Error("扩展名不在白名单：" + f.name);
        return true;
      },
    });
    if (!archive["manifest.json"])
      throw new Error("manifest.json：缺少清单文件");
    const manifest = JSON.parse(strFromU8(archive["manifest.json"]));
    if (manifest.schema_version !== 2)
      throw new Error("题包需使用工程任务格式 schema_version: 2");
    const metadata = manifest.project;
    if (!metadata || !taskTypes.includes(metadata.type))
      throw new Error("manifest.project：任务类型无效");
    const files = Object.fromEntries(
      Object.entries(archive)
        .filter(([path]) => path.startsWith("project/") && !path.endsWith("/"))
        .map(([path, bytes]) => [path.slice(8), strFromU8(bytes)]),
    );
    if (!Object.keys(files).length) throw new Error("project/ 中没有项目文件");
    const imported: Problem = {
      ...metadata,
      files,
      id: "E" + Date.now(),
      version: metadata.version || "v1.0",
      bank: state.banks[0],
      status: "草稿",
      solved: false,
      attempts: 0,
      passRate: 0,
    };
    if (
      !Array.isArray(imported.tags) ||
      !Array.isArray(imported.requirements) ||
      !Array.isArray(imported.acceptance) ||
      !Array.isArray(imported.constraints) ||
      !Array.isArray(imported.deliverables)
    )
      throw new Error("标签、需求、验收、约束和交付物须为数组");
    errors.value = validateProject(imported);
    if (!errors.value.length) preview.value = [imported];
  } catch (e) {
    errors.value.push((e as Error).message);
  } finally {
    busy.value = false;
    (e.target as HTMLInputElement).value = "";
  }
}
function exportPackage(p: Problem) {
  const { files, ...metadata } = p;
  const archive = {
    "manifest.json": strToU8(
      JSON.stringify({ schema_version: 2, project: metadata }, null, 2),
    ),
    ...Object.fromEntries(
      Object.entries(files).map(([path, text]) => [
        "project/" + path,
        strToU8(text),
      ]),
    ),
  };
  const bytes = zipSync(archive);
  const url = URL.createObjectURL(
    new Blob([new Uint8Array(bytes)], { type: "application/zip" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = p.repository + "-task.zip";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function confirmImport() {
  if (errors.value.length || !preview.value.length) return;
  state.problems.push(...preview.value);
  audit("导入题包", filename.value);
  dialog.value = false;
  ElMessage.success("题目已导入");
}
async function down(p: Problem) {
  try {
    await ElMessageBox.confirm(
      "下架只影响新使用，已引用的考试版本将保留。",
      "下架题目",
    );
    p.status = "已下架";
    audit("下架题目", p.id);
  } catch {}
}
</script>
<template>
  <div class="page-heading">
    <div>
      <h1>题库管理</h1>
    </div>
    <div class="button-row">
      <el-button @click="createBank"
        ><Icon name="folder" :size="16" />新建题库</el-button
      ><el-button @click="fileInput?.click()"
        ><Icon name="upload" :size="16" />导入题包</el-button
      ><el-button type="primary" @click="router.push('/problem-edit')"
        ><Icon name="plus" :size="16" />新建工程任务</el-button
      ><input
        ref="fileInput"
        type="file"
        accept=".zip"
        hidden
        @change="importFile"
      />
    </div>
  </div>
  <div class="library-overview">
    <div v-for="(b, i) in state.banks" :key="b" class="panel library-card">
      <span class="icon-tile large"><Icon name="folder" :size="24" /></span>
      <div>
        <h3>{{ b }}</h3>
        <p>
          {{ state.problems.filter((p) => p.bank === b).length }} 道题目 ·
          默认私有
        </p>
      </div>
      <Icon name="lock" :size="16" />
    </div>
    <button class="library-create" @click="router.push('/mock')">
      <Icon name="code" :size="23" /><b>创建个人模拟</b
      ><span>从自己的题库开始一次挑战 →</span>
    </button>
  </div>
  <section class="panel">
    <div class="panel-heading">
      <div class="tab-row flush">
        <button
          v-for="t in ['个人题库', '授权班级题库', '内置题库']"
          :key="t"
          :class="{ active: tab === t }"
          @click="tab = t"
        >
          {{ t }}
        </button>
      </div>
      <el-input
        v-model="query"
        placeholder="搜索题目名称"
        clearable
        style="width: 230px"
        ><template #prefix><Icon name="search" :size="15" /></template
      ></el-input>
    </div>
    <div class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>题目名称</th>
            <th>题型</th>
            <th>版本</th>
            <th>可见范围</th>
            <th>状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in list" :key="p.id">
            <td>
              <b>{{ p.title }}</b
              ><small class="table-sub">{{ p.id }} · {{ p.bank }}</small>
            </td>
            <td>{{ p.type }}</td>
            <td class="mono">{{ p.version }}</td>
            <td>
              <span class="status-label"
                ><Icon
                  :name="p.bank === '内置题库' ? 'book' : 'lock'"
                  :size="14"
                />{{ p.bank === "内置题库" ? "公开题面" : "仅自己" }}</span
              >
            </td>
            <td>
              <span
                class="tag"
                :class="
                  p.status === '已发布'
                    ? 'green'
                    : p.status === '已下架'
                      ? 'gray'
                      : 'orange'
                "
                >{{ p.status }}</span
              >
            </td>
            <td>
              <div class="button-row">
                <button class="text-link" @click="exportPackage(p)">
                  导出题包
                </button>
                <button
                  v-if="p.bank !== '内置题库' || state.role === 'admin'"
                  class="text-link"
                  @click="router.push('/problem-edit/' + p.id)"
                >
                  {{ p.status === "已发布" ? "编辑新版本" : "编辑" }}</button
                ><button
                  v-else
                  class="text-link"
                  @click="router.push('/workspace/' + p.id)"
                >
                  查看题面</button
                ><button
                  v-if="
                    p.status === '已发布' &&
                    (p.bank !== '内置题库' || state.role === 'admin')
                  "
                  class="text-link muted"
                  @click="down(p)"
                >
                  下架
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <el-empty
        v-if="!list.length"
        description="还没有题目，创建或导入你的第一道题"
      />
    </div>
    <div class="table-footer">
      <span>共 {{ list.length }} 道题目</span>
    </div>
  </section>
  <el-dialog v-model="dialog" title="题包导入预检" width="650px"
    ><p>
      <b>{{ filename }}</b>
    </p>
    <p class="muted tiny">最大 20 MB · 解压后 100 MB · 最多 1000 个文件</p>
    <div v-if="busy">正在校验结构…</div>
    <template v-else
      ><el-alert
        v-if="errors.length"
        title="预检失败，未创建任何题目"
        type="error"
        :closable="false"
      />
      <p v-for="err in errors" :key="err" class="danger">{{ err }}</p>
      <template v-if="preview.length"
        ><el-alert
          title="工程任务配置检查通过"
          type="success"
          :closable="false"
        />
        <div v-for="p in preview" :key="p.id" class="publish-problem">
          <b>{{ p.title }}</b
          ><span>{{ p.type }}</span
          ><span class="tag gray">导入为私有草稿</span>
        </div></template
      ></template
    >

    <template #footer
      ><el-button @click="dialog = false">取消</el-button
      ><el-button
        type="primary"
        :disabled="!!errors.length || !preview.length || busy"
        @click="confirmImport"
        >确认导入</el-button
      ></template
    ></el-dialog
  >
</template>
