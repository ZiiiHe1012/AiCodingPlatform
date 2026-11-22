<script setup lang="ts">
defineProps<{ name: string; color?: string; size?: number }>();
</script>
<template>
  <span
    class="personal-avatar"
    :class="'avatar-' + (color || 'blue')"
    :style="{
      width: (size || 48) + 'px',
      height: (size || 48) + 'px',
      fontSize: (size || 48) * 0.37 + 'px',
    }"
    :aria-label="name + '的头像'"
    ><svg viewBox="0 0 100 100" aria-hidden="true">
      <circle cx="77" cy="20" r="22" fill="currentColor" opacity=".1" />
      <path d="M0 85L38 47L100 100H0Z" fill="currentColor" opacity=".1" />
      <circle cx="18" cy="22" r="6" fill="currentColor" opacity=".18" /></svg
    ><b>{{ name.slice(0, 1).toUpperCase() }}</b></span
  >
</template>
