import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { getDatasetInfo, listDatasets, uploadDataset } from '../services/api'
import type { DatasetInfo, DatasetQualityIssue, DatasetUploadResponse } from '../types/forecast'

export function useDatasetWorkflow() {
  const { t } = useI18n()
  const dataset = ref<DatasetUploadResponse | null>(null)
  const datasets = ref<DatasetInfo[]>([])
  const datasetsLoading = ref(false)
  const datasetsError = ref<string | null>(null)
  const uploadError = ref<string | null>(null)
  const uploading = ref(false)

  const qualityIssues = computed<DatasetQualityIssue[]>(() => {
    if (!dataset.value) return []
    if (dataset.value.quality_issues && dataset.value.quality_issues.length > 0) {
      return dataset.value.quality_issues
    }
    const issues: DatasetQualityIssue[] = []

    if (!dataset.value.report_date_suggested) {
      issues.push({
        code: 'missing_report_date',
        severity: 'warning',
        message: t('datasetQuality.missingReportDate'),
      })
    }

    if (dataset.value.n_rows < 1000) {
      issues.push({
        code: 'small_dataset',
        severity: 'info',
        message: t('datasetQuality.smallDataset', { rows: dataset.value.n_rows }),
      })
    }

    const totalKnown = Object.values(dataset.value.status_counts).reduce((acc, v) => acc + v, 0)
    if (totalKnown !== dataset.value.n_rows) {
      issues.push({
        code: 'status_mismatch',
        severity: 'warning',
        message: t('datasetQuality.statusMismatch'),
      })
    }

    return issues
  })

  async function upload(file: File) {
    uploading.value = true
    uploadError.value = null
    try {
      dataset.value = await uploadDataset(file)
      await fetchDatasets()
      return dataset.value
    } catch (err) {
      uploadError.value = err instanceof Error ? err.message : t('alerts.uploadFailed')
      throw err
    } finally {
      uploading.value = false
    }
  }

  async function loadById(datasetId: string) {
    uploadError.value = null
    const info = await getDatasetInfo(datasetId)
    dataset.value = info
    return info
  }

  async function fetchDatasets(limit = 100) {
    datasetsLoading.value = true
    datasetsError.value = null
    try {
      datasets.value = await listDatasets(limit)
      return datasets.value
    } catch (err) {
      datasetsError.value = err instanceof Error ? err.message : t('alerts.loadFailed')
      throw err
    } finally {
      datasetsLoading.value = false
    }
  }

  function setDataset(value: DatasetUploadResponse | DatasetInfo | null) {
    dataset.value = value
  }

  function clear() {
    dataset.value = null
    uploadError.value = null
    datasetsError.value = null
    datasets.value = []
  }

  return {
    dataset,
    datasets,
    datasetsLoading,
    datasetsError,
    uploading,
    uploadError,
    qualityIssues,
    upload,
    loadById,
    fetchDatasets,
    setDataset,
    clear,
  }
}
