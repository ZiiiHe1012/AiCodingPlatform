<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from "vue";
import * as monaco from "monaco-editor/esm/vs/editor/editor.api";
import "monaco-editor/esm/vs/basic-languages/python/python.contribution";
import "monaco-editor/esm/vs/basic-languages/typescript/typescript.contribution";
import "monaco-editor/esm/vs/basic-languages/javascript/javascript.contribution";
import "monaco-editor/esm/vs/basic-languages/markdown/markdown.contribution";
import "monaco-editor/esm/vs/basic-languages/html/html.contribution";
import "monaco-editor/esm/vs/basic-languages/css/css.contribution";
import EditorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";
const props = defineProps<{
  modelValue: string;
  readOnly?: boolean;
  fileName: string;
}>();
const emit = defineEmits<{ "update:modelValue": [value: string] }>();
const host = ref<HTMLDivElement>();
let editor: monaco.editor.IStandaloneCodeEditor;
const models = new Map<string, monaco.editor.ITextModel>();
let currentFile = "";
let switching = false;
function language(path: string) {
  const extension = (path.split(".").pop() || "").toLowerCase();
  return (
    (
      {
        py: "python",
        ts: "typescript",
        js: "javascript",
        md: "markdown",
        vue: "html",
        html: "html",
        css: "css",
        json: "json",
      } as Record<string, string>
    )[extension] || "plaintext"
  );
}
function updateModel(fileName: string, value: string) {
  if (!editor) return;
  if (currentFile !== fileName) {
    switching = true;
    let model = models.get(fileName);
    if (!model) {
      model = monaco.editor.createModel(value, language(fileName));
      models.set(fileName, model);
    }
    editor.setModel(model);
    currentFile = fileName;
    switching = false;
  }
  if (editor.getValue() !== value) {
    editor.pushUndoStop();
    editor.executeEdits("apply-suggestion", [
      { range: editor.getModel()!.getFullModelRange(), text: value },
    ]);
    editor.pushUndoStop();
  }
}
(self as unknown as { MonacoEnvironment: unknown }).MonacoEnvironment = {
  getWorker: () => new EditorWorker(),
};
onMounted(() => {
  editor = monaco.editor.create(host.value!, {
    model: null,
    theme: "vs",
    fontSize: 13,
    fontFamily: "Consolas, monospace",
    minimap: { enabled: false },
    automaticLayout: true,
    scrollBeyondLastLine: false,
    padding: { top: 20, bottom: 16 },
    lineNumbersMinChars: 3,
    tabSize: 4,
    readOnly: props.readOnly,
    wordWrap: "on",
    renderLineHighlight: "gutter",
    overviewRulerLanes: 0,
  });
  updateModel(props.fileName, props.modelValue);
  editor.onDidChangeModelContent(() => {
    if (!switching) emit("update:modelValue", editor.getValue());
  });
});
watch(
  () => [props.fileName, props.modelValue],
  ([fileName, value]) => updateModel(fileName!, value!),
);
watch(
  () => props.readOnly,
  (v) => editor?.updateOptions({ readOnly: v }),
);
onBeforeUnmount(() => {
  editor?.dispose();
  models.forEach((model) => model.dispose());
});
</script>
<template>
  <div ref="host" class="monaco-host" aria-label="项目文件编辑器" />
</template>
