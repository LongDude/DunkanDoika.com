<template>
  <section class="card">
    <h2>{{ t('comparison.title') }}</h2>

    <div v-if="!baseItem || !rows.length" class="empty-state">{{ t('comparison.empty') }}</div>

    <div v-else class="table-wrap">
      <div class="base-picker">
        <label>
          {{ t('comparison.baseScenario') }}
          <select :value="baseId" @change="$emit('change-base', ($event.target as HTMLSelectElement).value)">
            <option v-for="item in items" :key="item.id" :value="item.id">{{ item.label }}</option>
          </select>
        </label>
      </div>
      <table>
        <thead>
          <tr>
            <th>{{ t('scenario.scenarioName') }}</th>
            <th>{{ t('comparison.dimDelta') }}</th>
            <th>{{ t('comparison.milkingDelta') }}</th>
            <th>{{ t('comparison.dryDelta') }}</th>
            <th>{{ t('comparison.heiferDelta') }}</th>
            <th>{{ t('comparison.pregnantHeiferDelta') }}</th>
            <th>{{ t('common.actions') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.id">
            <td>{{ row.label }}</td>
            <td>{{ row.dim_delta === null ? t('common.notAvailable') : formatNumber(row.dim_delta, localeAsApp, 1) }}</td>
            <td>{{ formatNumber(row.milking_delta, localeAsApp) }}</td>
            <td>{{ formatNumber(row.dry_delta, localeAsApp) }}</td>
            <td>{{ formatNumber(row.heifer_delta, localeAsApp) }}</td>
            <td>{{ formatNumber(row.pregnant_heifer_delta, localeAsApp) }}</td>
            <td><button @click="$emit('remove-item', row.id)">{{ t('common.remove') }}</button></td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { AppLocale } from '../i18n/messages'
import type { CompareItem, ComparisonDeltaRow } from '../types/forecast'
import { formatNumber } from '../utils/format'

defineProps<{
  baseId: string | null
  baseItem: CompareItem | null
  items: CompareItem[]
  rows: ComparisonDeltaRow[]
}>()

defineEmits<{
  (e: 'change-base', id: string): void
  (e: 'remove-item', id: string): void
}>()

const { t, locale } = useI18n()
const localeAsApp = computed(() => (locale.value === 'ru' ? 'ru' : 'en') as AppLocale)
</script>
