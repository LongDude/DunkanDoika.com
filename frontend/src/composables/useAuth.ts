import { computed, ref } from 'vue'
import {
  getSsoOauthUrl,
  ssoAuthenticate,
  ssoConfirmEmail,
  ssoConfirmPasswordReset,
  ssoLogin,
  ssoLogout,
  ssoRefresh,
  ssoRegister,
  ssoRequestPasswordReset,
} from '../services/api'
import { i18n } from '../i18n'
import type {
  SsoLoginRequest,
  SsoOauthProvider,
  SsoPasswordResetRequest,
  SsoRegisterRequest,
  SsoUser,
} from '../types/auth'

const ACCESS_TOKEN_STORAGE_KEY = 'sso_access_token'
const OAUTH_PENDING_STORAGE_KEY = 'sso_oauth_pending'

const user = ref<SsoUser | null>(null)
const accessToken = ref<string | null>(null)
const initializing = ref(false)
const submitting = ref(false)
const lastError = ref<string | null>(null)
const initialized = ref(false)

function tAuth(key: string, fallback: string): string {
  const translated = i18n.global.t(key)
  if (typeof translated === 'string' && translated !== key) {
    return translated
  }
  return fallback
}

const EMAIL_CONFIRM_REQUIRED_ERROR = tAuth(
  'auth.errors.emailNotConfirmed',
  'Email is not confirmed. Please confirm your email before signing in.',
)

function readStoredToken(): string | null {
  try {
    return localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)
  } catch {
    return null
  }
}

function persistToken(token: string | null) {
  try {
    if (token) {
      localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, token)
    } else {
      localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY)
    }
  } catch {
    // no-op (storage can be unavailable in restricted contexts)
  }
}

function clearSessionState() {
  user.value = null
  accessToken.value = null
  persistToken(null)
}

function setOauthPending() {
  try {
    sessionStorage.setItem(OAUTH_PENDING_STORAGE_KEY, '1')
  } catch {
    // no-op
  }
}

function consumeOauthPending(): boolean {
  try {
    const pending = sessionStorage.getItem(OAUTH_PENDING_STORAGE_KEY) === '1'
    sessionStorage.removeItem(OAUTH_PENDING_STORAGE_KEY)
    return pending
  } catch {
    return false
  }
}

async function authenticateByToken(token: string): Promise<boolean> {
  accessToken.value = token
  persistToken(token)
  try {
    const authUser = await ssoAuthenticate(token)
    if (!authUser.email_confirmed) {
      clearSessionState()
      lastError.value = EMAIL_CONFIRM_REQUIRED_ERROR
      return false
    }
    user.value = authUser
    return true
  } catch {
    clearSessionState()
    return false
  }
}

export function useAuth() {
  const isAuthenticated = computed(() => Boolean(user.value && accessToken.value))
  const displayName = computed(() => {
    if (!user.value) return ''
    const fullName = `${user.value.first_name ?? ''} ${user.value.last_name ?? ''}`.trim()
    return fullName || user.value.email || ''
  })

  async function bootstrap(options?: { showErrors?: boolean; force?: boolean }) {
    if (initializing.value) return
    if (initialized.value && !options?.force) return
    initializing.value = true
    lastError.value = null
    const showErrors = options?.showErrors ?? false
    try {
      const stored = readStoredToken()
      if (stored && (await authenticateByToken(stored))) {
        return
      }

      try {
        const refreshed = await ssoRefresh()
        if (refreshed.access_token) {
          await authenticateByToken(refreshed.access_token)
        } else if (showErrors) {
          lastError.value = tAuth(
            'auth.errors.oauthRestoreFailed',
            'Could not restore session after OAuth login.',
          )
        }
      } catch (err) {
        clearSessionState()
        if (showErrors) {
          lastError.value =
            err instanceof Error
              ? err.message
              : tAuth('auth.errors.sessionRestoreFailed', 'Unable to restore session.')
        }
      }
    } finally {
      initialized.value = true
      initializing.value = false
    }
  }

  async function login(payload: SsoLoginRequest) {
    submitting.value = true
    lastError.value = null
    try {
      const token = await ssoLogin(payload)
      const ok = await authenticateByToken(token.access_token)
      if (!ok) {
        throw new Error(
          lastError.value ||
            tAuth('auth.errors.authAfterLoginFailed', 'Authentication failed after login'),
        )
      }
    } catch (err) {
      clearSessionState()
      if (!lastError.value) {
        lastError.value = err instanceof Error ? err.message : tAuth('auth.errors.loginFailed', 'Login failed')
      }
      throw err
    } finally {
      submitting.value = false
    }
  }

  async function register(payload: SsoRegisterRequest) {
    submitting.value = true
    lastError.value = null
    try {
      return await ssoRegister(payload)
    } catch (err) {
      lastError.value =
        err instanceof Error ? err.message : tAuth('auth.errors.registerFailed', 'Registration failed')
      throw err
    } finally {
      submitting.value = false
    }
  }

  async function logout() {
    submitting.value = true
    lastError.value = null
    try {
      await ssoLogout()
    } catch (err) {
      // Keep local logout behavior regardless of server response.
      lastError.value = err instanceof Error ? err.message : tAuth('auth.errors.logoutFailed', 'Logout failed')
    } finally {
      clearSessionState()
      submitting.value = false
    }
  }

  async function requestPasswordReset(payload: SsoPasswordResetRequest) {
    submitting.value = true
    lastError.value = null
    try {
      return await ssoRequestPasswordReset(payload)
    } catch (err) {
      lastError.value =
        err instanceof Error
          ? err.message
          : tAuth('auth.errors.passwordResetRequestFailed', 'Password reset request failed')
      throw err
    } finally {
      submitting.value = false
    }
  }

  async function confirmPasswordReset(token: string) {
    submitting.value = true
    lastError.value = null
    try {
      return await ssoConfirmPasswordReset(token)
    } catch (err) {
      lastError.value =
        err instanceof Error
          ? err.message
          : tAuth('auth.errors.passwordResetConfirmFailed', 'Password reset confirmation failed')
      throw err
    } finally {
      submitting.value = false
    }
  }

  async function confirmEmail(token: string) {
    submitting.value = true
    lastError.value = null
    try {
      await ssoConfirmEmail(token)
    } catch (err) {
      lastError.value =
        err instanceof Error ? err.message : tAuth('auth.errors.emailConfirmFailed', 'Email confirmation failed')
      throw err
    } finally {
      submitting.value = false
    }
  }

  function startOauthLogin(provider: SsoOauthProvider, redirectUrl?: string) {
    lastError.value = null
    setOauthPending()
    const url = getSsoOauthUrl(provider, redirectUrl)
    window.location.assign(url)
  }

  return {
    user,
    accessToken,
    isAuthenticated,
    displayName,
    initializing,
    submitting,
    lastError,
    bootstrap,
    login,
    register,
    logout,
    requestPasswordReset,
    confirmPasswordReset,
    confirmEmail,
    startOauthLogin,
    consumeOauthPending,
  }
}
