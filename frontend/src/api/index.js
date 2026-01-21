import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 600000  // 10分钟超时
})

// 认证 API（不使用 /api 前缀）
const authApi = axios.create({
  baseURL: '/auth',
  timeout: 30000
})

// Token 存储键名
const TOKEN_KEY = 'access_token'
const USER_KEY = 'user_info'

// 获取 Token
export const getToken = () => localStorage.getItem(TOKEN_KEY)

// 设置 Token
export const setToken = (token) => localStorage.setItem(TOKEN_KEY, token)

// 移除 Token
export const removeToken = () => {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

// 获取用户信息
export const getStoredUser = () => {
  const user = localStorage.getItem(USER_KEY)
  return user ? JSON.parse(user) : null
}

// 设置用户信息
export const setStoredUser = (user) => {
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

// 请求拦截器 - 添加 Token
api.interceptors.request.use(
  config => {
    const token = getToken()
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`
    }
    return config
  },
  error => {
    return Promise.reject(error)
  }
)

// 响应拦截器 - 处理 401
api.interceptors.response.use(
  response => {
    return response.data
  },
  error => {
    if (error.response?.status === 401) {
      // Token 过期或无效，清除本地存储并跳转登录页
      removeToken()
      // 触发自定义事件通知应用
      window.dispatchEvent(new CustomEvent('auth:logout', { 
        detail: { reason: error.response?.data?.detail || '会话已过期' }
      }))
    }
    console.error('API Error:', error)
    return Promise.reject(error)
  }
)

// Auth API 拦截器
authApi.interceptors.request.use(
  config => {
    const token = getToken()
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`
    }
    return config
  },
  error => Promise.reject(error)
)

authApi.interceptors.response.use(
  response => response.data,
  error => {
    if (error.response?.status === 401 && !error.config?.url?.includes('/login')) {
      removeToken()
      window.dispatchEvent(new CustomEvent('auth:logout', { 
        detail: { reason: error.response?.data?.detail || '会话已过期' }
      }))
    }
    console.error('Auth API Error:', error)
    return Promise.reject(error)
  }
)

export default {
  // ==================== 认证相关 ====================
  
  // 用户注册
  register(data) {
    return authApi.post('/register', data)
  },
  
  // 用户登录
  login(data) {
    return authApi.post('/login', data)
  },
  
  // 用户登出
  logout() {
    return authApi.post('/logout')
  },
  
  // 获取当前用户信息
  getCurrentUser() {
    return authApi.get('/me')
  },
  
  // 修改密码
  changePassword(data) {
    return authApi.put('/password', data)
  },
  
  // 更新用户资料
  updateProfile(data) {
    return authApi.put('/profile', data)
  },
  
  // 获取会话信息
  getSessionInfo() {
    return authApi.get('/session')
  },

  // ==================== 任务相关 ====================
  
  createTask(data) {
    return api.post('/tasks', data)
  },
  
  getTask(taskId) {
    return api.get(`/tasks/${taskId}`)
  },
  
  listTasks(params) {
    return api.get('/tasks', { params })
  },
  
  retryTask(taskId) {
    return api.post(`/tasks/${taskId}/retry`)
  },
  
  cancelTask(taskId, reason) {
    return api.post(`/tasks/${taskId}/cancel`, { reason })
  },
  
  deleteTask(taskId) {
    return api.delete(`/tasks/${taskId}`)
  },
  
  // 统计相关
  getStatistics() {
    return api.get('/statistics')
  },
  
  // 文件上传
  uploadFile(file) {
    const formData = new FormData()
    formData.append('file', file)
    return api.post('/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
  },
  
  // 报告下载
  downloadReport(taskId, format = 'html') {
    return api.get(`/reports/${taskId}`, {
      params: { format },
      responseType: 'blob'
    })
  },
  
  // 获取原生 JSON 报告数据
  getReportData(taskId) {
    return api.get(`/reports/${taskId}/raw`)
  },
  
  // 获取 Markdown 报告
  getMarkdownReport(taskId) {
    return api.get(`/reports/${taskId}/markdown`)
  },
  
  // 生成 LLM 分析
  analyzeReport(taskId) {
    return api.post(`/reports/${taskId}/analyze`)
  },

  // 聊天相关
  sendChatMessage(data) {
    return api.post('/chat/send', data)
  },

  getChatHistory(conversationId) {
    return api.get(`/chat/history/${conversationId}`)
  },

  clearChat(conversationId) {
    return api.post(`/chat/clear/${conversationId}`)
  },

  // 上传聊天文件
  uploadChatFile(conversationId, file) {
    const formData = new FormData()
    formData.append('conversation_id', conversationId)
    formData.append('file', file)
    return api.post('/chat/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
  },

  // ==================== 对话历史相关 ====================
  
  // 创建对话
  createConversation(data) {
    return api.post('/conversations', data)
  },
  
  // 获取对话列表
  listConversations(params) {
    return api.get('/conversations', { params })
  },
  
  // 获取对话详情
  getConversation(conversationId) {
    return api.get(`/conversations/${conversationId}`)
  },
  
  // 更新对话标题
  updateConversation(conversationId, data) {
    return api.put(`/conversations/${conversationId}`, data)
  },
  
  // 删除对话
  deleteConversation(conversationId) {
    return api.delete(`/conversations/${conversationId}`)
  },
  
  // 创建消息
  createMessage(conversationId, data) {
    return api.post(`/conversations/${conversationId}/messages`, data)
  },
  
  // 获取对话消息列表
  listMessages(conversationId, params) {
    return api.get(`/conversations/${conversationId}/messages`, { params })
  }
}

// 导出辅助函数
export { api, authApi }
