<template>
  <div class="secret-kb">
    <div class="head">
      <h2>🔒 公司机密知识库</h2>
      <p class="sub">仅经理可维护。经理 Agent 访问前会提交申请，说明原因 / 用途 / 风险，你批准后才放行。</p>
    </div>

    <!-- 上传本地机密文件 -->
    <el-card shadow="never" class="panel">
      <h3>上传本地机密文件</h3>
      <p class="hint">支持 .txt / .md / .log / .csv / .json 等文本类文件，解析后写入本公司机密库。</p>
      <div class="upload-row">
        <el-button type="primary" :loading="uploading" @click="pickFile">📁 选择文件</el-button>
        <span v-if="selectedNames.length" class="sel">{{ selectedNames.join(', ') }}</span>
      </div>
      <input ref="fileInput" type="file" multiple hidden @change="onPick" />
    </el-card>

    <!-- 待审批的访问申请 -->
    <el-card shadow="never" class="panel">
      <div class="panel-head">
        <h3>访问申请</h3>
        <el-button link size="small" @click="showAll = !showAll">{{ showAll ? '只看待审批' : '查看全部' }}</el-button>
      </div>
      <div v-for="r in filteredReqs" :key="r.id" class="req-item">
        <div class="req-top">
          <span class="req-agent">{{ r.agent_name || '经理 Agent' }}</span>
          <el-tag size="small" :type="r.status === 'pending' ? 'warning' : r.status === 'approved' ? 'success' : 'danger'">
            {{ r.status === 'pending' ? '待审批' : r.status === 'approved' ? '已批准' : '已拒绝' }}
          </el-tag>
        </div>
        <div class="req-query">检索：{{ r.query }}</div>
        <div class="req-field"><b>为什么需要：</b>{{ r.why || '（未填写）' }}</div>
        <div class="req-field"><b>项目用途：</b>{{ r.usage || '（未填写）' }}</div>
        <div class="req-field danger"><b>潜在危险：</b>{{ r.danger || '（未填写）' }}</div>
        <div v-if="r.status === 'pending'" class="req-actions">
          <el-button size="small" type="success" @click="approve(r, 'once')">批准（仅本次）</el-button>
          <el-button size="small" type="primary" plain @click="approve(r, 'window')">批准（限时自由访问）</el-button>
          <el-button size="small" type="danger" plain @click="review(r, false)">拒绝</el-button>
        </div>
      </div>
      <p v-if="!filteredReqs.length" class="empty">暂无访问申请</p>
    </el-card>

    <!-- 已入库条目 -->
    <el-card shadow="never" class="panel">
      <h3>已入库机密条目（{{ entries.length }}）</h3>
      <div v-for="e in entries" :key="e.id" class="entry-item">
        <span class="entry-text">{{ e.content }}</span>
        <el-button link type="danger" size="small" @click="remove(e.id)">删除</el-button>
      </div>
      <p v-if="!entries.length" class="empty">机密库为空，请先上传</p>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue"
import { getSecretKb, deleteSecretKb, getSecretKbRequests, reviewSecretKbRequest, uploadSecretKb } from "./api.js"
import { ElMessage, ElMessageBox } from "element-plus"

const props = defineProps(["user"])
const entries = ref([]), requests = ref([])
const selectedNames = ref([]), uploading = ref(false), showAll = ref(false)
const fileInput = ref(null)

const filteredReqs = computed(() => showAll.value ? requests.value : requests.value.filter(r => r.status === "pending"))

async function load() {
  try {
    const [k, r] = [await getSecretKb(), await getSecretKbRequests()]
    entries.value = k.entries || []
    requests.value = r.requests || []
  } catch (e) { /* 忽略 */ }
}

function pickFile() { if (fileInput.value) fileInput.value.click() }

async function onPick(e) {
  const files = Array.from(e.target.files || [])
  e.target.value = ""
  if (!files.length) return
  selectedNames.value = files.map(f => f.name)
  uploading.value = true
  try {
    const r = await uploadSecretKb(files)
    if (r.ok) { ElMessage.success(r.msg || `已导入 ${r.count} 条`); selectedNames.value = []; await load() }
    else ElMessage.error(r.msg || "上传失败")
  } catch (err) {
    ElMessage.error("上传失败：" + (err.message || "请重试"))
  } finally {
    uploading.value = false
  }
}

async function approve(r, mode) {
  const tip = mode === 'window'
    ? '批准后该经理 Agent 可在一段时间内自由检索机密库（粒度较宽）。确定？'
    : '批准后仅放行本次检索，换检索词需重新申请。确定？'
  try { await ElMessageBox.confirm(tip, "批准访问") } catch (e) { return }
  const r2 = await reviewSecretKbRequest(r.id, true, mode)
  if (r2.ok) { ElMessage.success(r2.msg || "已批准"); await load() }
  else ElMessage.error(r2.msg || "操作失败")
}

async function review(r, approve) {
  const r2 = await reviewSecretKbRequest(r.id, approve, "once")
  if (r2.ok) { ElMessage.success(r2.msg || "已处理"); await load() }
  else ElMessage.error(r2.msg || "操作失败")
}

async function remove(id) {
  try { await ElMessageBox.confirm("确定删除该机密条目？", "删除确认") } catch (e) { return }
  await deleteSecretKb(id)
  await load()
}

onMounted(load)
</script>

<style scoped>
.secret-kb { max-width: 520px; margin: 0 auto; }
.head { margin-bottom: 14px; }
.head h2 { margin: 0 0 4px; }
.sub { margin: 0; font-size: 13px; color: var(--muted); }
.panel { margin-bottom: 16px; border-radius: 14px; }
.panel h3 { margin: 0 0 10px; font-size: 14px; }
.panel-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.hint { font-size: 12px; color: var(--muted); margin: 0 0 10px; }
.upload-row { display: flex; align-items: center; gap: 10px; }
.sel { font-size: 12px; color: var(--muted); }
.req-item { padding: 10px 0; border-bottom: 1px solid var(--line); }
.req-item:last-child { border-bottom: none; }
.req-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.req-agent { font-weight: 600; font-size: 13px; }
.req-query { font-size: 13px; color: var(--brand); margin-bottom: 4px; }
.req-field { font-size: 12px; color: #4b5158; margin-top: 2px; }
.req-field.danger { color: #b7791f; }
.req-actions { margin-top: 8px; }
.entry-item { display: flex; align-items: flex-start; gap: 10px; padding: 10px 0; border-bottom: 1px solid var(--line); }
.entry-item:last-child { border-bottom: none; }
.entry-text { flex: 1; font-size: 13px; color: #4b5158; white-space: pre-wrap; word-break: break-word; }
.empty { color: var(--muted); text-align: center; padding: 16px 0; }
</style>
