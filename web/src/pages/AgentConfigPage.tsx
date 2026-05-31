import { useEffect, useState } from 'react'
import { Button, Card, Form, Input, Slider, Switch, message } from 'antd'
import { agentConfigApi, type AgentConfig } from '@/api/agentConfig'

export default function AgentConfigPage() {
  const [form] = Form.useForm<AgentConfig>()
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const { data } = await agentConfigApi.get()
      form.setFieldsValue(data)
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

  const onSave = async () => {
    const values = await form.validateFields()
    setSaving(true)
    try {
      await agentConfigApi.update(values)
      message.success('已保存')
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fluid-narrow">
      <Card title="Agent 配置" loading={loading}>
        <Form form={form} layout="vertical">
          <Form.Item
            label="系统提示词（人设 / 风格）"
            name="system_prompt"
            extra="给 AI 设定固定的人设、语气或回答风格，每次对话都会注入"
          >
            <Input.TextArea
              autoSize={{ minRows: 4, maxRows: 10 }}
              placeholder="例如：你是一个简洁、专业的技术助手，回答尽量给出可运行的代码示例。"
            />
          </Form.Item>

          <Form.Item label="温度（创造性）" name="temperature">
            <Slider min={0} max={2} step={0.1} marks={{ 0: '严谨', 1: '平衡', 2: '发散' }} />
          </Form.Item>

          <Form.Item label="默认启用知识库检索" name="enable_knowledge" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item label="默认启用记忆检索" name="enable_memory" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item
            label="默认启用联网搜索"
            name="enable_web_search"
            valuePropName="checked"
            extra="需先在模型配置中添加联网搜索（websearch）配置"
          >
            <Switch />
          </Form.Item>

          <Button type="primary" loading={saving} onClick={onSave}>
            保存
          </Button>
        </Form>
      </Card>
    </div>
  )
}
