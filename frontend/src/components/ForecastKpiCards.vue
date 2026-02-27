<template>
  <section class="card" v-if="snapshot">
    <h2>{{ t('kpi.title') }}</h2>
    <div class="kpi-grid">
      <article class="kpi-card">
        <span>{{ t('kpi.p50Dim') }}</span>
        <strong>{{ formatNumber(snapshot.p50_dim, localeAsApp, 1) }}</strong>
      </article>
      <article class="kpi-card">
        <span>{{ t('kpi.milking') }}</span>
        <strong>{{ formatNumber(snapshot.milking_count, localeAsApp, 0) }}</strong>
      </article>
      <article class="kpi-card">
        <span>{{ t('kpi.dryRatio') }}</span>
        <strong>{{ formatPercent(snapshot.dry_ratio, localeAsApp, 1) }}</strong>
      </article>
      <article class="kpi-card">
        <span>{{ t('kpi.trendDelta') }}</span>
        <strong>{{ formatNumber(snapshot.trend_delta, localeAsApp, 1) }}</strong>
        <small>{{ t('kpi.vsStart') }}</small>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { formatNumber, formatPercent } from '../utils/format'
import type { AppLocale } from '../i18n/messages'
import type { ForecastKpiSnapshot } from '../types/forecast'

const props = defineProps<{ snapshot: ForecastKpiSnapshot | null }>()
const { t, locale } = useI18n()

const localeAsApp = computed(() => (locale.value === 'ru' ? 'ru' : 'en') as AppLocale)
</script>
