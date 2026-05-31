import client from './client'

interface Wrapped<T> {
  code: number
  message: string
  data: T
}

export type MemoryStatus = 'pending' | 'extracting' | 'done' | 'failed'

export interface MemoryStats {
  dialogue_id: string
  chunks: number
  statements: number
  entities: number
  relations: number
  entity_ids: string[]
}

export interface MemoryItem {
  id: string
  raw_text: string
  source: 'auto' | 'manual'
  status: MemoryStatus
  error_msg: string | null
  graph_stats: MemoryStats | null
  created_at: string
}

export interface MemoryListData {
  total: number
  page: number
  page_size: number
  items: MemoryItem[]
}

export interface MemoryRelation {
  predicate: string
  object_name: string | null
  object_type: string | null
  source_text: string | null
}

export interface MemoryHit {
  id: string
  name: string
  type: string
  description: string | null
  aliases: string[]
  score: number
  relations: MemoryRelation[]
}

export const memoryApi = {
  remember(text: string) {
    return client.post<unknown, Wrapped<MemoryItem>>('/memories/remember', { text })
  },
  list(page = 1, pageSize = 20) {
    const q = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
    return client.get<unknown, Wrapped<MemoryListData>>(`/memories?${q.toString()}`)
  },
  detail(id: string) {
    return client.get<unknown, Wrapped<MemoryItem>>(`/memories/${id}`)
  },
  remove(id: string) {
    return client.delete<unknown, Wrapped<null>>(`/memories/${id}`)
  },
  search(query: string, topK = 10) {
    return client.post<unknown, Wrapped<MemoryHit[]>>('/memories/search', {
      query,
      top_k: topK,
    })
  },
}
