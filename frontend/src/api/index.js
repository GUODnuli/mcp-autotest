import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 600000  // 10分钟超时
})

// 请求拦截器
api.interceptors.request.use(
  config => {
    return config
  },
  error => {
    return Promise.reject(error)
  }
)

// 响应拦截器
api.interceptors.response.use(
  response => {
    return response.data
  },
  error => {
    console.error('API Error:', error)
    return Promise.reject(error)
  }
)

export default {
  // 任务相关
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
  }
}
