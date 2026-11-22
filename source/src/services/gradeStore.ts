import { reactive, watch } from "vue";
export interface GradeRow {
  id: string;
  name: string;
  scores: number[] | null;
  status: "已评分" | "待评分" | "待复核" | "未作答";
}
const seed: Record<string, GradeRow[]> = {
  "exam-3": [
    {
      id: "u-student",
      name: "林同学",
      scores: [90, 80, 80, 70, 60, 80],
      status: "已评分",
    },
    {
      id: "20230002",
      name: "清风",
      scores: [100, 90, 90, 90, 80, 90],
      status: "已评分",
    },
    {
      id: "20230003",
      name: "代码漫游者",
      scores: [95, 90, 85, 90, 80, 80],
      status: "已评分",
    },
    {
      id: "20230004",
      name: "小舟",
      scores: [95, 90, 85, 90, 80, 80],
      status: "已评分",
    },
    {
      id: "20230005",
      name: "寻常",
      scores: [85, 75, 75, 75, 65, 75],
      status: "已评分",
    },
    {
      id: "20230006",
      name: "一行一行",
      scores: [80, 70, 70, 70, 70, 70],
      status: "已评分",
    },
    { id: "20230007", name: "学习者 07", scores: null, status: "待评分" },
    {
      id: "20230008",
      name: "学习者 08",
      scores: [80, 70, 75, 75, 60, 75],
      status: "待复核",
    },
  ],
};
let initial = seed;
try {
  initial =
    JSON.parse(localStorage.getItem("codelab-grades") || "null") || seed;
} catch {}
export const gradeRows = reactive<Record<string, GradeRow[]>>(initial);
watch(
  gradeRows,
  () => localStorage.setItem("codelab-grades", JSON.stringify(gradeRows)),
  { deep: true },
);
