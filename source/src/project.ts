import { zipSync, strToU8 } from "fflate";
import type { Problem, ProjectFiles, Draft } from "./types";
import { validatePackagePath, weightedScore } from "./domain";

export function validateProject(p: Problem): string[] {
  const errors: string[] = [];
  for (const key of [
    "title",
    "description",
    "stack",
    "repository",
    "entryFile",
    "source",
  ] as const)
    if (!p[key]?.trim()) errors.push(`${key} 不能为空`);
  if (!Number.isFinite(p.duration) || p.duration < 15)
    errors.push("建议时长至少 15 分钟");
  if (!p.files || !Object.hasOwn(p.files, p.entryFile))
    errors.push("入口文件不存在");
  else if (!p.files[p.entryFile].trim()) errors.push("入口文件内容不能为空");
  if (
    !Object.entries(p.files || {}).some(
      ([path, text]) =>
        /(^tests?\/|[./]test[./]|test_)/.test(path) && text.trim(),
    )
  )
    errors.push("请提供至少一个非空测试文件");
  for (const path of Object.keys(p.files || {}))
    if (!validatePackagePath(path) || path.endsWith("/"))
      errors.push("文件路径无效：" + path);
  if (!p.requirements?.length || p.requirements.some((r) => !r.trim()))
    errors.push("请填写需求清单");
  if (
    !p.acceptance?.length ||
    p.acceptance.some(
      (a) => !a.id?.trim() || !a.scenario?.trim() || !a.expected?.trim(),
    )
  )
    errors.push("请填写验收场景及预期行为");
  if (new Set(p.acceptance?.map((a) => a.id)).size !== p.acceptance?.length)
    errors.push("验收编号不能重复");
  if (!p.deliverables?.length) errors.push("请选择交付物");
  if (!p.commands?.test?.trim()) errors.push("请填写测试命令");
  if (!p.evaluation || p.evaluation.timeout < 1 || p.evaluation.memory < 128)
    errors.push("运行资源配置无效");
  try {
    weightedScore([0, 0, 0, 0, 0, 0], p.weights);
  } catch (e) {
    errors.push((e as Error).message);
  }
  return errors;
}

export function downloadProject(
  name: string,
  files: ProjectFiles,
  explanation = "",
  aiHistory: { role: string; text: string }[] = [],
) {
  const content = {
    ...files,
    ...(explanation ? { "DELIVERY.md": explanation } : {}),
    ...(aiHistory.length
      ? {
          "AI_COLLABORATION.md": aiHistory
            .map(
              (m) =>
                `## ${m.role === "user" ? "提问" : "AI 回复"}\n\n${m.text}`,
            )
            .join("\n\n"),
        }
      : {}),
  };
  const zip = zipSync(
    Object.fromEntries(
      Object.entries(content).map(([path, text]) => [path, strToU8(text)]),
    ),
  );
  const url = URL.createObjectURL(
    new Blob([new Uint8Array(zip)], { type: "application/zip" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = name + ".zip";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function upgradeProblem(value: Problem): Problem {
  if (value.files) return value;
  const old = value as unknown as Record<string, any>;
  return {
    ...value,
    type: "需求实现",
    stack: "Python 3.12 / pytest",
    duration: 60,
    repository: old.id,
    entryFile: "main.py",
    files: {
      "main.py": old.starter || "",
      "README.md": [old.description, old.input, old.output]
        .filter(Boolean)
        .join("\n\n"),
    },
    requirements: [old.description || old.title],
    acceptance: [
      {
        id: "AC-1",
        scenario: old.exampleInput || "原题验收",
        expected: old.exampleOutput || old.output || "见原题说明",
      },
    ],
    constraints: [],
    deliverables: ["项目代码与测试", "验证说明"],
    commands: { setup: "", test: "python -m pytest", start: "" },
    evaluation: { timeout: 10, memory: 512, network: "禁用" },
  };
}

export function upgradeDraft(value: Draft): Draft {
  if (value.files) return value;
  const old = value as unknown as { code: string; tests: string };
  return {
    ...value,
    files: { "main.py": old.code || "", "test_main.py": old.tests || "" },
    activeFile: "main.py",
  };
}

export function sameFiles(a: ProjectFiles, b: ProjectFiles) {
  const keys = Object.keys(a).sort();
  return (
    keys.length === Object.keys(b).length && keys.every((k) => a[k] === b[k])
  );
}
