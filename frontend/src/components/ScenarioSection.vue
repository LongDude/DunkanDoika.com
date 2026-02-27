<template>
  <section class="card" v-if="page.dataset.value">
    <h2>{{ t('scenario.sectionTitle') }}</h2>

    <div class="row controls-row">
      <div class="row controls-group">
        <label class="inline">
          {{ t('scenario.name') }}
          <input v-model="page.scenarioName.value" :placeholder="t('scenario.namePlaceholder')" style="min-width:260px" />
        </label>
        <button @click="page.saveScenario" :disabled="page.saving.value || !page.scenarioName.value">{{ t('scenario.save') }}</button>
        <button @click="page.runForecast" :disabled="page.running.value">{{ t('scenario.run') }}</button>
        <button @click="page.addToCompare" :disabled="!page.result.value">{{ t('scenario.addToCompare') }}</button>
        <button @click="page.clearCompare" :disabled="page.compare.value.length === 0">{{ t('scenario.clearCompare') }}</button>
      </div>

      <div class="row controls-group">
        <button @click="page.exportCsv" :disabled="page.running.value">{{ t('scenario.exportCsv') }}</button>
        <button @click="page.exportXlsx" :disabled="page.running.value">{{ t('scenario.exportXlsx') }}</button>
      </div>
    </div>

    <div class="grid4 top-form">
      <label>
        {{ t('scenario.reportDate') }}
        <input type="date" v-model="page.reportDate.value" />
      </label>
      <label>
        {{ t('scenario.horizonMonths') }}
        <input type="number" min="1" max="120" v-model.number="page.horizonMonths.value" />
      </label>
      <label>
        {{ t('scenario.futureDateOptional') }}
        <input type="date" v-model="page.futureDate.value" />
      </label>
      <label>
        {{ t('scenario.mcRuns') }}
        <input type="number" min="1" max="300" v-model.number="page.mcRuns.value" />
      </label>
    </div>

    <details style="margin-top:10px" open>
      <summary>{{ t('scenario.modelParams') }}</summary>
      <div class="grid4" style="margin-top:10px">
        <div class="subcard">
          <h3>{{ t('scenario.servicePeriod') }}</h3>
          <label>{{ t('scenario.meanDays') }} <input type="number" v-model.number="page.spMean.value" min="50" max="250" /></label>
          <label>{{ t('scenario.stdDays') }} <input type="number" v-model.number="page.spStd.value" min="0" max="80" /></label>
          <label>{{ t('scenario.minAfterCalving') }} <input type="number" v-model.number="page.spMin.value" min="0" max="120" /></label>
        </div>
        <div class="subcard">
          <h3>{{ t('scenario.heiferInsem') }}</h3>
          <label>{{ t('scenario.minAgeDays') }} <input type="number" v-model.number="page.hMin.value" min="250" max="700" /></label>
          <label>{{ t('scenario.maxAgeDays') }} <input type="number" v-model.number="page.hMax.value" min="250" max="800" /></label>
        </div>
        <div class="subcard">
          <h3>{{ t('scenario.culling') }}</h3>
          <label class="row between">
            <span>{{ t('scenario.estimateFromDataset') }}</span>
            <input type="checkbox" v-model="page.cullEstimate.value" />
          </label>
          <label>{{ t('scenario.grouping') }}
            <select v-model="page.cullGrouping.value">
              <option value="lactation">lactation</option>
              <option value="lactation_status">lactation_status</option>
              <option value="age_band">age_band</option>
            </select>
          </label>
          <label>{{ t('scenario.fallbackMonthlyHazard') }} <input type="number" step="0.001" v-model.number="page.cullFallback.value" min="0" max="0.2" /></label>
          <label>{{ t('scenario.ageBandYears') }} <input type="number" v-model.number="page.cullAgeBand.value" min="1" max="10" /></label>
        </div>
        <div class="subcard">
          <h3>{{ t('scenario.heiferIntro') }}</h3>
          <label class="row between">
            <span>{{ t('scenario.enabled') }}</span>
            <input type="checkbox" v-model="page.replEnabled.value" />
          </label>
          <label>{{ t('scenario.annualRatio') }} <input type="number" step="0.01" v-model.number="page.replRatio.value" min="0" max="1" /></label>
          <label>{{ t('scenario.lookaheadMonths') }} <input type="number" v-model.number="page.replLookahead.value" min="3" max="36" /></label>
        </div>
      </div>
    </details>

    <details style="margin-top:10px" open>
      <summary>{{ t('scenario.purchases') }}</summary>
      <div class="row" style="margin-top:10px; gap:10px; flex-wrap:wrap">
        <button @click="page.addPurchase">{{ t('scenario.addPurchaseRow') }}</button>
        <span class="muted">{{ t('scenario.purchaseHint') }}</span>
      </div>
      <div style="overflow:auto; margin-top:10px">
        <table>
          <thead>
            <tr>
              <th>{{ t('scenario.dateIn') }}</th>
              <th>{{ t('scenario.count') }}</th>
              <th>{{ t('scenario.expectedCalvingDate') }}</th>
              <th>{{ t('scenario.daysPregnant') }}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(purchase, idx) in page.purchases.value" :key="idx">
              <td><input type="date" v-model="purchase.date_in" /></td>
              <td><input type="number" min="1" max="5000" v-model.number="purchase.count" /></td>
              <td><input type="date" v-model="purchase.expected_calving_date" /></td>
              <td><input type="number" min="0" max="280" v-model.number="purchase.days_pregnant" /></td>
              <td><button @click="page.removePurchase(idx)">{{ t('scenario.delete') }}</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </details>

    <details style="margin-top:10px" v-if="page.scenarioList.value.length">
      <summary>{{ t('scenario.savedScenarios') }}</summary>
      <div style="overflow:auto; margin-top:10px">
        <table>
          <thead>
            <tr>
              <th>{{ t('scenario.name') }}</th>
              <th>{{ t('scenario.created') }}</th>
              <th>{{ t('scenario.reportDate') }}</th>
              <th>{{ t('scenario.horizon') }}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="scenario in page.scenarioList.value" :key="scenario.scenario_id">
              <td><b>{{ scenario.name }}</b></td>
              <td class="muted">{{ scenario.created_at }}</td>
              <td>{{ scenario.report_date }}</td>
              <td>{{ scenario.horizon_months }}</td>
              <td class="row" style="gap:8px">
                <button @click="page.loadScenario(scenario.scenario_id)">{{ t('scenario.load') }}</button>
                <button @click="page.runScenario(scenario.scenario_id)">{{ t('scenario.run') }}</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </details>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { ForecastPage } from '../composables/useForecastPage'

defineProps<{ page: ForecastPage }>()
const { t } = useI18n()
</script>
