<template>
  <div class="task-detail-view">
    <el-card v-loading="loading">
      <template #header>
        <div class="header">
          <h2>任务详情</h2>
          <el-button @click="goBack">返回列表</el-button>
        </div>
      </template>

      <div v-if="task">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="任务ID">
            {{ task.task_id }}
          </el-descriptions-item>
          <el-descriptions-item label="任务类型">
            {{ getTypeLabel(task.type) }}
          </el-descriptions-item>
          <el-descriptions-item label="当前步骤">
            <el-tag :type="getStateTagType(task.current_state)">
              {{ getStateLabel(task.current_state) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="任务状态">
            <el-tag :type="getStatusTagType(task.status)">
              {{ getStatusLabel(task.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="文档路径">
            {{ task.document_path || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="创建时间">
            {{ formatDateTime(task.created_at) }}
          </el-descriptions-item>
          <el-descriptions-item label="更新时间">
            {{ formatDateTime(task.updated_at) }}
          </el-descriptions-item>
        </el-descriptions>

        <el-divider />

        <div class="actions">
          <el-button
            v-if="task.status === 'FAILED'"
            type="primary"
            @click="handleRetry"
          >
            重试任务
          </el-button>
          <el-button
            v-if="task.status === 'RUNNING'"
            type="danger"
            @click="handleCancel"
          >
            取消任务
          </el-button>
          <el-button
            v-if="task.status === 'COMPLETED'"
            type="success"
            @click="handleDownloadReport"
          >
            下载报告
          </el-button>
        </div>

        <el-divider />

        <div class="logs">
          <h3>执行日志</h3>
          <el-card>
            <el-empty v-if="!logs.length" description="暂无日志" />
            <div v-else class="log-content">
              <div v-for="(log, index) in logs" :key="index" class="log-item">
                {{ log }}
              </div>
            </div>
          </el-card>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/api'

const route = useRoute()
const router = useRouter()

const task = ref(null)
const logs = ref([])
const loading = ref(false)
let intervalId = null

// 加载任务详情
const loadTask = async () => {
  loading.value = true
  try {
    const response = await api.getTask(route.params.id)
    if (response.success) {
      task.value = response.data
      // TODO: 加载日志数据（需要后端支持）
    } else {
      ElMessage.error(response.message || '加载任务详情失败')
    }
  } catch (error) {
    ElMessage.error('加载任务详情失败：' + error.message)
  } finally {
    loading.value = false
  }
}

// 重试任务
const handleRetry = async () => {
  try {
    const response = await api.retryTask(route.params.id)
    if (response.success) {
      ElMessage.success('任务重试已启动')
      loadTask()
    } else {
      ElMessage.error(response.message || '重试任务失败')
    }
  } catch (error) {
    ElMessage.error('重试任务失败：' + error.message)
  }
}

// 取消任务（二次确认）
const handleCancel = async () => {
  try {
    await ElMessageBox.confirm('确定要取消该任务吗？', '确认取消', {
      type: 'warning'
    })
    
    const response = await api.cancelTask(route.params.id, '用户手动取消')
    if (response.success) {
      ElMessage.success('任务已取消')
      loadTask()
    } else {
      ElMessage.error(response.message || '取消任务失败')
    }
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('取消任务失败：' + error.message)
    }
  }
}

// 下载报告
const handleDownloadReport = async () => {
  try {
    const blob = await api.downloadReport(route.params.id, 'html')
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `report_${route.params.id}.html`
    a.click()
    window.URL.revokeObjectURL(url)
    ElMessage.success('报告下载成功')
  } catch (error) {
    ElMessage.error('下载报告失败：' + error.message)
  }
}

// 返回列表
const goBack = () => {
  router.push('/tasks')
}

// 工具函数
const getTypeLabel = (type) => {
  const labels = {
    'generate-testcase': '生成测试用例',
    'autotest': '自动化测试',
    'analyze-report': '报告分析'
  }
  return labels[type] || type
}

const getStateLabel = (state) => {
  const labels = {
    'created': '已创建',
    'parsing_doc': '解析文档中',
    'generating_testcases': '生成用例中',
    'executing_tests': '执行测试中',
    'generating_report': '生成报告中',
    'completed': '已完成',
    'failed': '失败',
    'cancelled': '已取消'
  }
  return labels[state] || state || '-'
}

const getStateTagType = (state) => {
  const types = {
    'created': 'info',
    'parsing_doc': 'warning',
    'generating_testcases': 'warning',
    'executing_tests': 'warning',
    'generating_report': 'warning',
    'completed': 'success',
    'failed': 'danger',
    'cancelled': 'info'
  }
  return types[state] || 'info'
}

const getStatusLabel = (status) => {
  const labels = {
    'PENDING': '待执行',
    'RUNNING': '运行中',
    'COMPLETED': '已完成',
    'FAILED': '失败',
    'CANCELLED': '已取消'
  }
  return labels[status] || status
}

const getStatusTagType = (status) => {
  const types = {
    'PENDING': 'info',
    'RUNNING': 'warning',
    'COMPLETED': 'success',
    'FAILED': 'danger',
    'CANCELLED': 'info'
  }
  return types[status] || 'info'
}

const formatDateTime = (datetime) => {
  if (!datetime) return '-'
  const date = new Date(datetime)
  return date.toLocaleString('zh-CN')
}

onMounted(() => {
  loadTask()
  
  // 如果任务正在运行，定时刷新
  intervalId = setInterval(() => {
    if (task.value && task.value.status === 'RUNNING') {
      loadTask()
    }
  }, 3000)
})

// 组件卸载时清理定时器
onUnmounted(() => {
  if (intervalId) {
    clearInterval(intervalId)
  }
})
</script>

<style scoped>
.task-detail-view {
  padding: 20px;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header h2 {
  margin: 0;
}

.actions {
  display: flex;
  gap: 10px;
}

.logs {
  margin-top: 20px;
}

.logs h3 {
  margin-bottom: 10px;
}

.log-content {
  max-height: 400px;
  overflow-y: auto;
  font-family: 'Courier New', monospace;
  font-size: 12px;
}

.log-item {
  padding: 2px 0;
  border-bottom: 1px solid #f0f0f0;
}
</style>
