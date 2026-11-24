<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { request } from "../services/api";
import { showError } from "../services/management";
import { canManageBank, issueText, type Bank, type BankProblem, type CheckResult } from "../services/banks";
import { defaultWeights, dimensionNames, validatePackagePath } from "../domain";
import { taskTypes, stacks } from "../data";
import type { Problem } from "../types";
import Icon from "../components/Icon.vue";
const route = useRoute(),
  router = useRouter();
const old = ref<BankProblem>();
const banks = ref<Bank[]>([]), bankId = ref(""), ready = ref(false), busy = ref(false);
const forbidden = ref(false);
const tab = ref("任务与需求"), errors = ref<string[]>([]);
const hiddenCases = ref(""), references = ref("{}");
const savedSnapshot = ref(""), checkedSnapshot = ref("");
const form = ref<Problem>({
        id: "",
        title: "",
        type: "需求实现",
        difficulty: "中等",
        tags: [],
        solved: false,
        attempts: 0,
        passRate: 0,
        description: "",
        stack: stacks[1],
        duration: 90,
        repository: "engineering-task",
        entryFile: "src/index.ts",
        files: {
          "README.md": "# 项目任务\n",
          "src/index.ts": "",
          "tests/project.test.ts": "",
          "package.json": JSON.stringify(
            {
              name: "engineering-task",
              private: true,
              type: "module",
              scripts: { test: "vitest run" },
              devDependencies: { vitest: "3.2.4", typescript: "5.9.3" },
            },
            null,
            2,
          ),
        },
        requirements: [""],
        acceptance: [{ id: "AC-1", scenario: "", expected: "" }],
        constraints: ["保留现有公开接口与已提供的测试。"],
        deliverables: [
          "项目代码与测试",
          "变更说明与设计取舍",
          "AI 协作与验证记录",
        ],
        commands: { setup: "npm install", test: "npm test", start: "" },
        evaluation: { timeout: 30, memory: 256, network: "禁用" },
        version: "v1.0",
        bank: "",
        status: "草稿",
        source: "课程小组原创",
        weights: [...defaultWeights],
      });
const tags = ref(form.value.tags.join(", ")),
  file = ref(form.value.entryFile);
type Materials = { private_tests: Record<string,string>; reference_files: Record<string,string> };
const snapshot = computed(() => JSON.stringify([form.value, tags.value, hiddenCases.value, references.value, bankId.value]));
const checked = computed(() => !!checkedSnapshot.value && checkedSnapshot.value === snapshot.value);
function applySaved(p: BankProblem) {
  old.value = p; form.value = JSON.parse(JSON.stringify(p));
  bankId.value = p.bank_id; tags.value = p.tags.join(", ");
  if (!(file.value in p.files)) file.value = p.entryFile;
  savedSnapshot.value = snapshot.value;
  checkedSnapshot.value = p.status === "预检通过" ? snapshot.value : "";
}
onMounted(async () => {
  try {
    banks.value = (await request<Bank[]>("GET","/banks")).filter(canManageBank);
    const id = route.params.id;
    if (!id) { bankId.value = banks.value[0]?.id || ""; return; }
    const p = await request<BankProblem>("GET","/problems/"+encodeURIComponent(String(id))+"?manage=1");
    if (!banks.value.some(b => b.id === p.bank_id)) { forbidden.value = true; return; }
    const m = await request<Materials>("GET","/problem-versions/"+encodeURIComponent(p.problem_version_id)+"/author-materials");
    hiddenCases.value = m.private_tests["cases.json"] || "";
    references.value = JSON.stringify(m.reference_files,null,2);
    file.value = p.entryFile; applySaved(p);
  } catch (e) { forbidden.value = true; showError(e); }
  finally { ready.value = true; }
});
async function addFile() {
  try {
    const { value } = await ElMessageBox.prompt(
      "相对项目根目录的路径",
      "添加项目文件",
      {
        inputValidator: (v) =>
          (!!v &&
            validatePackagePath(v) &&
            !v.endsWith("/") &&
            !(v in form.value.files)) ||
          "路径无效或已存在",
      },
    );
    form.value.files[value] = "";
    file.value = value;
  } catch {}
}
async function removeFile() {
  if (file.value === form.value.entryFile)
    return ElMessage.warning("请先更换项目入口文件");
  try {
    await ElMessageBox.confirm("删除 " + file.value + "？", "删除文件");
    delete form.value.files[file.value];
    file.value = form.value.entryFile;
  } catch {}
}
async function persist() {
  if (!form.value.title.trim()) throw new Error("请填写项目名称");
  if (!bankId.value) throw new Error("请选择所属题库");
  const previous = old.value;
  if (previous && savedSnapshot.value === snapshot.value && ["草稿", "预检通过"].includes(previous.status)) return previous;
  let reference: unknown;
  try { reference = JSON.parse(references.value.trim() || "{}"); }
  catch { throw new Error("参考实现须填写有效的 JSON 文件映射"); }
  const payload = {...form.value, bank_id:bankId.value, tags:tags.value.split(/[,，]/).map(t=>t.trim()).filter(Boolean),
    author_materials:{private_tests:hiddenCases.value.trim() ? {"cases.json":hiddenCases.value.trim()} : {}, reference_files:reference}};
  const path = previous ? "/problems/"+encodeURIComponent(previous.id)+"/versions" : "/problems";
  const saved = await request<BankProblem>("POST",path,payload);
  applySaved(saved); return saved;
}
async function save(action: "draft" | "precheck" | "publish") {
  if (!ready.value || forbidden.value || busy.value) return;
  busy.value = true; errors.value = [];
  try {
    const p = await persist();
    if (action === "precheck") {
      const report = await request<CheckResult>("POST","/problem-versions/"+encodeURIComponent(p.problem_version_id)+"/precheck");
      errors.value = report.items.map(issueText);
      if (report.valid) {
        applySaved({...p, status:"预检通过"}); ElMessage.success(p.version+" 预检通过");
      }
      return;
    }
    if (action === "publish") {
      await request("POST","/problem-versions/"+encodeURIComponent(p.problem_version_id)+"/publish");
    }
    ElMessage.success(p.version+(action === "publish" ? " 已发布" : " 草稿已保存"));
    await router.push("/banks");
  } catch (e) { showError(e); }
  finally { busy.value = false; }
}
</script>
<template>
  <p v-if="!ready">正在读取题库…</p>
  <el-empty v-else-if="forbidden" description="该题目不存在或当前账户无权维护" />
  <template v-else>
    <div class="page-heading">
      <h1>{{ old ? "编辑工程任务" : "创建工程任务" }}</h1>
      <div class="button-row">
        <el-button @click="router.push('/banks')">取消</el-button
        ><el-button type="primary" :loading="busy" @click="save('draft')">保存草稿</el-button>
      </div>
    </div>
    <section class="panel editor-form-panel" v-loading="busy">
      <div class="tab-row">
        <button
          v-for="t in ['任务与需求', '项目仓库', '验收与评分', '环境与发布']"
          :key="t"
          :class="{ active: tab === t }"
          @click="tab = t"
        >
          {{ t }}
        </button>
      </div>
      <div class="form-panel">
        <el-form v-if="tab === '任务与需求'" label-position="top">
          <div class="form-two-columns">
            <el-form-item label="项目名称"
              ><el-input v-model="form.title" maxlength="80"
            /></el-form-item>
            <el-form-item label="所属题库"
              ><el-select v-model="bankId" :disabled="!!old"><el-option v-for="b in banks" :key="b.id" :label="b.name" :value="b.id"/></el-select
            ></el-form-item>
            <el-form-item label="任务类型"
              ><el-select v-model="form.type"
                ><el-option
                  v-for="t in taskTypes"
                  :key="t"
                  :value="t" /></el-select
            ></el-form-item>
            <el-form-item label="难度"
              ><el-select v-model="form.difficulty"
                ><el-option
                  v-for="d in ['简单', '中等', '困难']"
                  :key="d"
                  :value="d" /></el-select
            ></el-form-item>
            <el-form-item label="技术栈"
              ><el-select v-model="form.stack" filterable allow-create
                ><el-option
                  v-for="s in stacks"
                  :key="s"
                  :value="s" /></el-select
            ></el-form-item>
            <el-form-item label="建议时长（分钟）"
              ><el-input-number
                v-model="form.duration"
                :min="15"
                :max="300"
                :step="15"
            /></el-form-item>
          </div>
          <el-form-item label="业务背景与本次目标"
            ><el-input v-model="form.description" type="textarea" :rows="4"
          /></el-form-item>
          <h3>需求清单</h3>
          <div
            v-for="(_, i) in form.requirements"
            :key="i"
            class="project-edit-row"
          >
            <span>{{ i + 1 }}</span
            ><el-input
              v-model="form.requirements[i]"
              type="textarea"
              :rows="2"
            /><el-button @click="form.requirements.splice(i, 1)"
              >移除</el-button
            >
          </div>
          <el-button @click="form.requirements.push('')">添加需求</el-button>
          <el-form-item label="工程约束" class="project-field"
            ><el-input
              :model-value="form.constraints.join('\n')"
              @update:model-value="
                (v: string) =>
                  (form.constraints = v.split('\n').filter(Boolean))
              "
              type="textarea"
              :rows="3"
          /></el-form-item>
          <div class="form-two-columns">
            <el-form-item label="标签（逗号分隔）"
              ><el-input v-model="tags" /></el-form-item
            ><el-form-item label="来源与授权"
              ><el-input v-model="form.source"
            /></el-form-item>
          </div>
        </el-form>
        <el-form v-if="tab === '项目仓库'" label-position="top">
          <div class="form-two-columns">
            <el-form-item label="仓库名称"
              ><el-input v-model="form.repository" /></el-form-item
            ><el-form-item label="默认打开文件"
              ><el-select v-model="form.entryFile"
                ><el-option
                  v-for="path in Object.keys(form.files)"
                  :key="path"
                  :value="path" /></el-select
            ></el-form-item>
          </div>
          <div class="project-file-selector">
            <el-select v-model="file" filterable aria-label="编辑仓库文件"
              ><el-option
                v-for="path in Object.keys(form.files)"
                :key="path"
                :value="path" /></el-select
            ><el-button @click="addFile">添加文件</el-button
            ><el-button :disabled="file === form.entryFile" @click="removeFile"
              >删除文件</el-button
            >
          </div>
          <el-input
            v-model="form.files[file]"
            type="textarea"
            :rows="20"
            class="mono-input"
          />
        </el-form>
        <div v-if="tab === '验收与评分'">
          <h2>验收标准</h2>
          <div
            v-for="(a, i) in form.acceptance"
            :key="i"
            class="acceptance-editor"
          >
            <div class="button-row">
              <b>{{ a.id }}</b
              ><button class="text-link" @click="form.acceptance.splice(i, 1)">
                移除
              </button>
            </div>
            <el-input
              v-model="a.scenario"
              placeholder="操作场景与前置条件"
            /><el-input
              v-model="a.expected"
              type="textarea"
              :rows="2"
              placeholder="可观察、可验证的预期行为"
            />
          </div>
          <el-button
            @click="
              form.acceptance.push({
                id:
                  'AC-' +
                  (Math.max(
                    0,
                    ...form.acceptance.map((a) => Number(a.id.slice(3)) || 0),
                  ) +
                    1),
                scenario: '',
                expected: '',
              })
            "
            >添加验收场景</el-button
          >
          <h3 class="project-field">出题人专用材料</h3>
          <p class="muted tiny">隐藏验收与参考文件单独保存。考生的题面、工作区与 AI 上下文只使用公开项目文件。</p>
          <el-form label-position="top">
            <el-form-item label="隐藏验收（tests/hidden/cases.json）"><el-input v-model="hiddenCases" type="textarea" :rows="5" placeholder='可选。JSON 数组，覆盖 D1 与 D2，每项包含 dimension、module、function、args、expected。'/></el-form-item>
            <el-form-item label="参考实现（相对路径 → 文件内容）"><el-input v-model="references" type="textarea" :rows="4" placeholder='{"src/solution.py": "…"}'/></el-form-item>
          </el-form>
          <h3 class="project-field">交付物</h3>
          <el-checkbox-group v-model="form.deliverables"
            ><el-checkbox
              v-for="d in [
                '项目代码与测试',
                '变更说明与设计取舍',
                '调用链与根因分析',
                'AI 协作与验证记录',
              ]"
              :key="d"
              :value="d"
              >{{ d }}</el-checkbox
            ></el-checkbox-group
          >
          <h3 class="project-field">评分权重</h3>
          <div
            v-for="(d, i) in dimensionNames"
            :key="d"
            class="rubric-edit-row"
          >
            <span class="icon-tile">D{{ i + 1 }}</span
            ><b>{{ d }}</b
            ><el-input-number v-model="form.weights[i]" :min="0" :max="100" /> %
          </div>
          <p class="weight-total">
            总权重
            <b
              :class="
                form.weights.reduce((a, b) => a + b, 0) === 100
                  ? 'positive'
                  : 'danger'
              "
              >{{ form.weights.reduce((a, b) => a + b, 0) }}%</b
            >
          </p>
        </div>
        <el-form v-if="tab === '环境与发布'" label-position="top">
          <div class="form-two-columns">
            <el-form-item label="依赖安装命令"
              ><el-input v-model="form.commands.setup" /></el-form-item
            ><el-form-item label="验收测试命令"
              ><el-input v-model="form.commands.test" /></el-form-item
            ><el-form-item label="预览启动命令"
              ><el-input
                v-model="form.commands.start"
                placeholder="无预览服务时留空" /></el-form-item
            ><el-form-item label="网络策略"
              ><el-input model-value="禁用" disabled /></el-form-item
            ><el-form-item label="单次测试时限（秒）"
              ><el-input-number
                v-model="form.evaluation.timeout"
                :min="1"
                :max="90" /></el-form-item
            ><el-form-item label="运行内存（MB）"
              ><el-input-number
                v-model="form.evaluation.memory"
                :min="128"
                :max="512"
                :step="128"
            /></el-form-item>
          </div>
          <div class="publish-check">
            <Icon name="shield" :size="32" />
            <h2>发布检查</h2>
            <el-button :loading="busy" @click="save('precheck')">保存并预检</el-button>
            <p v-for="e in errors" :key="e" class="danger">{{ e }}</p>
            <p v-if="checked" class="positive">项目配置完整</p>
            <el-button type="primary" :disabled="!checked" :loading="busy" @click="save('publish')"
              >发布任务</el-button
            >
          </div>
        </el-form>
      </div>
    </section>
  </template>
</template>
