import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

// AI 消息的 Markdown 渲染：代码块浅灰底、表格边框、链接新窗口
export default function MarkdownMessage({ content }: { content: string }) {
  return (
    <div className="markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: (props) => <a {...props} target="_blank" rel="noreferrer" />,
          code({ className, children, ...props }) {
            const isInline = !className
            if (isInline) {
              return (
                <code
                  style={{
                    background: '#F2F4F7',
                    padding: '1px 5px',
                    borderRadius: 4,
                    fontSize: 13,
                  }}
                  {...props}
                >
                  {children}
                </code>
              )
            }
            return (
              <pre
                style={{
                  background: '#1E1E1E',
                  color: '#E6E6E6',
                  padding: 14,
                  borderRadius: 8,
                  overflowX: 'auto',
                  fontSize: 13,
                  lineHeight: 1.6,
                }}
              >
                <code className={className} {...props}>
                  {children}
                </code>
              </pre>
            )
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
