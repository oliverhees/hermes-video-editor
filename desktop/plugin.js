// Hermes Desktop page for hermes-video-editor: a sidebar entry that opens the local cut editor.
// The editor itself is a small web app served by the plugin on 127.0.0.1 and shown in a sandboxed frame.
//
// Namespace imports are used on purpose: a missing export then does not stop the module from loading, and
// register() can report exactly what is missing (shown as the plugin's error text in Capabilities -> Plugins).
import * as sdk from '@hermes/plugin-sdk'
import * as React from 'react'
import * as jsxRuntime from 'react/jsx-runtime'

const PATH = '/video-editor'
const ALLOWED_LINKS = ['https://lokyy.de', 'https://lokyy.de/']
const STANDALONE = 'python scripts/editor.py   (inside the hermes-video-editor folder)'

// jsx/jsxs: the React JSX runtime is the documented source; fall back to the SDK or plain createElement.
const h = (type, props) => {
  const { children, ...rest } = props || {}
  if (typeof jsxRuntime.jsx === 'function') return jsxRuntime.jsx(type, props || {})
  if (typeof sdk.jsx === 'function') return sdk.jsx(type, props || {})
  return React.createElement(type, rest, children)
}

// ---- theme: the editor runs in an isolated frame, so we read the app's colours here and pass them in -------------
function toHex(cssColor) {
  try {
    const canvas = document.createElement('canvas')
    canvas.width = canvas.height = 1
    const g = canvas.getContext('2d')
    g.clearRect(0, 0, 1, 1)
    g.fillStyle = cssColor
    g.fillRect(0, 0, 1, 1)
    const d = g.getImageData(0, 0, 1, 1).data
    if (d[3] < 200) return null
    return '#' + [d[0], d[1], d[2]].map(v => v.toString(16).padStart(2, '0')).join('')
  } catch (e) {
    return null
  }
}

function luminance(hex) {
  const v = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255)
  return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]
}

// "vivid" = a real accent colour, not white/black/grey
function isVivid(hex) {
  if (!hex) return false
  const v = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255)
  const max = Math.max(v[0], v[1], v[2])
  const min = Math.min(v[0], v[1], v[2])
  const light = (max + min) / 2
  const sat = max === min ? 0 : (max - min) / (1 - Math.abs(2 * light - 1))
  return sat >= 0.3 && light >= 0.15 && light <= 0.9
}

const ACCENT_NAME = /accent|primary|brand|ring|highlight|selection|link/i
const ACCENT_RANK = [/accent(?!-?fore)/i, /primary(?!-?fore)/i, /brand/i, /ring/i, /highlight|selection|link/i]

// names of CSS variables the app declares on :root / html / body / .dark ... that look like an accent colour
function accentVariableNames() {
  const names = []
  try {
    for (const sheet of Array.from(document.styleSheets || [])) {
      let rules
      try {
        rules = sheet.cssRules
      } catch (e) {
        continue
      }
      for (const rule of Array.from(rules || [])) {
        if (!rule.style || !/^(:root|html|body|:host|\.dark|\.light|\[data-theme)/i.test(rule.selectorText || '')) continue
        for (let i = 0; i < rule.style.length; i++) {
          const name = rule.style[i]
          if (name.indexOf('--') === 0 && ACCENT_NAME.test(name) && names.indexOf(name) < 0) names.push(name)
        }
      }
    }
  } catch (e) {
    return names
  }
  const rank = n => {
    const k = ACCENT_RANK.findIndex(re => re.test(n))
    return k < 0 ? 99 : k
  }
  return names.sort((a, b) => rank(a) - rank(b)).slice(0, 80)
}

// the app's accent: a vivid CSS variable first, then what the app actually paints (switches, selected items)
function findAccent() {
  try {
    const probe = document.createElement('span')
    document.body.appendChild(probe)
    let found = null
    for (const name of accentVariableNames()) {
      probe.style.color = 'var(' + name + ')'
      const hex = toHex(getComputedStyle(probe).color)
      if (isVivid(hex)) {
        found = hex
        break
      }
    }
    document.body.removeChild(probe)
    if (found) return found
    const painted = ['[role="switch"][aria-checked="true"]', '[data-state="checked"]', '[aria-selected="true"]', '[aria-current="page"]']
    for (const selector of painted) {
      const node = document.querySelector(selector)
      if (!node) continue
      const cs = getComputedStyle(node)
      for (const prop of [cs.backgroundColor, cs.color, cs.borderTopColor]) {
        const hex = toHex(prop)
        if (isVivid(hex)) return hex
      }
    }
  } catch (e) {
    return null
  }
  return null
}

function effectiveBackground(node) {
  for (let el = node; el; el = el.parentElement) {
    const hex = toHex(getComputedStyle(el).backgroundColor)
    if (hex) return hex
  }
  return toHex(getComputedStyle(document.body).backgroundColor) || '#ffffff'
}

function readTheme(node) {
  try {
    const bg = effectiveBackground(node || document.body)
    const fg = toHex(getComputedStyle(node || document.body).color) || (luminance(bg) > 0.5 ? '#1d2330' : '#e6eaf2')
    const out = { theme: luminance(bg) > 0.5 ? 'light' : 'dark', bg, fg }
    const accent = findAccent()
    if (accent) out.accent = accent
    return out
  } catch (e) {
    return {}
  }
}
function withTheme(url, theme) {
  const q = Object.keys(theme)
    .map(k => encodeURIComponent(k) + '=' + encodeURIComponent(theme[k]))
    .join('&')
  return q ? url + '&' + q : url
}

function EditorPage(props) {
  const ctx = props.ctx
  const SandboxedFrame = sdk.SandboxedFrame
  const [state, setState] = React.useState({ phase: 'loading' })
  const boxRef = React.useRef(null)
  const frameRef = React.useRef(null)

  const load = React.useCallback(() => {
    setState({ phase: 'loading' })
    ctx
      .rest('/start')
      .then(data => setState({ phase: 'ready', url: withTheme(data.url, readTheme(boxRef.current)) }))
      .catch(err => setState({ phase: 'error', message: String((err && err.message) || err) }))
  }, [ctx])

  React.useEffect(() => {
    load()
  }, [load])

  // the editor frame has no popup rights: it asks us to open its "Powered by" link (allow-listed addresses only)
  React.useEffect(() => {
    const onMessage = event => {
      const frame = frameRef.current
      const data = event && event.data
      if (!frame || event.source !== frame.contentWindow || !data || data.type !== 've-open-link') return
      if (ALLOWED_LINKS.indexOf(data.url) >= 0) window.open(data.url, '_blank', 'noopener,noreferrer')
    }
    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [])

  // follow theme changes while the page is open (no reload: the colours are posted into the frame)
  React.useEffect(() => {
    if (typeof MutationObserver !== 'function') return undefined
    let timer = null
    const push = () => {
      const win = frameRef.current && frameRef.current.contentWindow
      if (win) win.postMessage(Object.assign({ type: 've-theme' }, readTheme(boxRef.current)), '*')
    }
    const observer = new MutationObserver(() => {
      clearTimeout(timer)
      timer = setTimeout(push, 150)
    })
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'style', 'data-theme'] })
    return () => {
      clearTimeout(timer)
      observer.disconnect()
    }
  }, [])

  if (state.phase === 'ready') {
    return h('div', {
      ref: boxRef,
      className: 'flex h-full w-full flex-col',
      children: h(SandboxedFrame, {
        ref: frameRef,
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
  return h('div', { ref: boxRef, className: 'flex h-full flex-col items-center justify-center gap-3 p-6 text-center', children })
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
