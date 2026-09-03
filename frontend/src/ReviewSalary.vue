<template>
  <div class="review-salary">
    <el-card class="panel" shadow="never">
      <template #header>
        <div class="panel-head">
          <span class="panel-title">审核提交</span>
          <span class="desc">审核员工提交的成果，通过后按绩效计价</span>
        </div>
      </template>

      <div v-if="submissions.length">
        <div v-for="s in submissions" :key="s.sid" class="sub-item">
          <div class="sub-head">
            <span class="sub-task">{{ s.task_title }}</span>
            <span class="sub-from">{{ s.agent_name }}</span>
          </div>
          <p class="sub-content">{{ s.content }}</p>
          <div class="sub-actions">
            <span class="sub-exempt">
              <el-checkbox v-model="exemptMap[s.sid]">豁免绩效</el-checkbox>
            </span>
            <div class="sub-btns">
              <el-button size="small" type="success" @click="review(s, true)">通过</el-button>
              <el-button size="small" type="danger" plain @click="review(s, false)">打回</el-button>
            </div>
          </div>
        </div>
      </div>
      <p v-else class="empty">没有待审核的提交</p>
    </el-card>

    <el-card class="panel" shadow="never">
      <template #header>
        <div class="panel-head">
          <span class="panel-title">设置工资</span>
          <span class="desc">为成员设置基础工资与豁免状态</span>
        </div>
      </template>

      <el-form :model="salaryForm" label-width="80px" @submit.prevent>
        <el-form-item label="成员编号">
          <el-input v-model="salaryForm.uid" placeholder="输入成员的编号" clearable />
        </el-form-item>
        <el-form-item label="基础工资">
          <el-input-number
            v-model="salaryForm.baseSalary"
            :min="0"
            :precision="2"
            :step="100"
            controls-position="right"
            placeholder="每月基础工资"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="豁免绩效">
          <el-switch v-model="salaryForm.exempt" active-text="是" inactive-text="否" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="salaryLoading" @click="submitSalary">保存</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted } from "vue"
import { ElMessage } from "element-plus"
import { reviewSubmission, setSalary, getPendingSubmissions } from "./api.js"

const props = defineProps(["user"])
const submissions = ref([])
const exemptMap = reactive({})
const reviewLoading = ref(false)

const salaryForm = reactive({ uid: "", baseSalary: undefined, exempt: false })
const salaryLoading = ref(false)

async function load() {
  try {
    const r = await getPendingSubmissions()
    submissions.value = r.submissions || []
    submissions.value.forEach(s => { exemptMap[s.sid] = false })
  } catch (e) { /* 忽略 */ }
}

async function review(s, approve) {
  reviewLoading.value = true
  try {
    const res = await reviewSubmission(s.sid, approve, !!exemptMap[s.sid])
    ElMessage.success(res.msg || (approve ? "已通过" : "已打回"))
    await load()
  } catch (e) {
    ElMessage.error("操作失败：" + (e.message || "请稍后重试"))
  } finally {
    reviewLoading.value = false
  }
}

async function submitSalary() {
  if (!salaryForm.uid) { ElMessage.warning("请输入成员编号"); return }
  if (salaryForm.baseSalary == null) { ElMessage.warning("请输入基础工资"); return }
  salaryLoading.value = true
  try {
    await setSalary(salaryForm.uid, salaryForm.baseSalary, salaryForm.exempt)
    ElMessage.success("已保存")
    salaryForm.uid = ""; salaryForm.baseSalary = undefined; salaryForm.exempt = false
  } catch (e) {
    ElMessage.error("保存失败：" + (e.message || "请稍后重试"))
  } finally {
    salaryLoading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.review-salary { max-width: 520px; margin: 0 auto; }
.panel { margin-bottom: 16px; border-radius: 14px; }
.panel-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.panel-title { font-weight: 600; }
.panel-head .desc { font-size: 12px; color: var(--muted); }

.sub-item { padding: 12px 0; border-bottom: 1px solid var(--line); }
.sub-item:last-child { border-bottom: none; }
.sub-head { display: flex; justify-content: space-between; align-items: center; gap: 10px; }
.sub-task { font-size: 14px; font-weight: 600; }
.sub-from { font-size: 12px; color: var(--muted); }
.sub-content { margin: 8px 0; font-size: 13px; color: #4b5158; white-space: pre-wrap; }
.sub-actions { display: flex; justify-content: space-between; align-items: center; }
.sub-exempt { font-size: 13px; color: var(--muted); }
.sub-btns { display: flex; gap: 8px; }
.empty { color: var(--muted); text-align: center; padding: 24px 0; }
</style>
