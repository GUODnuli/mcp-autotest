<template>
  <div class="statistics-view">
    <el-card>
      <template #header>
        <h2>统计分析</h2>
      </template>
      
      <el-tabs v-model="activeTab" @tab-change="handleTabChange">
        <!-- 原生测试报告 -->
        <el-tab-pane label="原生测试报告" name="raw">
          <div class="report-controls">
            <el-select 
              v-model="selectedTask" 
              placeholder="选择已完成的任务" 
              filterable
              @change="loadRawReport"
              style="width: 400px"
            >
              <el-option 
                v-for="task in completedTasks" 
                :key="task.task_id" 
                :label="`${task.task_id} - ${getDocumentName(task.document_path)}`" 
                :value="task.task_id" 
              />
            </el-select>
            <el-button 
              v-if="selectedTask" 
              @click="loadRawReport" 
              :icon="Refresh"
              :loading="loadingRaw"
            >
              刷新
            </el-button>
          </div>
          
          <div v-if="loadingRaw" class="loading-container">
            <el-skeleton :rows="10" animated />
          </div>
          
          <MarkdownViewer 
            v-else-if="rawMarkdown" 
            :content="rawMarkdown" 
          />
          
          <el-empty 
            v-else 
            description="请选择任务查看报告" 
          />
        </el-tab-pane>
        
        <!-- LLM 分析报告 -->
        <el-tab-pane label="LLM 分析报告" name="analysis">
          <div class="report-controls">
            <el-select 
              v-model="selectedTask" 
              placeholder="选择已完成的任务" 
              filterable
              style="width: 400px"
            >
              <el-option 
                v-for="task in completedTasks" 
                :key="task.task_id" 
                :label="`${task.task_id} - ${getDocumentName(task.document_path)}`" 
                :value="task.task_id" 
              />
            </el-select>
            <el-button 
              type="primary" 
              @click="analyzeReport" 
              :loading="analyzing"
              :disabled="!selectedTask"
            >
              {{ analyzing ? '分析中...' : '生成分析' }}
            </el-button>
          </div>
          
          <el-alert
            v-if="!selectedTask"
            title="提示"
            type="info"
            description="请先选择任务，然后点击“生成分析”按钮，LLM 将对测试报告进行深入分析。"
            :closable="false"
            style="margin-top: 20px"
          />
          
          <div v-if="analyzing" class="loading-container">
            <el-skeleton :rows="10" animated />
            <p class="analyzing-tip">正在调用 LLM 分析报告，请稍候（可能需要 5-15 秒）...</p>
          </div>
          
          <MarkdownViewer 
            v-else-if="analysisMarkdown" 
            :content="analysisMarkdown" 
          />
          
          <el-empty 
            v-else-if="selectedTask && !analyzing" 
            description="点击“生成分析”按钮获取 LLM 深度分析" 
          />
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import api from '@/api'
import MarkdownViewer from '@/components/MarkdownViewer.vue'

const activeTab = ref('raw')
const selectedTask = ref('')
const completedTasks = ref([])
const loadingTasks = ref(false)

const rawMarkdown = ref('')
const loadingRaw = ref(false)

const analysisMarkdown = ref('')
const analyzing = ref(false)

// 加载已完成的任务列表
const loadTasks = async () => {
  loadingTasks.value = true
  try {
    const response = await api.listTasks({
      status: 'COMPLETED',
      page: 1,
      page_size: 100
    })
    
    if (response.success) {
      completedTasks.value = response.data.tasks || []
      
      // 如果有任务且没有选中任务，自动选中最新的
      if (completedTasks.value.length > 0 && !selectedTask.value) {
        selectedTask.value = completedTasks.value[0].task_id
      }
    } else {
      ElMessage.error(response.message || '加载任务列表失败')
    }
  } catch (error) {
    console.error('加载任务列表失败:', error)
    ElMessage.error('加载任务列表失败：' + error.message)
  } finally {
    loadingTasks.value = false
  }
}

// 加载原生 Markdown 报告
const loadRawReport = async () => {
  if (!selectedTask.value) {
    ElMessage.warning('请先选择任务')
    return
  }
  
  loadingRaw.value = true
  rawMarkdown.value = ''
  
  try {
    const response = await api.getMarkdownReport(selectedTask.value)
    
    if (response.success) {
      rawMarkdown.value = response.data.content || ''
      ElMessage.success('报告加载成功')
    } else {
      ElMessage.error(response.message || '加载报告失败')
    }
  } catch (error) {
    console.error('加载报告失败:', error)
    ElMessage.error('加载报告失败：' + error.message)
  } finally {
    loadingRaw.value = false
  }
}

// 生成 LLM 分析
const analyzeReport = async () => {
  if (!selectedTask.value) {
    ElMessage.warning('请先选择任务')
    return
  }
  
  analyzing.value = true
  analysisMarkdown.value = ''
  
  try {
    ElMessage.info('正在调用 LLM 分析报告，请稍候...')
    
    const response = await api.analyzeReport(selectedTask.value)
    
    if (response.success) {
      analysisMarkdown.value = response.data.content || ''
      ElMessage.success('分析完成')
    } else {
      ElMessage.error(response.message || '分析失败')
    }
  } catch (error) {
    console.error('分析失败:', error)
    ElMessage.error('分析失败：' + error.message)
  } finally {
    analyzing.value = false
  }
}

// 标签页切换
const handleTabChange = (tabName) => {
  // 切换到原生报告标签页时，如果有选中任务且没有报告，自动加载
  if (tabName === 'raw' && selectedTask.value && !rawMarkdown.value) {
    loadRawReport()
  }
}

// 工具函数
const getDocumentName = (path) => {
  if (!path) return '未知文档'
  const parts = path.split(/[\\/]/)
  return parts[parts.length - 1]
}

// 页面加载时获取任务列表
onMounted(() => {
  loadTasks()
})
</script>

<style scoped>
.statistics-view {
  padding: 20px;
}

.report-controls {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
  align-items: center;
}

.loading-container {
  padding: 20px;
}

.analyzing-tip {
  text-align: center;
  color: #909399;
  margin-top: 20px;
  font-size: 14px;
}
</style>
