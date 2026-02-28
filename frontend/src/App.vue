<template>
  <section v-if="auth.initializing.value" class="auth-page">
    <div class="auth-card card">
      <h1>{{ t('auth.loadingTitle') }}</h1>
      <p class="muted">{{ t('auth.loadingSubtitle') }}</p>
    </div>
  </section>

  <AuthGate
    v-else-if="!auth.isAuthenticated.value"
    :submitting="auth.submitting.value"
    :error="auth.lastError.value"
    :notice="notice"
    @login="handleLogin"
    @register="handleRegister"
    @forgot-password="handleForgotPassword"
    @oauth-login="handleOauthLogin"
  />

  <ForecastWorkspaceView
    v-else
    :user-name="auth.displayName.value"
    @logout="handleLogout"
  />
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AuthGate from './components/AuthGate.vue'
import ForecastWorkspaceView from './components/ForecastWorkspaceView.vue'
import { useAuth } from './composables/useAuth'
import type { SsoLoginRequest, SsoOauthProvider, SsoPasswordResetRequest, SsoRegisterRequest } from './types/auth'

const { t } = useI18n()
const auth = useAuth()
const notice = ref<string | null>(null)

function clearQueryParams() {
  const url = new URL(window.location.href)
  url.searchParams.delete('token')
  url.searchParams.delete('auth_mode')
  url.searchParams.delete('confirm_email_token')
  url.searchParams.delete('reset_password_token')
  window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`)
}

onMounted(() => {
  void initializeAuth()
})

async function handleLogin(payload: SsoLoginRequest) {
  notice.value = null
  try {
    await auth.login(payload)
  } catch {
    // user-facing error is stored in auth.lastError
  }
}

async function handleRegister(payload: SsoRegisterRequest) {
  notice.value = null
  try {
    await auth.register(payload)
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

async function handleLogout() {
  notice.value = null
  await auth.logout()
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

async function initializeAuth() {
  await processAuthTokenAction()
  const oauthReturn = auth.consumeOauthPending()
  await auth.bootstrap({ showErrors: oauthReturn })
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
    } else if (resetToken) {
      const response = await auth.confirmPasswordReset(resetToken)
      notice.value = response.message || t('auth.passwordResetConfirmed')
    }
  } catch {
    // user-facing error is stored in auth.lastError
  } finally {
    clearQueryParams()
  }
}
</script>
