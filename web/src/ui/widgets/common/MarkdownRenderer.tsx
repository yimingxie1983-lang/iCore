

import { Children, Fragment, useMemo, useState, type ReactNode } from 'react'
import { Check, Copy } from 'lucide-react'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Light as SyntaxHighlighter } from 'react-syntax-highlighter'

import CitationChip, { type ChipKind } from './CitationChip'

import oneLight from 'react-syntax-highlighter/dist/esm/styles/hljs/atom-one-light'

import bash from 'react-syntax-highlighter/dist/esm/languages/hljs/bash'
import javascript from 'react-syntax-highlighter/dist/esm/languages/hljs/javascript'
import typescript from 'react-syntax-highlighter/dist/esm/languages/hljs/typescript'
import python from 'react-syntax-highlighter/dist/esm/languages/hljs/python'
import r from 'react-syntax-highlighter/dist/esm/languages/hljs/r'
import sql from 'react-syntax-highlighter/dist/esm/languages/hljs/sql'
import json from 'react-syntax-highlighter/dist/esm/languages/hljs/json'
import yaml from 'react-syntax-highlighter/dist/esm/languages/hljs/yaml'
import markdown from 'react-syntax-highlighter/dist/esm/languages/hljs/markdown'
import diff from 'react-syntax-highlighter/dist/esm/languages/hljs/diff'

import { cn } from '@/shared/foundation/utils'
import { Button } from '@/ui/widgets/ui/button'

SyntaxHighlighter.registerLanguage('bash', bash)
SyntaxHighlighter.registerLanguage('sh', bash)
SyntaxHighlighter.registerLanguage('shell', bash)
SyntaxHighlighter.registerLanguage('zsh', bash)
SyntaxHighlighter.registerLanguage('javascript', javascript)
SyntaxHighlighter.registerLanguage('js', javascript)
SyntaxHighlighter.registerLanguage('typescript', typescript)
SyntaxHighlighter.registerLanguage('ts', typescript)
SyntaxHighlighter.registerLanguage('tsx', typescript)
SyntaxHighlighter.registerLanguage('python', python)
SyntaxHighlighter.registerLanguage('py', python)
SyntaxHighlighter.registerLanguage('r', r)
SyntaxHighlighter.registerLanguage('rscript', r)
SyntaxHighlighter.registerLanguage('sql', sql)
SyntaxHighlighter.registerLanguage('json', json)
SyntaxHighlighter.registerLanguage('yaml', yaml)
SyntaxHighlighter.registerLanguage('yml', yaml)
SyntaxHighlighter.registerLanguage('markdown', markdown)
SyntaxHighlighter.registerLanguage('md', markdown)
SyntaxHighlighter.registerLanguage('diff', diff)

const KNOWN_LANGS = new Set([
  'bash', 'sh', 'shell', 'zsh',
  'javascript', 'js', 'typescript', 'ts', 'tsx',
  'python', 'py', 'r', 'rscript',
  'sql', 'json', 'yaml', 'yml',
  'markdown', 'md', 'diff',
])

interface Props {

  text: string

  compact?: boolean
  className?: string
}

type CitationRule = {
  kind: ChipKind
  pattern: RegExp
}

const CITATION_RULES: CitationRule[] = [

  { kind: 'pmid', pattern: /\[REF[\s:]*PMID[\s:]*(\d{1,9})\]/gi },

  {
    kind: 'doi',
    pattern: /\[REF[\s:]*DOI[\s:]*(10\.\d{4,9}\/[\w\-.()/:;]+?)\]/gi,
  },

  {
    kind: 'placeholder',
    pattern: /\[REF[\s:]*(\?{2,}|TODO|todo|待填|TBD|tbd)\]/g,
  },

  { kind: 'pmid', pattern: /\[PMID[\s:]*(\d{1,9})\]/gi },

  { kind: 'doi', pattern: /\[DOI[\s:]*(10\.\d{4,9}\/[\w\-.()/:;]+?)\]/gi },

  { kind: 'pmid', pattern: /\bPMID[\s:：]+(\d{6,9})\b/gi },

  { kind: 'doi', pattern: /\bDOI[\s:：]+(10\.\d{4,9}\/[\w\-.()/:;]+)/gi },

  { kind: 'gov', pattern: /\[GOVCITE:([^\]\s]+)\]/g },
]

function splitStringWithChips(input: string, keyPrefix: string): ReactNode[] {

  type Hit = { start: number; end: number; node: ReactNode }
  const hits: Hit[] = []
  for (const rule of CITATION_RULES) {
    rule.pattern.lastIndex = 0
    let m: RegExpExecArray | null
    while ((m = rule.pattern.exec(input)) !== null) {
      const matchedText = m[0]
      let id = m[1] || ''

      let raw = matchedText
      if (rule.kind === 'gov') {
        try {
          id = decodeURIComponent(id)
        } catch {

        }
        raw = `[GOV:${id}]`
      }
      hits.push({
        start: m.index,
        end: m.index + matchedText.length,
        node: (
          <CitationChip
            key={`${keyPrefix}-${m.index}-${rule.kind}`}
            kind={rule.kind}
            id={id}
            raw={raw}
          />
        ),
      })
    }
  }
  if (hits.length === 0) return [input]

  hits.sort((a, b) => (a.start - b.start) || (b.end - a.end))
  const accepted: Hit[] = []
  let cursor = -1
  for (const h of hits) {
    if (h.start < cursor) continue
    accepted.push(h)
    cursor = h.end
  }

  const out: ReactNode[] = []
  let pos = 0
  for (const h of accepted) {
    if (h.start > pos) out.push(input.slice(pos, h.start))
    out.push(h.node)
    pos = h.end
  }
  if (pos < input.length) out.push(input.slice(pos))
  return out
}

function decorateCitations(children: ReactNode, keyPrefix = 'cite'): ReactNode {
  const arr = Children.toArray(children)
  if (arr.length === 0) return children
  const out: ReactNode[] = []
  arr.forEach((child, idx) => {
    if (typeof child === 'string') {
      const parts = splitStringWithChips(child, `${keyPrefix}-${idx}`)

      parts.forEach((p, j) => {
        if (typeof p === 'string') {
          out.push(<Fragment key={`${keyPrefix}-${idx}-s${j}`}>{p}</Fragment>)
        } else {
          out.push(p)
        }
      })
    } else {
      out.push(child)
    }
  })
  return out
}

function CodeBlock({
  language,
  code,
}: {
  language: string
  code: string
}) {
  const [copied, setCopied] = useState(false)
  const knownLang = KNOWN_LANGS.has(language) ? language : ''

  async function copy() {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {

    }
  }

  return (
    <div className="not-prose group/codeblock my-2 overflow-hidden rounded-lg border border-border bg-card-muted">
      {}
      <div className="flex items-center gap-2 border-b border-border bg-card-muted px-3 py-1.5">
        <span className="font-mono text-[10.5px] font-medium uppercase tracking-wider text-muted-foreground">
          {language || 'plain'}
        </span>
        <span className="flex-1" />
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          className="h-6 w-6 opacity-0 transition-opacity group-hover/codeblock:opacity-100"
          onClick={copy}
          title={copied ? '已复制' : '复制代码'}
        >
          {copied ? (
            <Check className="h-3 w-3 text-emerald-600" />
          ) : (
            <Copy className="h-3 w-3 text-muted-foreground" />
          )}
        </Button>
      </div>
      {}
      {knownLang ? (
        <SyntaxHighlighter
          language={knownLang}
          style={oneLight}
          showLineNumbers={false}
          wrapLongLines={false}
          customStyle={{
            margin: 0,
            padding: '12px 14px',
            background: 'transparent',
            fontSize: '12.5px',
            lineHeight: 1.6,
          }}
          codeTagProps={{
            style: {
              fontFamily:
                '"JetBrains Mono", "Cascadia Code", "Fira Code", Consolas, monospace',
              fontVariantLigatures: 'none',
            },
          }}
        >
          {code.replace(/\n$/, '')}
        </SyntaxHighlighter>
      ) : (
        <pre className="overflow-x-auto p-3 font-mono text-[12.5px] leading-[1.6] text-foreground">
          <code>{code}</code>
        </pre>
      )}
    </div>
  )
}

const components: Components = {

  h1: ({ node, children, ...props }) => (
    <h1
      {...props}
      className="mb-2 mt-4 text-[18px] font-semibold tracking-tight text-foreground first:mt-0"
    >
      {decorateCitations(children, 'h1')}
    </h1>
  ),
  h2: ({ node, children, ...props }) => (
    <h2
      {...props}
      className="mb-2 mt-4 text-[16px] font-semibold tracking-tight text-foreground first:mt-0"
    >
      {decorateCitations(children, 'h2')}
    </h2>
  ),
  h3: ({ node, children, ...props }) => (
    <h3
      {...props}
      className="mb-1.5 mt-3 text-[14px] font-semibold text-foreground first:mt-0"
    >
      {decorateCitations(children, 'h3')}
    </h3>
  ),
  h4: ({ node, children, ...props }) => (
    <h4
      {...props}
      className="mb-1 mt-3 text-[13px] font-semibold text-foreground/90 first:mt-0"
    >
      {decorateCitations(children, 'h4')}
    </h4>
  ),

  p: ({ node, children, ...props }) => (
    <p
      {...props}
      className="my-1.5 leading-[1.7] text-foreground first:mt-0 last:mb-0"
    >
      {decorateCitations(children, 'p')}
    </p>
  ),

  ul: ({ node, children, ...props }) => (
    <ul {...props} className="my-1.5 list-disc space-y-0.5 pl-5 marker:text-muted-foreground/60">
      {children}
    </ul>
  ),
  ol: ({ node, children, ...props }) => (
    <ol {...props} className="my-1.5 list-decimal space-y-0.5 pl-5 marker:text-muted-foreground/60 marker:font-mono marker:text-[11.5px]">
      {children}
    </ol>
  ),
  li: ({ node, children, ...props }) => {

    const isTask =
      (props as any).className === 'task-list-item' ||
      ((props as any).className && String((props as any).className).includes('task-list-item'))
    return (
      <li
        {...props}
        className={cn(
          'leading-[1.65]',
          isTask && 'list-none -ml-5 flex items-start gap-2',
        )}
      >
        {decorateCitations(children, 'li')}
      </li>
    )
  },

  blockquote: ({ node, children, ...props }) => (
    <blockquote
      {...props}
      className="my-2 rounded-r-md border-l-2 border-secondary bg-secondary/[0.06] px-3 py-1.5 text-[13px] italic text-muted-foreground"
    >
      {decorateCitations(children, 'bq')}
    </blockquote>
  ),

  a: ({ node, href, children, ...props }) => {
    const external = href && /^https?:\/\//.test(href)
    return (
      <a
        {...props}
        href={href}
        target={external ? '_blank' : undefined}
        rel={external ? 'noopener noreferrer' : undefined}
        className="text-secondary underline decoration-secondary/40 underline-offset-2 transition-colors hover:decoration-secondary"
      >
        {children}
      </a>
    )
  },

  hr: ({ node, ...props }) => (
    <hr
      {...props}
      className="my-3 border-0 bg-gradient-to-r from-transparent via-border to-transparent"
      style={{ height: 1 }}
    />
  ),

  table: ({ node, children, ...props }) => (
    <div className="not-prose my-2 overflow-x-auto rounded-md border border-border">
      <table {...props} className="w-full border-collapse text-[12.5px]">
        {children}
      </table>
    </div>
  ),
  thead: ({ node, children, ...props }) => (
    <thead {...props} className="bg-card-muted">
      {children}
    </thead>
  ),
  th: ({ node, children, ...props }) => (
    <th
      {...props}
      className="border-b border-border px-3 py-1.5 text-left font-semibold text-foreground"
    >
      {children}
    </th>
  ),
  tr: ({ node, children, ...props }) => (
    <tr
      {...props}
      className="border-b border-border last:border-b-0 even:bg-muted/30"
    >
      {children}
    </tr>
  ),
  td: ({ node, children, ...props }) => (
    <td {...props} className="px-3 py-1.5 align-top text-foreground/90">
      {decorateCitations(children, 'td')}
    </td>
  ),

  img: ({ node, alt, src, ...props }) => (
    <img
      {...props}
      src={src}
      alt={alt || ''}
      loading="lazy"
      className="my-2 max-h-[480px] max-w-full rounded-md border border-border bg-card object-contain"
    />
  ),

  strong: ({ node, children, ...props }) => (
    <strong {...props} className="font-semibold text-foreground">
      {children}
    </strong>
  ),
  em: ({ node, children, ...props }) => (
    <em {...props} className="italic text-foreground/90">
      {children}
    </em>
  ),

  kbd: ({ node, children, ...props }) => (
    <kbd
      {...props}
      className="rounded border border-border bg-card px-1 py-[1px] font-mono text-[10.5px] text-foreground shadow-sm"
    >
      {children}
    </kbd>
  ),

  code: ({ node, className, children, ...props }) => {
    const text = String(children).replace(/\n$/, '')
    const match = /language-([\w-]+)/.exec(className || '')
    const isInline = !match && !text.includes('\n')
    if (isInline) {
      return (
        <code
          {...props}
          className="rounded bg-muted px-[5px] py-[1px] font-mono text-[12.5px] text-foreground"
        >
          {children}
        </code>
      )
    }

    return (
      <CodeBlock
        language={(match?.[1] || '').toLowerCase()}
        code={text}
      />
    )
  },

  pre: ({ children }) => <>{children}</>,
}

const _CITATION_BRACKETS_PATTERN =
  /(?<!\\)\[((?:PMID|DOI|case|NCT|REF)[\s:：][^\]\n]+?)\]/gi

const _GOV_CITATION_PATTERN = /\[(?:GOV|政策)[\s:：]*(https?:\/\/[^\]\s]+)\]/gi

function escapeCitationBrackets(text: string): string {
  if (!text) return text

  let out = text.replace(_GOV_CITATION_PATTERN, (_m, url: string) => {

    const enc = encodeURIComponent(url)
      .replace(/_/g, '%5F')
      .replace(/\*/g, '%2A')
      .replace(/~/g, '%7E')
    return `\\[GOVCITE:${enc}\\]`
  })

  out = out.replace(_CITATION_BRACKETS_PATTERN, '\\[$1\\]')
  return out
}

export default function MarkdownRenderer({ text, compact, className }: Props) {

  const value = useMemo(() => escapeCitationBrackets(text || ''), [text])

  return (
    <div
      className={cn(
        'markdown-body break-words text-foreground',
        compact ? 'text-[12.5px] leading-[1.6]' : 'text-[14px] leading-[1.65]',
        className,
      )}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {value}
      </ReactMarkdown>
    </div>
  )
}
