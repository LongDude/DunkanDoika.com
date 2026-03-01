<template>
  <div class="app-shell">
    <header class="hero">
      <div class="hero-copy">
        <h1>{{ t('app.title') }}</h1>
        <p>{{ t('app.subtitle') }}</p>
      </div>
      <div class="hero-actions">
        <div v-if="userName" class="user-badge">{{ userName }}</div>
        <button v-if="userName" type="button" @click="$emit('logout')">{{ t('auth.logoutAction') }}</button>
        <LanguageSwitcher />
      </div>
    </header>

    <nav class="screen-nav" :aria-label="t('aria.mainNavigation')">
      <RouterLink
        v-for="screen in screens"
        :key="screen.id"
        class="screen-tab"
        :class="{ active: currentScreen === screen.id }"
        :to="{ name: 'workspace', params: { screen: screen.id } }"
      >
        {{ screen.label }}
      </RouterLink>
    </nav>

    <main class="screen-content">
      <slot />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute } from 'vue-router'
import LanguageSwitcher from './LanguageSwitcher.vue'
import type { RouteScreenId } from '../types/ui'

defineProps<{
  userName?: string | null
}>()

defineEmits<{
  (e: 'logout'): void
}>()

const { t } = useI18n()
const route = useRoute()

const currentScreen = computed<RouteScreenId>(() => {
  const raw = route.params.screen
  const screen = Array.isArray(raw) ? raw[0] : raw
  if (
    screen === 'dataset' ||
    screen === 'scenarios' ||
    screen === 'forecast' ||
    screen === 'comparison' ||
    screen === 'history' ||
    screen === 'export'
  ) {
    return screen
  }
  return 'dataset'
})

const screens = computed<Array<{ id: RouteScreenId; label: string }>>(() => [
  { id: 'dataset', label: t('nav.dataset') },
  { id: 'scenarios', label: t('nav.scenarios') },
  { id: 'forecast', label: t('nav.forecast') },
  { id: 'comparison', label: t('nav.comparison') },
  { id: 'history', label: t('nav.history') },
  { id: 'export', label: t('nav.export') },
])
</script>
