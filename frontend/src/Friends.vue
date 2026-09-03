<template>
  <div class="friends">
    <el-card class="box" shadow="never">
      <template #header>
        <div class="card-header">
          <span class="title">好友</span>
          <el-tag type="info" effect="plain">共 {{ friends.length }} 位好友</el-tag>
        </div>
      </template>

      <!-- 加好友 -->
      <div class="add-bar">
        <el-input
          v-model="targetId"
          placeholder="输入对方的成员编号"
          type="number"
          clearable
          @keyup.enter="add"
        />
        <el-button type="primary" @click="add">加好友</el-button>
      </div>

      <!-- 分组通讯录 -->
      <el-collapse v-model="active">
        <!-- 新的朋友（负责人可审核） -->
        <el-collapse-item v-if="user.role === 'manager'" name="new">
          <template #title>
            <span class="group-title">新的朋友</span>
            <el-badge v-if="pending.length" :value="pending.length" class="group-badge" />
          </template>
          <div v-for="p in pending" :key="p.id" class="row">
            <div class="row-info">
              <span class="avatar">🙂</span>
              <span class="name">{{ p.name }}</span>
              <el-tag type="warning" size="small" effect="plain">待审核</el-tag>
            </div>
            <div class="row-actions">
              <el-button type="success" size="small" @click="approve(p.id, true)">通过</el-button>
              <el-button type="danger" size="small" plain @click="approve(p.id, false)">拒绝</el-button>
            </div>
          </div>
          <el-empty v-if="!pending.length" :image-size="60" description="暂无待审核" />
        </el-collapse-item>

        <!-- 我的好友 -->
        <el-collapse-item name="friends">
          <template #title>
            <span class="group-title">我的好友</span>
            <span class="group-count">{{ friends.length }}</span>
          </template>
          <div v-for="f in friends" :key="f.id" class="row">
            <div class="row-info">
              <span class="avatar">{{ avatarOf(f.name) }}</span>
              <span class="name">{{ f.name }}</span>
              <el-tag :type="f.role === 'manager' ? 'danger' : 'info'" size="small" effect="plain">
                {{ roleOf(f.role) }}
              </el-tag>
            </div>
          </div>
          <el-empty v-if="!friends.length" :image-size="60" description="还没有好友" />
        </el-collapse-item>
      </el-collapse>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue"
import { getFriends, addFriend, getPendingFriends, approveFriend } from "./api.js"

const props = defineProps(["user"])
const friends = ref([]), pending = ref([]), targetId = ref("")
const active = ref(["new", "friends"])

async function load() {
  friends.value = (await getFriends(props.user.id)).friends || []
  if (props.user.role === "manager") {
    pending.value = (await getPendingFriends()).pending || []
  }
}

async function add() {
  if (!targetId.value) return
  await addFriend(props.user.id, Number(targetId.value), props.user.role)
  targetId.value = ""
  await load()
}

async function approve(id, ok) {
  await approveFriend(id, ok, props.user.role)
  await load()
}

function avatarOf(name) {
  return (name && name.trim().charAt(0)) || "🙂"
}

function roleOf(role) {
  return role === "manager" ? "负责人" : role === "employee" ? "员工" : "成员"
}

onMounted(load)
</script>

<style scoped>
.box { max-width: 720px; margin: 0 auto; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.card-header .title { font-weight: 600; font-size: 18px; }
.add-bar { display: flex; gap: 8px; margin-bottom: 12px; }
.add-bar .el-input { flex: 1; }
.group-title { font-weight: 600; }
.group-badge { margin-left: 8px; }
.group-count { margin-left: 8px; font-size: 12px; color: #999; }
.row { display: flex; justify-content: space-between; align-items: center; padding: 8px 4px; border-bottom: 1px solid #f0f0f0; }
.row:last-child { border-bottom: none; }
.row-info { display: flex; align-items: center; gap: 8px; }
.avatar { width: 28px; height: 28px; border-radius: 50%; background: #eef2ff; display: inline-flex; align-items: center; justify-content: center; color: #2563eb; font-size: 14px; }
.name { font-size: 14px; }
</style>
