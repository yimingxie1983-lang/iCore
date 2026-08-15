import { useState } from 'react'

import type { ChatMessage } from '@/application/state/chatStore'
import ArtifactsDock from '@/ui/views/chat/ArtifactsDock'

const SAMPLE_MESSAGES: ChatMessage[] = [
  {
    id: 'u1',
    role: 'user',
    text: '分析这份表',
    createdAt: Date.now(),
    steps: [],
    attachments: [
      { name: 'cohort.csv', path: 'uploads/cohort.csv', size: 1024, kind: 'file' },
      { name: 'scan.png', path: 'uploads/scan.png', size: 2048, kind: 'image' },
    ],
  },
  {
    id: 'a1',
    role: 'assistant',
    text: '报告已生成',
    createdAt: Date.now(),
    steps: [],
    presentedFiles: [
      {
        kind: 'files',
        title: '交付',
        files: [
          {
            name: 'report.md',
            path: 'workspace/report.md',
            size: 4096,
            mime: 'text/markdown',
            render_kind: 'markdown',
          },
          {
            name: 'km-curve.png',
            path: 'workspace/km-curve.png',
            size: 8192,
            mime: 'image/png',
            render_kind: 'image',
          },
        ],
      },
    ],
  },
]

export default function ArtifactsDockPreview() {
  const [open, setOpen] = useState(true)
  return (
    <div className="relative h-screen bg-background">
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        对话主区
      </div>
      <ArtifactsDock
        projectId="preview"
        messages={SAMPLE_MESSAGES}
        open={open}
        onOpenChange={setOpen}
      />
    </div>
  )
}
