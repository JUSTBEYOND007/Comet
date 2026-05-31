import type { Citation, ToolCall } from '@/api/chat'

// 前端消息模型（含流式中的临时状态）
export interface UiMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  citations?: Citation[]
  toolCalls?: ToolCall[]
  images?: string[] // 图片 url（用户消息）
  streaming?: boolean
  conversationId?: string // 所属会话（收藏深链用）
  favId?: string | null // 已收藏时的收藏记录 id（高亮+取消用）
}

export const TOOL_META: Record<string, { icon: string; label: string }> = {
  knowledge_search: { icon: '🔍', label: '知识库' },
  memory_search: { icon: '🧠', label: '记忆' },
  web_search: { icon: '🌐', label: '联网' },
}
