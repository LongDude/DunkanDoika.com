<template>
  <footer class="action-footer" :aria-label="t('aria.actionFooter')">
    <div class="action-group">
      <button
        class="primary"
        :disabled="runDisabled.disabled"
        :title="runDisabled.reason ?? ''"
        @click="$emit('run')"
      >
        {{ t('footerBar.runPrimary') }}
      </button>
      <button
        :disabled="runDisabled.disabled"
        :title="runDisabled.reason ?? ''"
        @click="$emit('fast-run')"
      >
        {{ t('footerBar.runFast') }}
      </button>
      <button
        :disabled="saveDisabled.disabled"
        :title="saveDisabled.reason ?? ''"
        @click="$emit('save')"
      >
        {{ t('footerBar.save') }}
      </button>
      <button
        :disabled="undoDisabled.disabled"
        :title="undoDisabled.reason ?? ''"
        @click="$emit('undo')"
      >
        {{ t('buttons.undo') }}
      </button>
    </div>

    <div class="action-group">
      <button
        :disabled="compareDisabled.disabled"
        :title="compareDisabled.reason ?? ''"
        @click="$emit('add-comparison')"
      >
        {{ t('footerBar.addComparison') }}
      </button>
      <button
        :disabled="exportDisabled.disabled"
        :title="exportDisabled.reason ?? ''"
        @click="$emit('export-csv')"
      >
        {{ t('footerBar.exportCsv') }}
      </button>
      <button
        :disabled="exportDisabled.disabled"
        :title="exportDisabled.reason ?? ''"
        @click="$emit('export-xlsx')"
      >
        {{ t('footerBar.exportXlsx') }}
      </button>
    </div>
  </footer>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { DisabledReason } from '../types/forecast'

defineProps<{
  runDisabled: DisabledReason
  saveDisabled: DisabledReason
  exportDisabled: DisabledReason
  compareDisabled: DisabledReason
  undoDisabled: DisabledReason
}>()

defineEmits<{
  (e: 'run'): void
  (e: 'fast-run'): void
  (e: 'save'): void
  (e: 'undo'): void
  (e: 'add-comparison'): void
  (e: 'export-csv'): void
  (e: 'export-xlsx'): void
}>()

const { t } = useI18n()
</script>
