<template>
  <div class="app-container" :class="theme">
    <!-- 侧边栏 - 仅在非认证页面显示 -->
    <aside v-if="!isAuthPage" class="sidebar" :class="{ collapsed: !sidebarExpanded }">
      <div class="sidebar-header">
        <button class="sidebar-toggle" @click="toggleSidebar" :title="sidebarExpanded ? '收起侧边栏' : '展开侧边栏'">
          <svg viewBox="0 0 1024 1024" class="toggle-icon" :class="{ flipped: !sidebarExpanded }">
            <path d="M768 102.4c54.186667 0 100.437333 19.2 138.752 57.514667C945.109333 198.229333 964.266667 244.48 964.266667 298.666667v426.666666c0 54.186667-19.2 100.437333-57.514667 138.794667C868.437333 902.4 822.186667 921.6 768 921.6H256c-54.186667 0-100.437333-19.2-138.752-57.514667C78.890667 825.813333 59.733333 779.52 59.733333 725.333333V298.666667c0-54.186667 19.2-100.437333 57.514667-138.752C155.562667 121.6 201.770667 102.4 256 102.4h512z m-512 85.333333c-73.941333 0-110.933333 36.992-110.933333 110.933334v426.666666c0 73.941333 36.949333 110.933333 110.933333 110.933334h85.333333V187.733333H256z m170.666667 648.533334h341.333333c73.941333 0 110.933333-36.992 110.933333-110.933334V298.666667c0-73.941333-36.992-110.933333-110.933333-110.933334h-341.333333v648.533334z"></path>
          </svg>
        </button>
        <button v-if="sidebarExpanded" class="new-chat-sidebar-btn" @click="handleNewChat" title="新建对话">
          <el-icon><Plus /></el-icon>
          <span>新建对话</span>
        </button>
      </div>
      
      <nav class="sidebar-nav">
        <!-- 对话历史列表 -->
        <div v-if="sidebarExpanded" class="sidebar-history">
          <div v-for="group in groupedConversations" :key="group.label" class="history-group">
            <div class="history-group-title">{{ group.label }}</div>
            <div
              v-for="conv in group.conversations"
              :key="conv.conversation_id"
              class="history-item"
              :class="{ active: currentConversationId === conv.conversation_id }"
              @click="loadConversation(conv.conversation_id)"
            >
              <span class="history-item-title">{{ conv.title }}</span>
              <button class="history-delete-btn" @click.stop="deleteConversation(conv.conversation_id)">
                <el-icon><Delete /></el-icon>
              </button>
            </div>
          </div>
          <div v-if="conversations.length === 0" class="history-empty">
            暂无对话历史
          </div>
        </div>
      </nav>
      
      <div class="sidebar-footer">
        <!-- 用户信息 -->
        <div v-if="isLoggedIn" class="user-info" @click="toggleUserMenu">
          <div class="user-avatar">{{ userInitial }}</div>
          <div class="user-details">
            <div class="user-name">{{ displayName }}</div>
          </div>
          <el-icon class="dropdown-icon" :class="{ rotated: showUserMenu }"><ArrowDown /></el-icon>
        </div>
        
        <!-- 用户下拉菜单 -->
        <transition name="menu-fade">
          <div v-if="showUserMenu" class="user-menu">
            <router-link to="/settings" class="menu-item" @click="closeUserMenu">
              <svg viewBox="0 0 1024 1024" class="menu-icon">
                <path d="M625.493333 176.042667q1.834667 6.058667 5.973334 10.922666 4.821333 5.632 11.648 8.448 6.826667 2.816 14.208 2.261334 7.381333-0.597333 13.738666-4.437334 78.037333-47.573333 142.634667 17.066667 64.64 64.597333 17.066667 142.677333-3.84 6.314667-4.437334 13.653334-0.554667 7.424 2.261334 14.250666 2.816 6.826667 8.448 11.648 5.632 4.778667 12.8 6.528Q938.666667 420.565333 938.666667 512q0 91.392-88.746667 112.938667-7.253333 1.749333-12.842667 6.570666-5.632 4.821333-8.448 11.648-2.816 6.826667-2.261333 14.208 0.554667 7.381333 4.437333 13.653334 47.530667 78.08-17.066666 142.72-64.64 64.597333-142.677334 17.066666-6.314667-3.84-13.653333-4.437333-7.424-0.554667-14.250667 2.261333-6.826667 2.816-11.690666 8.448-4.778667 5.632-6.528 12.8Q603.434667 938.666667 512 938.666667q-91.392 0-112.938667-88.832-1.706667-7.168-6.570666-12.8-4.778667-5.589333-11.648-8.448-6.826667-2.816-14.208-2.261334-7.338667 0.597333-13.653334 4.437334-78.08 47.573333-142.677333-17.066667-64.64-64.597333-17.066667-142.677333 3.84-6.314667 4.437334-13.653334 0.554667-7.381333-2.261334-14.250666-2.816-6.826667-8.448-11.605334-5.632-4.821333-12.8-6.570666Q85.333333 603.434667 85.333333 512.042667t88.789334-112.981334q15.232-3.712 21.248-18.218666 5.973333-14.506667-2.133334-27.904-47.573333-78.037333 17.066667-142.634667 64.597333-64.64 142.634667-17.066667 6.314667 3.84 13.653333 4.394667 7.424 0.597333 14.250667-2.261333 6.826667-2.816 11.605333-8.448 4.821333-5.632 6.570667-12.842667Q420.693333 85.333333 512 85.333333t112.981333 88.746667l0.469334 1.962667z m-84.053333 16Q535.210667 170.666667 512 170.666667q-24.32 0-30.08 23.594666-6.528 26.965333-24.618667 48.128-18.090667 21.162667-43.776 31.829334-25.728 10.666667-53.461333 8.533333-27.733333-2.133333-51.498667-16.64-20.778667-12.672-37.973333 4.522667-17.152 17.194667-4.522667 37.930666 30.72 50.346667 8.106667 104.96-22.570667 54.528-79.914667 68.48Q170.666667 487.68 170.666667 512q0 24.277333 23.594666 29.952 27.050667 6.570667 48.213334 24.661333 21.12 18.133333 31.786666 43.818667 10.666667 25.728 8.490667 53.504-2.176 27.733333-16.64 51.498667-12.672 20.736 4.522667 37.888 17.152 17.194667 37.930666 4.565333 23.722667-14.506667 51.498667-16.64 27.733333-2.176 53.461333 8.448 25.685333 10.666667 43.818667 31.829333 18.090667 21.12 24.661333 48.213334Q487.68 853.333333 512 853.333333q24.32 0 29.994667-23.552 6.613333-27.093333 24.746666-48.213333 18.048-21.12 43.776-31.786667 25.685333-10.666667 53.418667-8.533333 27.733333 2.176 51.498667 16.64 20.778667 12.672 37.973333-4.522667 17.152-17.152 4.48-37.930666-14.464-23.722667-16.64-51.498667-2.133333-27.733333 8.533333-53.418667 10.666667-25.728 31.786667-43.818666 21.12-18.090667 48.170667-24.661334Q853.333333 536.277333 853.333333 512q0-24.32-23.552-29.994667-27.093333-6.570667-48.213333-24.661333-21.162667-18.090667-31.829333-43.818667t-8.490667-53.461333q2.176-27.776 16.64-51.541333 12.672-20.693333-4.522667-37.888-17.152-17.194667-37.930666-4.522667-23.722667 14.506667-51.456 16.64-27.733333 2.133333-53.504-8.533333-25.685333-10.624-43.818667-31.744-18.090667-21.162667-24.661333-48.213334l-0.512-2.218666z m61.056 229.461333Q565.034667 384 512 384q-53.034667 0-90.496 37.504Q384 458.965333 384 512q0 53.034667 37.504 90.496Q458.965333 640 512 640q53.034667 0 90.496-37.504Q640 565.034667 640 512q0-53.034667-37.504-90.496z m-120.661333 60.330667Q494.336 469.333333 512 469.333333t30.165333 12.501334Q554.666667 494.336 554.666667 512t-12.501334 30.165333Q529.664 554.666667 512 554.666667t-30.165333-12.501334Q469.333333 529.664 469.333333 512t12.501334-30.165333z"></path>
              </svg>
              <span class="menu-text">设置</span>
            </router-link>
            <div class="menu-item" @click="handleLogout">
              <svg viewBox="0 0 1024 1024" class="menu-icon">
                <path d="M356.394667 332.8V243.2q0-54.869333 39.082666-93.653333 38.954667-38.613333 93.952-38.613334h316.202667q55.04 0 93.952 38.613334Q938.666667 188.330667 938.666667 243.2v537.6q0 54.912-39.082667 93.653333-38.954667 38.613333-93.952 38.613334h-316.202667q-55.04 0-93.952-38.613334-39.082667-38.741333-39.082666-93.653333v-89.6a42.666667 42.666667 0 1 1 85.333333 0v89.6q0 19.328 13.824 33.066667 13.994667 13.866667 33.877333 13.866666h316.202667q19.882667 0 33.877333-13.866666 13.824-13.738667 13.824-33.066667V243.2q0-19.328-13.824-33.066667-13.994667-13.866667-33.877333-13.866666h-316.202667q-19.882667 0-33.877333 13.866666-13.824 13.738667-13.824 33.066667v89.6a42.666667 42.666667 0 0 1-85.333333 0zM306.176 377.6a42.666667 42.666667 0 0 1-12.586667 30.293333L231.637333 469.333333h438.485334a42.666667 42.666667 0 1 1 0 85.333334H231.637333l61.866667 61.44a42.666667 42.666667 0 1 1-60.032 60.586666l-135.509333-134.4a42.666667 42.666667 0 0 1 0-60.586666l135.509333-134.4a42.666667 42.666667 0 0 1 72.704 30.293333z"></path>
              </svg>
              <span class="menu-text">退出登录</span>
            </div>
          </div>
        </transition>
      </div>
    </aside>
    
    <!-- 主内容区 -->
    <main class="main-content" :class="{ 'full-width': isAuthPage }">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useThemeStore } from '@/stores/theme'
import { useUserStore } from '@/stores/user'
import { useChatStore } from '@/stores/chat'

const route = useRoute()
const router = useRouter()
const themeStore = useThemeStore()
const userStore = useUserStore()
const chatStore = useChatStore()

const { theme, sidebarExpanded } = storeToRefs(themeStore)
const { toggleTheme, toggleSidebar, initTheme } = themeStore

const { isLoggedIn, displayName } = storeToRefs(userStore)
const { conversations, currentConversationId, groupedConversations } = storeToRefs(chatStore)
const { loadConversations, startNewChat, deleteConversation } = chatStore

// 用户菜单展开状态
const showUserMenu = ref(false)

// 监听路由变化，如果在首页且没有对话ID，则认为是新建对话
watch(() => route.path, (newPath) => {
  if (newPath === '/' && !route.query.id) {
    startNewChat()
  }
}, { immediate: true })

const handleNewChat = () => {
  startNewChat()
  if (route.path !== '/') {
    router.push('/')
  }
}

const loadConversation = (id) => {
  currentConversationId.value = id
  if (route.path !== '/') {
    router.push('/')
  }
}

// 判断是否是认证页面（登录/注册）
const isAuthPage = computed(() => {
  return route.path === '/login' || route.path === '/register' || route.path === '/settings'
})

// 用户名首字母
const userInitial = computed(() => {
  const name = displayName.value || ''
  return name.charAt(0).toUpperCase() || 'U'
})

const toggleUserMenu = () => {
  showUserMenu.value = !showUserMenu.value
}

const closeUserMenu = () => {
  showUserMenu.value = false
}

const handleLogout = async () => {
  closeUserMenu()
  await userStore.logout()
  router.push('/login')
}

const handleAuthLogout = (event) => {
  router.push('/login')
  // 可选：显示提示信息
  if (event.detail?.reason) {
    // 如果使用了 Element Plus，可以显示消息提示
    // ElMessage.warning(event.detail.reason)
  }
}

onMounted(() => {
  initTheme()
  // 初始化用户状态
  userStore.init()
  // 加载对话列表
  if (isLoggedIn.value) {
    loadConversations()
  }

  // 监听登出事件
  window.addEventListener('auth:logout', handleAuthLogout)
})

onBeforeUnmount(() => {
  window.removeEventListener('auth:logout', handleAuthLogout)
})

// 监听登录状态加载对话列表
watch(isLoggedIn, (loggedIn) => {
  if (loggedIn) {
    loadConversations()
  }
})
</script>

<style scoped>
.app-container {
  width: 100%;
  height: 100vh;
  display: flex;
  overflow: hidden;
  transition: background-color 0.3s;
  color: var(--text-primary);
}

/* ==================== 侧边栏 ==================== */
.sidebar {
  width: 260px;
  height: 100%;
  background: var(--sidebar-bg);
  display: flex;
  flex-direction: column;
  transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1), 
              background-color 0.3s;
  flex-shrink: 0;
  border-right: 1px solid var(--border-color);
  overflow: hidden;
}

.sidebar.collapsed {
  width: 64px;
}

/* 文字淡入淡出效果 */
.nav-text,
.menu-text,
.user-details,
.dropdown-icon,
.new-chat-sidebar-btn span,
.history-group-title,
.history-item-title {
  opacity: 1;
  transition: opacity 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.sidebar.collapsed .nav-text,
.sidebar.collapsed .menu-text,
.sidebar.collapsed .user-details,
.sidebar.collapsed .dropdown-icon,
.sidebar.collapsed .new-chat-sidebar-btn span,
.sidebar.collapsed .history-group-title,
.sidebar.collapsed .history-item-title {
  opacity: 0;
  pointer-events: none;
}

.sidebar-header {
  padding: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  border-bottom: 1px solid var(--border-color);
}

.new-chat-sidebar-btn {
  flex: 1;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background: var(--send-btn);
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.2s;
  white-space: nowrap;
  overflow: hidden;
}

.new-chat-sidebar-btn:hover {
  background: var(--send-btn-hover);
}

.sidebar-toggle {
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  transition: background-color 0.2s;
}

.sidebar-toggle:hover {
  background: var(--border-color);
}

.toggle-icon {
  width: 20px;
  height: 20px;
  fill: var(--text-secondary);
  transition: transform 0.3s;
}

.toggle-icon.flipped {
  transform: scaleX(-1);
}

.sidebar-nav {
  flex: 1;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  overflow-y: auto;
  overflow-x: hidden;
}

.sidebar-history {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 0;
}

.history-group-title {
  padding: 8px 12px 4px;
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.history-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  margin-bottom: 2px;
  position: relative;
  min-height: 36px;
  color: var(--text-primary);
}

.history-item:hover {
  background: var(--border-color);
}

.history-item.active {
  background: var(--send-btn);
  color: white;
}

.history-item-title {
  flex: 1;
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.history-delete-btn {
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  display: none;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  flex-shrink: 0;
}

.history-item:hover .history-delete-btn {
  display: flex;
}

.history-delete-btn:hover {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.1);
}

.history-empty {
  padding: 20px;
  text-align: center;
  font-size: 12px;
  color: var(--text-secondary);
}

.sidebar-footer {
  padding: 12px;
  border-top: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* ==================== 用户信息 ==================== */
.user-info {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px;
  background: var(--border-color);
  border-radius: 8px;
  cursor: pointer;
  transition: background-color 0.2s;
  position: relative;
}

.user-info:hover {
  background: rgba(97, 92, 237, 0.1);
}

.dropdown-icon {
  width: 16px;
  height: 16px;
  color: var(--text-secondary);
  transition: transform 0.3s, opacity 0.2s;
}

.dropdown-icon.rotated {
  transform: rotate(180deg);
}

/* ==================== 用户下拉菜单 ==================== */
.user-menu {
  position: fixed;
  bottom: 80px;
  left: 12px;
  width: 236px;
  background: var(--sidebar-bg);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
  z-index: 2000;
}

.sidebar.collapsed .user-menu {
  left: 72px;
  bottom: 20px;
  width: 200px;
}

.user-avatar {
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

.menu-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  color: var(--text-secondary);
  text-decoration: none;
  border-radius: 6px;
  transition: all 0.2s;
  font-size: 14px;
  cursor: pointer;
}

.menu-item:hover {
  background: var(--border-color);
  color: var(--text-primary);
}

.menu-item .el-icon {
  font-size: 16px;
  flex-shrink: 0;
}

.menu-icon {
  width: 16px;
  height: 16px;
  fill: currentColor;
  flex-shrink: 0;
}

/* 菜单淡入淡出动画 */
.menu-fade-enter-active,
.menu-fade-leave-active {
  transition: opacity 0.2s, transform 0.2s;
}

.menu-fade-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.menu-fade-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

.user-details {
  flex: 1;
  min-width: 0;
}

.user-name {
  font-size: 13px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.logout-btn {
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: all 0.2s;
}

.logout-btn:hover {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}

.theme-toggle {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: 8px;
  font-size: 14px;
  transition: all 0.2s;
}

.theme-toggle:hover {
  background: var(--border-color);
  color: var(--text-primary);
}

.theme-toggle .el-icon {
  font-size: 18px;
}

/* ==================== 主内容区 ==================== */
.main-content {
  flex: 1;
  background: var(--main-bg);
  overflow: hidden;
  transition: background-color 0.3s;
}

.main-content.full-width {
  width: 100%;
}

/* ==================== 主题变量 ==================== */
.app-container.dark {
  --sidebar-bg: #1d1d1f;
  --main-bg: #232326;
  --text-primary: #e0e0e0;
  --text-secondary: #999999;
  --border-color: #3a3a3a;
  --input-bg: #2a2a2a;
  --send-btn: #615ced;
  --send-btn-hover: #7571ff;
}

.app-container.light {
  --sidebar-bg: #f7f8fc;
  --main-bg: #ffffff;
  --text-primary: #1a1a1a;
  --text-secondary: #666666;
  --border-color: #e5e5e5;
  --input-bg: #f5f5f5;
  --send-btn: #615ced;
  --send-btn-hover: #5248d9;
}
</style>
