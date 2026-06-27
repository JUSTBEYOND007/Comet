/**
 * 仪表盘成本与执行卡 —— V0.0.5 ③ M8
 *
 * 数据源:GET /api/traces/cost-summary?days=30
 * 展示:
 * - 4 宫 KPI:总任务数 / 总成本 / 总 tokens / 缓存命中率
 * - 按 model 成本饼图(谁最贵)
 * - 按 task_type 调用次数 + 平均耗时(谁最频繁/谁最慢)
 * 没数据时整卡不显示,避免新用户看到空卡。
 */
import { useEffect, useMemo, useState } from 'react'
import { Card, Empty, Segmented, Space, Spin, Typography } from 'antd'
import ReactECharts from 'echarts-for-react'
import { Link } from 'react-router-dom'

import { traceApi, type CostSummary } from '@/api/traces'

const { Text } = Typography


function fmtCost(cny: number): string {
  if (cny === 0) return '¥0'
  if (cny < 0.01) return `¥${cny.toFixed(5)}`
  if (cny < 1) return `¥${cny.toFixed(4)}`
  return `¥${cny.toFixed(2)}`
}

function fmtNum(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return String(n)
}

function fmtMs(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`
  return `${(ms / 60_000).toFixed(1)}m`
}

const TASK_TYPE_LABELS: Record<string, string> = {
  research: '深度研究',
  chat: '对话',
  agent_task: '定时任务',
  verify: '审稿',
  repair: '修复',
}


export default function CostCard() {
  const [days, setDays] = useState<number>(30)
  const [data, setData] = useState<CostSummary | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    traceApi
      .costSummary(days)
      .then((res) => {
        if (!cancelled) setData(res.data)
      })
      .catch(() => {
        if (!cancelled) setData(null)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [days])

  // ── 衍生值 ──
  // 注意:所有 hook 必须在任何 early return 之前调用(React Hooks 规则)。
  const cacheRate = useMemo(() => {
    if (!data || data.total_input_tokens === 0) return 0
    return (data.total_cached_tokens / data.total_input_tokens) * 100
  }, [data])

  const avgCostPerTask = useMemo(() => {
    if (!data || data.total_traces === 0) return 0
    return data.total_cost_cny / data.total_traces
  }, [data])

  // model 饼图(按成本)
  const modelPieOption = useMemo(() => {
    if (!data) return null
    const items = data.by_model.slice(0, 8).map((m) => ({
      name: m.model,
      value: m.cost_cny,
    }))
    return {
      tooltip: {
        trigger: 'item',
        formatter: (p: { name: string; value: number; percent: number }) =>
          `${p.name}<br/>${fmtCost(p.value)} (${p.percent.toFixed(1)}%)`,
      },
      legend: {
        type: 'scroll',
        orient: 'vertical',
        right: 8,
        top: 'center',
        itemWidth: 10,
        itemHeight: 10,
        textStyle: { fontSize: 11, color: '#475467' },
      },
      series: [
        {
          type: 'pie',
          radius: ['40%', '68%'],
          center: ['38%', '50%'],
          avoidLabelOverlap: true,
          itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
          label: { show: false },
          emphasis: {
            label: {
              show: true,
              fontSize: 12,
              fontWeight: 'bold',
              formatter: '{b}\n{d}%',
            },
          },
          data: items,
        },
      ],
    }
  }, [data])

  // task_type 横向柱(按调用次数)
  const typeBarOption = useMemo(() => {
    if (!data) return null
    const items = [...data.by_task_type].reverse()
    return {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (params: unknown) => {
          const arr = params as Array<{ name: string; value: number; dataIndex: number }>
          const row = items[arr[0].dataIndex]
          if (!row) return ''
          return `${TASK_TYPE_LABELS[row.task_type] || row.task_type}<br/>
            调用 ${row.count} 次<br/>
            成本 ${fmtCost(row.total_cost_cny)}<br/>
            平均耗时 ${fmtMs(row.avg_duration_ms)}<br/>
            失败率 ${(row.fail_rate * 100).toFixed(1)}%`
        },
      },
      grid: { left: 70, right: 24, top: 12, bottom: 24 },
      xAxis: {
        type: 'value',
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: '#98A2B3', fontSize: 11 },
        splitLine: { lineStyle: { color: '#f2f4f7' } },
      },
      yAxis: {
        type: 'category',
        data: items.map((x) => TASK_TYPE_LABELS[x.task_type] || x.task_type),
        axisLine: { lineStyle: { color: '#eef0f4' } },
        axisTick: { show: false },
        axisLabel: { color: '#475467', fontSize: 12 },
      },
      series: [
        {
          type: 'bar',
          data: items.map((x) => x.count),
          barWidth: '52%',
          itemStyle: {
            color: '#155EEF',
            borderRadius: [0, 4, 4, 0],
          },
          label: {
            show: true,
            position: 'right',
            color: '#475467',
            fontSize: 11,
          },
        },
      ],
    }
  }, [data])

  // 没数据 → 整卡不渲染(对新用户友好)。
  // 必须放在所有 hook 调用之后,否则前后两次渲染 hook 数量不一致会触发
  // 「Rendered more hooks than during the previous render」。
  if (!loading && (!data || data.total_traces === 0)) {
    return null
  }

  return (
    <Card
      title={
        <Space>
          <span>💰 成本与执行</span>
          <Text type="secondary" style={{ fontSize: 12 }}>
            Agent 任务的真实 token 与成本透视
          </Text>
        </Space>
      }
      style={{ marginBottom: 22, borderRadius: 16 }}
      extra={
        <Space>
          <Segmented
            size="small"
            value={days}
            onChange={(v) => setDays(v as number)}
            options={[
              { label: '近 7 天', value: 7 },
              { label: '近 30 天', value: 30 },
              { label: '近 90 天', value: 90 },
            ]}
          />
          <Link to="/traces" style={{ fontSize: 12 }}>
            查看全部轨迹 →
          </Link>
        </Space>
      }
    >
      {loading || !data ? (
        <div style={{ textAlign: 'center', padding: 32 }}>
          <Spin />
        </div>
      ) : (
        <div>
          {/* 4 宫 KPI */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
              gap: 10,
              marginBottom: 16,
            }}
          >
            <Kpi label="任务总数" value={String(data.total_traces)} unit="次" color="#155EEF" />
            <Kpi
              label="总成本"
              value={fmtCost(data.total_cost_cny)}
              sub={`平均 ${fmtCost(avgCostPerTask)} / 次`}
              color="#FAAD14"
            />
            <Kpi
              label="总 tokens"
              value={fmtNum(data.total_input_tokens + data.total_output_tokens)}
              sub={`输入 ${fmtNum(data.total_input_tokens)} / 输出 ${fmtNum(data.total_output_tokens)}`}
              color="#7C4DFF"
            />
            <Kpi
              label="缓存命中率"
              value={`${cacheRate.toFixed(1)}%`}
              sub={`节省 ${fmtNum(data.total_cached_tokens)} tokens`}
              color={cacheRate >= 10 ? '#369F21' : '#98A2B3'}
            />
          </div>

          {/* 两张图 */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
              gap: 12,
            }}
          >
            {data.by_model.length > 0 ? (
              <div
                style={{
                  background: '#fafbfc',
                  border: '1px solid #eef0f4',
                  borderRadius: 10,
                  padding: 12,
                }}
              >
                <Text strong style={{ fontSize: 13 }}>
                  按 model 成本分布(谁最贵)
                </Text>
                <ReactECharts option={modelPieOption} style={{ height: 220 }} />
              </div>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="近期无 LLM 调用" />
            )}
            {data.by_task_type.length > 0 ? (
              <div
                style={{
                  background: '#fafbfc',
                  border: '1px solid #eef0f4',
                  borderRadius: 10,
                  padding: 12,
                }}
              >
                <Text strong style={{ fontSize: 13 }}>
                  按任务类型调用次数
                </Text>
                <ReactECharts option={typeBarOption} style={{ height: 220 }} />
              </div>
            ) : null}
          </div>
        </div>
      )}
    </Card>
  )
}


function Kpi({
  label,
  value,
  unit,
  sub,
  color,
}: {
  label: string
  value: string
  unit?: string
  sub?: string
  color: string
}) {
  return (
    <div
      style={{
        padding: '12px 14px',
        background: '#ffffff',
        border: '1px solid #eef0f4',
        borderRadius: 10,
      }}
    >
      <div style={{ fontSize: 11.5, color: '#98A2B3' }}>{label}</div>
      <div
        style={{
          fontSize: 20,
          fontWeight: 700,
          color,
          lineHeight: 1.15,
          marginTop: 4,
        }}
      >
        {value}
        {unit && <span style={{ fontSize: 12, color: '#98A2B3', marginLeft: 2, fontWeight: 500 }}>{unit}</span>}
      </div>
      {sub && <div style={{ fontSize: 10.5, color: '#98A2B3', marginTop: 4 }}>{sub}</div>}
    </div>
  )
}
