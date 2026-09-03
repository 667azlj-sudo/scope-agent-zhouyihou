<template>
  <div class="billing">
    <div class="head">
      <h2>套餐订阅</h2>
      <p class="sub">选择合适的套餐解锁更多 Agent 与有效期。</p>
    </div>

    <section class="current" v-if="subscription">
      <div class="current-left">
        <div class="current-name">{{ subscription.plan_name }}</div>
        <div class="current-meta">可建 {{ subscription.agent_limit }} 个 Agent</div>
      </div>
      <div class="current-right">
        <el-tag type="success">生效中</el-tag>
        <div class="expire">至 {{ subscription.expires_at }}</div>
      </div>
    </section>
    <section class="current none" v-else>
      <span>尚未开通套餐</span>
    </section>

    <div class="plan-list">
      <div v-for="p in plans" :key="p.id" class="plan-card" :class="{ free: p.price === 0 }">
        <div class="plan-top">
          <span class="plan-name">{{ p.name }}</span>
          <span class="plan-price">{{ p.price === 0 ? "免费" : money(p.price) }}</span>
        </div>
        <div class="plan-desc">{{ p.description }}</div>
        <div class="plan-meta">
          <span>有效期 {{ p.duration_days }} 天</span>
          <span>· {{ p.agent_limit }} 个 Agent</span>
        </div>
        <el-button
          v-if="p.price > 0"
          type="primary"
          plain
          size="small"
          style="width: 100%"
          :loading="payingPlan === p.id"
          @click="buy(p)"
        >购买</el-button>
        <el-button v-else size="small" disabled style="width: 100%">当前默认</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { getPlans, getSubscription, createOrder, payOrder } from "./api.js"
import { money } from "./format.js"

const props = defineProps(["user"])
const plans = ref([]), subscription = ref(null), payingPlan = ref(null)

async function load() {
  try { plans.value = (await getPlans()).plans || [] } catch (e) { /* 忽略 */ }
  try { subscription.value = await getSubscription(props.user.id) } catch (e) { /* 忽略 */ }
}

async function buy(p) {
  try {
    const order = await createOrder(props.user.id, p.id)
    if (!order.ok) { ElMessage.error(order.msg || "下单失败"); return }
    await ElMessageBox.confirm(`确认支付 ${money(order.amount)} 购买「${order.plan_name}」？（本地模拟支付）`, "支付确认", {
      confirmButtonText: "确认支付",
      cancelButtonText: "取消",
      type: "info",
    })
    payingPlan.value = p.id
    const res = await payOrder(order.order_no)
    if (res.ok) { ElMessage.success("支付成功，套餐已生效"); await load() }
    else ElMessage.error(res.msg || "支付失败")
  } catch (e) {
    if (e !== "cancel" && e !== "close") ElMessage.error("操作失败：" + (e.message || "请稍后重试"))
  } finally {
    payingPlan.value = null
  }
}

onMounted(load)
</script>

<style scoped>
.billing { max-width: 520px; margin: 0 auto; }
.head { margin-bottom: 14px; }
.head h2 { margin: 0 0 4px; }
.sub { margin: 0; font-size: 13px; color: var(--muted); }

.current { display: flex; justify-content: space-between; align-items: center; background: var(--brand-soft); border-radius: 14px; padding: 16px; margin-bottom: 16px; }
.current.none { background: #fff; border: 1px dashed var(--line); color: var(--muted); justify-content: center; }
.current-name { font-size: 16px; font-weight: 700; }
.current-meta { margin-top: 4px; font-size: 12px; color: var(--muted); }
.current-right { text-align: right; }
.expire { margin-top: 6px; font-size: 12px; color: var(--muted); }

.plan-list { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
.plan-card { background: #fff; border: 1px solid var(--line); border-radius: 14px; padding: 16px; display: flex; flex-direction: column; gap: 8px; }
.plan-card.free { border-color: #e4e7ec; }
.plan-top { display: flex; justify-content: space-between; align-items: baseline; }
.plan-name { font-size: 15px; font-weight: 700; }
.plan-price { font-size: 18px; font-weight: 700; color: var(--brand); }
.plan-desc { font-size: 12px; color: var(--muted); }
.plan-meta { font-size: 12px; color: var(--muted); }
</style>
