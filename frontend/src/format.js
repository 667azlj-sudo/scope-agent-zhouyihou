// format.js —— 把内部状态/枚举映射成用户能看懂的中文文案
export const taskStatus = {
  pending: "待处理",
  pending_classify: "待分级",
  internal: "待分发",
  outsource: "外包候选",
  distributed: "待报价",
  estimated: "待审核报价",
  assigned: "进行中",
  submitted: "已提交",
  approved: "已通过",
  rejected: "已打回",
  done: "已完成",
  pending_review: "待确认",
  negotiating: "协商中",
}

export function statusLabel(s) {
  return taskStatus[s] || s || "—"
}

export function roleLabel(r) {
  return r === "manager" ? "负责人" : r === "employee" ? "员工" : "成员"
}

// difficulty 0~1 → 简单 / 中等 / 困难
export function difficultyLabel(d) {
  const v = Number(d)
  if (Number.isNaN(v)) return "中等"
  if (v < 0.34) return "简单"
  if (v < 0.67) return "中等"
  return "困难"
}

export function money(n) {
  const v = Number(n)
  if (Number.isNaN(v)) return "¥0"
  return "¥" + v.toLocaleString("zh-CN", { minimumFractionDigits: 0, maximumFractionDigits: 2 })
}
