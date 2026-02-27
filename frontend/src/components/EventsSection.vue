<template>
  <section class="card">
    <h2>{{ t('events.sectionTitle') }}</h2>
    <div style="overflow:auto">
      <table>
        <thead>
          <tr>
            <th>{{ t('events.month') }}</th>
            <th>{{ t('events.calvings') }}</th>
            <th>{{ t('events.dryoffs') }}</th>
            <th>{{ t('events.culls') }}</th>
            <th>{{ t('events.purchases') }}</th>
            <th>{{ t('events.heiferIntros') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="eventItem in events" :key="eventItem.month">
            <td>{{ eventItem.month }}</td>
            <td>{{ eventItem.calvings }}</td>
            <td>{{ eventItem.dryoffs }}</td>
            <td>{{ eventItem.culls }}</td>
            <td>{{ eventItem.purchases_in }}</td>
            <td>{{ eventItem.heifer_intros }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { EventsByMonth } from '../types/forecast'

defineProps<{ events: EventsByMonth[] }>()
const { t } = useI18n()
</script>
