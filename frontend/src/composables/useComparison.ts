import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { v4 as uuidv4 } from 'uuid'
import type { CompareItem, ComparisonDeltaRow, ForecastResult } from '../types/forecast'

const MAX_COMPARE_ITEMS = 4

function findClosestPoint(result: ForecastResult): ForecastResult['series_p50']['points'][number] | null {
  const points = result.series_p50.points
  if (!points.length) return null
  return points[points.length - 1]
}

export function useComparison() {
  const { t } = useI18n()
  const items = ref<CompareItem[]>([])
  const baseId = ref<string | null>(null)

  function addScenario(label: string, res: ForecastResult) {
    if (items.value.length >= MAX_COMPARE_ITEMS) {
      return { ok: false, reason: t('comparison.maxItems', { max: MAX_COMPARE_ITEMS }) }
    }
    const id = uuidv4()
    items.value.push({ id, label, res })
    if (!baseId.value) baseId.value = id
    return { ok: true, reason: null }
  }

  function removeScenario(id: string) {
    items.value = items.value.filter(x => x.id !== id)
    if (baseId.value === id) {
      baseId.value = items.value[0]?.id ?? null
    }
  }

  function clear() {
    items.value = []
    baseId.value = null
  }

  const baseItem = computed(() => items.value.find(x => x.id === baseId.value) ?? null)

  const deltaRows = computed<ComparisonDeltaRow[]>(() => {
    if (!baseItem.value) return []
    const basePoint = findClosestPoint(baseItem.value.res)
    if (!basePoint) return []

    return items.value
      .filter(x => x.id !== baseItem.value!.id)
      .map(item => {
        const point = findClosestPoint(item.res)
        if (!point) {
          return {
            id: item.id,
            label: item.label,
            dim_delta: null,
            milking_delta: 0,
            dry_delta: 0,
            heifer_delta: 0,
            pregnant_heifer_delta: 0,
          }
        }
        return {
          id: item.id,
          label: item.label,
          dim_delta:
            point.avg_days_in_milk === null || basePoint.avg_days_in_milk === null
              ? null
              : point.avg_days_in_milk - basePoint.avg_days_in_milk,
          milking_delta: point.milking_count - basePoint.milking_count,
          dry_delta: point.dry_count - basePoint.dry_count,
          heifer_delta: point.heifer_count - basePoint.heifer_count,
          pregnant_heifer_delta: point.pregnant_heifer_count - basePoint.pregnant_heifer_count,
        }
      })
  })

  return {
    items,
    baseId,
    baseItem,
    deltaRows,
    addScenario,
    removeScenario,
    clear,
    maxItems: MAX_COMPARE_ITEMS,
  }
}
