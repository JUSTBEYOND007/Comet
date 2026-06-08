import { useEffect, useState } from 'react'
import { Spin, Switch, Tooltip, message } from 'antd'
import { PlusOutlined, QuestionCircleOutlined } from '@ant-design/icons'
import { agentConfigApi } from '@/api/agentConfig'
import { personaApi, type Persona } from '@/api/personas'
import PersonaCard from './agent/PersonaCard'
import PersonaEditModal from './agent/PersonaEditModal'

export default function AgentConfigPage() {
  const [personas, setPersonas] = useState<Persona[]>([])
  const [loading, setLoading] = useState(true)
  const [showAvatar, setShowAvatar] = useState(false)
  const [activatingId, setActivatingId] = useState<string | null>(null)
  const [editOpen, setEditOpen] = useState(false)
  const [editing, setEditing] = useState<Persona | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      const [pResp, cResp] = await Promise.all([
        personaApi.list(),
        agentConfigApi.get(),
      ])
      setPersonas(pResp.data)
      setShowAvatar(cResp.data.show_avatar)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const onToggleAvatar = async (v: boolean) => {
    setShowAvatar(v)
    try {
      await agentConfigApi.update({ show_avatar: v })
    } catch (e) {
      setShowAvatar(!v)
      message.error((e as Error).message)
    }
  }

  const onActivate = async (p: Persona) => {
    setActivatingId(p.id)
    try {
      await personaApi.activate(p.id)
      setPersonas((prev) =>
        prev.map((x) => ({ ...x, is_active: x.id === p.id })),
      )
      message.success(`已切换到「${p.name}」`)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setActivatingId(null)
    }
  }

  const onDelete = async (p: Persona) => {
    try {
      await personaApi.remove(p.id)
      message.success('已删除')
      load()
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  const onCreate = () => {
    setEditing(null)
    setEditOpen(true)
  }
  const onEdit = (p: Persona) => {
    setEditing(p)
    setEditOpen(true)
  }

  return (
    <div className="fluid-page persona-page">
      {/* Hero 条 */}
      <div className="persona-hero">
        <div className="persona-hero-bg" />
        <div className="persona-hero-content">
          <div>
            <div className="persona-hero-title">我的角色</div>
            <div className="persona-hero-sub">为对话选择一个灵魂，让 AI 化身你想聊的人</div>
          </div>
          <div className="persona-hero-switch">
            <span>
              显示对话头像
              <Tooltip title="开启后，对话界面会显示当前角色头像与你的头像；关闭则两边都不显示">
                <QuestionCircleOutlined style={{ marginLeft: 6, opacity: 0.7 }} />
              </Tooltip>
            </span>
            <Switch checked={showAvatar} onChange={onToggleAvatar} />
          </div>
        </div>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: 60 }}>
          <Spin />
        </div>
      ) : (
        <div className="persona-gallery">
          {/* 新建卡 */}
          <button className="persona-ghost-card" onClick={onCreate}>
            <PlusOutlined className="persona-ghost-plus" />
            <span>新建角色</span>
          </button>

          {personas.map((p, i) => (
            <PersonaCard
              key={p.id}
              persona={p}
              index={i}
              activating={activatingId === p.id}
              onActivate={onActivate}
              onEdit={onEdit}
              onDelete={onDelete}
            />
          ))}
        </div>
      )}

      <PersonaEditModal
        open={editOpen}
        persona={editing}
        onClose={() => setEditOpen(false)}
        onSaved={load}
      />
    </div>
  )
}
