import { useEffect, useState } from 'react'
import {
  Button,
  Card,
  ColorPicker,
  Empty,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { tagApi, type TagItem } from '@/api/tags'

export default function TagPage() {
  const [list, setList] = useState<TagItem[]>([])
  const [loading, setLoading] = useState(false)
  const [editing, setEditing] = useState<TagItem | null>(null)
  const [editName, setEditName] = useState('')
  const [editColor, setEditColor] = useState('#155EEF')
  const [mergeOpen, setMergeOpen] = useState(false)
  const [mergeSource, setMergeSource] = useState<string>()
  const [mergeTarget, setMergeTarget] = useState<string>()

  const load = async () => {
    setLoading(true)
    try {
      const { data } = await tagApi.list()
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

  const openEdit = (t: TagItem) => {
    setEditing(t)
    setEditName(t.name)
    setEditColor(t.color)
  }

  const onSaveEdit = async () => {
    if (!editing) return
    try {
      await tagApi.update(editing.id, { name: editName, color: editColor })
      message.success('更新成功')
      setEditing(null)
      load()
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  const onDelete = async (id: string) => {
    try {
      await tagApi.remove(id)
      message.success('删除成功')
      load()
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  const onMerge = async () => {
    if (!mergeSource || !mergeTarget) {
      message.warning('请选择源标签和目标标签')
      return
    }
    try {
      await tagApi.merge(mergeSource, mergeTarget)
      message.success('合并成功')
      setMergeOpen(false)
      setMergeSource(undefined)
      setMergeTarget(undefined)
      load()
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  const columns: ColumnsType<TagItem> = [
    {
      title: '标签',
      dataIndex: 'name',
      render: (name, r) => <Tag color={r.color}>{name}</Tag>,
    },
    { title: '关联文档数', dataIndex: 'doc_count', width: 140 },
    {
      title: '操作',
      key: 'action',
      width: 160,
      render: (_, r) => (
        <Space size="small">
          <Button size="small" type="link" onClick={() => openEdit(r)}>
            编辑
          </Button>
          <Popconfirm title="确定删除该标签？" onConfirm={() => onDelete(r.id)}>
            <Button size="small" type="link" danger>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div className="fluid-page">
      <Card
        title="标签管理"
        extra={
          <Button onClick={() => setMergeOpen(true)} disabled={list.length < 2}>
            合并标签
          </Button>
        }
      >
        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={list}
          pagination={false}
          locale={{ emptyText: <Empty description="还没有标签，上传文档后 AI 会自动打标签" /> }}
        />
      </Card>

      <Modal
        title="编辑标签"
        open={!!editing}
        onCancel={() => setEditing(null)}
        onOk={onSaveEdit}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Input
            value={editName}
            onChange={(e) => setEditName(e.target.value)}
            placeholder="标签名"
          />
          <Space>
            颜色：
            <ColorPicker
              value={editColor}
              onChange={(c) => setEditColor(c.toHexString())}
              showText
            />
          </Space>
        </Space>
      </Modal>

      <Modal
        title="合并标签"
        open={mergeOpen}
        onCancel={() => setMergeOpen(false)}
        onOk={onMerge}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <span>把「源标签」合并到「目标标签」，源标签将被删除：</span>
          <Select
            style={{ width: '100%' }}
            placeholder="源标签（被合并删除）"
            value={mergeSource}
            onChange={setMergeSource}
            options={list.map((t) => ({ label: t.name, value: t.id }))}
          />
          <Select
            style={{ width: '100%' }}
            placeholder="目标标签（合并到）"
            value={mergeTarget}
            onChange={setMergeTarget}
            options={list
              .filter((t) => t.id !== mergeSource)
              .map((t) => ({ label: t.name, value: t.id }))}
          />
        </Space>
      </Modal>
    </div>
  )
}
