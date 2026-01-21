<template>
  <div v-if="planData" class="plan-step-widget" :class="{ 'is-collapsed': !isExpanded }">
    <div class="plan-header" @click="isExpanded = !isExpanded">
      <div class="plan-title-wrapper">
        <el-icon class="plan-main-icon"><Management /></el-icon>
        <span class="plan-title-text">{{ planData.name }}</span>
      </div>
      <div class="plan-toggle">
        <el-icon :class="{ 'is-rotated': !isExpanded }"><ArrowUp /></el-icon>
      </div>
    </div>
    
    <div v-if="isExpanded" class="plan-body">
      <div class="steps-container">
        <div 
          v-for="(step, index) in planData.subtasks" 
          :key="index" 
          class="step-row"
          :class="step.state"
        >
          <div class="step-status-icon">
            <el-icon v-if="step.state === 'done'" class="status-done"><SuccessFilled /></el-icon>
            <el-icon v-else-if="step.state === 'in_progress'" class="status-progress is-loading"><Loading /></el-icon>
            <el-icon v-else-if="step.state === 'abandoned'" class="status-abandoned"><CircleCloseFilled /></el-icon>
            <el-icon v-else class="status-todo"><CircleCheck /></el-icon>
          </div>
          <div class="step-content">
            <div class="step-name">{{ step.name }}</div>
            <div v-if="step.outcome" class="step-outcome-text">
              {{ step.outcome }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { 
  Management, 
  ArrowUp, 
  SuccessFilled, 
  Loading, 
  CircleCloseFilled, 
  CircleCheck 
} from '@element-plus/icons-vue'

const props = defineProps({
  planData: {
    type: Object,
    default: null
  }
})

const isExpanded = ref(true)
</script>

<style scoped>
.plan-step-widget {
  position: absolute;
  top: 20px;
  right: 20px;
  width: 300px;
  max-height: 80vh;
  background: var(--input-bg);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  display: flex;
  flex-direction: column;
  z-index: 100;
  overflow: hidden;
  transition: all 0.3s ease;
}

.plan-step-widget.is-collapsed {
  width: 200px;
}

.plan-header {
  padding: 12px 16px;
  background: var(--main-bg);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--border-color);
  user-select: none;
}

.plan-title-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
  overflow: hidden;
}

.plan-main-icon {
  color: var(--send-btn);
  font-size: 18px;
  flex-shrink: 0;
}

.plan-title-text {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.plan-toggle {
  display: flex;
  align-items: center;
  color: var(--text-secondary);
}

.is-rotated {
  transform: rotate(180deg);
}

.plan-body {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
}

.steps-container {
  display: flex;
  flex-direction: column;
}

.step-row {
  padding: 10px 16px;
  display: flex;
  gap: 12px;
  transition: background 0.2s;
}

.step-row:hover {
  background: rgba(128, 128, 128, 0.05);
}

.step-status-icon {
  font-size: 18px;
  margin-top: 2px;
  flex-shrink: 0;
}

.status-done { color: #67c23a; }
.status-progress { color: #409eff; }
.status-abandoned { color: #f56c6c; }
.status-todo { color: var(--text-secondary); }

.step-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.step-name {
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.4;
}

.step-row.done .step-name {
  color: var(--text-secondary);
  text-decoration: line-through;
}

.step-row.in_progress .step-name {
  font-weight: 600;
  color: #409eff;
}

.step-outcome-text {
  font-size: 11px;
  color: var(--text-secondary);
  background: rgba(128, 128, 128, 0.05);
  padding: 4px 8px;
  border-radius: 4px;
  word-break: break-all;
}

/* 滚动条样式 */
.plan-body::-webkit-scrollbar {
  width: 4px;
}
.plan-body::-webkit-scrollbar-thumb {
  background: var(--border-color);
  border-radius: 2px;
}

.is-loading {
  animation: rotating 2s linear infinite;
}

@keyframes rotating {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
