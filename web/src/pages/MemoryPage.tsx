import { useEffect, useRef, useState } from 'react'
import {
  Button,
  Card,
  Empty,
  Input,
  Popconfirm,
  Segmented,
  Space,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import {
  BulbOutlined,
  DeleteOutlined,
  PlusOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import {
  memoryApi,
  type MemoryHit,
  type MemoryItem,
  type MemoryStatus,
} from '@/api/memories'

const { TextArea } = Input
const { Text, Paragraph } = Typography

const STATUS_META: Record<MemoryStatus, { color: string; label: string }> = {
  pending: { color: 'default', label: '待萃取' },
  extracting: { color: 'processing', label: '萃取中' },
  done: { color: 'success', label: '已记住' },
  failed: { color: 'error', label: '失败' },
}

export default function MemoryPage() {
  const [mode, setMode] = useState<'list' | 'search'>('list')
  const [list, setList] = useState<MemoryItem[]>([])
  const [loading, setLoading] = useState(false)
  const [text, setText] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<MemoryHit[]>([])
  const [searching, setSearching] = useState(false)
  const pollRef = useRef<number | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      const { data } = await memoryApi.list(1, 50)
      setList(data.items)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current)
    }
  }, [])

  // 有 pending/extracting 时轮询刷新，直到全部完成
  useEffect(() => {
    const hasRunning = list.some(
      (m) => m.status === 'pending' || m.status === 'extracting',
    )
    if (hasRunning && !pollRef.current) {
      pollRef.current = window.setInterval(load, 3000)
    } else if (!hasRunning && pollRef.current) {
      window.clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [list])

  const onRemember = async () => {
    const value = text.trim()
    if (!value) {
      message.warning('请输入要记住的内容')
      return
    }
    setSubmitting(true)
    try {
      await memoryApi.remember(value)
      message.success('已提交，正在萃取记忆')
      setText('')
      load()
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  const onDelete = async (id: string) => {
    try {
      await memoryApi.remove(id)
      message.success('删除成功')
      load()
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  const onSearch = async () => {
    const q = query.trim()
    if (!q) {
      message.warning('请输入检索关键词')
      return
    }
    setSearching(true)
    try {
      const { data } = await memoryApi.search(q, 10)
      setHits(data)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setSearching(false)
    }
  }

  return (
    <div style={{ maxWidth: 1000, margin: '0 auto' }}>
      <Card
        title="记忆"
        extra={
          <Segmented
            value={mode}
            onChange={(v) => setMode(v as 'list' | 'search')}
            options={[
              { label: '我的记忆', value: 'list', icon: <BulbOutlined /> },
              { label: '记忆检索', value: 'search', icon: <SearchOutlined /> },
            ]}
          />
        }
      >
        {mode === 'list' ? (
          <RememberPanel
            text={text}
            setText={setText}
            submitting={submitting}
            onRemember={onRemember}
            list={list}
            loading={loading}
            onDelete={onDelete}
          />
        ) : (
          <SearchPanel
            query={query}
            setQuery={setQuery}
            searching={searching}
            onSearch={onSearch}
            hits={hits}
          />
        )}
      </Card>
    </div>
  )
}


interface RememberPanelProps {
  text: string
  setText: (v: string) => void
  submitting: boolean
  onRemember: () => void
  list: MemoryItem[]
  loading: boolean
  onDelete: (id: string) => void
}

function RememberPanel({
  text,
  setText,
  submitting,
  onRemember,
  list,
  loading,
  onDelete,
}: RememberPanelProps) {
  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Space.Compact style={{ width: '100%' }}>
        <TextArea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="告诉我一些值得记住的事，例如：我在腾讯做后端，正在学 Rust，养了只叫多多的小狗"
          autoSize={{ minRows: 2, maxRows: 5 }}
        />
      </Space.Compact>
      <div style={{ textAlign: 'right' }}>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          loading={submitting}
          onClick={onRemember}
        >
          记住
        </Button>
      </div>

      {list.length === 0 && !loading ? (
        <Empty description="还没有记忆，在上面输入点什么让我记住吧" />
      ) : (
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          {list.map((m) => {
            const meta = STATUS_META[m.status]
            const s = m.graph_stats
            return (
              <Card key={m.id} size="small" styles={{ body: { padding: 16 } }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <Space size="small" style={{ marginBottom: 6 }}>
                      <Tag color={meta.color}>{meta.label}</Tag>
                      <Tag>{m.source === 'manual' ? '主动记住' : '对话萃取'}</Tag>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {new Date(m.created_at).toLocaleString()}
                      </Text>
                    </Space>
                    <Paragraph style={{ margin: 0 }} ellipsis={{ rows: 3, expandable: true }}>
                      {m.raw_text}
                    </Paragraph>
                    {m.status === 'done' && s && (
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        萃取出 {s.entities} 个实体、{s.relations} 条关系（共 {s.statements} 句陈述）
                      </Text>
                    )}
                    {m.status === 'failed' && m.error_msg && (
                      <Text type="danger" style={{ fontSize: 12 }}>
                        {m.error_msg}
                      </Text>
                    )}
                  </div>
                  <Popconfirm title="确定删除该记忆？" onConfirm={() => onDelete(m.id)}>
                    <Button type="text" danger icon={<DeleteOutlined />} />
                  </Popconfirm>
                </div>
              </Card>
            )
          })}
        </Space>
      )}
    </Space>
  )
}

interface SearchPanelProps {
  query: string
  setQuery: (v: string) => void
  searching: boolean
  onSearch: () => void
  hits: MemoryHit[]
}

function SearchPanel({ query, setQuery, searching, onSearch, hits }: SearchPanelProps) {
  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Space.Compact style={{ width: '100%' }}>
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onPressEnter={onSearch}
          placeholder="按语义检索记忆，例如：我养的宠物、我的工作"
          allowClear
        />
        <Button type="primary" loading={searching} icon={<SearchOutlined />} onClick={onSearch}>
          检索
        </Button>
      </Space.Compact>

      {hits.length === 0 ? (
        <Empty description="输入关键词，从记忆图谱里召回相关实体与关系" />
      ) : (
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          {hits.map((h) => (
            <Card key={h.id} size="small" styles={{ body: { padding: 16 } }}>
              <Space size="small" style={{ marginBottom: 6 }}>
                <Text strong>{h.name}</Text>
                <Tag color="blue">{h.type}</Tag>
                <Tooltip title="相关度">
                  <Tag>{h.score}</Tag>
                </Tooltip>
              </Space>
              {h.description && (
                <Paragraph type="secondary" style={{ margin: '4px 0' }}>
                  {h.description}
                </Paragraph>
              )}
              {h.aliases.length > 0 && (
                <div style={{ marginBottom: 6 }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>别名：</Text>
                  {h.aliases.map((a) => (
                    <Tag key={a}>{a}</Tag>
                  ))}
                </div>
              )}
              {h.relations.length > 0 && (
                <div style={{ paddingLeft: 8, borderLeft: '2px solid #EEF4FF' }}>
                  {h.relations.map((rel, i) => (
                    <div key={i} style={{ fontSize: 13, color: '#475467' }}>
                      {h.name} <Text type="secondary">{rel.predicate}</Text> {rel.object_name}
                    </div>
                  ))}
                </div>
              )}
            </Card>
          ))}
        </Space>
      )}
    </Space>
  )
}
