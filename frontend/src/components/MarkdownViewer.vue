<template>
  <div class="markdown-viewer" v-html="renderedHtml"></div>
</template>

<script setup>
import { computed } from 'vue'
import { marked } from 'marked'
import hljs from 'highlight.js'

// 配置 marked 使用 highlight.js 进行代码高亮
marked.setOptions({
  highlight: function(code, lang) {
    if (lang && hljs.getLanguage(lang)) {
      return hljs.highlight(code, { language: lang }).value
    }
    return hljs.highlightAuto(code).value
  },
  breaks: true,
  gfm: true
})

const props = defineProps({
  content: {
    type: String,
    default: ''
  }
})

const renderedHtml = computed(() => {
  if (!props.content) return ''
  return marked.parse(props.content)
})
</script>

<style scoped>
.markdown-viewer {
  padding: 20px;
  background-color: #ffffff;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  max-width: 100%;
  overflow-x: auto;
}

/* 全局样式（v-html 渲染的内容不受 scoped 限制，需要深度选择器） */
.markdown-viewer :deep(h1) {
  font-size: 2em;
  margin-top: 0.5em;
  margin-bottom: 0.5em;
  padding-bottom: 0.3em;
  border-bottom: 1px solid #e1e4e8;
  color: #24292e;
}

.markdown-viewer :deep(h2) {
  font-size: 1.5em;
  margin-top: 1em;
  margin-bottom: 0.5em;
  padding-bottom: 0.3em;
  border-bottom: 1px solid #e1e4e8;
  color: #24292e;
}

.markdown-viewer :deep(h3) {
  font-size: 1.25em;
  margin-top: 0.8em;
  margin-bottom: 0.4em;
  color: #24292e;
}

.markdown-viewer :deep(h4) {
  font-size: 1em;
  margin-top: 0.6em;
  margin-bottom: 0.3em;
  color: #24292e;
}

.markdown-viewer :deep(p) {
  margin-top: 0;
  margin-bottom: 16px;
  line-height: 1.6;
  color: #333;
}

.markdown-viewer :deep(ul),
.markdown-viewer :deep(ol) {
  padding-left: 2em;
  margin-top: 0;
  margin-bottom: 16px;
}

.markdown-viewer :deep(li) {
  margin-bottom: 0.25em;
  line-height: 1.6;
}

.markdown-viewer :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 16px;
  overflow-x: auto;
  display: block;
}

.markdown-viewer :deep(table thead) {
  background-color: #f6f8fa;
}

.markdown-viewer :deep(table th),
.markdown-viewer :deep(table td) {
  padding: 8px 12px;
  border: 1px solid #d0d7de;
  text-align: left;
}

.markdown-viewer :deep(table th) {
  font-weight: 600;
}

.markdown-viewer :deep(table tr:nth-child(even)) {
  background-color: #f6f8fa;
}

.markdown-viewer :deep(code) {
  background-color: #f6f8fa;
  padding: 0.2em 0.4em;
  border-radius: 3px;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 0.9em;
  color: #e83e8c;
}

.markdown-viewer :deep(pre) {
  background-color: #f6f8fa;
  padding: 16px;
  border-radius: 6px;
  overflow-x: auto;
  margin-bottom: 16px;
  line-height: 1.45;
}

.markdown-viewer :deep(pre code) {
  background-color: transparent;
  padding: 0;
  color: inherit;
  font-size: 0.85em;
}

.markdown-viewer :deep(blockquote) {
  padding: 0 1em;
  color: #57606a;
  border-left: 0.25em solid #d0d7de;
  margin-bottom: 16px;
}

.markdown-viewer :deep(hr) {
  height: 0.25em;
  padding: 0;
  margin: 24px 0;
  background-color: #d0d7de;
  border: 0;
}

.markdown-viewer :deep(a) {
  color: #0969da;
  text-decoration: none;
}

.markdown-viewer :deep(a:hover) {
  text-decoration: underline;
}

.markdown-viewer :deep(img) {
  max-width: 100%;
  height: auto;
  margin: 10px 0;
}

.markdown-viewer :deep(details) {
  margin-bottom: 16px;
}

.markdown-viewer :deep(summary) {
  cursor: pointer;
  font-weight: 600;
  padding: 8px;
  background-color: #f6f8fa;
  border-radius: 4px;
}

.markdown-viewer :deep(summary:hover) {
  background-color: #e1e4e8;
}
</style>

<style>
/* 导入 highlight.js GitHub 样式 */
@import 'highlight.js/styles/github.css';
</style>
