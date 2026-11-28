<script lang="ts">
import type { JobProgress } from "../services/platform";

const statusLabels = {
  pending: "正在等待回复",
  queued: "正在排队",
  running: "正在处理问题",
  done: "回复已完成",
  failed: "请求失败",
  cancelled: "任务已中止",
};
export type AgentActivityStatus = keyof typeof statusLabels;

const stepLabels = {
  ...statusLabels,
  accepted: "请求已受理",
  started: "开始处理",
  resumed: "恢复处理",
  received: "已收到问题",
  read: "已读取文件",
  edited: "已拟好修改建议",
  needsRevision: "修改建议需要修正",
  tested: "已执行公开测试",
  testUnavailable: "公开测试未执行",
};
type StepKind = keyof typeof stepLabels;
interface ActivityStep {
  kind: StepKind;
  detail?: string;
  at?: string;
}
export interface AgentActivityRecord {
  status: AgentActivityStatus;
  steps: ActivityStep[];
}

const eventKinds: Record<string, StepKind> = {
  已受理: "accepted",
  执行开始: "started",
  接收问题: "received",
  读取文件: "read",
  修改工作副本: "edited",
  建议需要修正: "needsRevision",
  执行公开测试: "tested",
  公开测试未执行: "testUnavailable",
  已完成: "done",
  SYSTEM_FAILED: "failed",
  中止任务: "cancelled",
  已中止: "cancelled",
};

function isFinished(status: AgentActivityStatus) {
  return status === "done" || status === "failed" || status === "cancelled";
}

// Only file actions and test exit codes have displayable details. Other events
// can contain the original prompt, service errors or internal identifiers.
function displayDetail(kind: StepKind, detail: string) {
  if (typeof detail !== "string") return;
  if (kind === "tested") {
    return /^退出码 -?\d{1,10}$/.test(detail) ? detail : undefined;
  }
  if (kind !== "read" && kind !== "edited" && kind !== "needsRevision") return;
  if (detail.length <= 240
    && !/[\\:*?"<>|\p{Cc}\p{Cf}\p{Zl}\p{Zp}]/u.test(detail)
    && detail.split("/").every(part => part && !/[ .]$/.test(part))) {
    return detail;
  }
}

export function summarizeAgentActivity(
  jobStatus: string,
  events: JobProgress["events"] = [],
): AgentActivityRecord {
  const status = Object.hasOwn(statusLabels, jobStatus)
    ? jobStatus as AgentActivityStatus
    : "pending";
  const steps: ActivityStep[] = [];
  for (const event of events) {
    if (!Object.hasOwn(eventKinds, event.event)) continue;
    let kind = eventKinds[event.event];
    if (kind === "started" && event.detail === "恢复中断任务") kind = "resumed";
    const detail = displayDetail(kind, event.detail);
    const stamp = Date.parse(event.at);
    const step: ActivityStep = { kind };
    if (detail) step.detail = detail;
    if (Number.isFinite(stamp)) step.at = new Date(stamp).toISOString();
    steps.push(step);
  }
  if (!steps.length || (isFinished(status) && steps.at(-1)?.kind !== status)) {
    steps.push({ kind: status });
  }
  return { status, steps };
}

const timeFormat = new Intl.DateTimeFormat("zh-CN", {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
});
</script>

<script setup lang="ts">
import { computed, ref, useId } from "vue";
import Icon from "./Icon.vue";

const props = defineProps<{ activity: AgentActivityRecord }>();
const expanded = ref(false);
const panelId = useId();
const busy = computed(() => !isFinished(props.activity.status));
const summary = computed(() => {
  const { status, steps } = props.activity;
  const last = steps.at(-1);
  if (status !== "running" || !last || ["accepted", "started", "received"].includes(last.kind))
    return statusLabels[status];
  return [stepLabels[last.kind], last.detail].filter(Boolean).join(" ");
});
</script>

<template>
  <div class="agent-activity" :class="'activity-' + activity.status">
    <button
      class="activity-toggle"
      type="button"
      :aria-expanded="expanded"
      :aria-controls="panelId"
      @click="expanded = !expanded"
    >
      <span v-if="busy" class="activity-pulse" aria-hidden="true" />
      <Icon v-else :name="activity.status === 'done' ? 'check' : activity.status === 'failed' ? 'warning' : 'close'" :size="15" />
      <span class="activity-summary" aria-live="polite" aria-atomic="true">{{ summary }}</span>
      <Icon name="right" :size="14" class="activity-chevron" />
      <span class="activity-sr">{{ expanded ? '收起' : '展开' }}处理记录</span>
    </button>
    <ol v-show="expanded" :id="panelId" class="activity-steps" aria-label="处理记录">
      <li v-for="(step, index) in activity.steps" :key="index">
        <span class="step-description">
          {{ stepLabels[step.kind] }}
          <span v-if="step.detail" class="step-detail">{{ step.detail }}</span>
        </span>
        <time v-if="step.at && Number.isFinite(Date.parse(step.at))" :datetime="step.at">
          {{ timeFormat.format(new Date(step.at)) }}
        </time>
      </li>
    </ol>
  </div>
</template>

<style scoped>
.agent-activity {
  min-width: 0;
  color: #48566b;
  font-size: 12px;
  line-height: 1.55;
}
.activity-toggle {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  min-height: 32px;
  gap: 7px;
  border: 0;
  border-radius: 5px;
  padding: 3px;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: start;
  cursor: pointer;
}
.activity-toggle:hover { color: #243957; }
.activity-toggle:focus-visible { outline: 2px solid var(--blue); outline-offset: 2px; }
.activity-toggle > svg { flex: none; }
.activity-summary {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.activity-chevron { color: #63738a; transition: transform 140ms ease; }
.activity-toggle[aria-expanded="true"] .activity-chevron { transform: rotate(90deg); }
.activity-pulse {
  flex: none;
  width: 8px;
  height: 8px;
  margin-inline: 3.5px;
  border-radius: 50%;
  background: #42669d;
  animation: activity-pulse 1.6s ease-in-out infinite;
}
@keyframes activity-pulse {
  50% { opacity: .48; }
}
.activity-failed .activity-toggle > svg:first-child { color: #a34a32; }
.activity-steps {
  list-style: none;
  margin: 2px 0 6px 10px;
  padding: 0;
}
.activity-steps li {
  position: relative;
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 1px 8px;
  padding: 1px 0 10px 16px;
  color: #536278;
}
.activity-steps li::before,
.activity-steps li:not(:last-child)::after {
  position: absolute;
  content: "";
}
.activity-steps li::before {
  left: -2px;
  top: 7px;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #8b9ab0;
}
.activity-steps li:not(:last-child)::after {
  top: 13px;
  bottom: -5px;
  left: 0;
  width: 1px;
  background: #d5dde7;
}
.activity-steps li:last-child { padding-bottom: 0; }
.step-description { min-width: 0; overflow-wrap: anywhere; }
.step-detail { color: #394c66; }
.activity-steps time {
  color: #65738a;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}
.activity-sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
@media (prefers-reduced-motion: reduce) {
  .activity-pulse { animation: none; }
  .activity-chevron { transition: none; }
}
</style>
