import { useState } from 'react'
import {
  App,
  Avatar,
  Button,
  Card,
  Descriptions,
  Form,
  Input,
  Upload,
} from 'antd'
import { LockOutlined, UploadOutlined, UserOutlined } from '@ant-design/icons'
import { authApi } from '@/api/auth'
import { useAuthStore } from '@/stores/authStore'
import { AuthenticatedImage } from '@/components/AuthenticatedImage'

export default function ProfilePage() {
  const { message } = App.useApp()
  const user = useAuthStore((s) => s.user)
  const fetchUser = useAuthStore((s) => s.fetchUser)
  const [pwdForm] = Form.useForm()
  const [savingPwd, setSavingPwd] = useState(false)
  const [uploading, setUploading] = useState(false)

  const onChangePassword = async (v: {
    oldPassword: string
    newPassword: string
  }) => {
    setSavingPwd(true)
    try {
      await authApi.changePassword(v.oldPassword, v.newPassword)
      message.success('密码修改成功')
      pwdForm.resetFields()
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setSavingPwd(false)
    }
  }

  return (
    <div className="fluid-page">
      <Card title="个人中心" style={{ marginBottom: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 24, flexWrap: 'wrap' }}>
          {/* 头像 */}
          <div style={{ textAlign: 'center' }}>
            {user?.avatar ? (
              <AuthenticatedImage
                src={user.avatar}
                alt="头像"
                style={{
                  width: 96,
                  height: 96,
                  borderRadius: '50%',
                  objectFit: 'cover',
                  border: '2px solid #f0f0f0',
                }}
              />
            ) : (
              <Avatar size={96} icon={<UserOutlined />} style={{ background: '#155EEF' }}>
                {user?.username?.[0]?.toUpperCase()}
              </Avatar>
            )}
            <div style={{ marginTop: 12 }}>
              <Upload
                showUploadList={false}
                accept=".jpg,.jpeg,.png,.webp,.gif"
                beforeUpload={async (file) => {
                  setUploading(true)
                  try {
                    await authApi.uploadAvatar(file as File)
                    await fetchUser()
                    message.success('头像更新成功')
                  } catch (e) {
                    message.error((e as Error).message)
                  } finally {
                    setUploading(false)
                  }
                  return false
                }}
              >
                <Button icon={<UploadOutlined />} loading={uploading} size="small">
                  更换头像
                </Button>
              </Upload>
            </div>
          </div>

          {/* 账号信息 */}
          <Descriptions column={1} style={{ flex: 1, minWidth: 240 }}>
            <Descriptions.Item label="账号">{user?.username}</Descriptions.Item>
            <Descriptions.Item label="邮箱">
              {user?.email || user?.username}
            </Descriptions.Item>
            <Descriptions.Item label="注册时间">
              {user?.created_at
                ? new Date(user.created_at).toLocaleString()
                : '-'}
            </Descriptions.Item>
          </Descriptions>
        </div>
      </Card>

      <Card title="修改密码">
        <Form
          form={pwdForm}
          layout="vertical"
          onFinish={onChangePassword}
          style={{ maxWidth: 420 }}
          requiredMark={false}
        >
          <Form.Item
            name="oldPassword"
            label="原密码"
            rules={[{ required: true, message: '请输入原密码' }]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="原密码" size="large" />
          </Form.Item>
          <Form.Item
            name="newPassword"
            label="新密码"
            rules={[
              { required: true, message: '请输入新密码' },
              { min: 6, message: '密码不能少于 6 位' },
            ]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="新密码（至少 6 位）" size="large" />
          </Form.Item>
          <Form.Item
            name="confirm"
            label="确认新密码"
            dependencies={['newPassword']}
            rules={[
              { required: true, message: '请再次输入新密码' },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('newPassword') === value) {
                    return Promise.resolve()
                  }
                  return Promise.reject(new Error('两次输入的密码不一致'))
                },
              }),
            ]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="确认新密码" size="large" />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button type="primary" htmlType="submit" loading={savingPwd}>
              保存修改
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}
