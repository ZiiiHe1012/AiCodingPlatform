<script setup lang="ts">
import { ref, watch } from "vue";
import { platform, type WorkspaceInfo, type SandboxPreview, type SandboxAction } from "../services/platform";

const props = defineProps<{ scope: string; pid: string; info: WorkspaceInfo | null; version: number;
  frozen: boolean; save: () => Promise<boolean>; test: string; running: boolean; output: string }>();
const emit = defineEmits<{ run: [command: string] }>();
const command = ref("");
const pending = ref(false), error = ref(""), shot = ref<SandboxPreview | null>(null);
const actions = ref<SandboxAction[]>([]);
async function render(action?: SandboxAction) {
  if (!platform?.live || pending.value || props.frozen) return;
  pending.value = true;
  error.value = "";
  try {
    if (!await props.save()) throw new Error("草稿尚未同步，无法构建此版本。");
    const replay = action ? [...actions.value, action] : [];
    if (action && props.version !== shot.value?.version) throw new Error("草稿已更新，请重新构建预览。");
    const view = await platform.preview(props.scope, props.pid, props.version, replay);
    if (!props.frozen) { shot.value = view; actions.value = replay; }
  } catch (e) { error.value = (e as Error).message; }
  finally { pending.value = false; }
}
function enter(index: number, event: Event) {
  const value = (event.target as HTMLInputElement | HTMLSelectElement).value;
  void render({index, kind:"fill", value});
}
watch(() => props.frozen, locked => { if (locked) { shot.value = null; actions.value = []; } });
</script>
<template>
  <div class="personal-sandbox">
    <p v-if="info"><strong>个人工作区</strong> <code>{{ info.id }}</code> · {{ info.stack }} · 草稿 v{{ version }}</p>
    <p v-if="info && info.runner_status !== 'on_demand'" aria-live="polite">
      {{ { ready: "个人考试容器已就绪", preparing: "正在准备个人考试容器…", unavailable: info.runner_note, closed: "已交卷，个人考试容器已关闭或正在回收" }[info.runner_status] }}
    </p>
    <form @submit.prevent="emit('run', command.trim())">
      <label>终端命令<input v-model="command" :placeholder="test" maxlength="500" :disabled="frozen || running" /></label>
      <el-button native-type="submit" :loading="running" :disabled="frozen">执行命令</el-button>
    </form>
    <pre v-if="output">{{ output }}</pre>
    <template v-if="info?.preview_available">
      <div class="preview-actions"><el-button :loading="pending" :disabled="frozen || pending" @click="render()">构建网页预览</el-button>
        <span v-if="shot">预览 v{{ shot.version }}{{ shot.version !== version ? " · 草稿已更新" : "" }}</span></div>
      <p v-if="error" role="alert">{{ error }}</p>
      <template v-if="shot && !frozen">
        <img :src="'data:image/png;base64,' + shot.image" :width="shot.width" :height="shot.height" alt="当前工程的网页预览" />
        <div class="preview-controls">
          <template v-for="control in shot.controls" :key="control.index + ':' + control.label">
            <button v-if="control.kind === 'button'" type="button" :disabled="pending" @click="render({index:control.index, kind:'click'})">{{ control.label }}</button>
            <label v-else-if="control.kind === 'select'">{{ control.label }}<select :value="control.value" :disabled="pending" @change="enter(control.index, $event)">
              <option v-for="o in control.options" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select></label>
            <label v-else>{{ control.label }}<input :type="['month','date','number','email','search'].includes(control.inputType) ? control.inputType : 'text'"
              :value="control.value" :disabled="pending" maxlength="500" @change="enter(control.index, $event)" @keydown.enter="($event.target as HTMLInputElement).blur()" /></label>
          </template>
        </div>
        <details v-if="shot.text"><summary>页面文字</summary><pre>{{ shot.text }}</pre></details>
      </template>
    </template>
  </div>
</template>
<style scoped>
.personal-sandbox {padding: .75rem 1rem; overflow: auto; max-height: 68vh; font-size: 13px}
.personal-sandbox p {margin: 0 0 .65rem}
.personal-sandbox form,.preview-actions,.preview-controls {display:flex; align-items:center; gap:.55rem; flex-wrap:wrap; margin-bottom:.65rem}
.personal-sandbox label {display:inline-flex; align-items:center; gap:.5rem}
.personal-sandbox input,.personal-sandbox select,.preview-controls button {font:inherit; color:inherit; border:1px solid #cbd5e1; border-radius:5px; padding:.35rem .5rem; background:white}
.personal-sandbox img {max-width:100%;height:auto;display:block;border:1px solid #cbd5e1; margin:.5rem 0}
.personal-sandbox pre {white-space:pre-wrap; overflow-wrap:anywhere}
</style>
