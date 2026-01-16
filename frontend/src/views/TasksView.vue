<template>
  <div class="tasks-view">
    <el-card>
      <template #header>
        <div class="header">
          <h2>任务列表</h2>
          <div class="filters">
            <el-select v-model="filterStatus" placeholder="筛选状态" clearable @change="loadTasks">
              <el-option label="全部" value="" />
              <el-option label="待执行" value="PENDING" />
              <el-option label="运行中" value="RUNNING" />
              <el-option label="已完成" value="COMPLETED" />
              <el-option label="失败" value="FAILED" />
              <el-option label="已取消" value="CANCELLED" />
            </el-select>
            <el-button @click="loadTasks" :icon="Refresh">刷新</el-button>
          </div>
        </div>
      </template>

      <el-table :data="tasks" v-loading="loading" stripe>
        <el-table-column label="序号" type="index" width="80" :index="getIndex" />
        <el-table-column label="任务ID" prop="task_id" width="200" show-overflow-tooltip />
        <el-table-column label="文档名称" width="250">
          <template #default="scope">
            {{ getDocumentName(scope.row.document_path) }}
          </template>
        </el-table-column>
        <el-table-column label="当前步骤" width="180">
          <template #default="scope">
            <el-tag :type="getStateTagType(scope.row.current_state)">
              {{ getStateLabel(scope.row.current_state) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="任务状态" width="120">
          <template #default="scope">
            <el-tag :type="getStatusTagType(scope.row.status)">
              {{ getStatusLabel(scope.row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="180">
          <template #default="scope">
            {{ formatDateTime(scope.row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="320" fixed="right">
          <template #default="scope">
            <el-button-group>
              <el-button
                v-if="canContinue(scope.row)"
                type="primary"
                size="small"
                @click="continueTask(scope.row.task_id)"
              >
                继续
              </el-button>
              <el-button
                type="warning"
                size="small"
                @click="handleCancel(scope.row.task_id)"
                :disabled="scope.row.status !== 'RUNNING'"
              >
                取消
              </el-button>
              <el-button
                type="success"
                size="small"
                @click="handleDownload(scope.row.task_id)"
                :disabled="scope.row.status !== 'COMPLETED'"
              >
                下载报告
              </el-button>
              <el-button
                type="danger"
                size="small"
                @click="handleDelete(scope.row.task_id)"
                :disabled="scope.row.status === 'RUNNING'"
              >
                删除
              </el-button>
            </el-button-group>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination">
        <el-pagination
          :current-page="currentPage"
          :page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handlePageChange"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import api from '@/api'

const router = useRouter()

// 数据状态
const tasks = ref([])
const loading = ref(false)
const filterStatus = ref('')
const currentPage = ref(1)
const pageSize = ref(20)
const total = ref(0)

// 加载任务列表
const loadTasks = async () => {
  loading.value = true
  try {
    const response = await api.listTasks({
      status: filterStatus.value,
      page: currentPage.value,
      page_size: pageSize.value
    })
    
    if (response.success) {
      tasks.value = response.data.tasks
      if (response.data.pagination) {
        total.value = response.data.pagination.total
      }
    } else {
      ElMessage.error(response.message || '加载任务列表失败')
    }
  } catch (error) {
    ElMessage.error('加载任务列表失败：' + error.message)
  } finally {
    loading.value = false
  }
}

// 继续任务
const continueTask = (taskId) => {
  router.push(`/tasks/${taskId}`)
}

// 取消任务（二次确认）
const handleCancel = async (taskId) => {
  try {
    await ElMessageBox.confirm('确定要取消该任务吗？', '确认取消', {
      type: 'warning'
    })
    
    const response = await api.cancelTask(taskId, '用户手动取消')
    if (response.success) {
      ElMessage.success('任务已取消')
      loadTasks()
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
const handleDownload = async (taskId) => {
  try {
    const blob = await api.downloadReport(taskId, 'html')
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `report_${taskId}.html`
    a.click()
    window.URL.revokeObjectURL(url)
    ElMessage.success('报告下载成功')
  } catch (error) {
    ElMessage.error('下载报告失败：' + error.message)
  }
}

// 删除任务（二次确认）
const handleDelete = async (taskId) => {
  try {
    await ElMessageBox.confirm('确定要删除该任务吗？此操作不可恢复。', '确认删除', {
      type: 'warning'
    })
    
    const response = await api.deleteTask(taskId)
    if (response.success) {
      ElMessage.success('任务已删除')
      loadTasks()
    } else {
      ElMessage.error(response.message || '删除任务失败')
    }
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除任务失败：' + error.message)
    }
  }
}

// 分页处理
const handleSizeChange = (val) => {
  pageSize.value = val
  currentPage.value = 1
  loadTasks()
}

const handlePageChange = (val) => {
  currentPage.value = val
  loadTasks()
}

// 工具函数
const getIndex = (index) => {
  return (currentPage.value - 1) * pageSize.value + index + 1
}

const getDocumentName = (path) => {
  if (!path) return '-'
  const parts = path.split('/')
  return parts[parts.length - 1]
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

const canContinue = (task) => {
  return task.status !== 'COMPLETED' && task.status !== 'CANCELLED'
}

onMounted(() => {
  loadTasks()
})
</script>

<style scoped>
.tasks-view {
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

.filters {
  display: flex;
  gap: 10px;
}

.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
</style>
