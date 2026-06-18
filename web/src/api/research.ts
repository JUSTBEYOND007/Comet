import client from './client'

interface Wrapped<T> {
  code: number
  message: string
  data: T
}

export type ResearchStatus =
  | 'pending'
  | 'planning'
  | 'searching'
  | 'writing'
  | 'summarizing'
  | 'done'
  | 'failed'

export interface ResearchSource {
  index: number
  type: 'web' | 'kb' | 'mcp'
  title: string
  url: string | null
}

export interface PlanSection {
  heading: string
  points: string
}

export interface ResearchPlan {
  title: string
  sections: PlanSection[]
  queries: string[]
}

export interface ReportBrief {
  id: string
  topic: string
  title: string | null
  status: ResearchStatus
  created_at: string | null
}

export interface ReportDetail extends ReportBrief {
  report_md: string | null
  outline: ResearchPlan | null
  sources: ResearchSource[]
  error_msg: string | null
}

export interface ResearchStep {
  icon: string // search | web | fetch | kb | mcp
  ok: boolean
  text: string
}

export interface ResearchStreamHandlers {
  onMeta?: (d: { report_id: string; topic: string }) => void
  onStatus?: (d: { phase: string; detail: string }) => void
  onPlan?: (d: ResearchPlan) => void
  onSources?: (sources: ResearchSource[]) => void
  onProgress?: (d: ResearchStep) => void
  onSectionStart?: (d: { heading: string }) => void
  onToken?: (text: string) => void
  onSectionDone?: (d: { heading: string }) => void
  onReport?: (d: { title: string; markdown: string; sources: ResearchSource[] }) => void
  onDone?: (d: { report_id: string }) => void
  onError?: (message: string) => void
  // 续传快照
  onResume?: (d: {
    phase: string
    title: string
    plan: ResearchPlan | null
    sources: ResearchSource[]
    steps: ResearchStep[]
    partial_md: string
  }) => void
  onIdle?: () => void
}

export const researchApi = {
  list(page = 1, pageSize = 20) {
    return client.get<unknown, Wrapped<{ items: ReportBrief[]; total: number }>>(
      `/research?page=${page}&page_size=${pageSize}`,
    )
  },
  detail(id: string) {
    return client.get<unknown, Wrapped<ReportDetail>>(`/research/${id}`)
  },
  remove(id: string) {
    return client.delete<unknown, Wrapped<null>>(`/research/${id}`)
  },
  saveToKb(id: string, kbId?: string | null) {
    return client.post<unknown, Wrapped<{ document_id: string; kb_id: string; kb_name: string }>>(
      `/research/${id}/save-to-kb`,
      { kb_id: kbId ?? null },
    )
  },
}

function dispatch(
  event: string,
  payload: Record<string, unknown>,
  h: ResearchStreamHandlers,
) {
  switch (event) {
    case 'meta':
      h.onMeta?.(payload as never)
      break
    case 'status':
      h.onStatus?.(payload as never)
      break
    case 'plan':
      h.onPlan?.(payload as never)
      break
    case 'sources':
      h.onSources?.((payload.sources as ResearchSource[]) ?? [])
      break
    case 'progress':
      h.onProgress?.(payload as never)
      break
    case 'section_start':
      h.onSectionStart?.(payload as never)
      break
    case 'token':
      h.onToken?.(payload.text as string)
      break
    case 'section_done':
      h.onSectionDone?.(payload as never)
      break
    case 'report':
      h.onReport?.(payload as never)
      break
    case 'resume':
      h.onResume?.(payload as never)
      break
    case 'idle':
      h.onIdle?.()
      break
    case 'done':
      h.onDone?.(payload as never)
      break
    case 'error':
      h.onError?.((payload.message as string) ?? '研究失败')
      break
  }
}

async function consumeSSE(
  resp: Response,
  h: ResearchStreamHandlers,
): Promise<void> {
  if (!resp.ok || !resp.body) {
    h.onError?.(`请求失败（HTTP ${resp.status}）`)
    return
  }
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    let chunk: ReadableStreamReadResult<Uint8Array>
    try {
      chunk = await reader.read()
    } catch {
      break
    }
    if (chunk.done) break
    buffer += decoder.decode(chunk.value, { stream: true })
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() ?? ''
    for (const block of blocks) {
      const lines = block.split('\n')
      let event = 'message'
      let data = ''
      for (const line of lines) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) data += line.slice(5).trim()
      }
      if (!data) continue
      let payload: Record<string, unknown> = {}
      try {
        payload = JSON.parse(data)
      } catch {
        continue
      }
      dispatch(event, payload, h)
    }
  }
}

// 发起研究并流式推进度（POST SSE）
export async function streamResearch(
  topic: string,
  handlers: ResearchStreamHandlers,
  signal?: AbortSignal,
  kbIds?: string[] | null,
): Promise<void> {
  const token = localStorage.getItem('access_token')
  let resp: Response
  try {
    resp = await fetch('/api/research/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ topic, kb_ids: kbIds ?? null }),
      signal,
    })
  } catch {
    handlers.onError?.('网络错误')
    return
  }
  await consumeSSE(resp, handlers)
}

// 重连续传：订阅进行中的研究（GET SSE），已结束会回放最终报告
export async function subscribeResearchEvents(
  reportId: string,
  handlers: ResearchStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const token = localStorage.getItem('access_token')
  let resp: Response
  try {
    resp = await fetch(`/api/research/${reportId}/events`, {
      method: 'GET',
      headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      signal,
    })
  } catch {
    return
  }
  await consumeSSE(resp, handlers)
}
