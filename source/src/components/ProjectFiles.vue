<script setup lang="ts">
import { computed } from "vue";
import Icon from "./Icon.vue";
const props = defineProps<{
  paths: string[];
  modelValue: string;
  repository: string;
  readOnly: boolean;
}>();
const emit = defineEmits<{ "update:modelValue": [path: string]; create: [] }>();
interface FileNode {
  label: string;
  path: string;
  folder: boolean;
  children?: FileNode[];
}
const tree = computed(() => {
  const root: FileNode[] = [];
  for (const path of props.paths) {
    let level = root;
    const parts = path.split("/");
    parts.forEach((part, i) => {
      const key = parts.slice(0, i + 1).join("/");
      let node = level.find((n) => n.path === key);
      if (!node) {
        node = {
          label: part,
          path: key,
          folder: i < parts.length - 1,
          ...(i < parts.length - 1 ? { children: [] } : {}),
        };
        level.push(node);
      }
      if (node.children) level = node.children;
    });
  }
  function sort(nodes: FileNode[]) {
    nodes.sort(
      (a, b) =>
        Number(b.folder) - Number(a.folder) || a.label.localeCompare(b.label),
    );
    nodes.forEach((n) => n.children && sort(n.children));
  }
  sort(root);
  return root;
});
function select(node: FileNode) {
  if (!node.folder) emit("update:modelValue", node.path);
}
const fileLabels: Record<string, string> = {
  ts: "TS",
  vue: "V",
  py: "Py",
  json: "{}",
  md: "M",
  html: "H",
  css: "#",
};
function extension(path: string) {
  return (path.split(".").pop() || "").toLowerCase();
}
</script>
<template>
  <aside class="project-explorer" aria-label="项目文件资源管理器">
    <div class="explorer-heading">
      <b>文件</b
      ><button
        class="icon-btn"
        aria-label="新建文件"
        :disabled="readOnly"
        @click="emit('create')"
      >
        <Icon name="plus" :size="16" />
      </button>
    </div>
    <div class="explorer-repository">
      <Icon name="folder" :size="14" /><span>{{ repository }}</span>
    </div>
    <el-tree
      :data="tree"
      node-key="path"
      :current-node-key="modelValue"
      default-expand-all
      highlight-current
      :indent="12"
      @node-click="select"
      aria-label="项目目录"
      ><template #default="{ data }"
        ><span class="explorer-item" :title="data.path"
          ><Icon v-if="data.folder" name="folder" :size="14" /><span
            v-else
            class="file-type-icon"
            :class="'file-' + extension(data.path)"
            >{{ fileLabels[extension(data.path)] || "·" }}</span
          ><span>{{ data.label }}</span></span
        ></template
      ></el-tree
    >
  </aside>
</template>
<style scoped>
.project-explorer {
  background: #f8fafc;
  border-right: 1px solid #e6ebf2;
  overflow: auto;
  min-width: 0;
  padding-bottom: 16px;
}
.explorer-heading {
  height: 39px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 10px 0 14px;
  border-bottom: 1px solid #e6ebf2;
  color: #56677e;
  font-size: 12px;
}
.explorer-heading .icon-btn {
  width: 24px;
  height: 24px;
}
.explorer-repository {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 12px 10px;
  font-size: 12px;
  font-weight: 600;
  color: #3c536c;
}
.explorer-repository span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.explorer-item {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
  font-size: 12px;
}
.explorer-item > span:last-child {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.file-type-icon {
  flex: none;
  width: 16px;
  font:
    bold 10px/1.3 Consolas,
    monospace;
  text-align: center;
  color: #8a97a9;
}
.file-ts {
  color: #2874bc;
}
.file-vue {
  color: #359675;
}
.file-py {
  color: #be912c;
}
.file-json {
  color: #ba8644;
}
.file-md {
  color: #607baf;
}
.project-explorer :deep(.el-tree) {
  background: transparent;
  --el-tree-node-hover-bg-color: #edf2fa;
  color: #526178;
}
.project-explorer :deep(.el-tree-node__content) {
  height: 30px;
  padding-right: 6px;
}
.project-explorer :deep(.is-current > .el-tree-node__content) {
  background: #e8effc;
  color: #2454c6;
  box-shadow: inset 2px 0 #3976d9;
}
</style>
