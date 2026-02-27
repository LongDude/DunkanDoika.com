import { createI18n } from 'vue-i18n'
import { messages, type AppLocale } from './messages'

const LOCALE_KEY = 'app-locale'

function getInitialLocale(): AppLocale {
  const saved = localStorage.getItem(LOCALE_KEY)
  if (saved === 'ru' || saved === 'en') return saved
  return 'ru'
}

export const i18n = createI18n({
  legacy: false,
  locale: getInitialLocale(),
  fallbackLocale: 'en',
  messages,
})

export function persistLocale(locale: string) {
  if (locale === 'ru' || locale === 'en') {
    localStorage.setItem(LOCALE_KEY, locale)
  }
}
