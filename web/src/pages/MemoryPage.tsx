import { useEffect, useRef, useState } from 'react'
import {
  Button,
  Card,
  Empty,
  Input,
  Popconfirm,
  Segmented,
  Space,
  Spin,
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
  StarFilled,
  StarOutlined,
} from '@ant-design/icons'
import {
  memoryApi,
  type MemoryHit,
  type MemoryProfile,
  type ProfileEntity,
} from '@/api/memories'
import { favoriteApi } from '@/api/favorites'

const { Text, Paragraph } = Typography

export default function MemoryPage() {
  const [mode, setMode] = useState<'profile' | 'search'>('profile')

  return (
    <div className="fluid-page">
      <Card
        title="记忆"
        extra={
          <Segmented
            value={mode}
            onChange={(v) => setMode(v as 'profile' | 'search')}
            options={[
              { label: '我的画像', value: 'profile', icon: <BulbOutlined /> },
              { label: '记忆检索', value: 'search', icon: <SearchOutlined /> },
            ]}
          />
        }
      >
        {mode === 'profile' ? <ProfilePanel /> : <SearchPanel />}
      </Card>
    </div>
  )
}

// ── 我的画像：主动记住输入 + 实体按类型分组卡片 ──
function ProfilePanel() {
  const [profile, setProfile] = useState<MemoryProfile | null>(null)
  const [loading, setLoading] = useState(false)
  const [text, setText] = useState('')
  const [submitting, setSubmitting] = useState(false)
  // 已收藏的记忆实体：entity_id -> favorite_id（用于高亮与取消）
  const [favMap, setFavMap] = useState<Record<string, string>>({})
  const pollRef = useRef<number | null>(null)
  const pollCount = useRef(0)

  const loadFavorites = async () => {
    try {
      const { data } = await favoriteApi.list('memory')
      const map: Record<string, string> = {}
      data.forEach((f) => {
        map[f.target_id] = f.id
      })
      setFavMap(map)
    } catch {
      // 收藏状态加载失败不影响画像
    }
  }

  const load = async () => {
    setLoading(true)
    try {
      const { data } = await memoryApi.profile()
      setProfile(data)
      loadFavorites()
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

  const onRemember = async () => {
    const value = text.trim()
    if (!value) {
      message.warning('请输入要记住的内容')
      return
    }
    setSubmitting(true)
    try {
      await memoryApi.remember(value)
      message.success('已提交，正在萃取记忆，稍后自动刷新')
      setText('')
      // 萃取是异步的，轮询几次刷新画像
      pollCount.current = 0
      if (pollRef.current) window.clearInterval(pollRef.current)
      pollRef.current = window.setInterval(() => {
        pollCount.current += 1
        load()
        if (pollCount.current >= 6 && pollRef.current) {
          window.clearInterval(pollRef.current)
          pollRef.current = null
        }
      }, 4000)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  const onDeleteEntity = async (id: string) => {
    try {
      await memoryApi.deleteEntity(id)
      message.success('已删除')
      load()
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  const onFavoriteEntity = async (ent: ProfileEntity) => {
    const existingFavId = favMap[ent.id]
    try {
      if (existingFavId) {
        // 已收藏 → 取消
        await favoriteApi.remove(existingFavId)
        setFavMap((prev) => {
          const next = { ...prev }
          delete next[ent.id]
          return next
        })
        message.success('已取消收藏')
      } else {
        // 未收藏 → 收藏
        const { data } = await favoriteApi.add('memory', ent.id, {
          title: ent.name,
          summary: ent.description,
        })
        setFavMap((prev) => ({ ...prev, [ent.id]: data.id }))
        message.success('已收藏')
      }
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      {/* 主动记住 */}
      <Space.Compact style={{ width: '100%' }}>
        <Input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onPressEnter={onRemember}
          placeholder="告诉我一些值得长期记住的事，例如：我在腾讯做后端，养了只叫多多的小狗"
          size="large"
          allowClear
        />
        <Button
          type="primary"
          size="large"
          icon={<PlusOutlined />}
          loading={submitting}
          onClick={onRemember}
        >
          记住
        </Button>
      </Space.Compact>

      {loading && !profile ? (
        <div style={{ textAlign: 'center', padding: 40 }}>
          <Spin />
        </div>
      ) : !profile || profile.total === 0 ? (
        <Empty description="还没有记忆。主动记住一些事，或在对话中聊聊你自己，我会自动记住" />
      ) : (
        <>
          <Text type="secondary">
            已记住 {profile.total} 个实体，覆盖 {profile.groups.length} 个类型
          </Text>
          {profile.groups.map((group) => (
            <div key={group.type}>
              <div style={{ marginBottom: 10 }}>
                <Tag color="blue" style={{ fontSize: 14, padding: '2px 10px' }}>
                  {group.type}
                </Tag>
                <Text type="secondary" style={{ fontSize: 13 }}>
                  {group.entities.length} 项
                </Text>
              </div>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(16rem, 1fr))',
                  gap: 12,
                  marginBottom: 8,
                }}
              >
                {group.entities.map((ent) => (
                  <Card key={ent.id} size="small" styles={{ body: { padding: 14 } }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                      <Text strong style={{ fontSize: 15 }}>
                        {ent.name}
                      </Text>
                      <Space size={4}>
                        {favMap[ent.id] ? (
                          <StarFilled
                            onClick={() => onFavoriteEntity(ent)}
                            style={{ color: '#FAAD14', cursor: 'pointer' }}
                          />
                        ) : (
                          <StarOutlined
                            onClick={() => onFavoriteEntity(ent)}
                            style={{ color: '#C0C4CC', cursor: 'pointer' }}
                          />
                        )}
                        <Popconfirm title="删除该记忆实体？" onConfirm={() => onDeleteEntity(ent.id)}>
                          <DeleteOutlined style={{ color: '#C0C4CC' }} />
                        </Popconfirm>
                      </Space>
                    </div>
                    {ent.description && (
                      <Paragraph
                        type="secondary"
                        style={{ margin: '4px 0 0', fontSize: 13 }}
                        ellipsis={{ rows: 2, expandable: true, symbol: '展开' }}
                      >
                        {ent.description}
                      </Paragraph>
                    )}
                    {ent.aliases.length > 0 && (
                      <div style={{ marginTop: 6 }}>
                        {ent.aliases.map((a) => (
                          <Tag key={a} style={{ fontSize: 12 }}>
                            {a}
                          </Tag>
                        ))}
                      </div>
                    )}
                    {ent.relations.length > 0 && (
                      <div style={{ marginTop: 8, paddingLeft: 8, borderLeft: '2px solid #EEF4FF' }}>
                        {ent.relations.slice(0, 4).map((rel, i) => (
                          <div key={i} style={{ fontSize: 12.5, color: '#475467', lineHeight: 1.8 }}>
                            <Text type="secondary">{rel.predicate}</Text> {rel.object_name}
                          </div>
                        ))}
                      </div>
                    )}
                  </Card>
                ))}
              </div>
            </div>
          ))}
        </>
      )}
    </Space>
  )
}

// ── 记忆检索 ──
function SearchPanel() {
  const [query, setQuery] = useState('')
  const [searching, setSearching] = useState(false)
  const [hits, setHits] = useState<MemoryHit[]>([])

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
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Space.Compact style={{ width: '100%' }}>
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onPressEnter={onSearch}
          placeholder="按语义检索记忆，例如：我养的宠物、我的工作"
          size="large"
          allowClear
        />
        <Button type="primary" size="large" loading={searching} icon={<SearchOutlined />} onClick={onSearch}>
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
