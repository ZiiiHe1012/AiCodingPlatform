<script setup lang="ts">
import { computed, ref } from "vue";
import { state, userId } from "../store";
import {
  dailyActivity,
  seedPractice,
  currentStreak,
  dayKey,
} from "../activity";
import { weightedScore, formatTime } from "../domain";
import Icon from "../components/Icon.vue";
import LineField from "../components/LineField.vue";
import ProfileAvatar from "../components/ProfileAvatar.vue";
import ContributionGrid from "../components/ContributionGrid.vue";
const now = new Date(),
  year = ref(now.getFullYear()),
  selectedDay = ref(dayKey(now));
const profile = computed(() => state.profile!);
const activity = computed(() =>
  dailyActivity(seedPractice, state.submissions, userId()),
);
const counts = computed(() =>
  Object.fromEntries(
    Object.entries(activity.value).map(([date, entries]) => [
      date,
      entries.length,
    ]),
  ),
);
const submissions = computed(() =>
  state.submissions.filter((s) => s.userId === userId()),
);
const completed = computed(
  () =>
    new Set(
      submissions.value
        .filter((s) => s.status === "COMPLETED")
        .map((s) => s.problemId),
    ).size,
);
const days = computed(
  () =>
    Object.keys(activity.value).filter((d) => d.startsWith(String(year.value)))
      .length,
);
const streak = computed(() => currentStreak(Object.keys(activity.value), now));
const years = computed(() =>
  Array.from(
    {
      length:
        now.getFullYear() -
        Math.min(
          now.getFullYear(),
          new Date(profile.value.joinedAt).getFullYear(),
        ) +
        1,
    },
    (_, i) => now.getFullYear() - i,
  ),
);
const selectedEntries = computed(() =>
  [
    ...new Set(
      (activity.value[selectedDay.value] || []).map((e) => e.problemId),
    ),
  ]
    .map((id) => state.problems.find((p) => p.id === id))
    .filter(Boolean),
);
const recent = computed(() => {
  const entries = [
    ...seedPractice.filter((e) => e.userId === userId()),
    ...submissions.value,
  ].sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  const used = new Set<string>();
  return entries
    .filter((e) => {
      if (used.has(e.problemId)) return false;
      used.add(e.problemId);
      return true;
    })
    .slice(0, 4)
    .map((e) => ({
      ...e,
      problem: state.problems.find((p) => p.id === e.problemId),
      report: submissions.value.find(
        (s) => s.problemId === e.problemId && s.scores,
      ),
    }));
});
const bestScore = computed(() =>
  submissions.value
    .filter((s) => s.scores)
    .reduce(
      (best, s) =>
        Math.max(best, weightedScore(s.scores!, s.problemSnapshot?.weights)),
      0,
    ),
);
function selectYear(value: number) {
  year.value = value;
  selectedDay.value =
    value === now.getFullYear() ? dayKey(now) : value + "-12-31";
}
</script>
<template>
  <div v-if="profile" class="personal-home">
    <section class="panel personal-header">
      <div class="personal-cover"><LineField /></div>
      <div class="personal-identity">
        <ProfileAvatar
          :name="profile.nickname"
          :color="profile.avatar"
          :size="92"
        />
        <div class="personal-name">
          <div>
            <h1>{{ profile.nickname }}</h1>
            <span class="tag blue">{{
              { student: "学生", teacher: "教师", admin: "管理员" }[
                profile.role
              ]
            }}</span>
          </div>
          <span>@{{ profile.username }}</span>
        </div>
        <RouterLink to="/settings" class="personal-edit"
          ><Icon name="edit" :size="16" />编辑资料</RouterLink
        >
      </div>
      <div class="personal-details">
        <p v-if="profile.bio">{{ profile.bio }}</p>
        <div class="personal-meta">
          <span v-if="profile.className"
            ><Icon name="graduation" :size="16" />{{ profile.className }}</span
          ><span
            ><Icon name="calendar" :size="15" />{{
              new Date(profile.joinedAt).toLocaleDateString("zh-CN", {
                year: "numeric",
                month: "long",
              })
            }}加入</span
          >
        </div>
        <div v-if="profile.skills.length" class="personal-skills">
          <span v-for="skill in profile.skills" :key="skill">{{ skill }}</span>
        </div>
      </div>
    </section>
  </div>
</template>
