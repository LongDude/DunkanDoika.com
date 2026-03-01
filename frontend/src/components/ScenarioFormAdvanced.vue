<template>
  <section class="card">
    <h2>{{ t('scenario.advanced') }}</h2>

    <details open>
      <summary>{{ t('scenario.modelParams') }}</summary>
      <div class="adv-grid">
        <label>
          {{ t('scenario.minFirstInsemAgeDays') }}
          <input type="number" min="250" max="800" v-model.number="editor.form.value.model.min_first_insem_age_days" />
        </label>
        <label>
          {{ t('scenario.voluntaryWaitingPeriod') }}
          <input type="number" min="0" max="200" v-model.number="editor.form.value.model.voluntary_waiting_period" />
        </label>
        <label>
          {{ t('scenario.maxServicePeriodAfterVwp') }}
          <input type="number" min="50" max="600" v-model.number="editor.form.value.model.max_service_period_after_vwp" />
        </label>
        <label>
          {{ t('scenario.populationRegulation') }}
          <input type="number" step="0.01" min="0" max="1" v-model.number="editor.form.value.model.population_regulation" />
        </label>
        <label>
          {{ t('scenario.gestationLo') }}
          <input type="number" min="240" max="320" v-model.number="editor.form.value.model.gestation_lo" />
        </label>
        <label>
          {{ t('scenario.gestationHi') }}
          <input type="number" min="240" max="330" v-model.number="editor.form.value.model.gestation_hi" />
        </label>
        <label>
          {{ t('scenario.gestationMu') }}
          <input type="number" step="0.1" min="240" max="320" v-model.number="editor.form.value.model.gestation_mu" />
        </label>
        <label>
          {{ t('scenario.gestationSigma') }}
          <input type="number" step="0.1" min="0.1" max="20" v-model.number="editor.form.value.model.gestation_sigma" />
        </label>
        <label>
          {{ t('scenario.heiferBirthProb') }}
          <input type="number" step="0.01" min="0" max="1" v-model.number="editor.form.value.model.heifer_birth_prob" />
        </label>
        <label>
          {{ t('scenario.purchasedDaysToCalvingLo') }}
          <input
            type="number"
            min="1"
            max="280"
            v-model.number="editor.form.value.model.purchased_days_to_calving_lo"
          />
        </label>
        <label>
          {{ t('scenario.purchasedDaysToCalvingHi') }}
          <input
            type="number"
            min="1"
            max="330"
            v-model.number="editor.form.value.model.purchased_days_to_calving_hi"
          />
        </label>
      </div>
      <small v-if="modelIssue" class="field-error">{{ modelIssue }}</small>
    </details>

    <details>
      <summary>{{ t('scenario.purchases') }}</summary>
      <div class="purchase-toolbar">
        <button @click="editor.addPurchase()" :disabled="editor.form.value.purchase_policy !== 'manual'">
          {{ t('buttons.addRow') }}
        </button>
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

const modelIssue = computed(() => {
  const issue = props.editor.validationIssues.value.find(
    x => x.field === 'model.gestation' || x.field === 'model.purchased_days_to_calving',
  )
  return issue?.message ?? null
})
</script>
