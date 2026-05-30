import { useState } from 'react'
import { Button, Form, Input, Tabs, message } from 'antd'
import { LockOutlined, UserOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'

interface FormValues {
  username: string
  password: string
}

export default function LoginPage() {
  const navigate = useNavigate()
  const login = useAuthStore((s) => s.login)
  const register = useAuthStore((s) => s.register)
  const [tab, setTab] = useState('login')
  const [loading, setLoading] = useState(false)

  const onLogin = async (v: FormValues) => {
    setLoading(true)
    try {
      await login(v.username, v.password)
      message.success('登录成功')
      navigate('/', { replace: true })
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  const onRegister = async (v: FormValues) => {
    setLoading(true)
    try {
      await register(v.username, v.password)
      message.success('注册成功，请登录')
      setTab('login')
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  const renderForm = (onFinish: (v: FormValues) => void, submitText: string) => (
    <Form layout="vertical" onFinish={onFinish} disabled={loading} requiredMark={false}>
      <Form.Item
        name="username"
        rules={[
          { required: true, message: '请输入用户名' },
          { min: 3, message: '用户名至少 3 位' },
        ]}
      >
        <Input prefix={<UserOutlined />} placeholder="用户名" size="large" />
      </Form.Item>
      <Form.Item
        name="password"
        rules={[
          { required: true, message: '请输入密码' },
          { min: 6, message: '密码至少 6 位' },
        ]}
      >
        <Input.Password prefix={<LockOutlined />} placeholder="密码" size="large" />
      </Form.Item>
      <Form.Item style={{ marginBottom: 0 }}>
        <Button type="primary" htmlType="submit" block size="large" loading={loading}>
          {submitText}
        </Button>
      </Form.Item>
    </Form>
  )

  return (
    <div style={{ height: '100vh', display: 'flex' }}>
      {/* 左侧品牌区 */}
      <div
        style={{
          flex: 1,
          background:
            'linear-gradient(135deg, #171719 0%, #1d2b53 55%, #155EEF 100%)',
          color: '#fff',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          padding: '0 64px',
        }}
      >
        <div
          style={{
            width: 56,
            height: 56,
            borderRadius: 14,
            background: 'rgba(255,255,255,0.12)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 28,
            fontWeight: 700,
            marginBottom: 28,
          }}
        >
          彗
        </div>
        <h1 style={{ fontSize: 36, margin: 0, fontWeight: 700 }}>彗记 Comet</h1>
        <p style={{ fontSize: 16, marginTop: 16, color: 'rgba(255,255,255,0.75)', lineHeight: 1.7 }}>
          个人 AI 知识库与记忆助手
          <br />
          沉淀你的知识，记住每一段对话。
        </p>
      </div>

      {/* 右侧表单区 */}
      <div
        style={{
          width: 480,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '0 56px',
          background: '#fff',
        }}
      >
        <div style={{ width: '100%' }}>
          <h2 style={{ fontSize: 24, marginBottom: 4 }}>
            {tab === 'login' ? '欢迎回来' : '创建账号'}
          </h2>
          <p style={{ color: '#667085', marginBottom: 24 }}>
            {tab === 'login' ? '登录以继续使用彗记' : '注册一个新账号开始使用'}
          </p>
          <Tabs
            activeKey={tab}
            onChange={setTab}
            items={[
              { key: 'login', label: '登录', children: renderForm(onLogin, '登录') },
              {
                key: 'register',
                label: '注册',
                children: renderForm(onRegister, '注册'),
              },
            ]}
          />
        </div>
      </div>
    </div>
  )
}
