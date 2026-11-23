<script setup lang="ts">
import { ref, computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { state, applyAccount } from "../store";
import { platform } from "../services/platform";
import { api } from "../services/api";
import {
  signOut,
  updateProfile,
  changeLocalPassword,
  avatarColors,
} from "../services/accounts";
import Icon from "../components/Icon.vue";
import LineField from "../components/LineField.vue";
import ProfileAvatar from "../components/ProfileAvatar.vue";
const route = useRoute(),
  router = useRouter();
const login = computed(() => route.path === "/login");
const register = ref(route.query.mode === "register"),
  username = ref(""),
  password = ref(""),
  confirmation = ref(""),
  nickname = ref(login.value ? "" : state.name),
  remember = ref(false),
  busy = ref(false),
  error = ref("");
const errors = ref<Record<string, string>>({});
const bio = ref(state.profile?.bio || ""),
  className = ref(state.profile?.className || ""),
  avatar = ref(state.profile?.avatar || "blue"),
  skills = ref([...(state.profile?.skills || [])]);
const oldPassword = ref(""),
  newPassword = ref(""),
  newConfirmation = ref(""),
  profileBusy = ref(false),
  passwordBusy = ref(false),
  passwordError = ref("");
const colorNames = ["蓝色", "薄荷", "紫色", "琥珀", "玫瑰", "石板"];
function switchMode(value: boolean) {
  register.value = value;
  password.value = confirmation.value = error.value = "";
  errors.value = {};
}
function destination() {
  const value = String(route.query.redirect || "/");
  return value.startsWith("/") &&
    !value.startsWith("//") &&
    !value.startsWith("/login")
    ? value
    : "/";
}
async function auth() {
  if (busy.value) return;
  errors.value = {};
  error.value = "";
  if (!/^[a-zA-Z0-9_]{4,32}$/.test(username.value.trim()))
    errors.value.username = "请输入 4–32 位字母、数字或下划线";
  if (password.value.length < 8 || password.value.length > 64)
    errors.value.password = "请输入 8–64 位密码";
  if (register.value && !nickname.value.trim())
    errors.value.nickname = "请填写昵称";
  if (register.value && confirmation.value !== password.value)
    errors.value.confirmation = "两次输入的密码不一致";
  if (Object.keys(errors.value).length) return;
  busy.value = true;
  try {
    const profile = register.value
      ? await api.register(
          username.value.trim(),
          password.value,
          nickname.value,
          remember.value,
        )
      : await api.login(username.value.trim(), password.value, remember.value);
    applyAccount(profile);
    password.value = confirmation.value = "";
    await router.replace(destination());
    ElMessage.success(register.value ? "账户已创建" : "登录成功");
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
async function saveProfile() {
  profileBusy.value = true;
  try {
    const save = platform?.live ? platform.updateProfile : updateProfile;
    applyAccount(
      await save({
        nickname: nickname.value,
        bio: bio.value,
        className: className.value,
        avatar: avatar.value,
        skills: skills.value,
      }),
    );
    ElMessage.success("个人资料已保存");
  } catch (e) {
    ElMessage.error((e as Error).message);
  } finally {
    profileBusy.value = false;
  }
}
async function changePassword() {
  passwordError.value = "";
  if (newPassword.value !== newConfirmation.value) {
    passwordError.value = "两次输入的新密码不一致";
    return;
  }
  passwordBusy.value = true;
  try {
    if (platform?.live) await platform.changePassword(oldPassword.value, newPassword.value);
    else await changeLocalPassword(oldPassword.value, newPassword.value);
    applyAccount(null);
    oldPassword.value = newPassword.value = newConfirmation.value = "";
    await router.replace("/login");
    ElMessage.success("密码已修改，请重新登录");
  } catch (e) {
    passwordError.value = (e as Error).message;
  } finally {
    passwordBusy.value = false;
  }
}
async function logout(create = false) {
  await platform?.logout();
  signOut();
  applyAccount(null);
  router.replace(create ? "/login?mode=register" : "/login");
}
</script>
<template>
  <div v-if="login" class="account-entry">
    <section class="account-art">
      <div class="account-wordmark">
        <span class="brand-mark"><Icon name="code" :size="25" /></span>CodeLab
      </div>
      <div class="account-art-title">
        <h1>AI Coding<br />工程实践空间</h1>
        <LineField />
      </div>
    </section>
    <section class="account-form-wrap">
      <div class="account-form-box">
        <div class="account-tabs" role="tablist" aria-label="账户操作">
          <button
            role="tab"
            :aria-selected="!register"
            :class="{ active: !register }"
            @click="switchMode(false)"
          >
            登录</button
          ><button
            role="tab"
            :aria-selected="register"
            :class="{ active: register }"
            @click="switchMode(true)"
          >
            注册
          </button>
        </div>
        <h1>{{ register ? "创建账户" : "欢迎回来" }}</h1>
        <form @submit.prevent="auth" novalidate class="account-fields">
          <label
            >用户名<el-input
              v-model="username"
              autocomplete="username"
              maxlength="32"
              placeholder="输入用户名"
              :aria-invalid="!!errors.username"
            /><span v-if="errors.username" class="field-error">{{
              errors.username
            }}</span></label
          >
          <label v-if="register"
            >昵称<el-input
              v-model="nickname"
              autocomplete="nickname"
              maxlength="24"
              placeholder="希望大家如何称呼你"
            /><span v-if="errors.nickname" class="field-error">{{
              errors.nickname
            }}</span></label
          >
          <label
            >密码<el-input
              v-model="password"
              type="password"
              show-password
              :autocomplete="register ? 'new-password' : 'current-password'"
              maxlength="64"
              placeholder="输入密码"
              :aria-invalid="!!errors.password"
            /><span v-if="errors.password" class="field-error">{{
              errors.password
            }}</span></label
          >
          <label v-if="register"
            >确认密码<el-input
              v-model="confirmation"
              type="password"
              show-password
              autocomplete="new-password"
              placeholder="再次输入密码"
            /><span v-if="errors.confirmation" class="field-error">{{
              errors.confirmation
            }}</span></label
          >
          <el-checkbox v-model="remember">保持登录</el-checkbox>
          <p v-if="error" role="alert" class="field-error account-error">
            {{ error }}
          </p>
          <el-button
            native-type="submit"
            type="primary"
            :loading="busy"
            class="full-width"
            >{{ register ? "创建并进入" : "登录"
            }}<Icon name="arrow" :size="17"
          /></el-button>
        </form>
      </div>
    </section>
  </div>
  <template v-else>
    <div class="page-heading">
      <h1>个人设置</h1>
      <RouterLink to="/" class="text-link"
        ><Icon name="back" :size="16" />返回个人主页</RouterLink
      >
    </div>
    <div class="account-settings-grid">
      <section class="panel form-panel">
        <h2>个人资料</h2>
        <form @submit.prevent="saveProfile" class="profile-settings-form">
          <div class="avatar-editor">
            <ProfileAvatar
              :name="nickname || state.name"
              :color="avatar"
              :size="88"
            />
            <div>
              <b>选择头像</b>
              <div class="avatar-options">
                <button
                  v-for="(color, i) in avatarColors"
                  :key="color"
                  type="button"
                  :class="{ selected: avatar === color }"
                  :aria-label="colorNames[i] + '头像'"
                  :aria-pressed="avatar === color"
                  @click="avatar = color"
                >
                  <ProfileAvatar
                    :name="nickname || state.name"
                    :color="color"
                    :size="36"
                  />
                </button>
              </div>
            </div>
          </div>
          <label>昵称<el-input v-model="nickname" maxlength="24" /></label
          ><label
            >个人简介<el-input
              v-model="bio"
              type="textarea"
              :rows="3"
              maxlength="120"
              placeholder="写下你关注的方向" /></label
          ><label
            >所属班级<el-input
              v-model="className"
              maxlength="40"
              placeholder="填写你所属的班级" /></label
          ><label
            >技术标签<el-select
              v-model="skills"
              multiple
              filterable
              allow-create
              default-first-option
              :multiple-limit="5"
              placeholder="最多选择 5 个标签"
              ><el-option
                v-for="skill in [
                  'Vue',
                  'React',
                  'TypeScript',
                  'Python',
                  'Java',
                  'Node.js',
                  '软件测试',
                  '工程设计',
                ]"
                :key="skill"
                :value="skill" /></el-select
          ></label>
          <div>
            <el-button
              type="primary"
              native-type="submit"
              :loading="profileBusy"
              >保存资料</el-button
            >
          </div>
        </form>
      </section>
      <section class="panel form-panel account-security">
        <h2>账户安全</h2>
        <dl>
          <div>
            <dt>用户名</dt>
            <dd>{{ state.profile?.username }}</dd>
          </div>
          <div>
            <dt>身份</dt>
            <dd>
              {{
                { student: "学生", teacher: "教师", admin: "管理员" }[
                  state.role
                ]
              }}
            </dd>
          </div>
        </dl>
        <template v-if="!state.profile?.demo"
          ><h3>修改密码</h3>
          <form @submit.prevent="changePassword" class="profile-settings-form">
            <label
              >原密码<el-input
                v-model="oldPassword"
                type="password"
                show-password
                autocomplete="current-password" /></label
            ><label
              >新密码<el-input
                v-model="newPassword"
                type="password"
                show-password
                autocomplete="new-password"
                placeholder="8–64 位密码" /></label
            ><label
              >确认新密码<el-input
                v-model="newConfirmation"
                type="password"
                show-password
                autocomplete="new-password"
            /></label>
            <p v-if="passwordError" class="field-error" role="alert">
              {{ passwordError }}
            </p>
            <div>
              <el-button native-type="submit" :loading="passwordBusy"
                >修改并重新登录</el-button
              >
            </div>
          </form></template
        >
        <div v-else class="demo-account-action">
          <span class="tag blue">体验账户</span
          ><el-button @click="logout(true)">注册个人账户</el-button>
        </div>
        <div class="divider" />
        <el-button type="danger" plain @click="logout()"
          ><Icon name="logout" :size="16" />退出登录</el-button
        >
      </section>
    </div>
  </template>
</template>
