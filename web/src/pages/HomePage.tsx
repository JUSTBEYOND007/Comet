import { useEffect, useMemo, useState } from 'react'
import { Button, Card, Col, Empty, Row, Spin, Tag, Tooltip } from 'antd'
import {
  ArrowRightOutlined,
  BookOutlined,
  CheckCircleFilled,
  CommentOutlined,
  CustomerServiceOutlined,
  DeploymentUnitOutlined,
  HddOutlined,
  PictureOutlined,
  QuestionCircleOutlined,
  RobotOutlined,
  SettingOutlined,
  SmileOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import ReactECharts from 'echarts-for-react'
import {
  dashboardApi,
  type DailyReview,
  type MemoryStatsData,
  type OverviewData,
} from '@/api/dashboard'
import {
  emotionApi,
  type EmotionDistributionItem,
  type EmotionProfile,
  type EmotionTrendPoint,
} from '@/api/emotion'
import { modelApi, type ModelConfigItem } from '@/api/models'
import { useAuthStore } from '@/stores/authStore'

export default function HomePage() {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const [review, setReview] = useState<DailyReview | null>(null)
  const [overview, setOverview] = useState<OverviewData | null>(null)
  const [memStats, setMemStats] = useState<MemoryStatsData | null>(null)
  const [emotionProfile, setEmotionProfile] = useState<EmotionProfile | null>(null)
  const [emotionTrend, setEmotionTrend] = useState<EmotionTrendPoint[]>([])
  const [emotionDist, setEmotionDist] = useState<EmotionDistributionItem[]>([])
  const [models, setModels] = useState<ModelConfigItem[] | null>(null)
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
      modelApi
        .list()
        .then(({ data }) => setModels(data))
        .catch(() => setModels([]))
      dashboardApi
        .dailyReview()
        .then(({ data }) => setReview(data))
        .catch(() => {})
      emotionApi
        .current()
        .then(({ data }) => setEmotionProfile(data))
        .catch(() => {})
      emotionApi
        .trend(14)
        .then(({ data }) => setEmotionTrend(data.points))
        .catch(() => {})
      emotionApi
        .distribution(30)
        .then(({ data }) => setEmotionDist(data.items))
        .catch(() => {})
    })()
  }, [])

  const c = overview?.counts

  // 快速开始：根据已配置模型类型判断完成度
  const modelTypes = useMemo(
    () => new Set((models ?? []).map((m) => m.type)),
    [models],
  )
  const hasChat = modelTypes.has('chat') || modelTypes.has('multimodal')
  const hasEmbedding = modelTypes.has('embedding')
  const hasDocs = (c?.documents ?? 0) > 0
  const hasChatted = (c?.conversations ?? 0) > 0

  const quickSteps = [
    {
      done: hasChat,
      title: '配置对话模型',
      icon: <SettingOutlined />,
      desc: '前往「模型配置」添加 chat 模型并设为默认，这是问答、记忆萃取、情绪与音乐标注的基础。',
      action: () => navigate('/settings/models'),
      btn: hasChat ? '已配置' : '去配置',
    },
    {
      done: hasEmbedding,
      title: '配置向量模型',
      icon: <SettingOutlined />,
      desc: '添加 embedding（向量）模型，知识库与记忆的语义检索都依赖它。建议再配一个 rerank 提升精度。',
      action: () => navigate('/settings/models'),
      btn: hasEmbedding ? '已配置' : '去配置',
    },
    {
      done: hasDocs,
      title: '建立你的知识库',
      icon: <BookOutlined />,
      desc: '上传文档或导入网页，系统自动分块、向量化、打标签，之后即可被 AI 检索引用。',
      action: () => navigate('/knowledge'),
      btn: hasDocs ? '去管理' : '去上传',
    },
    {
      done: hasChatted,
      title: '开始智能对话',
      icon: <CommentOutlined />,
      desc: 'AI 会自动调用知识库、记忆、联网工具回答，并在对话后沉淀记忆，越用越懂你。',
      action: () => navigate('/chat'),
      btn: hasChatted ? '继续对话' : '去对话',
    },
  ]

  // 功能导航
  const features = [
    { icon: <CommentOutlined />, label: '智能对话', desc: 'Agent 工具编排问答', to: '/chat', color: '#155EEF' },
    { icon: <BookOutlined />, label: '知识库', desc: '文档/网页 RAG 检索', to: '/knowledge', color: '#369F21' },
    { icon: <HddOutlined />, label: '记忆图谱', desc: '实体关系与画像', to: '/memory', color: '#7C4DFF' },
    { icon: <DeploymentUnitOutlined />, label: '图谱可视化', desc: '关系网络与时间线', to: '/graph', color: '#FF8A34' },
    { icon: <RobotOutlined />, label: '角色配置', desc: '人设与对话偏好', to: '/settings/agent', color: '#13C2C2' },
    { icon: <CustomerServiceOutlined />, label: '情绪音乐', desc: '随心情推荐歌单', to: '/music', color: '#EB2F96' },
  ]

  const pieOption = {
    tooltip: { trigger: 'item' },
    legend: { bottom: 0, type: 'scroll' },
    series: [
      {
        type: 'pie',
        radius: ['42%', '70%'],
        center: ['50%', '44%'],
        data: overview?.tag_distribution ?? [],
        label: { show: false },
        itemStyle: { borderColor: '#fff', borderWidth: 2 },
      },
    ],
  }

  const lineOption = {
    tooltip: { trigger: 'axis' },
    grid: { left: 36, right: 16, top: 24, bottom: 28 },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: (memStats?.trend ?? []).map((t) => t.date.slice(5)),
    },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      {
        type: 'line',
        smooth: true,
        data: (memStats?.trend ?? []).map((t) => t.count),
        areaStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(21,94,239,0.35)' },
              { offset: 1, color: 'rgba(21,94,239,0.02)' },
            ],
          },
        },
        lineStyle: { width: 3 },
        itemStyle: { color: '#155EEF' },
      },
    ],
  }

  const emotionTrendOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['情绪倾向', '情绪强度'], top: 0 },
    grid: { left: 36, right: 16, top: 32, bottom: 28 },
    xAxis: {
      type: 'category',
      data: emotionTrend.map((t) => t.date.slice(5)),
    },
    yAxis: { type: 'value', min: -1, max: 1 },
    series: [
      {
        name: '情绪倾向',
        type: 'line',
        smooth: true,
        connectNulls: true,
        data: emotionTrend.map((t) => (t.count > 0 ? t.avg_valence : null)),
        itemStyle: { color: '#369F21' },
        areaStyle: { opacity: 0.1 },
      },
      {
        name: '情绪强度',
        type: 'line',
        smooth: true,
        connectNulls: true,
        data: emotionTrend.map((t) => (t.count > 0 ? t.avg_arousal : null)),
        itemStyle: { color: '#FF8A34' },
      },
    ],
  }

  const emotionPieOption = {
    tooltip: { trigger: 'item' },
    legend: { bottom: 0, type: 'scroll' },
    series: [
      {
        type: 'pie',
        radius: ['42%', '70%'],
        center: ['50%', '44%'],
        data: emotionDist,
        label: { show: false },
        itemStyle: { borderColor: '#fff', borderWidth: 2 },
      },
    ],
  }

  const hasEmotion = (emotionProfile?.sample_count ?? 0) > 0
  const allReady = hasChat && hasEmbedding
  const finishedSteps = quickSteps.filter((s) => s.done).length

  // 数据概览 KPI 卡片（情绪指数若有则置顶）
  const healthIndex = emotionProfile?.health_index ?? 0
  const healthColor =
    healthIndex >= 60 ? '#369F21' : healthIndex >= 40 ? '#FF8A34' : '#FF5D34'
  const kpis = [
    ...(hasEmotion
      ? [{ label: '情绪指数', value: healthIndex, icon: <SmileOutlined />, color: healthColor }]
      : []),
    { label: '文档', value: c?.documents ?? 0, icon: <BookOutlined />, color: '#369F21' },
    { label: '图片', value: c?.images ?? 0, icon: <PictureOutlined />, color: '#FF8A34' },
    { label: '对话', value: c?.conversations ?? 0, icon: <CommentOutlined />, color: '#155EEF' },
    { label: '记忆实体', value: c?.entities ?? 0, icon: <HddOutlined />, color: '#7C4DFF' },
    { label: '记忆社区', value: c?.communities ?? 0, icon: <DeploymentUnitOutlined />, color: '#EB2F96' },
  ]

  return (
    <div className="fluid-page">
      {/* 欢迎横幅 */}
      <div className="dash-hero">
        <h2 className="dash-hero__title">
          你好，{user?.nickname || user?.username || '朋友'} 👋
        </h2>
        <p className="dash-hero__sub">
          欢迎使用彗记 Comet —— 你的个人 AI 知识库与记忆助手。让 AI 记住你、读懂你的资料。
        </p>
      </div>

      {/* 今日回顾 */}
      <Card
        title="📅 今日回顾"
        style={{ marginBottom: 22, borderRadius: 16 }}
        extra={
          review?.stats && (
            <span style={{ color: '#98A2B3', fontSize: 13 }}>
              对话 {review.stats.messages} · 记忆 {review.stats.memories} · 文档{' '}
              {review.stats.documents}
              {review.stats.songs ? ` · 听歌 ${review.stats.songs}` : ''}
            </span>
          )
        }
      >
        <p style={{ margin: 0, color: '#475467', lineHeight: 1.8, whiteSpace: 'pre-wrap' }}>
          {review?.content ?? '加载中…'}
        </p>
        {review?.care && (
          <div className="daily-care">
            <span className="daily-care-text">💛 {review.care}</span>
            <Button
              size="small"
              type="primary"
              ghost
              icon={<CommentOutlined />}
              onClick={() =>
                navigate(`/chat?greeting=${encodeURIComponent(review.care ?? '')}`)
              }
            >
              聊聊
            </Button>
          </div>
        )}
      </Card>

      {/* 快速开始 */}
      <Card
        style={{ marginBottom: 22, borderRadius: 16 }}
        styles={{ body: { padding: 22 } }}
        title={
          <span>
            🚀 快速开始
            <span style={{ color: '#98A2B3', fontWeight: 400, fontSize: 13, marginLeft: 10 }}>
              {finishedSteps}/{quickSteps.length} 已完成
            </span>
          </span>
        }
        extra={
          allReady ? (
            <Tag color="success" icon={<CheckCircleFilled />}>
              基础配置已就绪
            </Tag>
          ) : (
            <Tag color="warning">请先完成模型配置</Tag>
          )
        }
      >
        <Row gutter={[14, 14]}>
          {quickSteps.map((step, i) => (
            <Col xs={24} sm={12} lg={6} key={step.title}>
              <div className={`qs-step${step.done ? ' qs-step--done' : ''}`}>
                <div className="qs-step__num">
                  {step.done ? <CheckCircleFilled /> : i + 1}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column' }}>
                  <div className="qs-step__title">
                    {step.icon} {step.title}
                  </div>
                  <div className="qs-step__desc">{step.desc}</div>
                  <Button
                    type={step.done ? 'default' : 'primary'}
                    size="small"
                    style={{ marginTop: 10, alignSelf: 'flex-start' }}
                    onClick={step.action}
                  >
                    {step.btn} <ArrowRightOutlined />
                  </Button>
                </div>
              </div>
            </Col>
          ))}
        </Row>
      </Card>

      {/* 功能导航 */}
      <Card
        title="✨ 功能一览"
        style={{ marginBottom: 22, borderRadius: 16 }}
        styles={{ body: { padding: 18 } }}
      >
        <Row gutter={[14, 14]}>
          {features.map((f) => (
            <Col xs={12} sm={8} md={8} lg={4} key={f.label}>
              <div
                className="qs-step"
                style={{ cursor: 'pointer', alignItems: 'center' }}
                onClick={() => navigate(f.to)}
              >
                <div
                  className="stat-card__icon"
                  style={{ background: `${f.color}1a`, color: f.color, marginBottom: 0 }}
                >
                  {f.icon}
                </div>
                <div>
                  <div className="qs-step__title">{f.label}</div>
                  <div className="qs-step__desc" style={{ marginTop: 2 }}>
                    {f.desc}
                  </div>
                </div>
              </div>
            </Col>
          ))}
        </Row>
      </Card>

      {/* 数据概览 */}
      <div className="dash-section-title">📊 数据概览</div>
      {loading ? (
        <div style={{ textAlign: 'center', padding: 40 }}>
          <Spin />
        </div>
      ) : (
        <div className="dash-kpi-grid">
          {kpis.map((k) => (
            <div className="stat-card" key={k.label}>
              <div className="stat-card__bar" style={{ background: k.color }} />
              <div
                className="stat-card__icon"
                style={{ background: `${k.color}1a`, color: k.color }}
              >
                {k.icon}
              </div>
              <div className="stat-card__value">{k.value}</div>
              <div className="stat-card__label">{k.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* 图表：两行等宽 */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} md={12}>
          <Card title="知识库分类分布" style={{ borderRadius: 16 }}>
            {loading ? (
              <div style={{ textAlign: 'center', padding: 40 }}>
                <Spin />
              </div>
            ) : overview?.tag_distribution.length ? (
              <ReactECharts option={pieOption} style={{ height: 280 }} />
            ) : (
              <Empty description="还没有分类标签" />
            )}
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card title="近 14 天记忆新增" style={{ borderRadius: 16 }}>
            {memStats?.trend.length ? (
              <ReactECharts option={lineOption} style={{ height: 280 }} />
            ) : (
              <Empty description="暂无记忆数据" />
            )}
          </Card>
        </Col>
      </Row>

      {/* 情绪洞察：两张等宽 */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} md={12}>
          <Card
            title={
              <span>
                近 14 天情绪趋势
                <Tooltip
                  title="情绪倾向：越高越积极开心、越低越消极低落（范围 -1~1）；情绪强度：越高情绪越激动强烈、越低越平静（范围 -1~1）。由 AI 从你的对话中感知。"
                >
                  <QuestionCircleOutlined style={{ marginLeft: 6, color: '#98a2b3', fontSize: 13 }} />
                </Tooltip>
              </span>
            }
            style={{ borderRadius: 16 }}
          >
            {hasEmotion ? (
              <ReactECharts option={emotionTrendOption} style={{ height: 280 }} />
            ) : (
              <Empty description="多聊几句，AI 会感知你的情绪" />
            )}
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card title="近 30 天情绪分布" style={{ borderRadius: 16 }}>
            {emotionDist.length ? (
              <ReactECharts option={emotionPieOption} style={{ height: 280 }} />
            ) : (
              <Empty description="暂无情绪数据" />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  )
}
