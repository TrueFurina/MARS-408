import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import './assets/styles/main.css'
import 'highlight.js/styles/atom-one-dark.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
