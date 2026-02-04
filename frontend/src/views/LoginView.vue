<template>
  <div class="login-page">
    <div class="login-container">
      <div class="login-header">
        <h1 class="login-title">TestAgent</h1>
        <p class="login-subtitle">登录您的账户</p>
      </div>

      <form class="login-form" @submit.prevent="handleLogin">
        <div class="form-group">
          <label for="username">用户名</label>
          <input
            id="username"
            v-model="form.username"
            type="text"
            placeholder="请输入用户名"
            autocomplete="username"
            :disabled="loading"
          />
        </div>

        <div class="form-group">
          <label for="password">密码</label>
          <input
            id="password"
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            autocomplete="current-password"
            :disabled="loading"
          />
        </div>

        <div v-if="errorMessage" class="error-message">
          {{ errorMessage }}
        </div>

        <button type="submit" class="login-btn" :disabled="loading || !isFormValid">
          <span v-if="loading">登录中...</span>
          <span v-else>登录</span>
        </button>

        <div class="login-footer">
          <span>还没有账户？</span>
          <router-link to="/register" class="register-link">立即注册</router-link>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const form = ref({
  username: '',
  password: ''
})

const loading = ref(false)
const errorMessage = ref('')

const isFormValid = computed(() => {
  return form.value.username.trim() && form.value.password
})

const handleLogin = async () => {
  if (!isFormValid.value || loading.value) return

  loading.value = true
  errorMessage.value = ''

  const result = await userStore.login(form.value)

  loading.value = false

  if (result.success) {
    // 登录成功，跳转到之前的页面或首页
    const redirect = route.query.redirect || '/'
    router.push(redirect)
  } else {
    errorMessage.value = result.error
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: var(--main-bg, #232326);
  padding: 20px;
}

.login-container {
  width: 100%;
  max-width: 400px;
  background-color: var(--sidebar-bg, #1d1d1f);
  border-radius: 16px;
  padding: 40px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
}

.login-header {
  text-align: center;
  margin-bottom: 32px;
}

.login-title {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary, #e0e0e0);
  margin: 0 0 8px 0;
}

.login-subtitle {
  font-size: 14px;
  color: var(--text-secondary, #999999);
  margin: 0;
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-group label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary, #e0e0e0);
}

.form-group input {
  padding: 12px 16px;
  font-size: 14px;
  border: 1px solid var(--border-color, #3a3a3a);
  border-radius: 8px;
  background-color: var(--input-bg, #2a2a2a);
  color: var(--text-primary, #e0e0e0);
  transition: border-color 0.2s, box-shadow 0.2s;
}

.form-group input:focus {
  outline: none;
  border-color: var(--send-btn, #615ced);
  box-shadow: 0 0 0 3px rgba(97, 92, 237, 0.2);
}

.form-group input::placeholder {
  color: var(--text-secondary, #999999);
}

.form-group input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.error-message {
  padding: 12px;
  background-color: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 8px;
  color: #ef4444;
  font-size: 14px;
  text-align: center;
}

.login-btn {
  padding: 14px;
  font-size: 16px;
  font-weight: 600;
  color: white;
  background-color: var(--send-btn, #615ced);
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: background-color 0.2s, transform 0.1s;
}

.login-btn:hover:not(:disabled) {
  background-color: var(--send-btn-hover, #7571ff);
}

.login-btn:active:not(:disabled) {
  transform: scale(0.98);
}

.login-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.login-footer {
  text-align: center;
  font-size: 14px;
  color: var(--text-secondary, #999999);
  margin-top: 8px;
}

.register-link {
  color: var(--send-btn, #615ced);
  text-decoration: none;
  font-weight: 500;
  margin-left: 4px;
}

.register-link:hover {
  text-decoration: underline;
}
</style>
