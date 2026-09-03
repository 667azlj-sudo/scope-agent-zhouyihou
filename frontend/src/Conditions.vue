<template>
  <div class="conditions">
    <div class="head">
      <h2>任务条件库</h2>
      <p class="sub">维护「某类任务需要什么条件」。员工 Agent 会来查询，查不到就通知你补充。</p>
    </div>

    <el-card shadow="never" class="panel">
      <el-form @submit.prevent="add">
        <el-form-item label="关键词">
          <el-input v-model="keywords" placeholder="例如：开发、测试、文案（多个用逗号分隔）" />
        </el-form-item>
        <el-form-item label="条件">
          <el-input v-model="conditions" type="textarea" :rows="2" placeholder="例如：需要熟悉 Python，有 2 年以上后端经验" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="add">添加条件</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" class="panel">
      <h3>已维护的条件</h3>
      <div v-for="c in list" :key="c.id" class="cond-item">
        <div class="cond-kw">{{ c.keywords }}</div>
        <div class="cond-text">{{ c.conditions }}</div>
        <el-button link type="danger" size="small" @click="remove(c.id)">删除</el-button>
      </div>
      <p v-if="!list.length" class="empty">还没有维护任何条件</p>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue"
import { getTaskConditions, addTaskCondition, deleteTaskCondition } from "./api.js"
import { ElMessage } from "element-plus"

const props = defineProps(["user"])
const list = ref([]), keywords = ref(""), conditions = ref(""), loading = ref(false)

async function load() {
  if (!props.user.company_id) return
  try { list.value = (await getTaskConditions(props.user.company_id)).conditions || [] } catch (e) { /* 忽略 */ }
}

async function add() {
  if (!keywords.value.trim()) { ElMessage.warning("请填写关键词"); return }
  if (!conditions.value.trim()) { ElMessage.warning("请填写条件"); return }
  loading.value = true
  try {
    await addTaskCondition(props.user.company_id, keywords.value.trim(), conditions.value.trim())
    keywords.value = ""; conditions.value = ""
    await load()
    ElMessage.success("已添加")
  } catch (e) {
    ElMessage.error("添加失败：" + (e.message || "请重试"))
  } finally {
    loading.value = false
  }
}

async function remove(id) {
  await deleteTaskCondition(id)
  await load()
}

onMounted(load)
</script>

<style scoped>
.conditions { max-width: 520px; margin: 0 auto; }
.head { margin-bottom: 14px; }
.head h2 { margin: 0 0 4px; }
.sub { margin: 0; font-size: 13px; color: var(--muted); }
.panel { margin-bottom: 16px; border-radius: 14px; }
.panel h3 { margin: 0 0 10px; font-size: 14px; }
.cond-item { display: flex; align-items: center; gap: 10px; padding: 10px 0; border-bottom: 1px solid var(--line); }
.cond-item:last-child { border-bottom: none; }
.cond-kw { font-size: 12px; color: var(--brand); background: var(--brand-soft); padding: 2px 8px; border-radius: 8px; flex-shrink: 0; }
.cond-text { flex: 1; font-size: 13px; color: #4b5158; }
.empty { color: var(--muted); text-align: center; padding: 16px 0; }
</style>
