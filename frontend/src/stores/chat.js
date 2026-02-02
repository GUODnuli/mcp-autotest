import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/api'

export const useChatStore = defineStore('chat', () => {
  const conversations = ref([])
  const currentConversationId = ref(null)
  const collapsedGroups = ref({})
  const messages = ref([])
  const loading = ref(false)
  // Pending title updates that arrived before loadConversations() completed
  const pendingTitleUpdates = ref({})

  // 时间分组辅助函数
  const groupConversationsByTime = (conversations) => {
    const now = new Date()
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
    const yesterday = new Date(today)
    yesterday.setDate(yesterday.getDate() - 1)
    const last3Days = new Date(today)
    last3Days.setDate(last3Days.getDate() - 3)
    const last7Days = new Date(today)
    last7Days.setDate(last7Days.getDate() - 7)
    const last3Months = new Date(today)
    last3Months.setMonth(last3Months.getMonth() - 3)
    const last6Months = new Date(today)
    last6Months.setMonth(last6Months.getMonth() - 6)
    const thisYear = new Date(now.getFullYear(), 0, 1)

    const groups = {
      today: { label: '今天', conversations: [] },
      yesterday: { label: '昨天', conversations: [] },
      last3Days: { label: '近3天', conversations: [] },
      last7Days: { label: '近7天', conversations: [] },
      last3Months: { label: '近3月', conversations: [] },
      last6Months: { label: '近6月', conversations: [] },
      thisYear: { label: '年度', conversations: [] }
    }

    conversations.forEach(conv => {
      const convDate = new Date(conv.updated_at)
      
      if (convDate >= today) {
        groups.today.conversations.push(conv)
      } else if (convDate >= yesterday) {
        groups.yesterday.conversations.push(conv)
      } else if (convDate >= last3Days) {
        groups.last3Days.conversations.push(conv)
      } else if (convDate >= last7Days) {
        groups.last7Days.conversations.push(conv)
      } else if (convDate >= last3Months) {
        groups.last3Months.conversations.push(conv)
      } else if (convDate >= last6Months) {
        groups.last6Months.conversations.push(conv)
      } else if (convDate >= thisYear) {
        groups.thisYear.conversations.push(conv)
      }
    })

    return Object.values(groups).filter(group => group.conversations.length > 0)
  }

  const groupedConversations = computed(() => groupConversationsByTime(conversations.value))

  const loadConversations = async () => {
    try {
      const data = await api.listConversations({ limit: 1000 })
      conversations.value = data
      // Apply any pending title updates that arrived before this load completed
      const pending = pendingTitleUpdates.value
      pendingTitleUpdates.value = {}
      if (Object.keys(pending).length > 0) {
        conversations.value = conversations.value.map(c =>
          pending[c.conversation_id] ? { ...c, title: pending[c.conversation_id] } : c
        )
      }
    } catch (error) {
      console.error('加载对话列表失败:', error)
    }
  }

  const startNewChat = () => {
    currentConversationId.value = null
    messages.value = []
  }

  const deleteConversation = async (conversationId) => {
    if (!confirm('确定要删除此对话吗？')) return
    
    try {
      await api.deleteConversation(conversationId)
      conversations.value = conversations.value.filter(c => c.conversation_id !== conversationId)
      
      if (currentConversationId.value === conversationId) {
        startNewChat()
      }
    } catch (error) {
      console.error('删除对话失败:', error)
      throw error
    }
  }

  const toggleGroup = (label) => {
    collapsedGroups.value[label] = !collapsedGroups.value[label]
  }

  const updateConversationTitle = (conversationId, title) => {
    const found = conversations.value.some(c => c.conversation_id === conversationId)
    if (found) {
      conversations.value = conversations.value.map(c =>
        c.conversation_id === conversationId ? { ...c, title } : c
      )
    } else {
      // Conversation not yet in store (loadConversations still pending) — queue the update
      pendingTitleUpdates.value = { ...pendingTitleUpdates.value, [conversationId]: title }
    }
  }

  return {
    conversations,
    currentConversationId,
    collapsedGroups,
    messages,
    loading,
    groupedConversations,
    loadConversations,
    startNewChat,
    deleteConversation,
    toggleGroup,
    updateConversationTitle
  }
})
