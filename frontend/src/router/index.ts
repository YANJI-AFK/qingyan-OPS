import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'Home',
      component: () => import('../views/HomePage.vue'),
    },
    {
      path: '/tickets',
      component: () => import('../views/TicketsLayout.vue'),
      children: [
        {
          path: '',
          name: 'Tickets',
          component: () => import('../views/TicketsPage.vue'),
        },
        {
          path: 'stats',
          name: 'Stats',
          component: () => import('../views/StatsPage.vue'),
        },
        {
          path: 'config',
          name: 'Config',
          component: () => import('../views/ConfigPage.vue'),
        },
      ],
    },
    {
      path: '/monitor',
      name: 'Monitor',
      component: () => import('../views/MonitorPage.vue'),
    },
    {
      path: '/staff',
      component: () => import('../views/StaffLayout.vue'),
      children: [
        {
          path: '',
          name: 'StaffList',
          component: () => import('../views/StaffListPage.vue'),
        },
        {
          path: 'schedule',
          name: 'Schedule',
          component: () => import('../views/SchedulePage.vue'),
        },
        {
          path: 'roles',
          name: 'StaffRoles',
          component: () => import('../views/RoleConfigPage.vue'),
        },
      ],
    },
  ],
})

export default router
