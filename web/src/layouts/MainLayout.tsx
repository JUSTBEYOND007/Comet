import { Avatar, Dropdown, Input, Layout, Menu, Space, message } from 'antd'
import {
  AppstoreOutlined,
  BookOutlined,
  CommentOutlined,
  CustomerServiceOutlined,
  DeploymentUnitOutlined,
  HddOutlined,
  LogoutOutlined,
  PictureOutlined,
  RobotOutlined,
  SearchOutlined,
  SettingOutlined,
  StarOutlined,
  ToolOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { AuthenticatedImage } from '@/components/AuthenticatedImage'
import MusicPlayer from '@/components/MusicPlayer'
import logo from '@/images/logo.png'

const { Sider, Content, Header } = Layout

// 分组导航：按职责归类，分组标题灰色小字，更清晰
const menuItems = [
  {
    type: 'group' as const,
    label: '工作台',
    children: [
      { key: '/', icon: <AppstoreOutlined />, label: '仪表盘' },
      { key: '/chat', icon: <CommentOutlined />, label: '对话' },
    ],
  },
  {
    type: 'group' as const,
    label: '知识与记忆',
    children: [
      { key: '/knowledge', icon: <BookOutlined />, label: '知识库' },
      { key: '/images', icon: <PictureOutlined />, label: '图片库' },
      { key: '/memory', icon: <HddOutlined />, label: '记忆' },
      { key: '/graph', icon: <DeploymentUnitOutlined />, label: '知识图谱' },
      { key: '/music', icon: <CustomerServiceOutlined />, label: '音乐' },
    ],
  },
  {
    type: 'group' as const,
    label: '检索与收藏',
    children: [
      { key: '/search', icon: <SearchOutlined />, label: '全局搜索' },
      { key: '/favorites', icon: <StarOutlined />, label: '收藏夹' },
    ],
  },
  {
    type: 'group' as const,
    label: '设置',
    children: [
      { key: '/settings/models', icon: <SettingOutlined />, label: '模型配置' },
      { key: '/settings/agent', icon: <RobotOutlined />, label: 'Agent 配置' },
      { key: '/settings/tools', icon: <ToolOutlined />, label: '工具配置' },
    ],
  },
]

export default function MainLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)

  // 音乐页沉浸式深色主题：进入 /music 整体变深色霓虹，离开自动恢复
  const immersive = location.pathname === '/music'

  const onLogout = async () => {
    await logout()
    message.success('已退出登录')
    navigate('/login', { replace: true })
  }

  return (
    <Layout style={{ height: '100%' }} className={immersive ? 'immersive-layout' : ''}>
      <Sider
        width={236}
        style={{
          display: 'flex',
          flexDirection: 'column',
          borderInlineEnd: immersive
            ? '1px solid rgba(255,255,255,0.08)'
            : '1px solid #f0f0f0',
          background: immersive
            ? 'linear-gradient(180deg, #141633 0%, #0c0d18 100%)'
            : undefined,
          transition: 'background 0.4s',
        }}
      >
        <div
          style={{
            height: 64,
            flexShrink: 0,
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            paddingInline: 20,
            color: immersive ? '#fff' : '#171719',
          }}
        >
          <img
            src={logo}
            alt="彗记"
            style={{ width: 36, height: 36, borderRadius: 9, objectFit: 'cover' }}
          />
          <span style={{ fontWeight: 600, fontSize: 19 }}>彗记 Comet</span>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', paddingBottom: 12 }}>
          <Menu
            mode="inline"
            theme={immersive ? 'dark' : 'light'}
            selectedKeys={[location.pathname]}
            items={menuItems}
            onClick={({ key }) => navigate(key)}
            style={{
              borderInlineEnd: 'none',
              background: 'transparent',
            }}
          />
        </div>
      </Sider>
      <Layout style={{ background: immersive ? '#0b0c16' : undefined, transition: 'background 0.4s' }}>
        <Header
          style={{
            paddingInline: 24,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: immersive
              ? '1px solid rgba(255,255,255,0.08)'
              : '1px solid #f0f0f0',
            background: immersive ? 'rgba(18,20,40,0.8)' : undefined,
            backdropFilter: immersive ? 'blur(10px)' : undefined,
            transition: 'background 0.4s',
          }}
        >
          <Input.Search
            placeholder="搜索文档、图片、记忆…"
            allowClear
            style={{ maxWidth: 420, width: '40vw' }}
            onSearch={(v) => {
              const q = v.trim()
              if (q) navigate(`/search?q=${encodeURIComponent(q)}`)
            }}
          />
          <Dropdown
            menu={{
              items: [
                {
                  key: 'profile',
                  icon: <UserOutlined />,
                  label: '个人中心',
                  onClick: () => navigate('/profile'),
                },
                { type: 'divider' },
                {
                  key: 'logout',
                  icon: <LogoutOutlined />,
                  label: '退出登录',
                  onClick: onLogout,
                },
              ],
            }}
          >
            <Space style={{ cursor: 'pointer' }}>
              {user?.avatar ? (
                <AuthenticatedImage
                  src={user.avatar}
                  alt="头像"
                  style={{
                    width: 30,
                    height: 30,
                    borderRadius: '50%',
                    objectFit: 'cover',
                  }}
                />
              ) : (
                <Avatar size={30} style={{ background: '#155EEF' }}>
                  {user?.username?.[0]?.toUpperCase() ?? <UserOutlined />}
                </Avatar>
              )}
              <span style={{ fontWeight: 500, color: immersive ? '#fff' : undefined }}>
                {user?.username ?? '用户'}
              </span>
            </Space>
          </Dropdown>
        </Header>
        <Content style={{ padding: 24, overflow: 'auto' }}>
          <Outlet />
        </Content>
      </Layout>
      <MusicPlayer />
    </Layout>
  )
}
