import { createRouter, createWebHistory } from 'vue-router'
import AuthView from '../views/AuthView.vue'
import WorkspaceView from '../views/WorkspaceView.vue'
import { useAuth } from '../composables/useAuth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      redirect: () => {
        const auth = useAuth()
        return auth.isAuthenticated.value ? '/workspace/dataset' : '/auth/login'
      },
    },
    {
      path: '/auth',
      redirect: '/auth/login',
    },
    {
      path: '/auth/:mode(login|register|forgot)',
      name: 'auth',
      component: AuthView,
      meta: { guestOnly: true },
    },
    {
      path: '/workspace',
      redirect: '/workspace/dataset',
    },
    {
      path: '/workspace/:screen(dataset|scenarios|forecast|comparison|history|export)',
      name: 'workspace',
      component: WorkspaceView,
      meta: { requiresAuth: true },
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/',
    },
  ],
})

router.beforeEach(async to => {
  const auth = useAuth()
  await auth.bootstrap({ showErrors: false })

  if (to.meta.requiresAuth && !auth.isAuthenticated.value) {
    return '/auth/login'
  }

  if (to.meta.guestOnly && auth.isAuthenticated.value) {
    return '/workspace/dataset'
  }

  return true
})

export default router
