<script setup lang="ts">
import { ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { state, audit } from "../store";
import { request, isMock } from "../services/api";
import Icon from "../components/Icon.vue";
const dialog = ref(false),
  name = ref(""),
  expires = ref("2027-01-31"),
  scopes = ref(["problems:read", "submissions:read"]),
  secret = ref(""),
  secretDialog = ref(false),
  busy = ref(false);
const navigator = window.navigator;
const expired = (value: string) => Date.parse(value) < Date.now();
async function create() {
  if (
    !name.value.trim() ||
    !scopes.value.length ||
    !expires.value ||
    Date.parse(expires.value) <= Date.now()
  )
    return ElMessage.warning("请填写名称、未来有效期并至少选择一个授权范围");
  busy.value = true;
  try {
    const raw = isMock
      ? "demo_" + crypto.randomUUID().replaceAll("-", "")
      : (
          await request<{ key: string }>("POST", "/api-keys", {
            name: name.value,
            scopes: scopes.value,
            expires_at: expires.value,
          })
        ).key;
    const id = crypto.randomUUID();
    state.keys.push({
      id,
      name: name.value,
      prefix: raw.slice(0, 10) + "…",
      scopes: [...scopes.value],
      expires: expires.value,
      revoked: false,
    });
    secret.value = raw;
    dialog.value = false;
    secretDialog.value = true;
    audit("创建 API 凭证", name.value);
    name.value = "";
  } catch (e) {
    ElMessage.error((e as Error).message);
  } finally {
    busy.value = false;
  }
}
async function revoke(id: string) {
  try {
    await ElMessageBox.confirm(
      "撤销后凭证立即失效，历史审计记录将保留。",
      "撤销凭证",
      { type: "warning" },
    );
    if (!isMock) await request("DELETE", "/api-keys/" + id);
    state.keys.find((k) => k.id === id)!.revoked = true;
    audit("撤销 API 凭证", id);
    ElMessage.success("凭证已撤销");
  } catch {}
}
const sample = `curl -X POST /api/v1/submissions \\\n  -H "Authorization: Bearer <YOUR_API_KEY>" \\\n  -H "Idempotency-Key: practice-001" \\\n  -H "Content-Type: application/json" \\\n  -d '{"problem_version_id":"E1001@v2.0",\n       "stack":"Vue 3 / TypeScript",\n       "files":{"src/tickets.ts":"export const tickets = [];", "tests/tickets.test.ts":"import { it } from \"vitest\";", "CHANGELOG.md":"# 设计与验证"}}'`;
</script>
<template>
  <div class="page-heading">
    <div><h1>开放 API 与凭证</h1></div>
    <el-button type="primary" @click="dialog = true"
      ><Icon name="plus" :size="16" />创建凭证</el-button
    >
  </div>
  <div class="api-limits">
    <div class="panel">
      <Icon name="activity" /><b>60 <small>次 / 分钟</small></b
      ><span>读请求上限</span>
    </div>
    <div class="panel">
      <Icon name="send" /><b>10 <small>次 / 分钟</small></b
      ><span>练习提交上限</span>
    </div>
    <div class="panel">
      <Icon name="clock" /><b>5 <small>个任务</small></b
      ><span>最多未完成提交</span>
    </div>
    <div class="panel">
      <Icon name="shield" /><b>Scope <small>授权</small></b
      ><span>权限不超过所属账户</span>
    </div>
  </div>
  <section class="panel">
    <div class="panel-heading">
      <h2>我的 API 凭证</h2>
      <span class="muted tiny">明文仅显示一次</span>
    </div>
    <div class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>名称</th>
            <th>凭证摘要</th>
            <th>授权范围</th>
            <th>有效期</th>
            <th>状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="k in state.keys" :key="k.id">
            <td>
              <b>{{ k.name }}</b>
            </td>
            <td class="mono">{{ k.prefix }}</td>
            <td>
              <span class="tiny">{{ k.scopes.join(" / ") }}</span>
            </td>
            <td>{{ k.expires }}</td>
            <td>
              <span
                class="tag"
                :class="k.revoked || expired(k.expires) ? 'gray' : 'green'"
                >{{
                  k.revoked ? "已撤销" : expired(k.expires) ? "已过期" : "有效"
                }}</span
              >
            </td>
            <td>
              <button
                class="text-link danger"
                :disabled="k.revoked"
                @click="revoke(k.id)"
              >
                撤销
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <el-empty v-if="!state.keys.length" description="还没有 API 凭证"
        ><el-button @click="dialog = true">创建第一个凭证</el-button></el-empty
      >
    </div>
  </section>
  <div class="api-doc-grid">
    <section class="panel form-panel">
      <h2>从一次练习提交开始</h2>
      <p class="muted">提交返回 202 与 submission_id，随后查询状态和报告。</p>
      <div class="code-block-header">
        <span>POST /api/v1/submissions</span
        ><button
          class="icon-btn"
          aria-label="复制 API 示例"
          @click="
            navigator.clipboard
              .writeText(sample)
              .then(() => ElMessage.success('示例已复制'))
          "
        >
          <Icon name="copy" :size="16" />
        </button>
      </div>
      <pre class="api-code">{{ sample }}</pre>
    </section>
    <section class="panel form-panel">
      <h2>最小接口契约</h2>
      <div
        v-for="[method, path, desc] in [
          ['GET', '/problems', '查询授权题目与版本'],
          ['POST', '/submissions', '幂等提交个人练习'],
          ['GET', '/submissions/{id}', '获取提交状态'],
          ['GET', '/submissions/{id}/report', '获取报告，未就绪时 score=null'],
        ]"
        :key="path + method"
        class="endpoint"
      >
        <span class="tag" :class="method === 'GET' ? 'green' : 'blue'">{{
          method
        }}</span
        ><code>{{ path }}</code>
        <p>{{ desc }}</p>
      </div>
      <p class="tiny muted">
        统一前缀 /api/v1。响应包含 code、message、data、request_id。轮询建议从 3
        秒开始并逐步退避。
      </p>
      <p class="tiny muted">
        401 未认证 · 403 无权限 · 409 状态冲突 · 429 限流 · 503 暂不可用
      </p>
    </section>
  </div>
  <el-dialog v-model="dialog" title="创建 API 凭证" width="520px"
    ><el-form label-position="top"
      ><el-form-item label="凭证名称"
        ><el-input
          v-model="name"
          placeholder="例如：课程练习工具"
          maxlength="40" /></el-form-item
      ><el-form-item label="到期日期"
        ><el-date-picker
          v-model="expires"
          type="date"
          value-format="YYYY-MM-DD" /></el-form-item
      ><el-form-item label="授权范围"
        ><el-checkbox-group v-model="scopes"
          ><el-checkbox value="problems:read">题目读取</el-checkbox
          ><el-checkbox value="submissions:write">练习提交</el-checkbox
          ><el-checkbox value="submissions:read"
            >状态与报告查询</el-checkbox
          ></el-checkbox-group
        ></el-form-item
      ></el-form
    ><template #footer
      ><el-button @click="dialog = false">取消</el-button
      ><el-button type="primary" :loading="busy" @click="create"
        >创建凭证</el-button
      ></template
    ></el-dialog
  ><el-dialog
    v-model="secretDialog"
    title="保存你的凭证"
    width="560px"
    @closed="secret = ''"
    ><el-alert
      title="明文仅显示这一次，关闭后将无法再次查看。"
      type="warning"
      :closable="false"
    />
    <div class="secret-value">
      <code>{{ secret }}</code>
    </div>
    <el-button
      @click="
        navigator.clipboard
          .writeText(secret)
          .then(() => ElMessage.success('凭证已复制'))
      "
      ><Icon name="copy" :size="16" />复制凭证</el-button
    >

    <template #footer
      ><el-button type="primary" @click="secretDialog = false"
        >我已保存</el-button
      ></template
    ></el-dialog
  >
</template>
