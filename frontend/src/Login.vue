<template>
  <div class="login-wrap">
    <el-form class="login-card" @submit.prevent="submit">
      <h2>Scope Agent</h2>
      <p class="sub">企业级权责分化与智能协作系统</p>
      <el-form-item>
        <el-input v-model="name" placeholder="用户名" />
      </el-form-item>
      <el-form-item>
        <el-input v-model="password" type="password" placeholder="密码" show-password />
      </el-form-item>
      <el-form-item v-if="isRegister">
        <el-select v-model="role" style="width: 100%">
          <el-option value="user" label="普通用户" />
          <el-option value="employee" label="员工" />
          <el-option value="manager" label="负责人" />
        </el-select>
      </el-form-item>
      <el-button type="primary" style="width: 100%" :loading="loading" @click="submit">
        {{ isRegister ? "注册" : "登录" }}
      </el-button>
      <div class="switch">
        <el-button link type="primary" @click="isRegister = !isRegister">
          {{ isRegister ? "已有账号？去登录" : "没有账号？去注册" }}
        </el-button>
      </div>
    </el-form>
  </div>
</template>

<script setup>
import { ref } from "vue"
import { ElMessage } from "element-plus"
import { login, register } from "./api.js"

const emit = defineEmits(["logged-in"])
const name = ref(""), password = ref(""), role = ref("user"), isRegister = ref(false), loading = ref(false)

async function submit() {
  loading.value = true
  try {
    if (isRegister.value) {
      const r = await register(name.value, password.value, role.value)
      if (!r.ok) { ElMessage.error(r.msg); return }
      ElMessage.success("注册成功，请登录")
      isRegister.value = false
    }
    const res = await login(name.value, password.value)
    if (res.ok) emit("logged-in", res.user, res.token)
    else ElMessage.error(res.msg)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-wrap { display: flex; justify-content: center; align-items: center; height: 100vh; background: #f5f7fa; }
.login-card { width: 360px; padding: 32px; background: #fff; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
h2 { text-align: center; margin: 0 0 4px; }
.sub { text-align: center; color: #999; font-size: 13px; margin: 0 0 24px; }
.switch { text-align: center; margin-top: 8px; }
</style>
