<template>
  <div class="chat-container-root">
    <!-- 右侧聊天区域 -->
    <main class="chat-main">
      <div class="chat-container" :class="{ 'has-messages': hasMessages }">
        <!-- 无对话时的居中布局 -->
        <div v-if="!hasMessages" class="empty-state">
          <h1 class="welcome-title">我现在能怎么帮您？</h1>
          
          <div class="prompt-input-container">
            <!-- 文件预览区 -->
            <div v-if="selectedFile" class="file-preview-tab">
              <div class="file-info">
                <el-icon><Document /></el-icon>
                <span class="file-name">{{ selectedFile.name }}</span>
              </div>
              <button class="cancel-file-btn" @click="cancelFile">
                <el-icon><Close /></el-icon>
              </button>
            </div>

            <div class="prompt-input-input-area">
              <textarea
                ref="inputTextarea"
                v-model="inputMessage"
                placeholder="有什么我能帮您的吗？"
                @input="adjustTextareaHeight"
                @keydown="handleKeydown"
                rows="1"
              ></textarea>
            </div>

            <div class="prompt-input-action-bar">
              <button 
                class="action-btn upload-btn" 
                @click="triggerFileInput"
                title="上传文件"
              >
                <el-icon><Paperclip /></el-icon>
              </button>
              <div class="spacer"></div>
              <button 
                class="action-btn send-btn" 
                @click="sendMessage" 
                :disabled="(!inputMessage.trim() && !selectedFile) || loading"
                title="发送消息"
              >
                <el-icon><Top /></el-icon>
              </button>
            </div>
          </div>
        </div>

        <!-- 有对话时的布局 -->
        <template v-else>
          <div class="chat-messages" ref="messagesContainer">
            <div 
              v-for="(msg, index) in messages" 
              :key="index" 
              :class="['message', msg.role]"
            >
              <div class="message-content">
                <div class="message-avatar">
                  {{ msg.role === 'user' ? 'U' : 'A' }}
                </div>
                <div class="message-text">
                  <template v-if="msg.role === 'user'">{{ msg.content }}</template>
                  <template v-else-if="msg.role === 'assistant'">
                    <!-- 思考过程展示（灰色小号字体） -->
                    <div v-if="msg.thinking" class="thinking-block">
                      <div class="thinking-label">思考过程</div>
                      <div class="thinking-content">{{ msg.thinking }}</div>
                    </div>
                    <!-- 正常回复内容 -->
                    <MarkdownViewer 
                      v-if="msg.content" 
                      :content="msg.content" 
                    />
                    <div v-else-if="loading && index === messages.length - 1" class="loading-dots">
                      <span></span><span></span><span></span>
                    </div>
                  </template>
                  <span v-if="loading && msg.role === 'assistant' && index === messages.length - 1 && msg.content" class="typing-cursor"></span>
                </div>
              </div>
            </div>
          </div>

          <!-- 计划步骤展示组件 -->
          <PlanStepBar :planData="currentPlanData" />

          <div class="bottom-input-wrapper">
            <div class="bottom-input-container">
              <!-- 文件预览区 -->
              <div v-if="selectedFile" class="file-preview-tab">
                <div class="file-info">
                  <el-icon><Document /></el-icon>
                  <span class="file-name">{{ selectedFile.name }}</span>
                </div>
                <button class="cancel-file-btn" @click="cancelFile">
                  <el-icon><Close /></el-icon>
                </button>
              </div>

              <div class="prompt-input-input-area">
                <textarea
                  ref="bottomInputTextarea"
                  v-model="inputMessage"
                  placeholder="输入消息..."
                  @input="adjustBottomTextareaHeight"
                  @keydown="handleKeydown"
                  rows="1"
                ></textarea>
              </div>

              <div class="prompt-input-action-bar">
                <button 
                  class="action-btn upload-btn" 
                  @click="triggerFileInput"
                  title="上传文件"
                >
                  <el-icon><Paperclip /></el-icon>
                </button>
                <div class="spacer"></div>
                <button 
                  class="action-btn send-btn" 
                  @click="sendMessage" 
                  :disabled="(!inputMessage.trim() && !selectedFile) || loading"
                  title="发送消息"
                >
                  <el-icon><Top /></el-icon>
                </button>
              </div>
            </div>
          </div>
        </template>
      </div>
    </main>

    <!-- 隐藏的文件上传 input -->
    <input
      type="file"
      ref="fileInput"
      style="display: none"
      @change="onFileSelected"
    />
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted, watch } from 'vue'
import { storeToRefs } from 'pinia'
import api from '@/api'
import { useChatStore } from '@/stores/chat'
import MarkdownViewer from '@/components/MarkdownViewer.vue'
import PlanStepBar from '@/components/PlanStepBar.vue'

const chatStore = useChatStore()
const { 
  conversations, 
  currentConversationId, 
  messages, 
  loading 
} = storeToRefs(chatStore)
const { loadConversations, startNewChat } = chatStore

const inputMessage = ref('')

const selectedFile = ref(null)
const fileInput = ref(null)

const inputTextarea = ref(null)
const bottomInputTextarea = ref(null)
const messagesContainer = ref(null)

const currentPlanData = ref(null)

const hasMessages = computed(() => messages.value.length > 0)

// 标志位，防止发送消息时触发的 ID 变化导致重复加载
const isSending = ref(false)

// 监听当前对话变化，加载消息
watch(currentConversationId, async (newId) => {
  if (isSending.value) return // 如果正在发送中，不触发自动加载，避免覆盖本地正在生成的流

  if (newId) {
    try {
      const data = await api.listMessages(newId, { limit: 1000 })
      messages.value = data.map(msg => ({
        role: msg.role,
        content: msg.content
      }))
      
      await nextTick()
      scrollToBottom()
    } catch (error) {
      console.error('加载对话消息失败:', error)
    }
  } else {
    messages.value = []
  }
}, { immediate: true })

// 发送消息
const sendMessage = async () => {
  if ((!inputMessage.value.trim() && !selectedFile.value) || loading.value) return

  isSending.value = true
  let userMessage = inputMessage.value.trim()
  const hasFile = !!selectedFile.value
  const currentFile = selectedFile.value
  
  inputMessage.value = ''
  selectedFile.value = null
  resetTextareaHeight()

  try {
    // 处理文件上传
    let fileInfoString = ''
    if (hasFile) {
      // 如果没有会话ID，先创建一个，否则上传会失败
      if (!currentConversationId.value) {
        try {
          const newConv = await api.createConversation({ 
            title: userMessage.substring(0, 50) || currentFile.name 
          })
          currentConversationId.value = newConv.conversation_id
          await loadConversations()
        } catch (err) {
          console.error('创建会话失败:', err)
          throw new Error('无法开始新对话并上传文件')
        }
      }

      try {
        const uploadRes = await api.uploadChatFile(currentConversationId.value, currentFile)
        if (uploadRes.success) {
          fileInfoString = `\n\n[文件已上传: ${currentFile.name}]`
        }
      } catch (err) {
        console.error('文件上传失败:', err)
        // 继续发送消息，但提示上传失败
        fileInfoString = `\n\n[文件上传失败: ${currentFile.name}]`
      }
    }

    const finalMessage = userMessage + fileInfoString

    // 添加用户消息
    messages.value.push({
      role: 'user',
      content: finalMessage
    })

    await nextTick()
    scrollToBottom()

    loading.value = true

    // 添加空的助手消息占位
    const assistantMsgIndex = messages.value.length
    messages.value.push({
      role: 'assistant',
      content: '',
      thinking: ''  // 思考过程
    })

    // 调用聊天接口(SSE流式)
    const response = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('access_token')}`
      },
      body: JSON.stringify({
        message: finalMessage,
        conversation_id: currentConversationId.value || undefined
      })
    })

    if (!response.ok) {
      throw new Error('请求失败')
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let assistantResponse = ''
    let thinkingResponse = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      const chunk = decoder.decode(value, { stream: true })
      const lines = chunk.split('\n')

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.substring(6).trim()
          
          try {
            const parsed = JSON.parse(data)
            if (parsed.type === 'start') {
              // 如果是新对话，更新对话ID并加载列表
              if (!currentConversationId.value) {
                currentConversationId.value = parsed.conversation_id
                await loadConversations()
              }
            } else if (parsed.type === 'plan_update' && parsed.data) {
              // 处理计划更新
              currentPlanData.value = parsed.data
            } else if (parsed.type === 'thinking' && parsed.content) {
              // 处理思考过程
              thinkingResponse += parsed.content
              messages.value[assistantMsgIndex].thinking = thinkingResponse
              await nextTick()
              scrollToBottom()
            } else if (parsed.type === 'chunk' && parsed.content) {
              assistantResponse += parsed.content
              messages.value[assistantMsgIndex].content = assistantResponse
              await nextTick()
              scrollToBottom()
            } else if (parsed.type === 'error') {
              throw new Error(parsed.message || '流式输出错误')
            }
          } catch (e) {
            console.warn('解析消息块失败:', e)
          }
        }
      }
    }

  } catch (error) {
    console.error('发送消息失败:', error)
    if (messages.value.length > 0) {
      const lastMsg = messages.value[messages.value.length - 1]
      if (lastMsg.role === 'assistant') {
        lastMsg.content = `抱歉,发送消息时出现错误: ${error.message}`
      }
    }
  } finally {
    loading.value = false
    isSending.value = false
  }
}

// 文本框高度调整
const adjustTextareaHeight = () => {
  const textarea = inputTextarea.value
  if (!textarea) return
  textarea.style.height = 'auto'
  textarea.style.height = textarea.scrollHeight + 'px'
}

const adjustBottomTextareaHeight = () => {
  const textarea = bottomInputTextarea.value
  if (!textarea) return
  textarea.style.height = 'auto'
  textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px'
}

const resetTextareaHeight = () => {
  if (inputTextarea.value) {
    inputTextarea.value.style.height = 'auto'
  }
  if (bottomInputTextarea.value) {
    bottomInputTextarea.value.style.height = 'auto'
  }
}

// 文件处理逻辑
const triggerFileInput = () => {
  if (fileInput.value) {
    fileInput.value.click()
  }
}

const onFileSelected = (e) => {
  const file = e.target.files[0]
  if (file) {
    selectedFile.value = file
  }
  // 清空 input 使得同一个文件可以重复触发 change
  e.target.value = ''
}

const cancelFile = () => {
  selectedFile.value = null
}

// 键盘事件处理
const handleKeydown = (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}

// 滚动到底部
const scrollToBottom = () => {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

// 初始化
onMounted(() => {
  loadConversations()
})
</script>

<style scoped>
.chat-container-root {
  width: 100%;
  height: 100%;
  display: flex;
  background: var(--main-bg);
  overflow: hidden;
}

/* ==================== 右侧聊天区域 ==================== */
.chat-main {
  flex: 1;
  height: 100%;
  overflow: hidden;
  width: 100%;
}

.chat-container {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: var(--main-bg);
  overflow: hidden;
}

.chat-container.has-messages {
  justify-content: flex-start;
}

/* 空状态 */
.empty-state {
  width: 100%;
  max-width: 800px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 32px;
  padding: 0 24px;
}

.welcome-title {
  font-size: 32px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
  text-align: center;
}

/* 输入框样式 */
.prompt-input-container,
.bottom-input-container {
  width: 100%;
  max-width: 760px;
  background: var(--input-bg);
  border: 1px solid var(--border-color);
  border-radius: 16px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.prompt-input-input-area {
  width: 100%;
}

.prompt-input-input-area textarea {
  width: 100%;
  min-height: 24px;
  max-height: 200px;
  padding: 8px 12px;
  border: none;
  background: transparent;
  color: var(--text-primary);
  font-size: 15px;
  line-height: 1.6;
  resize: none;
  outline: none;
  font-family: inherit;
}

.prompt-input-input-area textarea::placeholder {
  color: var(--text-secondary);
}

.prompt-input-action-bar {
  display: flex;
  align-items: center;
  gap: 8px;
}

.spacer {
  flex: 1;
}

.action-btn {
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  transition: all 0.2s;
}

.action-btn:hover:not(:disabled) {
  background: var(--border-color);
}

.send-btn {
  background: var(--send-btn);
  color: white;
}

.send-btn:hover:not(:disabled) {
  background: var(--send-btn-hover);
}

.send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 消息列表 */
.chat-messages {
  flex: 1;
  width: 100%;
  max-width: 800px;
  overflow-y: auto;
  padding: 24px;
  margin: 0 auto;
}

.message {
  margin-bottom: 24px;
}

.message-content {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.message-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--send-btn);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 600;
  flex-shrink: 0;
}

.message.user .message-avatar {
  background: var(--border-color);
  color: var(--text-primary);
}

.message-text {
  flex: 1;
  color: var(--text-primary);
  font-size: 15px;
  line-height: 1.6;
  word-break: break-word;
}

.message.user .message-text {
  white-space: pre-wrap;
}

/* 思考过程样式 - 灰色小号字体，黑白主题下均为灰色 */
.thinking-block {
  margin-bottom: 12px;
  padding: 8px 12px;
  background: rgba(128, 128, 128, 0.1);
  border-radius: 6px;
  border-left: 3px solid #888;
}

.thinking-label {
  font-size: 12px;
  color: #888;
  margin-bottom: 4px;
  font-weight: 500;
}

.thinking-content {
  font-size: 13px;
  color: #888;
  line-height: 1.5;
  white-space: pre-wrap;
}

.typing-cursor {
  display: inline-block;
  width: 2px;
  height: 1em;
  background: var(--text-primary);
  margin-left: 2px;
  animation: blink 1s step-end infinite;
}

@keyframes blink {
  50% { opacity: 0; }
}

.loading-dots {
  display: flex;
  gap: 4px;
}

.loading-dots span {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-secondary);
  animation: bounce 1.4s infinite ease-in-out both;
}

.loading-dots span:nth-child(1) {
  animation-delay: -0.32s;
}

.loading-dots span:nth-child(2) {
  animation-delay: -0.16s;
}

@keyframes bounce {
  0%, 80%, 100% { transform: scale(0); }
  40% { transform: scale(1); }
}

/* 底部输入框 */
.bottom-input-wrapper {
  width: 100%;
  padding: 16px 24px;
  background: var(--main-bg);
  border-top: 1px solid var(--border-color);
  display: flex;
  justify-content: center;
}

.bottom-input-container {
  max-width: 800px;
}

/* 文件预览 Tab 样式 */
.file-preview-tab {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--main-bg);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 6px 12px;
  margin-bottom: 8px;
  max-width: fit-content;
}

.file-info {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-primary);
  font-size: 13px;
}

.file-name {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cancel-file-btn {
  background: transparent;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 2px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  margin-left: 8px;
  transition: background 0.2s;
}

.cancel-file-btn:hover {
  background: var(--border-color);
  color: #f56c6c;
}

.upload-btn {
  margin-right: auto;
}

.upload-btn:hover:not(:disabled) {
  background: var(--border-color);
  color: var(--send-btn);
}
</style>
