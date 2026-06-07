import { useEffect, useMemo, useState } from 'react'
import {
  Button,
  Collapse,
  Empty,
  Popconfirm,
  Spin,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import {
  ApiOutlined,
  CheckCircleFilled,
  DeleteOutlined,
  EditOutlined,
  GlobalOutlined,
  KeyOutlined,
  LinkOutlined,
  PlusOutlined,
  StarFilled,
  ThunderboltOutlined,
} from '@ant-design/icons'
import {
  modelApi,
  type ModelConfigItem,
  type ModelConfigPayload,
  type ModelType,
} from '@/api/models'
import ModelConfigModal from './modelConfig/ModelConfigModal'
import { PROVIDER_LINKS, PROVIDER_OPTIONS, TYPE_LABEL } from './modelConfig/constants'

const PROVIDER_LABEL = Object.fromEntries(
  PROVIDER_OPTIONS.map((p) => [p.value, p.label]),
)

// 每种模型类型一套配色 + 分组标题
const TYPE_META: Record<
  ModelType,
  { color: string; bg: string; gradient: string; desc: string }
> = {
  chat: {
    color: '#155EEF',
    bg: '#EEF4FF',
    gradient: 'linear-gradient(135deg, #155EEF 0%, #4E8CFF 100%)',
    desc: '负责对话问答的大语言模型',
  },
  multimodal: {
    color: '#7A5AF8',
    bg: '#F4F1FE',
    gradient: 'linear-gradient(135deg, #7A5AF8 0%, #B69CFF 100%)',
    desc: '能看图理解的多模态模型',
  },
  embedding: {
    color: '#0E9384',
    bg: '#E6F6F4',
    gradient: 'linear-gradient(135deg, #0E9384 0%, #4FD1C5 100%)',
    desc: '把文本转成向量用于检索',
  },
  rerank: {
    color: '#DD6B20',
    bg: '#FEF3E8',
    gradient: 'linear-gradient(135deg, #DD6B20 0%, #F6AD55 100%)',
    desc: '对检索结果重排，提升相关度',
  },
  websearch: {
    color: '#0BA5EC',
    bg: '#E7F6FE',
    gradient: 'linear-gradient(135deg, #0BA5EC 0%, #5CC9F5 100%)',
    desc: '联网搜索实时信息',
  },
}

const TYPE_ORDER: ModelType[] = [
  'chat',
  'multimodal',
  'embedding',
  'rerank',
  'websearch',
]

const CAP_LABEL: Record<string, string> = {
  function_call: '工具调用',
  vision: '图片理解',
}

// 密钥掩码归一化：统一显示为「固定圆点 + 真实尾部」，避免长短不一撑乱卡片
function normalizeKey(masked: string): string {
  if (!masked) return '-'
  // 取末尾连续的非掩码字符作为可见尾部（后端掩码用 * 号）
  const tail = masked.replace(/\*+/g, '').slice(-4)
  return `${'•'.repeat(12)}${tail}`
}

export default function ModelConfigPage() {
  const [list, setList] = useState<ModelConfigItem[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<ModelConfigItem | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [testingId, setTestingId] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      const { data } = await modelApi.list()
      setList(data)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const openCreate = () => {
    setEditing(null)
    setModalOpen(true)
  }

  const openEdit = (item: ModelConfigItem) => {
    setEditing(item)
    setModalOpen(true)
  }

  const onSubmit = async (values: ModelConfigPayload) => {
    setSubmitting(true)
    try {
      if (editing) {
        const payload = { ...values }
        if (!payload.api_key) delete (payload as Partial<ModelConfigPayload>).api_key
        await modelApi.update(editing.id, payload)
        message.success('更新成功')
      } else {
        await modelApi.create(values)
        message.success('创建成功')
      }
      setModalOpen(false)
      load()
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  const onDelete = async (id: string) => {
    try {
      await modelApi.remove(id)
      message.success('删除成功')
      load()
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  const onTest = async (id: string) => {
    setTestingId(id)
    try {
      const { data } = await modelApi.test(id)
      if (data.success) message.success(data.message)
      else message.error(data.message)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setTestingId(null)
    }
  }

  const onSetDefault = async (id: string) => {
    try {
      await modelApi.setDefault(id)
      message.success('已设为默认')
      load()
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  // 按类型排序展示（统一两列网格，不再按类型分块）
  const sorted = useMemo(
    () =>
      [...list].sort(
        (a, b) => TYPE_ORDER.indexOf(a.type) - TYPE_ORDER.indexOf(b.type),
      ),
    [list],
  )

  const renderCard = (item: ModelConfigItem) => {
    const meta = TYPE_META[item.type]
    const provider = PROVIDER_LABEL[item.provider] ?? item.provider
    return (
      <div key={item.id} className="model-card">
        <div className="model-card-glow" style={{ background: meta.gradient }} />
        <div className="model-card-head">
          <div
            className="model-card-icon"
            style={{ background: meta.gradient }}
          >
            <ApiOutlined />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="model-card-title">
              <span className="model-card-name" title={item.name}>
                {item.name}
              </span>
              {item.is_default && (
                <Tooltip title="默认配置">
                  <StarFilled style={{ color: '#FAAD14', fontSize: 14 }} />
                </Tooltip>
              )}
            </div>
            <div className="model-card-provider">
              <GlobalOutlined style={{ fontSize: 12 }} /> {provider}
            </div>
          </div>
          <Tag
            style={{
              margin: 0,
              border: 'none',
              color: meta.color,
              background: meta.bg,
              fontWeight: 500,
              borderRadius: 6,
            }}
          >
            {TYPE_LABEL[item.type]}
          </Tag>
        </div>

        <div className="model-card-body">
          <div className="model-card-row">
            <ThunderboltOutlined style={{ color: '#98A2B3' }} />
            <span className="model-card-label">模型</span>
            <span className="model-card-value" title={item.model_name}>
              {item.model_name || '-'}
            </span>
          </div>
          <div className="model-card-row">
            <KeyOutlined style={{ color: '#98A2B3' }} />
            <span className="model-card-label">密钥</span>
            <span className="model-card-value model-card-key" title={item.api_key_masked}>
              {normalizeKey(item.api_key_masked)}
            </span>
          </div>
          {item.capability.length > 0 && (
            <div className="model-card-row">
              <CheckCircleFilled style={{ color: '#52C41A' }} />
              <span className="model-card-label">能力</span>
              <span style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                {item.capability.map((c) => (
                  <Tag
                    key={c}
                    color="green"
                    style={{ margin: 0, borderRadius: 6 }}
                  >
                    {CAP_LABEL[c] ?? c}
                  </Tag>
                ))}
              </span>
            </div>
          )}
        </div>

        <div className="model-card-actions">
          <Button
            size="small"
            type="text"
            loading={testingId === item.id}
            icon={<ApiOutlined />}
            onClick={() => onTest(item.id)}
          >
            测试
          </Button>
          {!item.is_default && (
            <Button
              size="small"
              type="text"
              icon={<StarFilled />}
              onClick={() => onSetDefault(item.id)}
            >
              设默认
            </Button>
          )}
          <Button
            size="small"
            type="text"
            icon={<EditOutlined />}
            onClick={() => openEdit(item)}
          >
            编辑
          </Button>
          <Popconfirm
            title="确定删除该配置？"
            onConfirm={() => onDelete(item.id)}
          >
            <Button size="small" type="text" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </div>
      </div>
    )
  }

  return (
    <div className="fluid-page" style={{ maxWidth: '80rem' }}>
      <div className="model-page-header">
        <div>
          <Typography.Title level={3} style={{ margin: 0 }}>
            模型配置
          </Typography.Title>
          <Typography.Text type="secondary">
            管理对话、多模态、向量、重排与联网搜索模型，密钥加密存储
          </Typography.Text>
        </div>
        <Button
          type="primary"
          size="large"
          icon={<PlusOutlined />}
          onClick={openCreate}
        >
          新增配置
        </Button>
      </div>

      <Collapse
        defaultActiveKey={list.length === 0 ? ['guide'] : []}
        style={{ marginBottom: 20, background: '#fff', borderRadius: 12 }}
        items={[
          {
            key: 'guide',
            label: (
              <span style={{ fontWeight: 600 }}>
                📖 配置流程说明 · 去哪里申请 API Key？
              </span>
            ),
            children: (
              <div>
                <Typography.Paragraph style={{ marginBottom: 14, color: '#475467' }}>
                  彗记不内置任何模型，需你自己填入大模型供应商的 API Key（密钥会
                  <b>加密存储</b>，仅你可见）。按以下步骤配置：
                </Typography.Paragraph>

                <ol style={{ paddingLeft: 20, margin: '0 0 16px', color: '#475467', lineHeight: 2 }}>
                  <li>
                    选一个供应商（推荐<b>智谱</b>，注册送额度、模型类型最全），到其官网注册并创建 API Key。
                  </li>
                  <li>
                    点右上角<b>「新增配置」</b>，选择模型类型与供应商，base_url 会自动带出默认值，填入模型名与 API Key。
                  </li>
                  <li>
                    保存后点卡片上的<b>「测试」</b>验证连通，再点<b>「设默认」</b>把它设为该类型的默认模型。
                  </li>
                  <li>
                    至少配置 <b>对话(chat)</b> 与 <b>向量(embedding)</b> 两类；想看图配
                    <b>多模态</b>，想联网问答配<b>联网搜索</b>，想提升检索精度配 <b>rerank</b>。
                  </li>
                </ol>

                <Typography.Text strong style={{ display: 'block', marginBottom: 10 }}>
                  各供应商申请入口
                </Typography.Text>
                <div className="provider-link-grid">
                  {PROVIDER_LINKS.map((p) => (
                    <a
                      key={p.label}
                      className="provider-link"
                      href={p.url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <div className="provider-link__head">
                        <LinkOutlined />
                        <span className="provider-link__name">{p.label}</span>
                      </div>
                      <div className="provider-link__desc">{p.desc}</div>
                    </a>
                  ))}
                </div>
                <Typography.Text type="secondary" style={{ fontSize: 12, marginTop: 12, display: 'block' }}>
                  提示：以上为第三方平台地址，注册与计费以各平台为准；密钥请勿泄露给他人。
                </Typography.Text>
              </div>
            ),
          },
        ]}
      />

      <Spin spinning={loading}>
        {sorted.length === 0 && !loading ? (
          <Empty
            style={{ padding: '60px 0' }}
            description="还没有模型配置，点击右上角新增一个"
          />
        ) : (
          <div className="model-card-grid">{sorted.map(renderCard)}</div>
        )}
      </Spin>

      <ModelConfigModal
        open={modalOpen}
        editing={editing}
        confirmLoading={submitting}
        onCancel={() => setModalOpen(false)}
        onSubmit={onSubmit}
      />
    </div>
  )
}
