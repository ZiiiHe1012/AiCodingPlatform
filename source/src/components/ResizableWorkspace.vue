<script setup lang="ts">
import { ref, computed, onBeforeUnmount } from "vue";
import {
  defaultPaneSizes,
  resizePane,
  type PaneSizes,
} from "../workspaceLayout";
const grid = ref<HTMLElement>();
function readPaneSizes(): Partial<PaneSizes> | null {
  try {
    const value = JSON.parse(localStorage.getItem("codelab-pane-sizes") || "null");
    return value && typeof value === "object" ? value : null;
  } catch {
    return null;
  }
}
const saved = readPaneSizes();
const sizes = ref<PaneSizes>(
  saved &&
    typeof saved.statement === "number" &&
    Number.isFinite(saved.statement) &&
    typeof saved.assistant === "number" &&
    Number.isFinite(saved.assistant) &&
    saved.statement > 0 &&
    saved.assistant > 0 &&
    saved.statement + saved.assistant < 100
    ? { statement: saved.statement, assistant: saved.assistant }
    : { ...defaultPaneSizes },
);
const dragging = ref<keyof PaneSizes | null>(null);
const columns = computed(
  () =>
    `minmax(0, ${sizes.value.statement}fr) 6px minmax(0, ${100 - sizes.value.statement - sizes.value.assistant}fr) 6px minmax(0, ${sizes.value.assistant}fr)`,
);
function start(event: PointerEvent, side: keyof PaneSizes) {
  if (event.button !== 0) return;
  dragging.value = side;
  (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
  document.body.classList.add("resizing-workspace");
  event.preventDefault();
}
function move(event: PointerEvent) {
  if (!dragging.value || !grid.value) return;
  const box = grid.value.getBoundingClientRect();
  const desired =
    ((dragging.value === "statement"
      ? event.clientX - box.left
      : box.right - event.clientX) /
      (box.width - 12)) *
    100;
  sizes.value = resizePane(sizes.value, dragging.value, desired, box.width);
}
function finish() {
  if (!dragging.value) return;
  dragging.value = null;
  document.body.classList.remove("resizing-workspace");
  localStorage.setItem("codelab-pane-sizes", JSON.stringify(sizes.value));
}
function keyboard(event: KeyboardEvent, side: keyof PaneSizes) {
  if (!["ArrowLeft", "ArrowRight", "Home"].includes(event.key)) return;
  event.preventDefault();
  if (event.key === "Home") sizes.value = { ...defaultPaneSizes };
  else {
    const delta =
      (event.key === "ArrowRight" ? 2 : -2) * (side === "statement" ? 1 : -1);
    sizes.value = resizePane(
      sizes.value,
      side,
      sizes.value[side] + delta,
      grid.value!.getBoundingClientRect().width,
    );
  }
  localStorage.setItem("codelab-pane-sizes", JSON.stringify(sizes.value));
}
function reset() {
  sizes.value = { ...defaultPaneSizes };
  localStorage.setItem("codelab-pane-sizes", JSON.stringify(sizes.value));
}
onBeforeUnmount(() => document.body.classList.remove("resizing-workspace"));
</script>
<template>
  <div
    ref="grid"
    class="workbench-grid"
    :class="{ dragging }"
    :style="{ gridTemplateColumns: columns }"
  >
    <slot name="statement" />
    <div
      class="pane-divider"
      role="separator"
      tabindex="0"
      aria-label="调整题目与工作区宽度"
      aria-orientation="vertical"
      :aria-valuenow="Math.round(sizes.statement)"
      :aria-valuemin="15"
      :aria-valuemax="60"
      title="拖动调整宽度，双击恢复"
      @pointerdown="start($event, 'statement')"
      @pointermove="move"
      @pointerup="finish"
      @pointercancel="finish"
      @lostpointercapture="finish"
      @keydown="keyboard($event, 'statement')"
      @dblclick="reset"
    >
      <span />
    </div>
    <slot name="editor" />
    <div
      class="pane-divider"
      role="separator"
      tabindex="0"
      aria-label="调整工作区与 AI 助手宽度"
      aria-orientation="vertical"
      :aria-valuenow="Math.round(sizes.assistant)"
      :aria-valuemin="15"
      :aria-valuemax="60"
      title="拖动调整宽度，双击恢复"
      @pointerdown="start($event, 'assistant')"
      @pointermove="move"
      @pointerup="finish"
      @pointercancel="finish"
      @lostpointercapture="finish"
      @keydown="keyboard($event, 'assistant')"
      @dblclick="reset"
    >
      <span />
    </div>
    <slot name="assistant" />
  </div>
</template>
<style scoped>
.workbench-grid {
  display: grid;
  height: calc(100vh - 129px);
  min-height: 520px;
}
.pane-divider {
  position: relative;
  background: #edf1f6;
  cursor: col-resize;
  touch-action: none;
  transition: background 150ms ease-out;
  outline-offset: -2px;
}
.pane-divider::before {
  content: "";
  position: absolute;
  inset: 0 -3px;
  z-index: 4;
}
.pane-divider span {
  position: absolute;
  top: 45%;
  left: 2px;
  width: 2px;
  height: 32px;
  background: #bac6d7;
  border-radius: 3px;
}
.pane-divider:hover,
.pane-divider:focus-visible,
.dragging .pane-divider:active {
  background: #3677dc;
}
.pane-divider:hover span,
.pane-divider:focus-visible span {
  background: white;
}
@media (max-width: 1250px) {
  .workbench-grid {
    height: calc(100vh - 121px);
  }
}
@media (max-width: 760px) {
  .workbench-grid {
    display: flex;
    flex-direction: column;
    height: auto;
    min-height: 0;
  }
  .pane-divider {
    display: none;
  }
}
</style>
