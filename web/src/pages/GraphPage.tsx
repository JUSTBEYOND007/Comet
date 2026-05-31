import { useEffect, useMemo, useRef, useState } from 'react'
import { Button, Card, Empty, Space, Spin, Tag, Typography, message } from 'antd'
import { MergeCellsOutlined, ReloadOutlined } from '@ant-design/icons'
import { Graph } from '@antv/x6'
import { memoryApi, type GraphData, type GraphNode } from '@/api/memories'

const { Text, Paragraph } = Typography

// 社区调色板：按社区 id 稳定取色；无社区按实体类型回退
const PALETTE = [
  '#155EEF', '#369F21', '#FF5D34', '#9254DE', '#13A8A8',
  '#FA8C16', '#EB2F96', '#2F54EB', '#52C41A', '#FAAD14',
  '#722ED1', '#08979C', '#D4380D', '#C41D7F', '#1677FF',
]

function colorForKey(key: string, table: Map<string, string>): string {
  if (!table.has(key)) {
    table.set(key, PALETTE[table.size % PALETTE.length])
  }
  return table.get(key)!
}

export default function GraphPage() {
  const containerRef = useRef<HTMLDivElement>(null)
  const graphRef = useRef<Graph | null>(null)
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState<GraphData | null>(null)
  const [selected, setSelected] = useState<GraphNode | null>(null)
  const [merging, setMerging] = useState(false)
  const adjRef = useRef<Map<string, Set<string>>>(new Map())

  const colorTable = useMemo(() => new Map<string, string>(), [])

  const reload = () => {
    setLoading(true)
    setSelected(null)
    memoryApi
      .graph()
      .then(({ data }) => setData(data))
      .catch((e) => message.error((e as Error).message))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    let mounted = true
    setLoading(true)
    memoryApi
      .graph()
      .then(({ data }) => {
        if (mounted) setData(data)
      })
      .catch((e) => message.error((e as Error).message))
      .finally(() => {
        if (mounted) setLoading(false)
      })
    return () => {
      mounted = false
    }
  }, [])

  const onMergeDuplicates = async () => {
    setMerging(true)
    try {
      const { data } = await memoryApi.mergeDuplicates()
      message.success(`已合并 ${data.removed} 个重复实体`)
      reload()
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setMerging(false)
    }
  }

  useEffect(() => {
    if (!data || !containerRef.current) return
    if (data.nodes.length === 0) return

    const container = containerRef.current
    const width = container.clientWidth || 800
    const height = container.clientHeight || 600

    const graph = new Graph({
      container,
      width,
      height,
      background: { color: '#FAFAFA' },
      panning: true,
      mousewheel: { enabled: true, modifiers: [], minScale: 0.2, maxScale: 3 },
      interacting: { nodeMovable: true },
    })
    graphRef.current = graph

    const adj = new Map<string, Set<string>>()
    data.nodes.forEach((nd) => adj.set(nd.id, new Set()))
    data.edges.forEach((e) => {
      adj.get(e.source)?.add(e.target)
      adj.get(e.target)?.add(e.source)
    })
    adjRef.current = adj

    // 环形布局（可拖拽）。半径随节点数增长，节点更分散不挤在一起。
    const count = data.nodes.length
    const radius = Math.max(Math.min(width, height) / 2 - 60, count * 52)
    const cx = width / 2
    const cy = height / 2

    data.nodes.forEach((node, i) => {
      const angle = (2 * Math.PI * i) / count
      const key = node.community_id || `type:${node.type}`
      const color = colorForKey(key, colorTable)
      // 圆形节点：直径按名称长度自适应，文字在圆内自动换行完整显示
      const size = Math.max(70, Math.min(130, node.name.length * 13 + 34))
      graph.addNode({
        id: node.id,
        x: cx + radius * Math.cos(angle) - size / 2,
        y: cy + radius * Math.sin(angle) - size / 2,
        width: size,
        height: size,
        shape: 'circle',
        label: node.name,
        attrs: {
          body: { fill: color, stroke: '#fff', strokeWidth: 2 },
          label: {
            fill: '#fff',
            fontSize: 13,
            fontWeight: 600,
            textWrap: { width: size - 14, height: size - 12, ellipsis: false },
          },
        },
        data: node,
      })
    })

    data.edges.forEach((e) => {
      graph.addEdge({
        source: e.source,
        target: e.target,
        attrs: {
          line: {
            stroke: '#C0C4CC',
            strokeWidth: 1.2,
            targetMarker: { name: 'classic', size: 5 },
          },
        },
        labels: e.predicate
          ? [
              {
                attrs: {
                  label: { text: e.predicate, fontSize: 10, fill: '#8C8C8C' },
                  body: { fill: '#FAFAFA', stroke: 'none' },
                },
              },
            ]
          : [],
      })
    })

    graph.on('node:click', ({ node }) => {
      const nd = node.getData<GraphNode>()
      setSelected(nd)
      highlight(graph, node.id, adjRef.current)
    })
    graph.on('blank:click', () => {
      setSelected(null)
      resetHighlight(graph)
    })

    graph.zoomToFit({ padding: 40, maxScale: 1 })

    return () => {
      graph.dispose()
      graphRef.current = null
    }
  }, [data, colorTable])

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <Card
        title="知识图谱"
        extra={
          <Space>
            <Button icon={<MergeCellsOutlined />} loading={merging} onClick={onMergeDuplicates}>
              合并重复
            </Button>
            <Button icon={<ReloadOutlined />} onClick={reload} disabled={loading}>
              刷新
            </Button>
          </Space>
        }
        styles={{ body: { padding: 0, height: 'calc(100% - 57px)' } }}
        style={{ flex: 1, display: 'flex', flexDirection: 'column' }}
      >
        <div style={{ position: 'relative', height: '100%', minHeight: '32rem' }}>
          {loading ? (
            <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
              <Spin />
            </div>
          ) : !data || data.nodes.length === 0 ? (
            <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
              <Empty description="还没有记忆实体，先去主动记住或对话萃取一些记忆" />
            </div>
          ) : (
            <>
              <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
              {selected && (
                <div
                  style={{
                    position: 'absolute',
                    top: 16,
                    right: 16,
                    width: '18rem',
                    maxWidth: '80%',
                    background: '#fff',
                    borderRadius: 12,
                    boxShadow: '0 4px 16px rgba(0,0,0,0.1)',
                    padding: 16,
                  }}
                >
                  <Text strong style={{ fontSize: 16 }}>
                    {selected.name}
                  </Text>
                  <div style={{ margin: '8px 0' }}>
                    <Tag color="blue">{selected.type}</Tag>
                  </div>
                  {selected.description && (
                    <Paragraph type="secondary" style={{ fontSize: 13, marginBottom: 0 }}>
                      {selected.description}
                    </Paragraph>
                  )}
                </div>
              )}
              <div
                style={{
                  position: 'absolute',
                  left: 16,
                  bottom: 16,
                  background: 'rgba(255,255,255,0.9)',
                  borderRadius: 8,
                  padding: '6px 10px',
                  fontSize: 12,
                  color: '#667085',
                }}
              >
                {data.nodes.length} 个实体 · {data.edges.length} 条关系 · 颜色区分主题社区
              </div>
            </>
          )}
        </div>
      </Card>
    </div>
  )
}

function highlight(graph: Graph, nodeId: string, adj: Map<string, Set<string>>) {
  const neighbors = adj.get(nodeId) || new Set<string>()
  graph.getNodes().forEach((node) => {
    const isActive = node.id === nodeId || neighbors.has(node.id)
    node.attr('body/opacity', isActive ? 1 : 0.2)
    node.attr('label/opacity', isActive ? 1 : 0.2)
  })
  graph.getEdges().forEach((edge) => {
    const s = edge.getSourceCellId()
    const t = edge.getTargetCellId()
    const isActive = s === nodeId || t === nodeId
    edge.attr('line/stroke', isActive ? '#155EEF' : '#E5E6EB')
    edge.attr('line/opacity', isActive ? 1 : 0.2)
  })
}

function resetHighlight(graph: Graph) {
  graph.getNodes().forEach((node) => {
    node.attr('body/opacity', 1)
    node.attr('label/opacity', 1)
  })
  graph.getEdges().forEach((edge) => {
    edge.attr('line/stroke', '#C0C4CC')
    edge.attr('line/opacity', 1)
  })
}
