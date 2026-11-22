import type { Submission } from "./types";
export interface PracticeEvent {
  id: string;
  userId: string;
  problemId: string;
  createdAt: string;
}
export function dayKey(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}
export const seedPractice: PracticeEvent[] = Array.from(
  { length: 60 },
  (_, i) => {
    const date = new Date(2026, 8, 1 + i, 15);
    if ((i * 7 + i * i) % 11 < 4) return [];
    return Array.from({ length: 1 + ((i * 3) % 4) }, (_, j) => ({
      id: `practice-${i}-${j}`,
      userId: "u-student",
      problemId: `E${1001 + ((i + j) % 12)}`,
      createdAt: new Date(date.getTime() + j * 3600000).toISOString(),
    }));
  },
).flat();
export function dailyActivity(
  events: PracticeEvent[],
  submissions: Submission[],
  userId: string,
) {
  const days: Record<
    string,
    { id: string; problemId: string; submissionId?: string }[]
  > = {};
  for (const event of events.filter((e) => e.userId === userId)) {
    const key = dayKey(new Date(event.createdAt));
    (days[key] ||= []).push({ id: event.id, problemId: event.problemId });
  }
  for (const submission of submissions.filter((s) => s.userId === userId)) {
    const key = dayKey(new Date(submission.createdAt));
    (days[key] ||= []).push({
      id: submission.id,
      problemId: submission.problemId,
      submissionId: submission.id,
    });
  }
  return days;
}
export function contributionCalendar(year: number, now = new Date()) {
  const first = new Date(year, 0, 1, 12);
  const last = new Date(year, 11, 31, 12);
  const start = new Date(first);
  start.setDate(first.getDate() - first.getDay());
  const end = new Date(last);
  end.setDate(last.getDate() + 6 - last.getDay());
  const days: {
    date: string;
    day: number;
    month: number;
    inYear: boolean;
    future: boolean;
    monthStart: boolean;
  }[] = [];
  for (
    const date = new Date(start);
    date <= end;
    date.setDate(date.getDate() + 1)
  ) {
    days.push({
      date: dayKey(date),
      day: date.getDay(),
      month: date.getMonth(),
      inYear: date.getFullYear() === year,
      future: dayKey(date) > dayKey(now),
      monthStart: date.getDate() === 1,
    });
  }
  return Array.from({ length: days.length / 7 }, (_, i) =>
    days.slice(i * 7, i * 7 + 7),
  );
}
export function currentStreak(dates: string[], now = new Date()) {
  const active = new Set(dates);
  const date = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 12);
  if (!active.has(dayKey(date))) date.setDate(date.getDate() - 1);
  let streak = 0;
  while (active.has(dayKey(date))) {
    streak++;
    date.setDate(date.getDate() - 1);
  }
  return streak;
}
