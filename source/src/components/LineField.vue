<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from "vue";
const canvas = ref<HTMLCanvasElement>();
const active = ref(false);
let raf = 0;
let observer: ResizeObserver;
let dprQuery: MediaQueryList;
let visible = true;
let pointer = { x: -1000, y: -1000 };
let last = 0;
const light = new Float32Array(3600);
const weights = [0.38, 1.12, 2.28, 3.8];
const alpha = [0.15, 0.64, 0.93, 1];
const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
let seed = 7319;
const noise = new Float32Array(128 * 128);
for (let i = 0; i < noise.length; i++) {
  seed ^= seed << 13;
  seed ^= seed >>> 17;
  seed ^= seed << 5;
  noise[i] = ((seed >>> 0) / 4294967295) * 2 - 1;
}
function n(x: number, y: number) {
  const xx = Math.floor(x),
    yy = Math.floor(y),
    fx = x - xx,
    fy = y - yy,
    sx = fx * fx * (3 - 2 * fx),
    sy = fy * fy * (3 - 2 * fy);
  const at = (a: number, b: number) =>
    noise[(((b % 128) + 128) % 128) * 128 + (((a % 128) + 128) % 128)];
  return (
    (at(xx, yy) * (1 - sx) + at(xx + 1, yy) * sx) * (1 - sy) +
    (at(xx, yy + 1) * (1 - sx) + at(xx + 1, yy + 1) * sx) * sy
  );
}
function draw(t = 0) {
  const c = canvas.value;
  if (!c) return;
  const ctx = c.getContext("2d")!;
  const r = c.getBoundingClientRect(),
    dpr = window.devicePixelRatio || 1;
  if (
    c.width !== Math.round(r.width * dpr) ||
    c.height !== Math.round(r.height * dpr)
  ) {
    c.width = Math.round(r.width * dpr);
    c.height = Math.round(r.height * dpr);
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, r.width, r.height);
  const cell = Math.min(r.width / 65, r.height / 33);
  const ox = (r.width - cell * 60) / 2,
    oy = (r.height - cell * 30) / 2;
  const buckets = [new Path2D(), new Path2D(), new Path2D(), new Path2D()];
  let best = { v: 0, x: 0, y: 0 };
  for (let x = 0; x < 60; x++)
    for (let y = 0; y < 30; y++) {
      const value =
        ((light[y * 120 + x] + light[y * 120 + 60 + x]) / 2) * 0.94 +
        n(x * 0.15, y * 0.16 - t * 0.00017) * 0.04;
      const b = value < 0.12 ? 0 : value < 0.42 ? 1 : value < 0.89 ? 2 : 3;
      let px = ox + x * cell,
        py = oy + y * cell;
      const dx = px - pointer.x,
        dy = py - pointer.y,
        dist = Math.hypot(dx, dy),
        push = active.value ? Math.max(0, 1 - dist / 65) ** 2 * 8 : 0;
      px += (dx / (dist || 1)) * push;
      py += (dy / (dist || 1)) * push * 0.58;
      buckets[b].moveTo(px, py);
      buckets[b].lineTo(px, py + cell - 0.7);
      if (value > best.v) {
        best = { v: value, x: px, y: py };
      }
    }
  ctx.strokeStyle = "#9fb8ff";
  weights.forEach((w, i) => {
    ctx.globalAlpha = alpha[i];
    ctx.lineWidth = (w * cell) / 5.25;
    ctx.stroke(buckets[i]);
  });
  if (active.value && pointer.x > 0) {
    ctx.globalAlpha = 0.6;
    ctx.strokeStyle = "#d6e2ff";
    ctx.lineWidth = 1;
    ctx.strokeRect(best.x - 20, best.y - 14, 40, 28);
  }
  ctx.globalAlpha = 1;
  last = t;
  if (active.value && !document.hidden && visible && !reduced.matches)
    raf = requestAnimationFrame(draw);
}
function toggle() {
  active.value = !active.value;
  cancelAnimationFrame(raf);
  draw(last);
}
function move(e: PointerEvent) {
  const r = canvas.value!.getBoundingClientRect();
  pointer = { x: e.clientX - r.left, y: e.clientY - r.top };
  if (!active.value) draw(last);
}
function visibility() {
  cancelAnimationFrame(raf);
  draw(last);
}
function dprChange() {
  dprQuery?.removeEventListener("change", dprChange);
  dprQuery = matchMedia(`(resolution: ${devicePixelRatio}dppx)`);
  dprQuery.addEventListener("change", dprChange);
  cancelAnimationFrame(raf);
  draw(last);
}
let intersection: IntersectionObserver;
onMounted(() => {
  const off = document.createElement("canvas");
  off.width = off.height = 300;
  const c = off.getContext("2d")!;
  c.fillStyle = "black";
  c.fillRect(0, 0, 300, 300);
  c.fillStyle = "white";
  c.translate(150, 150);
  c.scale(10, 10);
  c.translate(-12, -12);
  c.fill(
    new Path2D(
      "M8 4L0 12L8 20L10 17L5 12L10 7Z M16 4L14 7L19 12L14 17L16 20L24 12Z M13 3L9 21L12 21L16 3Z",
    ),
  );
  const pixels = c.getImageData(0, 0, 300, 300).data;
  for (let y = 0; y < 60; y++)
    for (let x = 0; x < 60; x++) {
      let sum = 0;
      for (let sy = 0; sy < 5; sy++)
        for (let sx = 0; sx < 5; sx++)
          sum += pixels[((y * 5 + sy) * 300 + x * 5 + sx) * 4] / 255;
      light[y * 60 + x] = sum / 25;
    }
  off.width = off.height = 0;
  observer = new ResizeObserver(() => {
    cancelAnimationFrame(raf);
    draw(last);
  });
  observer.observe(canvas.value!);
  intersection = new IntersectionObserver((e) => {
    visible = e[0].isIntersecting;
    visibility();
  });
  intersection.observe(canvas.value!);
  document.addEventListener("visibilitychange", visibility);
  reduced.addEventListener("change", visibility);
  dprChange();
});
onBeforeUnmount(() => {
  cancelAnimationFrame(raf);
  observer?.disconnect();
  intersection?.disconnect();
  document.removeEventListener("visibilitychange", visibility);
  dprQuery?.removeEventListener("change", dprChange);
  reduced.removeEventListener("change", visibility);
});
</script>
<template>
  <div class="line-field">
    <canvas
      ref="canvas"
      aria-hidden="true"
      @pointermove="move"
      @pointerleave="pointer = { x: -1000, y: -1000 }"
    />
    <div class="field-caption">
      <button :aria-pressed="active" aria-label="切换线场动效" @click="toggle">
        {{ active ? "Ⅱ" : "▷" }}
      </button>
    </div>
  </div>
</template>
