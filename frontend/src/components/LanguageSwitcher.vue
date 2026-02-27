<template>
  <div class="lang-switcher">
    <label for="locale-select">{{ t('language.label') }}</label>
    <select id="locale-select" v-model="selectedLocale">
      <option value="ru">{{ t('language.ru') }}</option>
      <option value="en">{{ t('language.en') }}</option>
    </select>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { persistLocale } from '../i18n'

const { t, locale } = useI18n()

const selectedLocale = computed({
  get: () => locale.value,
  set: value => {
    locale.value = value
    persistLocale(value)
  },
})
</script>
