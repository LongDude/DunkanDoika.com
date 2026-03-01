<template>
  <RouterView />
  <ToastHost />
</template>

<script setup lang="ts">
import { computed, onUnmounted, watch } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import ToastHost from './components/ui/ToastHost.vue'

const route = useRoute()
const isAuthScreen = computed(() => route.path.startsWith('/auth'))

function setAuthScreenClass(enabled: boolean) {
  if (typeof document === 'undefined') return
  document.body.classList.toggle('auth-screen', enabled)
}

watch(
  isAuthScreen,
  value => {
    setAuthScreenClass(value)
  },
  { immediate: true },
)

onUnmounted(() => {
  setAuthScreenClass(false)
})
</script>
