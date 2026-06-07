import { useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent } from 'react'
import { Slider, Spin, Tooltip } from 'antd'
import {
  CaretRightOutlined,
  CloseOutlined,
  CustomerServiceOutlined,
  HeartOutlined,
  PauseOutlined,
  ShrinkOutlined,
  StepBackwardOutlined,
  StepForwardOutlined,
} from '@ant-design/icons'
import { useMusicStore } from '@/stores/musicStore'
import { activeLineIndex, parseLrc } from '@/pages/music/lrc'
import { useLocation } from 'react-router-dom'

// 带鉴权的资源地址解析：/api/files/.. 需带 token fetch 成 blob；外链直接用
function useAuthedSrc(src: string | null | undefined) {
  const [resolved, setResolved] = useState<string | undefined>(src ?? undefined)
  useEffect(() => {
    if (!src) {
      setResolved(undefined)
      return
    }
    if (!src.startsWith('/api/files/')) {
      setResolved(src)
      return
    }
    let active = true
    let objectUrl: string | undefined
    const token = localStorage.getItem('access_token')
    fetch(src, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status))
        return r.blob()
      })
      .then((blob) => {
        if (!active) return
        objectUrl = URL.createObjectURL(blob)
        setResolved(objectUrl)
      })
      .catch(() => {
        if (active) setResolved(undefined)
      })
    return () => {
      active = false
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [src])
  return resolved
}

function fmt(sec: number): string {
  if (!Number.isFinite(sec) || sec < 0) return '0:00'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

export default function MusicPlayer() {
  const {
    track,
    playlist,
    visible,
    expanded,
    playing,
    loading,
    recommendReason,
    setPlaying,
    setExpanded,
    close,
    next,
    prev,
    recommend,
  } = useMusicStore()

  const audioRef = useRef<HTMLAudioElement>(null)
  const lrcContainerRef = useRef<HTMLDivElement>(null)
  const shellRef = useRef<HTMLDivElement>(null)
  const [current, setCurrent] = useState(0)
  const [duration, setDuration] = useState(0)
  // 拖动位置：null 表示用默认（右下角）；非 null 用 left/top 固定
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null)
  const dragRef = useRef<{ dx: number; dy: number } | null>(null)
  // 手机端窄屏：迷你态把传输控制并到歌名后面，整体更紧凑
  const [isMobile, setIsMobile] = useState(
    () => typeof window !== 'undefined' && window.innerWidth <= 768,
  )
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 768px)')
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])

  // 拖动：按住顶部条移动播放器（仅桌面端）。
  // 注意全局 #root 有 zoom 缩放，getBoundingClientRect 是屏幕像素、CSS left/top 是缩放前坐标，
  // 二者差一个 zoom 比例，需换算，否则一拖就飞。
  const onDragStart = (e: ReactMouseEvent) => {
    if (isMobile) return
    const target = e.target as HTMLElement
    if (target.closest('.player-ctrl-btn, button, a, input, .ant-slider')) return
    const el = shellRef.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    // zoom 比例 = 渲染宽(屏幕px) / 布局宽(CSS px)
    const zoom = el.offsetWidth ? rect.width / el.offsetWidth : 1
    // 起始位置换算到 CSS 坐标系
    const startLeft = rect.left / zoom
    const startTop = rect.top / zoom
    const startMouseX = e.clientX
    const startMouseY = e.clientY
    dragRef.current = { dx: 0, dy: 0 }

    const onMove = (ev: MouseEvent) => {
      if (!dragRef.current) return
      const cssW = el.offsetWidth
      const cssH = el.offsetHeight
      const viewW = window.innerWidth / zoom
      const viewH = window.innerHeight / zoom
      // 鼠标位移(屏幕px)换算回 CSS px
      let x = startLeft + (ev.clientX - startMouseX) / zoom
      let y = startTop + (ev.clientY - startMouseY) / zoom
      x = Math.max(8, Math.min(x, viewW - cssW - 8))
      y = Math.max(8, Math.min(y, viewH - cssH - 8))
      setPos({ x, y })
    }
    const onUp = () => {
      dragRef.current = null
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  const audioSrc = useAuthedSrc(track?.url)
  const coverSrc = useAuthedSrc(track?.coverUrl)
  const lines = useMemo(() => parseLrc(track?.lyric), [track?.lyric])
  const activeIdx = activeLineIndex(lines, current)
  const resolving = useMusicStore((s) => s.resolving)
  const hasAudio = !!track?.url
  const playable = !!track?.playable
  const canSwitch = playlist.length > 1
  // 音乐页保持深色霓虹；其他页面用浅色，融入整体浅色风格
  const light = useLocation().pathname !== '/music'
  const cSub = light ? 'rgba(0,0,0,0.45)' : 'rgba(255,255,255,0.6)'
  const cFaint = light ? 'rgba(0,0,0,0.35)' : 'rgba(255,255,255,0.45)'
  const cGhost = light ? 'rgba(0,0,0,0.25)' : 'rgba(255,255,255,0.3)'

  // 切歌时重置进度
  useEffect(() => {
    setCurrent(0)
    setDuration(0)
  }, [track?.id, track?.url])

  // 播放/暂停状态同步到 audio 元素
  useEffect(() => {
    const audio = audioRef.current
    if (!audio || !audioSrc) return
    if (playing) {
      audio.play().catch(() => setPlaying(false))
    } else {
      audio.pause()
    }
  }, [playing, audioSrc, setPlaying])

  // 歌词自动滚动居中
  useEffect(() => {
    if (!expanded || activeIdx < 0) return
    const container = lrcContainerRef.current
    if (!container) return
    const el = container.children[activeIdx] as HTMLElement | undefined
    if (el) {
      container.scrollTo({
        top: el.offsetTop - container.clientHeight / 2 + el.clientHeight / 2,
        behavior: 'smooth',
      })
    }
  }, [activeIdx, expanded])

  if (!visible) return null

  const discSize = expanded ? 156 : 48
  const disc = (
    <div style={{ position: 'relative', width: discSize, height: discSize, flexShrink: 0 }}>
      {expanded && <div className="player-disc-aura" />}
      <div
        className={`player-disc ${playing && hasAudio ? '' : 'paused'}`}
        style={{ width: '100%', height: '100%' }}
      >
        {coverSrc ? (
          <img
            src={coverSrc}
            alt=""
            className="player-disc-cover"
            style={{ width: '64%', height: '64%' }}
          />
        ) : (
          <div className="player-disc-cover" style={{ width: '64%', height: '64%' }} />
        )}
        <div className="player-disc-hole" />
      </div>
    </div>
  )

  const transportControls = (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <Tooltip title="上一首">
        <div
          className="player-ctrl-btn"
          style={{ opacity: canSwitch ? 1 : 0.4, pointerEvents: canSwitch ? 'auto' : 'none' }}
          onClick={prev}
        >
          <StepBackwardOutlined />
        </div>
      </Tooltip>
      {loading || resolving ? (
        <div className="player-ctrl-btn player-ctrl-main">
          <Spin size="small" />
        </div>
      ) : (
        <div
          className="player-ctrl-btn player-ctrl-main"
          style={{ opacity: playable ? 1 : 0.5, pointerEvents: playable ? 'auto' : 'none' }}
          onClick={() => setPlaying(!playing)}
        >
          {playing ? <PauseOutlined /> : <CaretRightOutlined />}
        </div>
      )}
      <Tooltip title="下一首">
        <div
          className="player-ctrl-btn"
          style={{ opacity: canSwitch ? 1 : 0.4, pointerEvents: canSwitch ? 'auto' : 'none' }}
          onClick={next}
        >
          <StepForwardOutlined />
        </div>
      </Tooltip>
    </div>
  )

  // 手机端迷你态：控制按钮内联到歌名行后面，省去底部那一排
  const inlineMini = isMobile && !expanded

  return (
    <>
      {track?.url && (
        <audio
          ref={audioRef}
          src={audioSrc}
          onTimeUpdate={(e) => setCurrent(e.currentTarget.currentTime)}
          onLoadedMetadata={(e) => setDuration(e.currentTarget.duration)}
          onEnded={() => (canSwitch ? next() : setPlaying(false))}
          onError={() => setPlaying(false)}
        />
      )}

      <div
        ref={shellRef}
        className={`player-shell ${light ? 'player-light' : ''}`}
        style={{
          width: expanded ? 360 : 312,
          ...(pos && !isMobile
            ? { left: pos.x, top: pos.y, right: 'auto', bottom: 'auto' }
            : {}),
        }}
      >
        {/* 顶部条 */}
        <div
          onMouseDown={onDragStart}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            padding: 12,
            cursor: isMobile ? 'default' : 'move',
            userSelect: 'none',
          }}
        >
          {!expanded && disc}
          <div style={{ flex: 1, minWidth: 0 }}>
            <div
              style={{
                fontWeight: 600,
                fontSize: 14,
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              {track?.title ?? '暂无歌曲'}
            </div>
            <div
              style={{
                fontSize: 12,
                color: cSub,
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              {resolving
                ? '正在获取音源…'
                : !playable && track
                  ? `${track.artist || '未知歌手'} · 暂无音源`
                  : track?.artist || (loading ? '正在挑选…' : '点击「为此刻选歌」')}
            </div>
          </div>
          {/* 手机端迷你态：播放控制内联到歌名后面 */}
          {inlineMini && transportControls}
          <Tooltip title={expanded ? '收起' : '展开'}>
            <div
              className="player-ctrl-btn text-only"
              onClick={() => setExpanded(!expanded)}
            >
              {expanded ? <ShrinkOutlined /> : <CustomerServiceOutlined />}
            </div>
          </Tooltip>
          <Tooltip title="关闭">
            <div className="player-ctrl-btn text-only" onClick={close}>
              <CloseOutlined />
            </div>
          </Tooltip>
        </div>

        {/* 迷你态：底部一行传输控制（手机端已内联到顶部，故此处仅桌面端显示） */}
        {!expanded && !inlineMini && (
          <div style={{ padding: '0 12px 12px', display: 'flex', justifyContent: 'center' }}>
            {transportControls}
          </div>
        )}

        {/* 展开态 */}
        {expanded && (
          <div style={{ padding: '4px 18px 18px' }}>
            <div style={{ display: 'flex', justifyContent: 'center', margin: '10px 0 14px' }}>
              {disc}
            </div>

            {recommendReason && (
              <div
                style={{
                  textAlign: 'center',
                  fontSize: 13,
                  color: '#a5b4fc',
                  marginBottom: 8,
                }}
              >
                {recommendReason}
              </div>
            )}

            {!playable && (
              <div
                style={{
                  textAlign: 'center',
                  fontSize: 12,
                  color: cFaint,
                  marginBottom: 8,
                }}
              >
                暂无可播放音源，可在「音乐」页上传该歌曲
              </div>
            )}

            {/* 歌词 */}
            {lines.length > 0 ? (
              <div ref={lrcContainerRef} className="player-lrc">
                {lines.map((l, i) => (
                  <div key={i} className={`lrc-line ${i === activeIdx ? 'active' : ''}`}>
                    {l.text}
                  </div>
                ))}
              </div>
            ) : (
              <div
                style={{
                  height: 56,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: cGhost,
                  fontSize: 13,
                }}
              >
                暂无歌词
              </div>
            )}

            {/* 进度条 */}
            {hasAudio && (
              <>
                <Slider
                  min={0}
                  max={duration || 0}
                  value={current}
                  tooltip={{ open: false }}
                  onChange={(v) => {
                    if (audioRef.current) audioRef.current.currentTime = v as number
                    setCurrent(v as number)
                  }}
                  style={{ margin: '6px 0 0' }}
                />
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    fontSize: 12,
                    color: cSub,
                  }}
                >
                  <span>{fmt(current)}</span>
                  <span>{fmt(duration)}</span>
                </div>
              </>
            )}

            {/* 传输控制 */}
            <div style={{ display: 'flex', justifyContent: 'center', marginTop: 12 }}>
              {transportControls}
            </div>

            {/* 为此刻选歌 */}
            <div
              className="player-ctrl-btn"
              style={{
                width: '100%',
                height: 38,
                borderRadius: 10,
                marginTop: 14,
                gap: 8,
                background: 'linear-gradient(135deg, #6366f1, #ec4899)',
                border: 'none',
                color: '#fff',
                fontSize: 14,
                fontWeight: 500,
              }}
              onClick={() => recommend()}
            >
              <HeartOutlined /> 为此刻选歌
            </div>
          </div>
        )}
      </div>
    </>
  )
}
