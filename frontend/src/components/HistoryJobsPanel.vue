<template>
  <section class="card">
    <h2>{{ t('history.title') }}</h2>

    <div class="history-filters">
      <label>
        {{ t('history.status') }}
        <select v-model="history.statusFilter.value">
          <option value="">{{ t('history.statusAll') }}</option>
          <option value="queued">{{ t('history.statusQueued') }}</option>
          <option value="running">{{ t('history.statusRunning') }}</option>
          <option value="succeeded">{{ t('history.statusSucceeded') }}</option>
          <option value="failed">{{ t('history.statusFailed') }}</option>
          <option value="canceled">{{ t('history.statusCanceled') }}</option>
        </select>
      </label>
      <label>
        {{ t('history.search') }}
        <input v-model.trim="history.query.value" :placeholder="t('history.searchPlaceholder')" />
      </label>
      <label>
        {{ t('history.dateFrom') }}
        <input type="date" v-model="history.dateFrom.value" />
      </label>
      <label>
        {{ t('history.dateTo') }}
        <input type="date" v-model="history.dateTo.value" />
      </label>
      <label>
        {{  }}
        <button :disabled="history.loading.value" @click="$emit('refresh')">{{ t('buttons.refresh') }}</button>
      </label>
    </div>

    <div class="history-bulk-actions">
      <button :disabled="history.items.value.length === 0" @click="history.selectCurrentPage">
        {{ t('history.selectPage') }}
      </button>
      <button :disabled="history.selectedIds.value.length === 0" @click="history.clearSelection">
        {{ t('history.clearSelection') }}
      </button>
      <button :disabled="history.selectedIds.value.length === 0" @click="$emit('compare-selected')">
        {{ t('history.bulkCompare') }}
      </button>
      <button :disabled="history.selectedIds.value.length === 0 || history.deleting.value" @click="$emit('delete-selected')">
        {{ t('history.bulkDelete') }}
      </button>
    </div>

    <p v-if="history.loading.value" class="muted">{{ t('common.loading') }}</p>
    <p v-else-if="history.items.value.length === 0" class="muted">{{ t('history.empty') }}</p>

    <div v-else class="table-wrap">
      <table>
        <thead>
          <tr>
            <th></th>
            <th>{{ t('history.jobId') }}</th>
            <th>{{ t('history.datasetId') }}</th>
            <th>{{ t('history.status') }}</th>
            <th>{{ t('run.progress') }}</th>
            <th>{{ t('history.queuedAt') }}</th>
            <th>{{ t('common.actions') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in history.items.value" :key="item.job_id">
            <td>
              <input
                type="checkbox"
                :checked="history.isSelected(item.job_id)"
                @change="history.toggleSelected(item.job_id)"
              />
            </td>
            <td>{{ item.job_id }}</td>
            <td>{{ item.dataset_id }}</td>
            <td>{{ t(`history.statusValue.${item.status}`) }}</td>
            <td>{{ formatNumber(item.progress_pct, localeAsApp) }}%</td>
            <td>{{ formatDate(item.queued_at, localeAsApp) }}</td>
            <td class="row-actions">
              <button @click="$emit('load-job', item.job_id)">{{ t('history.load') }}</button>
              <button :disabled="!item.has_result" @click="$emit('compare-job', item.job_id)">
                {{ t('history.compare') }}
              </button>
              <button :disabled="history.deleting.value" @click="$emit('delete-job', item.job_id)">
                {{ t('common.remove') }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="history-pagination">
      <button :disabled="history.page.value <= 1 || history.loading.value" @click="$emit('prev-page')">
        {{ t('history.prevPage') }}
      </button>
      <span>
        {{ t('history.pageLabel', { page: history.page.value, pages: history.totalPages.value, total: history.total.value }) }}
      </span>
      <button :disabled="history.page.value >= history.totalPages.value || history.loading.value" @click="$emit('next-page')">
        {{ t('history.nextPage') }}
      </button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { HistoryStore } from '../composables/useHistory'
import type { AppLocale } from '../i18n/messages'
import { formatDate, formatNumber } from '../utils/format'

defineProps<{
  history: HistoryStore
}>()

defineEmits<{
  (e: 'refresh'): void
  (e: 'load-job', jobId: string): void
  (e: 'compare-job', jobId: string): void
  (e: 'delete-job', jobId: string): void
  (e: 'compare-selected'): void
  (e: 'delete-selected'): void
  (e: 'prev-page'): void
  (e: 'next-page'): void
}>()

const { t, locale } = useI18n()
const localeAsApp = computed(() => (locale.value === 'ru' ? 'ru' : 'en') as AppLocale)
</script>
