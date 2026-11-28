<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { state } from "../store";
import { baseURL, request } from "../services/api";
import { allPages, showError } from "../services/management";
import { canManageBank, issueText, type Bank, type BankProblem, type CheckResult } from "../services/banks";
import Icon from "../components/Icon.vue";

const router = useRouter();
const tab = ref("个人题库"), query = ref(""), banks = ref<Bank[]>([]);
const projects = ref<BankProblem[]>([]), busy = ref(false);
const bankDialog = ref(false), bankName = ref(""), classroom = ref("");
const rooms = computed(() => state.classes.filter(c => !!c.code && !c.archived));
const dialog = ref(false), fileInput = ref<HTMLInputElement>();
const selectedBank = ref(""), file = ref<File>(), result = ref<CheckResult>();
const errors = ref<string[]>([]);
const ownBanks = computed(() => banks.value.filter(canManageBank));
const visibility = (p: BankProblem) => banks.value.find(b => b.id === p.bank_id)?.visibility;
const list = computed(() => projects.value.filter(p => visibility(p) ===
  ({"内置题库":"public","授权班级题库":"class","个人题库":"private"} as Record<string,string>)[tab.value]
  && p.title.includes(query.value)));
const canEdit = (p: BankProblem) => canManageBank(banks.value.find(b => b.id === p.bank_id));
async function refresh() {
  const [b, p] = await Promise.all([request<Bank[]>("GET","/banks"), allPages<BankProblem>("/problems?manage=1")]);
  banks.value = b;
  projects.value = p;
  if (!selectedBank.value) selectedBank.value = ownBanks.value[0]?.id || "";
}
onMounted(() => refresh().catch(showError));
async function createBank() {
  if (!bankName.value.trim() || busy.value) return;
  busy.value = true;
  try {
    const bank = await request<Bank>("POST","/banks",{name:bankName.value.trim(), visibility:classroom.value ? "class":"private", class_id:classroom.value || null});
    await refresh(); selectedBank.value = bank.id; tab.value = bank.class_id ? "授权班级题库":"个人题库";
    bankDialog.value = false; ElMessage.success("题库已创建");
  } catch (e) { showError(e); } finally { busy.value = false; }
}
function openImport() {
  file.value = undefined; result.value = undefined; errors.value = []; dialog.value = true;
}
async function validateFile() {
  if (!file.value || !selectedBank.value || busy.value) return;
  busy.value = true; errors.value = []; result.value = undefined;
  try {
    const target = "/banks/" + encodeURIComponent(selectedBank.value) + "/imports";
    const upload = await request<{object_id:string;upload_url:string}>("POST",target+"/upload-url",{name:file.value.name,size:file.value.size});
    const res = await fetch(upload.upload_url,{method:"PUT",credentials:"same-origin",body:file.value,headers:{"Content-Type":"application/zip"}});
    if (!res.ok) throw new Error((await res.json()).message || "上传失败");
    result.value = await request<CheckResult>("POST",target+"/validate",{object_id:upload.object_id});
    errors.value = result.value.items.filter(i => i.severity === "error").map(issueText);
  } catch (e) { errors.value = [e instanceof Error ? e.message : "预检失败"]; }
  finally { busy.value = false; }
}
function importFile(event: Event) {
  const input = event.target as HTMLInputElement;
  file.value = input.files?.[0]; input.value = ""; void validateFile();
}
async function confirmImport() {
  if (!result.value?.valid || busy.value) return;
  busy.value = true;
  try {
    await request("POST","/banks/"+encodeURIComponent(selectedBank.value)+"/imports",{validation_id:result.value.validation_id});
    const b = banks.value.find(b => b.id === selectedBank.value);
    tab.value = b?.visibility === "class" ? "授权班级题库" : b?.visibility === "public" ? "内置题库" : "个人题库";
    await refresh(); dialog.value = false; ElMessage.success("题目已导入为草稿");
  } catch (e) { showError(e); } finally { busy.value = false; }
}
async function exportPackage(p: BankProblem) {
  try {
    const url = baseURL + "/problem-versions/" + encodeURIComponent(p.problem_version_id) + "/package" + (canEdit(p) ? "?author=1" : "");
    const response = await fetch(url, {credentials:"same-origin"});
    if (!response.ok) throw new Error((await response.json()).message || "导出失败");
    const blob = URL.createObjectURL(await response.blob());
    const a = document.createElement("a"); a.href = blob; a.download = p.repository + "-" + p.version + ".zip"; a.click();
    setTimeout(() => URL.revokeObjectURL(blob), 1000);
  } catch (e) { showError(e); }
}
async function down(p: BankProblem) {
  try {
    const {value} = await ElMessageBox.prompt("说明下架原因。已经引用该版本的考试将继续使用其快照。","下架题目",
      {inputValidator:v => !!v?.trim() || "请填写下架原因"});
    await request("POST","/problem-versions/"+encodeURIComponent(p.problem_version_id)+"/unpublish",{reason:value.trim()});
    await refresh(); ElMessage.success("题目已下架");
  } catch (e) { showError(e); }
}
</script>
<template>
  <div class="page-heading">
    <div>
      <h1>题库管理</h1>
    </div>
    <div class="button-row">
      <el-button @click="bankName = ''; classroom = ''; bankDialog = true"
        ><Icon name="folder" :size="16" />新建题库</el-button
      ><el-button @click="openImport"
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
    <div v-for="b in banks.filter(b => b.id !== 'builtin')" :key="b.id" class="panel library-card">
      <span class="icon-tile large"><Icon name="folder" :size="24" /></span>
      <div>
        <h3>{{ b.name }}</h3>
        <p>
          {{ projects.filter((p) => p.bank_id === b.id).length }} 道题目 ·
          {{ b.visibility === "class" ? "班级共享" : "仅自己" }}
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
                  :name="p.bank_id === 'builtin' ? 'book' : 'lock'"
                  :size="14"
                />{{ visibility(p) === "public" ? "公开题面" : visibility(p) === "class" ? "班级共享" : "仅自己" }}</span
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
                  {{ canEdit(p) ? "导出完整题包" : "导出公开题面" }}
                </button>
                <button
                  v-if="canEdit(p)"
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
                    (canEdit(p))
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
  <el-dialog v-model="bankDialog" title="新建题库" width="440px">
    <el-form label-position="top"><el-form-item label="题库名称"><el-input v-model="bankName" maxlength="80"/></el-form-item>
      <el-form-item label="可见范围"><el-select v-model="classroom"><el-option value="" label="仅自己"/>
        <el-option v-for="c in rooms" :key="c.id" :value="c.id" :label="'班级 · '+c.name"/></el-select></el-form-item></el-form>
    <template #footer><el-button @click="bankDialog = false">取消</el-button><el-button type="primary" :loading="busy" :disabled="!bankName.trim()" @click="createBank">创建题库</el-button></template>
  </el-dialog>
  <el-dialog v-model="dialog" title="题包导入预检" width="650px" :close-on-click-modal="!busy" :show-close="!busy">
    <el-form label-position="top"><el-form-item label="导入到题库">
      <el-select v-model="selectedBank" :disabled="busy" @change="validateFile"><el-option v-for="b in ownBanks" :key="b.id" :label="b.name" :value="b.id"/></el-select>
    </el-form-item></el-form>
    <el-button :disabled="busy || !selectedBank" @click="fileInput?.click()">选择 ZIP 题包</el-button> {{ file?.name }}
    <p class="muted tiny">支持课程格式 v1 和工程格式 v2 · 最大 20 MB · 解压后 100 MB · 最多 1000 个文件</p>
    <p v-if="busy">正在处理…</p>
    <p v-for="error in errors" :key="error" class="danger">{{ error }}</p>
    <p v-for="warning in result?.items.filter(i => i.severity === 'warning')" :key="issueText(warning)">{{ issueText(warning) }}</p>
    <template v-if="result?.valid"><el-alert title="工程任务配置检查通过" type="success" :closable="false"/>
      <div v-for="title in result.titles" :key="title" class="publish-problem"><b>{{ title }}</b><span class="tag gray">导入为草稿</span></div>
    </template>
    <template #footer><el-button :disabled="busy" @click="dialog = false">取消</el-button><el-button type="primary" :disabled="!result?.valid || busy" @click="confirmImport">确认导入</el-button></template>
  </el-dialog>
</template>
