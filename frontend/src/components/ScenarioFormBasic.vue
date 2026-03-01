<template>
  <section class="card">
    <h2>{{ t('scenario.basic') }}</h2>

    <div class="scenario-top">
      <label>
        {{ t('scenario.scenarioName') }}
        <input v-model="editor.scenarioName.value" :placeholder="t('scenario.scenarioNamePlaceholder')" />
      </label>

      <label>
        {{ t('scenario.preset') }}
        <select v-model="presetModel" @change="$emit('apply-preset', presetModel)">
          <option value="baseline">{{ t('scenario.presetBaseline') }}</option>
          <option value="conservative">{{ t('scenario.presetConservative') }}</option>
          <option value="aggressive">{{ t('scenario.presetAggressive') }}</option>
        </select>
      </label>
    </div>

    <div class="scenario-grid">
      <label>
        {{ t('scenario.reportDate') }}
        <input type="date" :lang="dateLang" v-model="editor.form.value.report_date" readonly disabled />
        <small class="muted">{{ t('scenario.reportDateLocked') }}</small>
        <small v-if="fieldIssue('report_date')" class="field-error">{{ fieldIssue('report_date') }}</small>
      </label>
      <label>
        {{ t('scenario.horizonMonths') }}
        <input type="number" min="1" max="120" v-model.number="editor.form.value.horizon_months" />
        <small v-if="fieldIssue('horizon_months')" class="field-error">{{ fieldIssue('horizon_months') }}</small>
      </label>
      <label>
        {{ t('scenario.futureDate') }}
        <input type="date" :lang="dateLang" v-model="editor.form.value.future_date" />
        <small v-if="fieldIssue('future_date')" class="field-error">{{ fieldIssue('future_date') }}</small>
      </label>
      <label>
        {{ t('scenario.mcRuns') }}
        <input type="number" min="1" max="30000" v-model.number="editor.form.value.mc_runs" />
        <small v-if="fieldIssue('mc_runs')" class="field-error">{{ fieldIssue('mc_runs') }}</small>
      </label>
      <label>
        {{ t('scenario.seed') }}
        <input type="number" v-model.number="editor.form.value.seed" />
      </label>
      <label>
        {{ t('scenario.mode') }}
        <select v-model="editor.form.value.mode">
          <option value="empirical">{{ t('scenario.modeEmpirical') }}</option>
          <option value="theoretical">{{ t('scenario.modeTheoretical') }}</option>
        </select>
      </label>
      <label>
        {{ t('scenario.purchasePolicy') }}
        <select v-model="editor.form.value.purchase_policy">
          <option value="manual">{{ t('scenario.policyManual') }}</option>
          <option value="auto_counter">{{ t('scenario.policyAutoCounter') }}</option>
          <option value="auto_forecast">{{ t('scenario.policyAutoForecast') }}</option>
        </select>
      </label>
      <label>
        {{ t('scenario.leadTimeDays') }}
        <input type="number" min="1" max="365" v-model.number="editor.form.value.lead_time_days" />
      </label>
      <label>
        {{ t('scenario.confidenceCentral') }}
        <input type="number" min="0.5" max="0.99" step="0.01" v-model.number="editor.form.value.confidence_central" />
        <small v-if="fieldIssue('confidence_central')" class="field-error">{{ fieldIssue('confidence_central') }}</small>
      </label>
    </div>

    <div class="validation-block" v-if="editor.validationIssues.value.length">
      <h3>{{ t('validation.title') }}</h3>
      <ul>
        <li v-for="issue in editor.validationIssues.value" :key="`${issue.field}:${issue.message}`">{{ issue.message }}</li>
      </ul>
    </div>

    <div class="saved-scenarios" v-if="editor.scenarioList.value.length">
      <h3>{{ t('scenario.savedScenarios') }}</h3>
      <table>
        <thead>
          <tr>
            <th>{{ t('scenario.scenarioName') }}</th>
            <th>{{ t('scenario.createdAt') }}</th>
            <th>{{ t('scenario.reportDate') }}</th>
            <th>{{ t('scenario.horizonMonths') }}</th>
            <th>{{ t('common.actions') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in editor.scenarioList.value" :key="item.scenario_id">
            <td>
              {{ item.name }}
              <span v-if="item.is_legacy" class="muted"> ({{ t('scenario.legacyTag') }})</span>
            </td>
            <td>{{ formatDate(item.created_at, localeAsApp) }}</td>
            <td>{{ formatDate(item.report_date ?? null, localeAsApp) }}</td>
            <td>{{ formatNumber(item.horizon_months ?? null, localeAsApp) }}</td>
            <td class="row-actions">
              <button
                @click="$emit('load-scenario', item.scenario_id)"
                :disabled="item.is_legacy"
                :title="item.legacy_reason ?? ''"
              >
                {{ t('buttons.load') }}
              </button>
              <button
                @click="$emit('run-scenario', item.scenario_id)"
                :disabled="item.is_legacy"
                :title="item.legacy_reason ?? ''"
              >
                {{ t('buttons.runSaved') }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ScenarioPreset } from '../types/forecast'
import type { ScenarioEditorStore } from '../composables/useScenarioEditor'
import type { AppLocale } from '../i18n/messages'
import { formatDate, formatNumber } from '../utils/format'

const props = defineProps<{
  editor: ScenarioEditorStore
}>()

defineEmits<{
  (e: 'apply-preset', preset: ScenarioPreset): void
  (e: 'load-scenario', id: string): void
  (e: 'run-scenario', id: string): void
}>()

const { t, locale } = useI18n()

const presetModel = computed({
  get: () => props.editor.activePreset.value,
  set: value => {
    props.editor.activePreset.value = value
  },
})

const dateLang = computed(() => (locale.value === 'ru' ? 'ru-RU' : 'en-US'))
const localeAsApp = computed(() => (locale.value === 'ru' ? 'ru' : 'en') as AppLocale)

function fieldIssue(field: string) {
  const issue = props.editor.validationIssues.value.find(x => x.field === field)
  return issue?.message ?? null
}
</script>
