<script setup lang="ts">
import { computed, ref, nextTick } from "vue";
import { contributionCalendar, dayKey } from "../activity";
const props = defineProps<{
  year: number;
  counts: Record<string, number>;
  selected: string;
}>();
const emit = defineEmits<{ select: [date: string] }>();
const grid = ref<HTMLElement>();
const weeks = computed(() => contributionCalendar(props.year));
const today = dayKey(new Date());
const months = computed(() =>
  weeks.value
    .map((week, index) => {
      const first = week.find((d) => d.inYear && d.monthStart);
      return first ? { index, label: first.month + 1 + "月" } : null;
    })
    .filter(Boolean),
);
const total = computed(() =>
  Object.entries(props.counts)
    .filter(([date]) => date.startsWith(String(props.year)))
    .reduce((n, [, count]) => n + count, 0),
);
const selectable = computed(() =>
  weeks.value.flat().filter((d) => d.inYear && !d.future),
);
const focusDay = computed(() =>
  selectable.value.some((d) => d.date === props.selected)
    ? props.selected
    : selectable.value.at(-1)?.date,
);
function label(date: string) {
  return `${date}，${props.counts[date] || 0} 次练习`;
}
async function navigate(event: KeyboardEvent, date: string) {
  const delta = (
    { ArrowLeft: -7, ArrowRight: 7, ArrowUp: -1, ArrowDown: 1 } as Record<
      string,
      number
    >
  )[event.key];
  if (delta === undefined) return;
  event.preventDefault();
  const index = selectable.value.findIndex((d) => d.date === date);
  const target =
    selectable.value[
      Math.max(0, Math.min(selectable.value.length - 1, index + delta))
    ];
  emit("select", target.date);
  await nextTick();
  grid.value
    ?.querySelector<HTMLButtonElement>(`[data-date="${target.date}"]`)
    ?.focus();
}
</script>
<template>
  <div class="contribution-summary">
    <span
      ><b>{{ total }}</b> 次练习</span
    ><span class="contribution-legend" aria-label="练习次数由少到多"
      >少<i
        v-for="level in 5"
        :key="level"
        :class="'contribution-level-' + (level - 1)"
      />多</span
    >
  </div>
  <div class="contribution-scroll" ref="grid">
    <div class="contribution-calendar" :style="{ '--weeks': weeks.length }">
      <div class="contribution-months">
        <span
          v-for="month in months"
          :key="month!.index"
          :style="{ gridColumn: month!.index + 1 }"
          >{{ month!.label }}</span
        >
      </div>
      <div class="contribution-weekdays">
        <span>周日</span><span>周二</span><span>周四</span><span>周六</span>
      </div>
      <div
        class="contribution-weeks"
        role="group"
        :aria-label="year + '年每日练习记录'"
      >
        <div v-for="(week, i) in weeks" :key="i" class="contribution-week">
          <button
            v-for="day in week"
            :key="day.date"
            :data-date="day.date"
            :disabled="!day.inYear || day.future"
            :tabindex="day.date === focusDay ? 0 : -1"
            :aria-label="label(day.date)"
            :title="label(day.date)"
            :aria-pressed="selected === day.date"
            :class="[
              'contribution-day',
              'contribution-level-' + Math.min(props.counts[day.date] || 0, 4),
              {
                'outside-year': !day.inYear,
                'future-day': day.future,
                selected: selected === day.date,
                today: day.date === today,
              },
            ]"
            @click="emit('select', day.date)"
            @keydown="navigate($event, day.date)"
          />
        </div>
      </div>
    </div>
  </div>
</template>
