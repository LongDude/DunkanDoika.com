import { readonly, ref } from 'vue'
import type { UiNotice, UiNoticeLevel } from '../types/ui'

const DEFAULT_TTL_MS = 4500
const noticesState = ref<UiNotice[]>([])
const timers = new Map<string, ReturnType<typeof setTimeout>>()

function makeId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

function removeNotice(id: string) {
  const timer = timers.get(id)
  if (timer) {
    clearTimeout(timer)
    timers.delete(id)
  }
  noticesState.value = noticesState.value.filter(item => item.id !== id)
}

function notify(level: UiNoticeLevel, message: string, ttlMs = DEFAULT_TTL_MS): string {
  const id = makeId()
  noticesState.value = [...noticesState.value, { id, level, message, ttlMs }]
  if (ttlMs > 0) {
    const timer = setTimeout(() => removeNotice(id), ttlMs)
    timers.set(id, timer)
  }
  return id
}

function clearNotices() {
  timers.forEach(timer => clearTimeout(timer))
  timers.clear()
  noticesState.value = []
}

export function useToast() {
  return {
    notices: readonly(noticesState),
    notify,
    removeNotice,
    clearNotices,
  }
}
