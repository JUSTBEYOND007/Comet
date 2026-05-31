import client from './client'

interface Wrapped<T> {
  code: number
  message: string
  data: T
}

export interface DailyReview {
  date: string
  content: string
  stats: { messages: number; memories: number; documents: number } | null
  created_at: string
}

export const dashboardApi = {
  dailyReview() {
    return client.get<unknown, Wrapped<DailyReview>>('/dashboard/daily-review')
  },
}
