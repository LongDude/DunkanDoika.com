<template>
  <section class="auth-page">
    <div class="auth-lang-corner">
      <LanguageSwitcher />
    </div>

    <div class="auth-card card">
      <div class="auth-head">
        <div class="auth-copy">
          <h1>{{ t('auth.title') }}</h1>
        </div>
      </div>

      <p v-if="error" class="auth-error">{{ error }}</p>
      <p v-else-if="notice" class="auth-notice">{{ notice }}</p>

      <form v-if="mode === 'login'" class="auth-form" @submit.prevent="onLoginSubmit">
        <label>
          {{ t('auth.login') }}
          <input v-model.trim="loginForm.login" required autocomplete="username" />
        </label>
        <label>
          {{ t('auth.password') }}
          <input v-model="loginForm.password" type="password" required minlength="8" autocomplete="current-password" />
        </label>
        <button type="button" class="linkish auth-link-centered auth-forgot-link" :disabled="submitting" @click="$emit('change-mode', 'forgot')">
          {{ t('auth.forgotPasswordAction') }}
        </button>
        <button class="primary" type="submit" :disabled="submitting">{{ t('auth.loginAction') }}</button>
        <div class="auth-divider" role="presentation">
          <span>{{ t('auth.oauthDivider') }}</span>
        </div>
        <div class="auth-oauth">
          <button type="button" class="auth-oauth-btn" :disabled="submitting" @click="onOauthLogin('google')">
            {{ t('auth.oauthGoogle') }}
          </button>
          <button type="button" class="auth-oauth-btn" :disabled="submitting" @click="onOauthLogin('yandex')">
            {{ t('auth.oauthYandex') }}
          </button>
        </div>
        <button type="button" class="linkish auth-link-centered auth-switch-link" :disabled="submitting" @click="$emit('change-mode', 'register')">
          {{ t('auth.registerTab') }}
        </button>
      </form>

      <form v-else-if="mode === 'register'" class="auth-form" @submit.prevent="onRegisterSubmit">
        <label>
          {{ t('auth.firstName') }}
          <input v-model.trim="registerForm.first_name" required autocomplete="given-name" />
        </label>
        <label>
          {{ t('auth.lastName') }}
          <input v-model.trim="registerForm.last_name" required autocomplete="family-name" />
        </label>
        <label>
          {{ t('auth.email') }}
          <input v-model.trim="registerForm.email" type="email" required autocomplete="email" />
        </label>
        <label>
          {{ t('auth.password') }}
          <input v-model="registerForm.password" type="password" required minlength="8" autocomplete="new-password" />
        </label>
        <div class="password-hints">
          <p class="muted">{{ t('auth.passwordPolicyTitle') }}</p>
          <ul>
            <li :class="{ ok: passwordChecks.minLength }">{{ t('auth.passwordPolicyLength') }}</li>
            <li :class="{ ok: passwordChecks.hasLower }">{{ t('auth.passwordPolicyLower') }}</li>
            <li :class="{ ok: passwordChecks.hasUpper }">{{ t('auth.passwordPolicyUpper') }}</li>
            <li :class="{ ok: passwordChecks.hasSpecial }">{{ t('auth.passwordPolicySpecial') }}</li>
          </ul>
        </div>
        <p v-if="registerValidationError" class="field-error">{{ registerValidationError }}</p>
        <button class="primary" type="submit" :disabled="submitting || !isRegisterPasswordValid">
          {{ t('auth.registerAction') }}
        </button>
        <button type="button" class="linkish auth-link-centered auth-switch-link" :disabled="submitting" @click="$emit('change-mode', 'login')">
          {{ t('auth.loginTab') }}
        </button>
      </form>

      <form v-else class="auth-form" @submit.prevent="onForgotSubmit">
        <label>
          {{ t('auth.email') }}
          <input v-model.trim="forgotForm.email" type="email" required autocomplete="email" />
        </label>
        <button class="primary" type="submit" :disabled="submitting">{{ t('auth.forgotPasswordAction') }}</button>
        <button type="button" class="linkish auth-link-centered auth-switch-link" :disabled="submitting" @click="$emit('change-mode', 'login')">
          {{ t('auth.backToLoginAction') }}
        </button>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import LanguageSwitcher from './LanguageSwitcher.vue'
import type { SsoLoginRequest, SsoOauthProvider, SsoPasswordResetRequest, SsoRegisterRequest } from '../types/auth'

const props = defineProps<{
  mode: 'login' | 'register' | 'forgot'
  submitting: boolean
  error: string | null
  notice: string | null
  registerSuccessTick?: number
}>()

const emit = defineEmits<{
  (e: 'login', payload: SsoLoginRequest): void
  (e: 'register', payload: SsoRegisterRequest): void
  (e: 'forgot-password', payload: SsoPasswordResetRequest): void
  (e: 'oauth-login', provider: SsoOauthProvider): void
  (e: 'change-mode', mode: 'login' | 'register' | 'forgot'): void
}>()

const { t } = useI18n()

const loginForm = ref<SsoLoginRequest>({
  login: '',
  password: '',
})
const registerForm = ref<SsoRegisterRequest>({
  email: '',
  first_name: '',
  last_name: '',
  password: '',
})
const registerValidationError = ref<string | null>(null)
const forgotForm = ref<SsoPasswordResetRequest>({
  email: '',
})

const passwordChecks = computed(() => {
  const value = registerForm.value.password
  return {
    minLength: value.length >= 8,
    hasLower: /[a-z]/.test(value),
    hasUpper: /[A-Z]/.test(value),
    hasSpecial: /[^A-Za-z0-9\s]/.test(value),
  }
})

const isRegisterPasswordValid = computed(
  () =>
    passwordChecks.value.minLength &&
    passwordChecks.value.hasLower &&
    passwordChecks.value.hasUpper &&
    passwordChecks.value.hasSpecial,
)

watch(
  () => registerForm.value.password,
  () => {
    registerValidationError.value = null
  },
)

watch(
  () => props.registerSuccessTick,
  (next, prev) => {
    if (typeof next === 'number' && next !== prev) {
      registerValidationError.value = null
      loginForm.value.login = registerForm.value.email
      loginForm.value.password = ''
      emit('change-mode', 'login')
    }
  },
)

function onLoginSubmit() {
  emit('login', { ...loginForm.value })
}

function onRegisterSubmit() {
  if (!isRegisterPasswordValid.value) {
    registerValidationError.value = t('auth.passwordPolicyError')
    return
  }
  registerValidationError.value = null
  emit('register', { ...registerForm.value })
}

function onForgotSubmit() {
  emit('forgot-password', { ...forgotForm.value })
}

function onOauthLogin(provider: SsoOauthProvider) {
  emit('oauth-login', provider)
}
</script>
