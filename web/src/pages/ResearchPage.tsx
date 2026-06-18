import { useCallback, useEffect, useRef, useState } from 'react'
import {
  App,
  Button,
  Card,
  Drawer,
  Empty,
  Input,
  Space,
  Spin,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import {
  CheckCircleFilled,
  DeleteOutlined,
  DownloadOutlined,
  DownOutlined,
  FileSearchOutlined,
  GlobalOutlined,
  PlusOutlined,
  SaveOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons'
import MarkdownMessage from '@/components/MarkdownMessage'
import {
  researchApi,
  streamResearch,
  subscribeResearchEvents,
  type ReportBrief,
  type ReportDetail,
  type ResearchPlan,
  type ResearchSource,
  type ResearchStep,
  type ResearchStreamHandlers,
} from '@/api/research'

const { TextArea } = Input

const EXAMPLES = [
  '调研 AI Agent / 大模型开发岗秋招：在招公司、岗位要求与投递链接',
  '梳理大模型应用开发岗面试高频考点与准备路径',
  '盘点 2025 国内大模型 Agent 创业公司与融资情况',
  '对比主流向量数据库的选型要点与适用场景',
]

const RUNNING_STATUSES = ['pending', 'planning', 'searching', 'writing', 'summarizing']

const PHASE_LABEL: Record<string, string> = {
  planning: '规划中',
  searching: '检索中',
  searching_done: '检索中',
  writing: '撰写中',
  summarizing: '汇总中',
}

const SOURCE_META: Record<string, { label: string; color: string }> = {
  web: { label: '网页', color: 'blue' },
  kb: { label: '知识库', color: 'green' },
  mcp: { label: '工具', color: 'purple' },
}

const STEP_ICON: Record<string, string> = {
  search: '🔎',
  web: '🌐',
  fetch: '📄',
  kb: '📚',
  mcp: '🔧',
  stage: '🧭',
  write: '✍️',
}

export default function ResearchPage() {
  const { message } = App.useApp()
  const [reports, setReports] = useState<ReportBrief[]>([])
  const [topic, setTopic] = useState('')
  const [running, setRunning] = useState(false)
  const [currentId, setCurrentId] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  // 流式状态
  const [phase, setPhase] = useState('')
  const [statusDetail, setStatusDetail] = useState('')
  const [plan, setPlan] = useState<ResearchPlan | null>(null)
  const [sources, setSources] = useState<ResearchSource[]>([])
  const [steps, setSteps] = useState<ResearchStep[]>([])
  const [liveText, setLiveText] = useState('')
  const [finalMd, setFinalMd] = useState<string | null>(null)
  const [detail, setDetail] = useState<ReportDetail | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)
  // 进度面板展开态：桌面默认展开，手机默认收起（省屏幕）
  const isMobile =
    typeof window !== 'undefined' && window.matchMedia('(max-width: 768px)').matches
  const [feedOpen, setFeedOpen] = useState(!isMobile)
  const [historyDrawerOpen, setHistoryDrawerOpen] = useState(false)

  const abortRef = useRef<AbortController | null>(null)
  const bodyRef = useRef<HTMLDivElement>(null)

  const loadReports = useCallback(async () => {
    try {
      const res = await researchApi.list(1, 50)
      setReports(res.data.items)
    } catch {
      /* 忽略 */
    }
  }, [])

  useEffect(() => {
    loadReports()
    return () => abortRef.current?.abort()
  }, [loadReports])

  const stepsRef = useRef<HTMLDivElement>(null)

  // 流式时自动滚到底部
  useEffect(() => {
    if (running && bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight
    }
  }, [liveText, running])

  // 活动流自动滚到最新
  useEffect(() => {
    if (stepsRef.current) {
      stepsRef.current.scrollTop = stepsRef.current.scrollHeight
    }
  }, [steps])

  const resetLive = () => {
    setPhase('')
    setStatusDetail('')
    setPlan(null)
    setSources([])
    setSteps([])
    setLiveText('')
    setFinalMd(null)
    setDetail(null)
  }

  const buildHandlers = (): ResearchStreamHandlers => ({
    onMeta: (d) => {
      setCurrentId(d.report_id)
      setReports((prev) => [
        { id: d.report_id, topic: d.topic, title: null, status: 'planning', created_at: null },
        ...prev,
      ])
    },
    onStatus: (d) => {
      setPhase(d.phase)
      setStatusDetail(d.detail)
      // 阶段切换也作为一条活动记录，让流程更连贯
      if (d.phase === 'writing' || d.phase === 'summarizing' || d.phase === 'planning') {
        setSteps((s) => [...s, { icon: 'stage', ok: true, text: d.detail }])
      }
    },
    onPlan: (p) => setPlan(p),
    onSources: (s) => setSources(s),
    onProgress: (st) => setSteps((s) => [...s, st]),
    onSectionStart: (d) => {
      setLiveText((t) => `${t}\n\n## ${d.heading}\n\n`)
      setSteps((s) => [...s, { icon: 'write', ok: true, text: `撰写：${d.heading}` }])
    },
    onToken: (text) => setLiveText((t) => t + text),
    onReport: (d) => {
      setFinalMd(d.markdown)
      setSources(d.sources)
    },
    onResume: (d) => {
      setPhase(d.phase)
      setPlan(d.plan)
      setSources(d.sources)
      setSteps(d.steps || [])
      setLiveText(d.partial_md || '')
    },
    onDone: () => {
      setRunning(false)
      setFeedOpen(false)
      loadReports()
    },
    onIdle: () => setRunning(false),
    onError: (msg) => {
      message.error(msg)
      setRunning(false)
    },
  })

  const startResearch = async () => {
    const t = topic.trim()
    if (!t) {
      message.warning('请输入研究主题')
      return
    }
    if (running) return
    abortRef.current?.abort()
    const ac = new AbortController()
    abortRef.current = ac
    resetLive()
    setRunning(true)
    setFeedOpen(!isMobile)
    setCurrentId(null)
    await streamResearch(t, buildHandlers(), ac.signal)
  }

  const openReport = async (id: string) => {
    setHistoryDrawerOpen(false)
    if (running) {
      message.warning('请等待当前研究完成')
      return
    }
    abortRef.current?.abort()
    resetLive()
    setCurrentId(id)
    setLoadingDetail(true)
    try {
      const res = await researchApi.detail(id)
      const d = res.data
      if (RUNNING_STATUSES.includes(d.status)) {
        // 仍在进行中：订阅续传
        setRunning(true)
        setPhase(d.status)
        setPlan(d.outline ?? null)
        setSources(d.sources ?? [])
        const ac = new AbortController()
        abortRef.current = ac
        subscribeResearchEvents(id, buildHandlers(), ac.signal)
      } else {
        setDetail(d)
        setFinalMd(d.report_md)
        setSources(d.sources ?? [])
        setPlan(d.outline ?? null)
      }
    } catch {
      message.error('加载报告失败')
    } finally {
      setLoadingDetail(false)
    }
  }

  const newResearch = () => {
    setHistoryDrawerOpen(false)
    if (running) {
      message.warning('请等待当前研究完成')
      return
    }
    abortRef.current?.abort()
    resetLive()
    setCurrentId(null)
    setTopic('')
  }

  const removeReport = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      await researchApi.remove(id)
      setReports((prev) => prev.filter((r) => r.id !== id))
      if (currentId === id) {
        setCurrentId(null)
        resetLive()
      }
      message.success('已删除')
    } catch {
      message.error('删除失败')
    }
  }

  const displayMd = finalMd ?? detail?.report_md ?? liveText
  const reportTitle = detail?.title || plan?.title || ''

  const downloadMd = () => {
    if (!displayMd) return
    const blob = new Blob([displayMd], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${reportTitle || '研究报告'}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  const saveToKb = async () => {
    if (!currentId || saving) return
    setSaving(true)
    try {
      const res = await researchApi.saveToKb(currentId)
      const kbName = res.data?.kb_name || '知识库'
      message.success(`已存入「${kbName}」，正在解析入库`)
    } catch (err) {
      const m = (err as { message?: string })?.message
      message.error(m || '存入失败')
    } finally {
      setSaving(false)
    }
  }

  const showReport = !!displayMd && displayMd.trim().length > 0
  const canManage = !running && (detail?.status === 'done' || finalMd)

  const historyList = (
    <>
      <Button type="primary" icon={<PlusOutlined />} block onClick={newResearch} style={{ marginBottom: 12 }}>
        新建研究
      </Button>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {reports.length === 0 && (
          <Typography.Text type="secondary" style={{ fontSize: 13 }}>
            还没有研究报告，输入一句话开始吧。
          </Typography.Text>
        )}
        {reports.map((r) => (
          <Card
            key={r.id}
            size="small"
            hoverable
            onClick={() => openReport(r.id)}
            style={{
              cursor: 'pointer',
              borderColor: currentId === r.id ? '#155EEF' : undefined,
            }}
            styles={{ body: { padding: '10px 12px' } }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div
                  style={{
                    fontWeight: 500,
                    fontSize: 13,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {r.title || r.topic}
                </div>
                <div style={{ marginTop: 4 }}>
                  {RUNNING_STATUSES.includes(r.status) ? (
                    <Tag color="processing" style={{ marginInlineEnd: 0 }}>
                      进行中
                    </Tag>
                  ) : r.status === 'failed' ? (
                    <Tag color="error" style={{ marginInlineEnd: 0 }}>
                      失败
                    </Tag>
                  ) : (
                    <Tag color="success" style={{ marginInlineEnd: 0 }}>
                      已完成
                    </Tag>
                  )}
                </div>
              </div>
              <Tooltip title="删除">
                <DeleteOutlined
                  onClick={(e) => removeReport(r.id, e)}
                  style={{ color: '#A8A9AA' }}
                />
              </Tooltip>
            </div>
          </Card>
        ))}
      </div>
    </>
  )

  return (
    <div className="fluid-page research-page" style={{ display: 'flex', gap: 20, alignItems: 'flex-start', flexWrap: 'wrap' }}>
      {/* 左：历史报告（桌面端常驻；手机端收进抽屉） */}
      <div className="research-history" style={{ flex: '0 0 260px', minWidth: 220, maxWidth: '100%' }}>
        {historyList}
      </div>

      {/* 手机端历史抽屉 */}
      <Drawer
        title="研究报告"
        placement="left"
        open={historyDrawerOpen}
        onClose={() => setHistoryDrawerOpen(false)}
        width="80%"
      >
        {historyList}
      </Drawer>

      {/* 右：研究主区 */}
      <div style={{ flex: 1, minWidth: 0, width: '100%' }}>
        {/* 手机端顶部工具条：新建 / 历史 */}
        <div className="research-mobile-bar">
          <Button icon={<PlusOutlined />} onClick={newResearch}>
            新建
          </Button>
          <Button icon={<UnorderedListOutlined />} onClick={() => setHistoryDrawerOpen(true)}>
            历史报告{reports.length ? `（${reports.length}）` : ''}
          </Button>
        </div>

        {/* 输入区（初始态：居中引导） */}
        {!showReport && !running && (
          <div className="research-hero">
            <div className="research-hero-icon">
              <FileSearchOutlined />
            </div>
            <h2 className="research-hero-title">深度研究</h2>
            <p className="research-hero-sub">
              用一句话描述主题，AI 会自主规划、联网检索并抓取资料、分章节撰写一份带来源链接的报告。
            </p>

            <div className="research-hero-input">
              <TextArea
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                placeholder="例如：调研 AI Agent 开发岗秋招的在招公司、岗位要求与投递链接"
                autoSize={{ minRows: 3, maxRows: 6 }}
                onPressEnter={(e) => {
                  if (!e.shiftKey) {
                    e.preventDefault()
                    startResearch()
                  }
                }}
              />
              <Button
                type="primary"
                size="large"
                icon={<FileSearchOutlined />}
                onClick={startResearch}
                block
                style={{ marginTop: 12, height: 44, borderRadius: 10 }}
              >
                开始研究
              </Button>
            </div>

            <div className="research-hero-examples">
              <span className="research-hero-examples-label">试试这些 👇</span>
              <div className="research-hero-chips">
                {EXAMPLES.map((ex) => (
                  <button key={ex} className="research-chip" onClick={() => setTopic(ex)}>
                    {ex}
                  </button>
                ))}
              </div>
            </div>

            <div className="research-flow">
              {[
                { icon: '🧭', t: '规划', d: '拆解提纲与检索角度' },
                { icon: '🔎', t: '检索', d: '多源搜索 + 抓取正文' },
                { icon: '✍️', t: '撰写', d: '分章节撰写并标注引用' },
                { icon: '🔗', t: '成稿', d: '带来源链接，可存知识库' },
              ].map((s, i) => (
                <div key={i} className="research-flow-step">
                  <div className="research-flow-icon">{s.icon}</div>
                  <div className="research-flow-t">{s.t}</div>
                  <div className="research-flow-d">{s.d}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {loadingDetail && (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <Spin />
          </div>
        )}

        {/* 进度 + 计划 + 来源 */}
        {(running || showReport) && (
          <div ref={bodyRef} className="research-body">
            {/* 固定进度面板：滚动正文时始终可见 */}
            {(running || steps.length > 0) && (
              <div className="research-progress">
                <div
                  className="research-progress-head"
                  onClick={() => setFeedOpen((o) => !o)}
                >
                  {running ? (
                    <Spin size="small" />
                  ) : (
                    <CheckCircleFilled style={{ color: '#52C41A', fontSize: 16 }} />
                  )}
                  {running && PHASE_LABEL[phase] && (
                    <Tag color="processing" style={{ marginInlineEnd: 0 }}>
                      {PHASE_LABEL[phase]}
                    </Tag>
                  )}
                  <span className="research-progress-latest">
                    {running
                      ? statusDetail || '研究进行中…'
                      : `研究完成 · 共 ${steps.length} 步`}
                  </span>
                  <DownOutlined
                    className="research-progress-caret"
                    rotate={feedOpen ? 180 : 0}
                  />
                </div>
                {feedOpen && (
                  <div ref={stepsRef} className="research-feed">
                    {steps.map((st, i) => (
                      <div
                        key={i}
                        className={`research-step${st.ok ? '' : ' research-step--warn'}`}
                      >
                        <span className="research-step-icon">
                          {STEP_ICON[st.icon] || '•'}
                        </span>
                        <span className="research-step-text">{st.text}</span>
                      </div>
                    ))}
                    {running && (
                      <div className="research-step research-step--pending">
                        <span className="research-step-icon">
                          <Spin size="small" />
                        </span>
                        <span className="research-step-text">
                          {statusDetail || '处理中…'}
                        </span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {plan && plan.queries?.length > 0 && (
              <Card size="small" title="检索角度" style={{ marginBottom: 12 }}>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  {plan.queries.map((q, i) => (
                    <Tag key={i} icon={<GlobalOutlined />} color="blue">
                      {q}
                    </Tag>
                  ))}
                </div>
              </Card>
            )}

            {sources.length > 0 && (
              <Card size="small" title={`参考来源（${sources.length}）`} style={{ marginBottom: 12 }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {sources.map((s) => (
                    <div key={s.index} style={{ fontSize: 13 }}>
                      <Tag color={SOURCE_META[s.type]?.color}>{SOURCE_META[s.type]?.label || s.type}</Tag>
                      [{s.index}]{' '}
                      {s.url ? (
                        <a href={s.url} target="_blank" rel="noreferrer">
                          {s.title || s.url}
                        </a>
                      ) : (
                        <span>{s.title}</span>
                      )}
                    </div>
                  ))}
                </div>
              </Card>
            )}

            {/* 报告正文 */}
            {showReport && (
              <Card
                title={reportTitle || '研究报告'}
                extra={
                  canManage && (
                    <Space>
                      <Tooltip title="下载 Markdown">
                        <Button size="small" icon={<DownloadOutlined />} onClick={downloadMd} />
                      </Tooltip>
                      <Tooltip title="存入「深度研究报告」知识库">
                        <Button
                          size="small"
                          icon={<SaveOutlined />}
                          loading={saving}
                          onClick={saveToKb}
                        />
                      </Tooltip>
                    </Space>
                  )
                }
              >
                <MarkdownMessage content={displayMd} />
                {running && <span className="research-caret">▍</span>}
              </Card>
            )}

            {detail?.status === 'failed' && (
              <Empty
                description={`研究失败：${detail.error_msg || '未知错误'}`}
                style={{ marginTop: 24 }}
              />
            )}
          </div>
        )}
      </div>
    </div>
  )
}
