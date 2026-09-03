<template>
  <div class="agent-manage">
    <div class="head">
      <h2>Agent 管理</h2>
      <p class="sub">为每位成员绑定一个专属 Agent，职责内的任务会自动派发给它。</p>
    </div>

    <el-form class="agent-form" :model="form" label-width="90px" @submit.prevent="create">
      <el-form-item label="成员编号">
        <el-input v-model="form.userId" placeholder="输入成员的编号" clearable />
      </el-form-item>

      <el-form-item label="角色类型">
        <el-select v-model="form.roleType" placeholder="选择角色" style="width: 100%">
          <el-option label="负责人" value="manager" />
          <el-option label="职能" value="functional" />
          <el-option label="员工" value="employee" />
        </el-select>
      </el-form-item>

      <el-form-item label="Agent 名">
        <el-input v-model="form.name" placeholder="例如：小王的产品 Agent" clearable />
      </el-form-item>

      <el-form-item>
        <el-button type="primary" :loading="loading" @click="create">保存</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup>
import { reactive, ref } from "vue"
import { ElMessage } from "element-plus"
import { createAgent } from "./api.js"

const props = defineProps(["user"])

const form = reactive({ userId: props.user?.id ?? "", roleType: "", name: "" })
const loading = ref(false)

async function create() {
  if (!form.userId) { ElMessage.warning("请输入成员编号"); return }
  if (!form.roleType) { ElMessage.warning("请选择角色"); return }
  if (!form.name) { ElMessage.warning("请输入 Agent 名称"); return }
  loading.value = true
  try {
    await createAgent(form.userId, form.roleType, form.name)
    ElMessage.success("Agent 已绑定")
    form.name = ""
  } catch (e) {
    ElMessage.error("保存失败：" + (e.message || "请稍后重试"))
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.agent-manage { max-width: 520px; margin: 0 auto; }
.head { margin-bottom: 16px; }
.head h2 { margin: 0 0 4px; }
.sub { margin: 0; font-size: 13px; color: var(--muted); }
.agent-form { padding: 24px 24px 8px; background: #fff; border: 1px solid var(--line); border-radius: 14px; }
</style>
