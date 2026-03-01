<template>
  <ForecastWorkspaceView :user-name="auth.displayName.value" @logout="handleLogout" />
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import ForecastWorkspaceView from '../components/ForecastWorkspaceView.vue'
import { useAuth } from '../composables/useAuth'

const auth = useAuth()
const router = useRouter()

async function handleLogout() {
  await auth.logout()
  await router.replace('/auth/login')
}
</script>
