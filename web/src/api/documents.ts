import client from './client'

interface Wrapped<T> {
  code: number
  message: string
  data: T
}

export type DocStatus = 'pending' | 'parsing' | 'done' | 'failed'

export interface DocumentItem {
  id: string
  file_name: string
  file_ext: string
  file_size: number
  source_type: string
  source_url: string | null
  status: DocStatus
  progress: number
  chunk_num: number
  error_msg: string | null
  tags: string[]
  created_at: string
}

export interface DocumentListData {
  total: number
  page: number
  page_size: number
  items: DocumentItem[]
}

export interface SearchHit {
  chunk_id: string
  content: string
  doc_name: string | null
  source_id: string | null
  source_type: string | null
  score: number
}

export const documentApi = {
  list(page = 1, pageSize = 20) {
    return client.get<unknown, Wrapped<DocumentListData>>(
      `/documents?page=${page}&page_size=${pageSize}`,
    )
  },
  // 上传文档（multipart）
  upload(file: File) {
    const form = new FormData()
    form.append('file', file)
    return client.post<unknown, Wrapped<DocumentItem>>(
      '/documents/upload',
      form,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    )
  },
  importUrl(url: string) {
    return client.post<unknown, Wrapped<DocumentItem>>('/documents/from-url', {
      url,
    })
  },
  detail(id: string) {
    return client.get<unknown, Wrapped<DocumentItem>>(`/documents/${id}`)
  },
  status(id: string) {
    return client.get<unknown, Wrapped<{ status: DocStatus; progress: number; error_msg: string | null }>>(
      `/documents/${id}/status`,
    )
  },
  retry(id: string) {
    return client.post<unknown, Wrapped<DocumentItem>>(`/documents/${id}/retry`)
  },
  remove(id: string) {
    return client.delete<unknown, Wrapped<null>>(`/documents/${id}`)
  },
  search(query: string, topK = 5, tags?: string[]) {
    return client.post<unknown, Wrapped<SearchHit[]>>('/documents/search', {
      query,
      top_k: topK,
      tags,
    })
  },
}
