<template>
  <AuthGate
    :mode="authMode"
    :register-success-tick="registerSuccessTick"
    :submitting="auth.submitting.value"
    :error="auth.lastError.value"
    :notice="notice"
    @login="handleLogin"
    @register="handleRegister"
    @forgot-password="handleForgotPassword"
    @oauth-login="handleOauthLogin"
    @change-mode="handleModeChange"
  />
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import AuthGate from '../components/AuthGate.vue'
import { useAuth } from '../composables/useAuth'
import type { SsoLoginRequest, SsoOauthProvider, SsoPasswordResetRequest, SsoRegisterRequest } from '../types/auth'

const auth = useAuth()
const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const notice = ref<string | null>(null)
const registerSuccessTick = ref(0)

const authMode = computed(() => {
  const raw = route.params.mode
  const mode = Array.isArray(raw) ? raw[0] : raw
  if (mode === 'register' || mode === 'forgot' || mode === 'login') {
    return mode
  }
  return 'login'
})

onMounted(() => {
  void initializeAuth()
})

async function initializeAuth() {
  await processAuthTokenAction()
  const oauthReturn = auth.consumeOauthPending()
  await auth.bootstrap({ showErrors: oauthReturn, force: oauthReturn })
}

async function processAuthTokenAction(): Promise<void> {
  const search = new URLSearchParams(window.location.search)
  const explicitMode = search.get('auth_mode')
  const confirmToken = search.get('confirm_email_token') || (explicitMode === 'confirm_email' ? search.get('token') : null)
  const resetToken = search.get('reset_password_token') || (explicitMode === 'reset_password' ? search.get('token') : null)

  if (!confirmToken && !resetToken) {
    return
  }

  notice.value = null
  try {
    if (confirmToken) {
      await auth.confirmEmail(confirmToken)
      notice.value = t('auth.emailConfirmed')
      await router.replace('/auth/login')
    } else if (resetToken) {
      const response = await auth.confirmPasswordReset(resetToken)
      notice.value = response.message || t('auth.passwordResetConfirmed')
      await router.replace('/auth/login')
    }
  } catch {
    // user-facing error is stored in auth.lastError
  } finally {
    clearQueryParams()
  }
}

function clearQueryParams() {
  const url = new URL(window.location.href)
  url.searchParams.delete('token')
  url.searchParams.delete('auth_mode')
  url.searchParams.delete('confirm_email_token')
  url.searchParams.delete('reset_password_token')
  window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`)
}

function handleModeChange(mode: 'login' | 'register' | 'forgot') {
  void router.push(`/auth/${mode}`)
}

async function handleLogin(payload: SsoLoginRequest) {
  notice.value = null
  try {
    await auth.login(payload)
    await router.replace('/workspace/dataset')
  } catch {
    // user-facing error is stored in auth.lastError
  }
}

async function handleRegister(payload: SsoRegisterRequest) {
  notice.value = null
  try {
    await auth.register(payload)
    registerSuccessTick.value += 1
    notice.value = t('auth.registrationRequiresEmailConfirm')
    await router.replace('/auth/login')
  } catch {
    // user-facing error is stored in auth.lastError
  }
}

async function handleForgotPassword(payload: SsoPasswordResetRequest) {
  notice.value = null
  try {
    const response = await auth.requestPasswordReset(payload)
    notice.value = response.message || t('auth.passwordResetRequested')
  } catch {
    // user-facing error is stored in auth.lastError
  }
}

function handleOauthLogin(provider: SsoOauthProvider) {
  notice.value = t('auth.oauthRedirecting')
  try {
    auth.startOauthLogin(provider)
  } catch {
    notice.value = null
    // user-facing error is stored in auth.lastError
  }
}
</script>
