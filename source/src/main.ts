import { createApp } from "vue";
import ElementPlus from "element-plus";
import zhCn from "element-plus/es/locale/lang/zh-cn";
import "element-plus/dist/index.css";
import "./style.css";
import "./personal.css";
import App from "./App.vue";
import { router } from "./router";
import { connectPlatform } from "./services/platform";
import { api, ApiError } from "./services/api";
import { state } from "./store";

// Classroom LAN hosts can provide secure random bytes over HTTP even when randomUUID is unavailable.
if (typeof crypto.randomUUID !== "function") {
  Object.defineProperty(crypto, "randomUUID", { value: () => {
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 15) | 64;
    bytes[8] = (bytes[8] & 63) | 128;
    const hex = Array.from(bytes, b => b.toString(16).padStart(2, "0")).join("");
    return [hex.slice(0,8),hex.slice(8,12),hex.slice(12,16),hex.slice(16,20),hex.slice(20)].join("-");
  }});
}
async function start() {
  if (import.meta.env.VITE_USE_MOCK !== "true") {
    await connectPlatform(api, state, ApiError);
  }
  createApp(App).use(router).use(ElementPlus, { locale: zhCn }).mount("#app");
}
void start();
