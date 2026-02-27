import type { AppLocale } from '../i18n/messages'

function toIntlLocale(locale: string) {
  return locale === 'ru' ? 'ru-RU' : 'en-US'
}

export function formatDate(value: string | null | undefined, locale: AppLocale): string {
  if (!value) return '-'
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return value
  return new Intl.DateTimeFormat(toIntlLocale(locale), { dateStyle: 'medium' }).format(dt)
}

export function formatNumber(value: number | null | undefined, locale: AppLocale, digits = 0): string {
  if (value === null || value === undefined) return '-'
  return new Intl.NumberFormat(toIntlLocale(locale), {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value)
}

export function formatPercent(value: number | null | undefined, locale: AppLocale, digits = 1): string {
  if (value === null || value === undefined) return '-'
  return new Intl.NumberFormat(toIntlLocale(locale), {
    style: 'percent',
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value)
}
