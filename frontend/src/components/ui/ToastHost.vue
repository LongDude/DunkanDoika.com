<template>
  <section class="toast-host" aria-live="polite" aria-atomic="false">
    <article
      v-for="item in toasts.notices.value"
      :key="item.id"
      class="toast-item"
      :class="`toast-${item.level}`"
      role="status"
    >
      <p>{{ item.message }}</p>
      <button type="button" class="toast-close" @click="toasts.removeNotice(item.id)" :aria-label="t('common.remove')">×</button>
    </article>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useToast } from '../../composables/useToast'

const { t } = useI18n()
const toasts = useToast()
</script>
