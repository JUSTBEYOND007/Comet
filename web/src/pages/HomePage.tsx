import { useEffect, useState } from 'react'
import { Alert, Badge, Card, Col, Empty, List, Row, Spin, Statistic } from 'antd'
import {
  BookOutlined,
  CloudServerOutlined,
  ClusterOutlined,
  CommentOutlined,
  DatabaseOutlined,
  DeploymentUnitOutlined,
  HddOutlined,
  PictureOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import client from '@/api/client'
import {
  dashboardApi,
  type DailyReview,
  type MemoryStatsData,
  type OverviewData,
} from '@/api/dashboard'
import { useAuthStore } from '@/stores/authStore'

interface HealthData {
  healthy: boolean
  checks: Record<string, boolean>
}

const STORE_META: Record<string, { label: string; icon: React.ReactNode }> = {
  postgres: { label: 'PostgreSQL', icon: <DatabaseOutlined /> },
  elasticsearch: { label: 'Elasticsearch', icon: <CloudServerOutlined /> },
  neo4j: { label: 'Neo4j', icon: <DeploymentUnitOutlined /> },
  redis: { label: 'Redis', icon: <ThunderboltOutlined /> },
}

export default function HomePage() {
  const user = useAuthStore((s) => s.user)
  const [health, setHealth] = useState<HealthData | null>(null)
  const [review, setReview] = useState<DailyReview | null>(null)
  const [overview, setOverview] = useState<OverviewData | null>(null)
  const [memStats, setMemStats] = useState<MemoryStatsData | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    void (async () => {
      setLoading(true)
      try {
        const [ov, ms] = await Promise.all([
          dashboardApi.overview(),
          dashboardApi.memoryStats(),
        ])
        setOverview(ov.data)
        setMemStats(ms.data)
      } catch {
        // 统计失败不致命
      } finally {
        setLoading(false)
      }
      client
        .get<unknown, { data: HealthData }>('/health')
        .then((hb) => setHealth(hb.data))
        .catch(() => {})
      dashboardApi
        .dailyReview()
        .then(({ data }) => setReview(data))
        .catch(() => {})
    })()
  }, [])

  const c = overview?.counts
  const statCards = [
    { label: '知识库文档', value: c?.documents ?? 0, icon: <BookOutlined />, color: '#155EEF' },
    { label: '图片素材', value: c?.images ?? 0, icon: <PictureOutlined />, color: '#369F21' },
    { label: '记忆实体', value: c?.entities ?? 0, icon: <HddOutlined />, color: '#7C4DFF' },
    { label: '主题社区', value: c?.communities ?? 0, icon: <ClusterOutlined />, color: '#FF8A34' },
    { label: '对话会话', value: c?.conversations ?? 0, icon: <CommentOutlined />, color: '#13C2C2' },
  ]

  const pieOption = {
    tooltip: { trigger: 'item' },
    legend: { bottom: 0, type: 'scroll' },
    series: [
      {
        type: 'pie',
        radius: ['40%', '68%'],
        center: ['50%', '44%'],
        data: overview?.tag_distribution ?? [],
        label: { show: false },
      },
    ],
  }

  const lineOption = {
    tooltip: { trigger: 'axis' },
    grid: { left: 36, right: 16, top: 24, bottom: 28 },
    xAxis: {
      type: 'category',
      data: (memStats?.trend ?? []).map((t) => t.date.slice(5)),
    },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      {
        type: 'line',
        smooth: true,
        data: (memStats?.trend ?? []).map((t) => t.count),
        areaStyle: { opacity: 0.12 },
        itemStyle: { color: '#155EEF' },
      },
    ],
  }

  return (
    <div className="fluid-page">
      <Card
        style={{
          marginBottom: 24,
          background: 'linear-gradient(120deg, #171719 0%, #1d2b53 100%)',
          border: 'none',
        }}
        styles={{ body: { padding: '28px 32px' } }}
      >
        <h2 style={{ color: '#fff', margin: 0, fontSize: 24 }}>
          你好，{user?.username ?? '朋友'} 👋
        </h2>
        <p style={{ color: 'rgba(255,255,255,0.7)', marginTop: 8, marginBottom: 0 }}>
          欢迎使用彗记 Comet —— 你的个人 AI 知识库与记忆助手。
        </p>
      </Card>

      {/* 数字卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        {statCards.map((s) => (
          <Col xs={12} sm={8} md={Math.floor(24 / 5) || 4} key={s.label} style={{ flex: 1 }}>
            <Card styles={{ body: { padding: 18 } }}>
              <Statistic
                title={<span style={{ color: '#667085' }}>{s.icon} {s.label}</span>}
                value={s.value}
                valueStyle={{ color: s.color, fontWeight: 600 }}
              />
            </Card>
          </Col>
        ))}
      </Row>

      {/* 今日回顾 */}
      <Card
        title="今日回顾"
        style={{ marginBottom: 24 }}
        extra={
          review?.stats && (
            <span style={{ color: '#98A2B3', fontSize: 13 }}>
              对话 {review.stats.messages} · 记忆 {review.stats.memories} · 文档 {review.stats.documents}
            </span>
          )
        }
      >
        <p style={{ margin: 0, color: '#475467', lineHeight: 1.8, whiteSpace: 'pre-wrap' }}>
          {review?.content ?? '加载中…'}
        </p>
      </Card>

      {/* 图表区 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} md={12}>
          <Card title="知识库分类分布">
            {loading ? (
              <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
            ) : overview?.tag_distribution.length ? (
              <ReactECharts option={pieOption} style={{ height: 280 }} />
            ) : (
              <Empty description="还没有分类标签" />
            )}
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card title="近 14 天记忆新增">
            <ReactECharts option={lineOption} style={{ height: 280 }} />
          </Card>
        </Col>
      </Row>

      {/* 最近活动 + 系统状态 */}
      <Row gutter={[16, 16]}>
        <Col xs={24} md={12}>
          <Card title="最近活动">
            {overview?.recent.length ? (
              <List
                size="small"
                dataSource={overview.recent}
                renderItem={(r) => (
                  <List.Item>
                    <BookOutlined style={{ color: '#155EEF', marginRight: 8 }} />
                    {r.title}
                    <span style={{ marginLeft: 'auto', color: '#98A2B3', fontSize: 12 }}>
                      {r.time ? new Date(r.time).toLocaleDateString() : ''}
                    </span>
                  </List.Item>
                )}
              />
            ) : (
              <Empty description="暂无活动" />
            )}
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card title="系统状态">
            {health ? (
              <>
                <Alert
                  style={{ marginBottom: 16 }}
                  type={health.healthy ? 'success' : 'warning'}
                  showIcon
                  message={health.healthy ? '所有存储服务运行正常' : '部分存储服务未就绪'}
                />
                <Row gutter={[12, 12]}>
                  {Object.entries(health.checks).map(([name, ok]) => {
                    const meta = STORE_META[name] ?? { label: name, icon: null }
                    return (
                      <Col xs={12} key={name}>
                        <Badge status={ok ? 'success' : 'error'} text={<span>{meta.icon} {meta.label}</span>} />
                      </Col>
                    )
                  })}
                </Row>
              </>
            ) : (
              <Spin />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  )
}
