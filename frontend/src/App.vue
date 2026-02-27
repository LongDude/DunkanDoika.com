<template>
  <div class="wrap">
    <div class="topbar">
      <h1>{{ t('app.title') }}</h1>
      <LanguageSwitcher />
    </div>

    <DatasetSection
      :dataset="page.dataset.value"
      :on-file="page.onFile"
      :on-refresh-scenarios="page.refreshScenarios"
    />

    <ScenarioSection :page="page" />

    <ChartsSection
      v-if="page.result.value"
      :result="page.result.value"
      :compare="page.compare.value"
      :scenario-name="page.scenarioName.value"
      :fmt="page.fmt"
    />

    <EventsSection v-if="page.result.value" :events="page.result.value.events" />
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import LanguageSwitcher from './components/LanguageSwitcher.vue'
import DatasetSection from './components/DatasetSection.vue'
import ScenarioSection from './components/ScenarioSection.vue'
import ChartsSection from './components/ChartsSection.vue'
import EventsSection from './components/EventsSection.vue'
import { useForecastPage } from './composables/useForecastPage'

const { t } = useI18n()
const page = useForecastPage()
</script>
