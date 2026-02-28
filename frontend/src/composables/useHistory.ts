import { computed, ref } from 'vue'
import {
  bulkDeleteMyHistoryJobs,
  deleteMyHistoryJob,
  getMyHistoryJob,
  getMyHistoryJobResult,
  listMyHistoryJobs,
} from '../services/api'
import type {
  BulkDeleteResponse,
  ForecastJobStatus,
  ForecastResult,
  HistoryJobDetail,
  HistoryJobItem,
} from '../types/forecast'


const HISTORY_PAGE_LIMIT = 20

export function useHistory() {
  const items = ref<HistoryJobItem[]>([])
  const total = ref(0)
  const page = ref(1)
  const limit = ref(HISTORY_PAGE_LIMIT)
  const statusFilter = ref<'' | ForecastJobStatus>('')
  const query = ref('')
  const dateFrom = ref('')
  const dateTo = ref('')
  const loading = ref(false)
  const deleting = ref(false)
  const lastError = ref<string | null>(null)
  const selectedIds = ref<string[]>([])

  const totalPages = computed(() => Math.max(1, Math.ceil(total.value / limit.value)))
  const selectedSet = computed(() => new Set(selectedIds.value))

  function isSelected(id: string) {
    return selectedSet.value.has(id)
  }

  function toggleSelected(id: string) {
    if (isSelected(id)) {
      selectedIds.value = selectedIds.value.filter(x => x !== id)
      return
    }
    selectedIds.value = [...selectedIds.value, id]
  }

  function clearSelection() {
    selectedIds.value = []
  }

  function selectCurrentPage() {
    selectedIds.value = [...new Set([...selectedIds.value, ...items.value.map(x => x.job_id)])]
  }

  async function fetchPage() {
    loading.value = true
    lastError.value = null
    try {
      const response = await listMyHistoryJobs({
        page: page.value,
        limit: limit.value,
        status: statusFilter.value || undefined,
        q: query.value.trim() || undefined,
        date_from: dateFrom.value || undefined,
        date_to: dateTo.value || undefined,
      })
      items.value = response.items
      total.value = response.total

      const currentIds = new Set(items.value.map(x => x.job_id))
      selectedIds.value = selectedIds.value.filter(id => currentIds.has(id))
    } catch (err) {
      lastError.value = err instanceof Error ? err.message : 'Failed to load history'
      throw err
    } finally {
      loading.value = false
    }
  }

  async function refresh() {
    if (page.value > totalPages.value) {
      page.value = 1
    }
    await fetchPage()
  }

  async function deleteOne(jobId: string): Promise<BulkDeleteResponse> {
    deleting.value = true
    try {
      const response = await deleteMyHistoryJob(jobId)
      await fetchPage()
      selectedIds.value = selectedIds.value.filter(id => id !== jobId)
      return response
    } finally {
      deleting.value = false
    }
  }

  async function deleteSelected(): Promise<BulkDeleteResponse> {
    const ids = selectedIds.value.slice()
    if (ids.length === 0) {
      return { deleted_ids: [], skipped: [] }
    }
    deleting.value = true
    try {
      const response = await bulkDeleteMyHistoryJobs(ids)
      await fetchPage()
      selectedIds.value = []
      return response
    } finally {
      deleting.value = false
    }
  }

  async function getDetail(jobId: string): Promise<HistoryJobDetail> {
    return getMyHistoryJob(jobId)
  }

  async function getResult(jobId: string): Promise<ForecastResult> {
    return getMyHistoryJobResult(jobId)
  }

  return {
    items,
    total,
    page,
    limit,
    totalPages,
    statusFilter,
    query,
    dateFrom,
    dateTo,
    loading,
    deleting,
    lastError,
    selectedIds,
    isSelected,
    toggleSelected,
    clearSelection,
    selectCurrentPage,
    fetchPage,
    refresh,
    deleteOne,
    deleteSelected,
    getDetail,
    getResult,
  }
}

export type HistoryStore = ReturnType<typeof useHistory>
