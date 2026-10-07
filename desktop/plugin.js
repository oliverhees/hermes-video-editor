// Hermes Desktop page for hermes-video-editor: a sidebar entry that opens the local cut editor.
// The editor itself is a small web app served by the plugin on 127.0.0.1 and shown in a sandboxed frame.
//
// Namespace imports are used on purpose: a missing export then does not stop the module from loading, and
// register() can report exactly what is missing (shown as the plugin's error text in Capabilities -> Plugins).
import * as sdk from '@hermes/plugin-sdk'
import * as React from 'react'
import * as jsxRuntime from 'react/jsx-runtime'

const PATH = '/video-editor'
const STANDALONE = 'python scripts/editor.py   (inside the hermes-video-editor folder)'

// jsx/jsxs: the React JSX runtime is the documented source; fall back to the SDK or plain createElement.
const h = (type, props) => {
  const { children, ...rest } = props || {}
  if (typeof jsxRuntime.jsx === 'function') return jsxRuntime.jsx(type, props || {})
  if (typeof sdk.jsx === 'function') return sdk.jsx(type, props || {})
  return React.createElement(type, rest, children)
}

function EditorPage(props) {
  const ctx = props.ctx
  const SandboxedFrame = sdk.SandboxedFrame
  const [state, setState] = React.useState({ phase: 'loading' })

  const load = React.useCallback(() => {
    setState({ phase: 'loading' })
    ctx
      .rest('/start')
      .then(data => setState({ phase: 'ready', url: data.url }))
      .catch(err => setState({ phase: 'error', message: String((err && err.message) || err) }))
  }, [ctx])

  React.useEffect(() => {
    load()
  }, [load])

  if (state.phase === 'ready') {
    return h('div', {
      className: 'flex h-full w-full flex-col',
      children: h(SandboxedFrame, {
        src: state.url,
        title: 'Video Editor',
        sandbox: 'allow-scripts allow-forms allow-downloads',
        className: 'h-full w-full flex-1 border-0'
      })
    })
  }

  const text = state.phase === 'loading' ? 'Starting the video editor…' : 'The video editor could not start.'
  const children = [h('div', { key: 'title', className: 'text-base font-medium', children: text })]
  if (state.phase === 'error') {
    children.push(
      h('div', { key: 'msg', className: 'text-sm opacity-80', children: state.message }),
      h('div', {
        key: 'help',
        className: 'text-sm opacity-80',
        children:
          'Check that the plugin is enabled (hermes plugins list) and restart Hermes. ' +
          'You can also run the editor on its own and open the printed link in a browser: ' +
          STANDALONE
      }),
      h('button', { key: 'retry', className: 'rounded border px-3 py-1 text-sm', onClick: load, children: 'Try again' })
    )
  }
  return h('div', { className: 'flex h-full flex-col items-center justify-center gap-3 p-6 text-center', children })
}

export default {
  id: 'hermes-video-editor',
  name: 'Video Editor',
  defaultEnabled: true,
  register(ctx) {
    const missing = ['ROUTES_AREA', 'SIDEBAR_NAV_AREA', 'SandboxedFrame'].filter(name => sdk[name] == null)
    if (missing.length) {
      throw new Error(
        'This Hermes Desktop version does not provide: ' + missing.join(', ') +
          '. Exports available: ' + Object.keys(sdk).slice(0, 60).join(', ')
      )
    }
    ctx.registerMany([
      {
        id: 'page',
        area: sdk.ROUTES_AREA,
        data: { path: PATH },
        render: () => h(EditorPage, { ctx })
      },
      {
        id: 'nav',
        area: sdk.SIDEBAR_NAV_AREA,
        data: { path: PATH, label: 'Video Editor', codicon: 'device-camera-video' }
      }
    ])
  }
}
