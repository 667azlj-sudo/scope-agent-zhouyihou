<template>
  <div class="login-wrap">
    <el-form class="login-card" @submit.prevent="submit">
      <h2>Scope Agent</h2>
      <p class="sub">让每件事都有负责人</p>

      <!-- 登录 -->
      <template v-if="!isRegister">
        <el-form-item>
          <el-input v-model="account" placeholder="手机号或用户名" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="password" type="password" placeholder="密码" show-password />
        </el-form-item>
      </template>

      <!-- 注册 -->
      <template v-else>
        <el-form-item>
          <div class="phone-row">
            <el-input v-model="phone" placeholder="手机号" />
            <el-button class="code-btn" :disabled="countdown > 0" @click="sendCode">
              {{ countdown > 0 ? countdown + "s" : "获取验证码" }}
            </el-button>
          </div>
        </el-form-item>
        <el-form-item>
          <el-input v-model="code" placeholder="验证码" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="name" placeholder="用户名" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="password" type="password" placeholder="密码" show-password />
        </el-form-item>
        <el-form-item>
          <el-select v-model="role" style="width: 100%" placeholder="选择你的岗位">
            <el-option value="manager" label="负责人" />
            <el-option value="employee" label="员工" />
            <el-option value="user" label="普通成员" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="role === 'manager'">
          <el-input v-model="companyName" placeholder="公司名称" />
        </el-form-item>
        <el-form-item v-if="role === 'employee'">
          <el-input v-model="inviteCode" placeholder="公司邀请码" />
        </el-form-item>
        <el-form-item v-if="role === 'manager' || role === 'employee'">
          <el-input v-model="position" placeholder="公司岗位，如：后端工程师" />
        </el-form-item>
      </template>

      <el-button type="primary" style="width: 100%" :loading="loading" @click="submit">
        {{ isRegister ? "注册" : "登录" }}
      </el-button>
      <div class="switch">
        <el-button link type="primary" @click="toggleMode">
          {{ isRegister ? "已有账号？去登录" : "没有账号？去注册" }}
        </el-button>
      </div>
    </el-form>
  </div>
</template>

<script setup>
import { ref } from "vue"
import { ElMessage } from "element-plus"
import { login, register, smsSend } from "./api.js"

const emit = defineEmits(["logged-in"])
const isRegister = ref(false)
const account = ref(""), name = ref(""), password = ref("")
const phone = ref(""), code = ref(""), role = ref("")
const companyName = ref(""), inviteCode = ref(""), position = ref("")
const loading = ref(false), countdown = ref(0)
let timer = null

function toggleMode() {
  isRegister.value = !isRegister.value
  if (countdown.value > 0) { clearInterval(timer); countdown.value = 0 }
}

async function sendCode() {
  const p = phone.value.trim()
  if (!/^1\d{10}$/.test(p)) { ElMessage.warning("请输入正确的手机号"); return }
  try {
    const r = await smsSend(p)
    if (!r.ok) { ElMessage.error(r.msg || "发送失败"); return }
    if (r.mock && r.code) ElMessage.success("验证码（本地模拟）：" + r.code)
    else ElMessage.success("验证码已发送，请查收短信")
    countdown.value = 60
    timer = setInterval(() => {
      countdown.value -= 1
      if (countdown.value <= 0) { clearInterval(timer); countdown.value = 0 }
    }, 1000)
  } catch (e) {
    ElMessage.error("发送失败：" + (e.message || "请稍后重试"))
  }
}

async function submit() {
  if (isRegister.value) {
    if (!/^1\d{10}$/.test(phone.value.trim())) { ElMessage.warning("请输入正确的手机号"); return }
    if (!code.value.trim()) { ElMessage.warning("请输入验证码"); return }
    if (!name.value.trim()) { ElMessage.warning("请输入用户名"); return }
    if (!role.value) { ElMessage.warning("请选择你的岗位"); return }
    if (role.value === "manager" && !companyName.value.trim()) { ElMessage.warning("请填写公司名称"); return }
    if (role.value === "employee" && !inviteCode.value.trim()) { ElMessage.warning("请填写公司邀请码"); return }
    if ((role.value === "manager" || role.value === "employee") && !position.value.trim()) { ElMessage.warning("请填写公司岗位"); return }
  } else {
    if (!account.value.trim()) { ElMessage.warning("请输入手机号或用户名"); return }
  }
  loading.value = true
  try {
    if (isRegister.value) {
      const r = await register(name.value.trim(), password.value, role.value, phone.value.trim(), code.value.trim(), companyName.value.trim(), inviteCode.value.trim(), position.value.trim())
      if (!r.ok) { ElMessage.error(r.msg); return }
      ElMessage.success("注册成功，请登录")
      toggleMode()
      account.value = phone.value
      password.value = ""
      return
    }
    const res = await login(account.value.trim(), password.value)
    if (res.ok) emit("logged-in", res.user, res.token)
    else ElMessage.error(res.msg)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-wrap { display: flex; justify-content: center; align-items: center; height: 100vh; background: #f5f7fa; }
.login-card { width: min(360px, calc(100vw - 32px)); padding: 32px; background: #fff; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
h2 { text-align: center; margin: 0 0 4px; }
.sub { text-align: center; color: #999; font-size: 13px; margin: 0 0 24px; }
.switch { text-align: center; margin-top: 8px; }
.phone-row { display: flex; gap: 8px; width: 100%; }
.phone-row .el-input { flex: 1; }
.code-btn { flex-shrink: 0; }
</style>
