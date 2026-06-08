import client from './client'

interface Wrapped<T> {
  code: number
  message: string
  data: T
}

export interface AgentConfig {
  system_prompt: string
  temperature: number
  enable_knowledge: boolean
  enable_memory: boolean
  enable_web_search: boolean
  show_avatar: boolean
}

export const agentConfigApi = {
  get() {
    return client.get<unknown, Wrapped<AgentConfig>>('/agent-config')
  },
  update(body: Partial<AgentConfig>) {
    return client.put<unknown, Wrapped<AgentConfig>>('/agent-config', body)
  },
  optimizePrompt(systemPrompt: string) {
    return client.post<unknown, Wrapped<{ optimized: string }>>(
      '/agent-config/optimize-prompt',
      { system_prompt: systemPrompt },
    )
  },
}
