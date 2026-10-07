// Hermes Desktop page for hermes-video-editor: a sidebar entry that opens the local cut editor.
// The editor itself is a small web app served by the plugin on 127.0.0.1 and shown in a sandboxed frame.
import { ROUTES_AREA, SIDEBAR_NAV_AREA, SandboxedFrame, jsx, jsxs } from '@hermes/plugin-sdk'
import { useCallback, useEffect, useState } from 'react'

const PATH = '/video-editor'
const STANDALONE = 'python scripts/editor.py   (inside the hermes-video-editor folder)'

function EditorPage(props) {
  const ctx = props.ctx
  const [state, setState] = useState({ phase: 'loading' })

  const load = useCallback(() => {
    setState({ phase: 'loading' })
    ctx
      .rest('/start')
      .then(data => setState({ phase: 'ready', url: data.url }))
      .catch(err => setState({ phase: 'error', message: String((err && err.message) || err) }))
  }, [ctx])

  useEffect(() => {
    load()
  }, [load])

  if (state.phase === 'ready') {
    return jsxs('div', {
      className: 'flex h-full w-full flex-col',
      children: [
        jsx(SandboxedFrame, {
          src: state.url,
          title: 'Video Editor',
          sandbox: 'allow-scripts allow-forms allow-downloads',
          className: 'h-full w-full flex-1 border-0'
        })
      ]
    })
  }

  const text = state.phase === 'loading' ? 'Starting the video editor…' : 'The video editor could not start.'
  const children = [jsx('div', { className: 'text-base font-medium', children: text })]
  if (state.phase === 'error') {
    children.push(
      jsx('div', { className: 'text-sm opacity-80', children: state.message }),
      jsxs('div', {
        className: 'text-sm opacity-80',
        children: [
          'Check that the plugin is enabled (hermes plugins list) and restart Hermes. ',
          'You can also run the editor on its own and open the printed link in a browser: ',
          STANDALONE
        ]
      }),
      jsx('button', {
        className: 'rounded border px-3 py-1 text-sm',
        onClick: load,
        children: 'Try again'
      })
    )
  }
  return jsx('div', { className: 'flex h-full flex-col items-center justify-center gap-3 p-6 text-center', children })
}

export default {
  id: 'hermes-video-editor',
  name: 'Video Editor',
  defaultEnabled: true,
  register(ctx) {
    ctx.registerMany([
      {
        id: 'page',
        area: ROUTES_AREA,
        data: { path: PATH },
        render: () => jsx(EditorPage, { ctx })
      },
      {
        id: 'nav',
        area: SIDEBAR_NAV_AREA,
        data: { path: PATH, label: 'Video Editor', codicon: 'device-camera-video' }
      }
    ])
  }
}
