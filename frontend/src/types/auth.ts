export type SsoUser = {
  email: string
  email_confirmed: boolean
  first_name: string
  last_name: string
  locale_type?: string
  photo?: string
  roles: string[]
}

export type SsoLoginRequest = {
  login: string
  password: string
}

export type SsoRegisterRequest = {
  email: string
  first_name: string
  last_name: string
  password: string
}

export type SsoTokenResponse = {
  access_token: string
}

export type SsoPasswordResetRequest = {
  email: string
}

export type SsoMessageResponse = {
  message: string
}

export type SsoOauthProvider = 'google' | 'yandex'
