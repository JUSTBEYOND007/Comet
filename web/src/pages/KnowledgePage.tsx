import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Button,
  Card,
  Empty,
  Input,
  Modal,
  Popconfirm,
  Progress,
  Space,
  Table,
  Tag,
  Upload,
  message,
} from 'antd'
import {
  InboxOutlined,
  LinkOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  documentApi,
  type DocumentItem,
  type SearchHit,
} from '@/api/documents'
import { StatusTag, formatSize } from './knowledge/helpers'

const { Dragger } = Upload

export default function KnowledgePage() {
  const [list, setList] = useState<DocumentItem[]>([])
  const [loading, setLoading] = useState(false)
  const [urlModalOpen, setUrlModalOpen] = useState(false)
  const [url, setUrl] = useState('')
  const [importing, setImporting] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<SearchHit[]>([])
  const [searching, setSearching] = useState(false)
  const pollRef = useRef<number | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await documentApi.list(1, 100)
      setList(data.items)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  // 有解析中的文档时轮询刷新
  useEffect(() => {
    const hasPending = list.some(
      (d) => d.status === 'pending' || d.status === 'parsing',
    )
    if (hasPending && pollRef.current === null) {
      pollRef.current = window.setInterval(load, 3000)
    } else if (!hasPending && pollRef.current !== null) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
    return () => {
      if (pollRef.current !== null) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
    }
  }, [list, load])

  const onUpload = async (file: File) => {
    try {
      await documentApi.upload(file)
      message.success('上传成功，正在解析')
      load()
    } catch (e) {
      message.error((e as Error).message)
    }
    return false // 阻止 antd 默认上传
  }

  const onImportUrl = async () => {
    if (!url.trim()) return
    setImporting(true)
    try {
      await documentApi.importUrl(url.trim())
      message.success('导入成功，正在解析')
      setUrlModalOpen(false)
      setUrl('')
      load()
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setImporting(false)
    }
  }

  const onRetry = async (id: string) => {
    try {
      await documentApi.retry(id)
      message.success('已重新提交解析')
      load()
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  const onDelete = async (id: string) => {
    try {
      await documentApi.remove(id)
      message.success('删除成功')
      load()
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  const onSearch = async () => {
    if (!query.trim()) return
    setSearching(true)
    try {
      const { data } = await documentApi.search(query.trim(), 5)
      setHits(data)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setSearching(false)
    }
  }

  const columns: ColumnsType<DocumentItem> = [
    {
      title: '文件名',
      dataIndex: 'file_name',
      render: (name, r) => (
        <Space>
          {name}
          {r.source_type === 'url' && <Tag color="blue">网页</Tag>}
        </Space>
      ),
    },
    {
      title: '大小',
      dataIndex: 'file_size',
      width: 100,
      render: (s) => formatSize(s),
    },
    {
      title: '标签',
      dataIndex: 'tags',
      render: (tags: string[]) =>
        tags.length ? tags.map((t) => <Tag key={t}>{t}</Tag>) : '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 160,
      render: (status, r) => (
        <Space>
          <StatusTag status={status} />
          {status === 'parsing' && (
            <Progress
              percent={Math.round(r.progress * 100)}
              size="small"
              style={{ width: 80 }}
            />
          )}
          {status === 'done' && (
            <span style={{ color: '#A8A9AA' }}>{r.chunk_num} 块</span>
          )}
        </Space>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 160,
      render: (_, r) => (
        <Space size="small">
          {r.status === 'failed' && (
            <Button
              size="small"
              icon={<ReloadOutlined />}
              onClick={() => onRetry(r.id)}
            >
              重试
            </Button>
          )}
          <Popconfirm title="确定删除该文档？" onConfirm={() => onDelete(r.id)}>
            <Button size="small" type="link" danger>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div style={{ maxWidth: 1400, margin: '0 auto' }}>
      <Card
        title="知识库"
        extra={
          <Space>
            <Button icon={<LinkOutlined />} onClick={() => setUrlModalOpen(true)}>
              网页导入
            </Button>
            <Button icon={<SearchOutlined />} onClick={() => setSearchOpen(true)}>
              检索测试
            </Button>
          </Space>
        }
      >
        <Dragger
          accept=".pdf,.docx,.md,.markdown,.txt,.html,.htm"
          showUploadList={false}
          beforeUpload={onUpload}
          multiple
          style={{ marginBottom: 16 }}
        >
          <p className="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p className="ant-upload-text">点击或拖拽文件到此区域上传</p>
          <p className="ant-upload-hint">支持 PDF / Word / Markdown / TXT / HTML</p>
        </Dragger>

        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={list}
          pagination={false}
          locale={{ emptyText: <Empty description="还没有文档，上传一个试试" /> }}
        />
      </Card>

      <Modal
        title="从网页导入"
        open={urlModalOpen}
        onCancel={() => setUrlModalOpen(false)}
        onOk={onImportUrl}
        confirmLoading={importing}
      >
        <Input
          placeholder="https://..."
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onPressEnter={onImportUrl}
        />
      </Modal>

      <Modal
        title="知识库检索测试"
        open={searchOpen}
        onCancel={() => setSearchOpen(false)}
        footer={null}
        width={680}
      >
        <Space.Compact style={{ width: '100%', marginBottom: 16 }}>
          <Input
            placeholder="输入问题，测试混合检索召回"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onPressEnter={onSearch}
          />
          <Button type="primary" loading={searching} onClick={onSearch}>
            检索
          </Button>
        </Space.Compact>
        {hits.map((hit) => (
          <Card key={hit.chunk_id} size="small" style={{ marginBottom: 8 }}>
            <div style={{ marginBottom: 4 }}>
              <Tag color="blue">{hit.doc_name}</Tag>
              <Tag>score {hit.score}</Tag>
            </div>
            <div style={{ color: '#475467', fontSize: 14 }}>{hit.content}</div>
          </Card>
        ))}
        {!hits.length && (
          <Empty description="暂无结果" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </Modal>
    </div>
  )
}
