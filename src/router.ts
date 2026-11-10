import { createRouter, createWebHistory } from 'vue-router'

// 第一批 + 第二批已启用页面；其余模块随批次逐步开放
export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'today', component: () => import('./views/TodayView.vue') },
    { path: '/money', name: 'money', component: () => import('./views/MoneyView.vue') },
    { path: '/margin', name: 'margin', component: () => import('./views/MarginView.vue') },
    { path: '/index', name: 'index', component: () => import('./views/IndexView.vue') },
    { path: '/widebase', redirect: '/index' },
    { path: '/concentration', name: 'concentration', component: () => import('./views/ConcentrationView.vue') },
    { path: '/liquidity', name: 'liquidity', component: () => import('./views/LiquidityView.vue') },
    { path: '/emotion', name: 'emotion', component: () => import('./views/EmotionView.vue') },
    { path: '/industry', name: 'industry', component: () => import('./views/IndustryView.vue') },
    { path: '/notes', name: 'notes', component: () => import('./views/NotesView.vue') },
    { path: '/report', name: 'report', component: () => import('./views/ReportView.vue') },
    { path: '/export/:date', name: 'export', component: () => import('./views/ExportView.vue'), meta: { bare: true } },
    { path: '/daily-observation', name: 'daily-observation', component: () => import('./views/DailyObservationView.vue') },
    { path: '/observation-export/:date', name: 'observation-export', component: () => import('./views/ObservationExportView.vue'), meta: { bare: true } },
    { path: '/calendar', name: 'calendar', component: () => import('./views/CalendarView.vue') },
    { path: '/status', name: 'status', component: () => import('./views/StatusView.vue') },
    { path: '/:pathMatch(.*)*', redirect: '/' }
  ],
  scrollBehavior: () => ({ top: 0 })
})
