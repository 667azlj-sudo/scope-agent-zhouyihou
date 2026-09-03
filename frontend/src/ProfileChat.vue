<template>
  <section class="card">
    <div class="card-title">个人画像与智能问答</div>
    <p class="desc">把你的信息与习惯告诉专属 Agent，它会据此为你个性化作答</p>

    <div class="field">
      <label>基本信息（职业 / 经验 / 技能）</label>
      <el-input v-model="info" type="textarea" :rows="2" placeholder="例：我是后端开发，3 年经验，主要负责 API 与数据库" />
    </div>
    <div class="field">
      <label>习惯与偏好（作息 / 沟通 / 工具）</label>
      <el-input v-model="habits" type="textarea" :rows="2" placeholder="例：上午深度工作，喜欢简洁文档，常用 Python" />
    </div>
    <div class="actions">
      <el-button type="primary" :loading="saving" @click="save">保存画像</el-button>
      <el-button :loading="indexing" @click="index">索引进知识库</el-button>
    </div>

    <div class="divider"></div>

    <div class="chat">
      <div v-for="(m, i) in history" :key="i" class="msg">
        <div class="q">🙋 {{ m.q }}</div>
        <div class="a">{{ m.a }}</div>
        <div v-if="m.sources && m.sources.length" class="src">
          参考片段：
          <span v-for="(s, j) in m.sources" :key="j" class="chip">{{ s.text }}</span>
        </div>
      </div>
      <div v-if="asking" class="msg"><div class="a thinking">正在思考…</div></div>
      <div v-if="!history.length && !asking" class="hint">问问它，比如「我该学什么语言」「帮我梳理最近的工作」</div>
    </div>

    <div class="ask-row">
      <el-input v-model="question" placeholder="问点什么…" @keyup.enter="ask" />
      <el-button type="primary" :loading="asking" :disabled="!question.trim()" @click="ask">发送</el-button>
    </div>
  </section>
</template>

<script setup>
import { ref, onMounted } from "vue"
import { ElMessage } from "element-plus"
import { getProfile, setProfile, agentChat, indexProfile } from "./api.js"

const props = defineProps(["user"])
const info = ref(""), habits = ref("")
const saving = ref(false), indexing = ref(false), asking = ref(false)
const question = ref("")
const history = ref([])

onMounted(async () => {
  try {
    const r = await getProfile(props.user.id)
    if (r.profile) {
      info.value = r.profile.info || ""
      habits.value = r.profile.habits || ""
    }
  } catch (e) { /* 忽略 */ }
})

async function save() {
  saving.value = true
  try {
    const r = await setProfile(props.user.id, info.value, habits.value)
    if (r.ok) ElMessage.success("画像已保存")
    else ElMessage.error(r.msg || "保存失败")
  } catch (e) {
    ElMessage.error("保存失败：" + (e.message || ""))
  } finally { saving.value = false }
}

async function index() {
  indexing.value = true
  try {
    const r = await indexProfile(props.user.id)
    ElMessage.success("已索引 " + (r.count ?? 0) + " 条到本地知识库")
  } catch (e) {
    ElMessage.error("索引失败：" + (e.message || ""))
  } finally { indexing.value = false }
}

async function ask() {
  const q = question.value.trim()
  if (!q) return
  history.value.push({ q, a: "", sources: [] })
  question.value = ""
  asking.value = true
  try {
    const r = await agentChat(q, props.user.id)
    const last = history.value[history.value.length - 1]
    if (r.ok) {
      last.a = r.answer || "（无回答）"
      last.sources = r.sources || []
    } else {
      last.a = "出错了：" + (r.msg || "未知错误")
    }
  } catch (e) {
    const last = history.value[history.value.length - 1]
    last.a = "请求失败：" + (e.message || "")
  } finally { asking.value = false }
}
</script>

<style scoped>
.card { background: #fff; border: 1px solid var(--line); border-radius: 14px; padding: 16px; margin-bottom: 16px; }
.card-title { font-size: 14px; font-weight: 600; margin-bottom: 4px; }
.desc { font-size: 12px; color: var(--muted); margin: 0 0 12px; }
.field { margin-bottom: 12px; }
.field label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 6px; }
.actions { display: flex; gap: 8px; }
.divider { height: 1px; background: var(--line); margin: 16px 0; }
.chat { max-height: 320px; overflow-y: auto; }
.msg { margin-bottom: 12px; }
.q { font-size: 13px; font-weight: 600; color: var(--brand); margin-bottom: 4px; }
.a { font-size: 14px; white-space: pre-wrap; line-height: 1.6; }
.a.thinking { color: var(--muted); }
.src { margin-top: 6px; font-size: 12px; color: var(--muted); display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.chip { background: #f2f3f5; border-radius: 6px; padding: 2px 6px; max-width: 100%; overflow: hidden; text-overflow: ellipsis; }
.hint { font-size: 12px; color: var(--muted); padding: 12px 0; }
.ask-row { display: flex; gap: 8px; margin-top: 12px; }
.ask-row .el-input { flex: 1; }
</style>
