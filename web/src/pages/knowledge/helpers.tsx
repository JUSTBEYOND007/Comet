import { Tag } from 'antd'
import type { DocStatus } from '@/api/documents'

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

const STATUS_META: Record<DocStatus, { color: string; text: string }> = {
  pending: { color: 'default', text: '待处理' },
  parsing: { color: 'processing', text: '解析中' },
  done: { color: 'success', text: '已完成' },
  failed: { color: 'error', text: '失败' },
}

export function StatusTag({ status }: { status: DocStatus }) {
  const meta = STATUS_META[status]
  return <Tag color={meta.color}>{meta.text}</Tag>
}
