import client from './client'

interface Wrapped<T> {
  code: number
  message: string
  data: T
}

export interface DailyReview {
  date: string
  content: string
  care?: string
  stats: { messages: number; memories: number; documents: number; songs?: number } | null
  generating?: boolean
  created_at: string
}

export interface OverviewData {
  counts: {
    documents: number
    images: number
    conversations: number
    entities: number
    communities: number
  }
  tag_distribution: { name: string; value: number }[]
  recent: { type: string; title: string; time: string | null }[]
}

export interface MemoryStatsData {
  trend: { date: string; count: number }[]
  community_distribution: { name: string; value: number }[]
}

export interface AgentBriefItem {
  id: string
  title: string
  scheduled: boolean
  created_at: string | null
}

export const dashboardApi = {
  dailyReview() {
    return client.get<unknown, Wrapped<DailyReview>>('/dashboard/daily-review')
  },
  overview() {
    return client.get<unknown, Wrapped<OverviewData>>('/dashboard/overview')
  },
  memoryStats() {
    return client.get<unknown, Wrapped<MemoryStatsData>>('/dashboard/memory-stats')
  },
  agentBriefing() {
    return client.get<unknown, Wrapped<AgentBriefItem[]>>('/dashboard/agent-briefing')
  },
}
