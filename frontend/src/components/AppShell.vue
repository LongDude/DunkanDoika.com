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
      <button
        v-for="screen in screens"
        :key="screen.id"
        class="screen-tab"
        :class="{ active: activeScreen === screen.id }"
        @click="$emit('change-screen', screen.id)"
      >
        {{ screen.label }}
      </button>
    </nav>

    <main class="screen-content">
      <slot />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import LanguageSwitcher from './LanguageSwitcher.vue'

type ScreenId = 'dataset' | 'scenarios' | 'forecast' | 'comparison' | 'history' | 'export'

defineProps<{
  activeScreen: ScreenId
  userName?: string | null
}>()

defineEmits<{
  (e: 'change-screen', screen: ScreenId): void
  (e: 'logout'): void
}>()

const { t } = useI18n()

const screens = computed<Array<{ id: ScreenId; label: string }>>(() => [
  { id: 'dataset', label: t('nav.dataset') },
  { id: 'scenarios', label: t('nav.scenarios') },
  { id: 'forecast', label: t('nav.forecast') },
  { id: 'comparison', label: t('nav.comparison') },
  { id: 'history', label: t('nav.history') },
  { id: 'export', label: t('nav.export') },
])
</script>
