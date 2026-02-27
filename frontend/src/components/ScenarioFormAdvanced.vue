<template>
  <section class="card">
    <h2>{{ t('scenario.advanced') }}</h2>

    <details>
      <summary>{{ t('scenario.servicePeriod') }}</summary>
      <div class="adv-grid">
        <label>
          {{ t('scenario.meanDays') }}
          <input type="number" min="50" max="250" v-model.number="editor.form.value.service_period.mean_days" />
        </label>
        <label>
          {{ t('scenario.stdDays') }}
          <input type="number" min="0" max="80" v-model.number="editor.form.value.service_period.std_days" />
        </label>
        <label>
          {{ t('scenario.minAfterCalving') }}
          <input type="number" min="0" max="120" v-model.number="editor.form.value.service_period.min_days_after_calving" />
        </label>
      </div>
    </details>

    <details>
      <summary>{{ t('scenario.heiferInsem') }}</summary>
      <div class="adv-grid">
        <label>
          {{ t('scenario.minAgeDays') }}
          <input type="number" min="250" max="700" v-model.number="editor.form.value.heifer_insem.min_age_days" />
        </label>
        <label>
          {{ t('scenario.maxAgeDays') }}
          <input type="number" min="250" max="800" v-model.number="editor.form.value.heifer_insem.max_age_days" />
        </label>
        <small v-if="heiferIssue" class="field-error">{{ heiferIssue }}</small>
      </div>
    </details>

    <details>
      <summary>{{ t('scenario.culling') }}</summary>
      <div class="adv-grid">
        <label class="toggle">
          <span>{{ t('scenario.estimateFromDataset') }}</span>
          <input type="checkbox" v-model="editor.form.value.culling.estimate_from_dataset" />
        </label>
        <label>
          {{ t('scenario.grouping') }}
          <select v-model="editor.form.value.culling.grouping">
            <option value="lactation">{{ t('scenario.groupingLactation') }}</option>
            <option value="lactation_status">{{ t('scenario.groupingLactationStatus') }}</option>
            <option value="age_band">{{ t('scenario.groupingAgeBand') }}</option>
          </select>
        </label>
        <label>
          {{ t('scenario.fallbackMonthlyHazard') }}
          <input type="number" step="0.001" min="0" max="0.2" v-model.number="editor.form.value.culling.fallback_monthly_hazard" />
        </label>
        <label>
          {{ t('scenario.ageBandYears') }}
          <input type="number" min="1" max="10" v-model.number="editor.form.value.culling.age_band_years" />
        </label>
      </div>
    </details>

    <details>
      <summary>{{ t('scenario.replacement') }}</summary>
      <div class="adv-grid">
        <label class="toggle">
          <span>{{ t('scenario.replacementEnabled') }}</span>
          <input type="checkbox" v-model="editor.form.value.replacement.enabled" />
        </label>
        <label>
          {{ t('scenario.annualRatio') }}
          <input type="number" step="0.01" min="0" max="1" v-model.number="editor.form.value.replacement.annual_heifer_ratio" />
        </label>
        <label>
          {{ t('scenario.lookaheadMonths') }}
          <input type="number" min="3" max="36" v-model.number="editor.form.value.replacement.lookahead_months" />
        </label>
      </div>
    </details>

    <details>
      <summary>{{ t('scenario.purchases') }}</summary>
      <div class="purchase-toolbar">
        <button @click="editor.addPurchase()">{{ t('buttons.addRow') }}</button>
        <p>{{ t('scenario.purchaseHint') }}</p>
      </div>
      <table>
        <thead>
          <tr>
            <th>{{ t('scenario.dateIn') }}</th>
            <th>{{ t('scenario.count') }}</th>
            <th>{{ t('scenario.expectedCalvingDate') }}</th>
            <th>{{ t('scenario.daysPregnant') }}</th>
            <th>{{ t('common.actions') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(purchase, index) in editor.form.value.purchases" :key="index">
            <td><input type="date" :lang="dateLang" v-model="purchase.date_in" /></td>
            <td><input type="number" min="1" max="5000" v-model.number="purchase.count" /></td>
            <td><input type="date" :lang="dateLang" v-model="purchase.expected_calving_date" /></td>
            <td><input type="number" min="0" max="280" v-model.number="purchase.days_pregnant" /></td>
            <td><button @click="editor.removePurchase(index)">{{ t('common.remove') }}</button></td>
          </tr>
        </tbody>
      </table>
    </details>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ScenarioEditorStore } from '../composables/useScenarioEditor'

const props = defineProps<{ editor: ScenarioEditorStore }>()
const { t, locale } = useI18n()

const dateLang = computed(() => (locale.value === 'ru' ? 'ru-RU' : 'en-US'))

const heiferIssue = computed(() => {
  const issue = props.editor.validationIssues.value.find(x => x.field === 'heifer_insem')
  return issue?.message ?? null
})
</script>
