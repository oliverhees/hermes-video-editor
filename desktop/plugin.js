// Hermes Desktop page for hermes-video-editor: a sidebar entry that opens the local cut editor.
// The editor itself is a small web app served by the plugin on 127.0.0.1 and shown in a sandboxed frame.
//
// Namespace imports are used on purpose: a missing export then does not stop the module from loading, and
// register() can report exactly what is missing (shown as the plugin's error text in Capabilities -> Plugins).
import * as sdk from '@hermes/plugin-sdk'
import * as React from 'react'
import * as jsxRuntime from 'react/jsx-runtime'

const PATH = '/video-editor'
const PLUGIN_ID = 'hermes-video-editor'
const SETTINGS_KEY = 'settings'
const POLL_MS = 4000
const DEFAULT_SETTINGS = {
  autoOpen: true, // open the editor page by itself when the agent hands a video over
  focus: true, // ... and bring it to the front
  whatsNew: true, // show the changelog the first time after an update
  magnet: true, // items snap to the playhead and to each other
  aspect: 'auto',
  short: 1080,
  bg: 'blur',
  captionLang: '',
  captionModel: 'base'
}
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

// Standard theme variable names (shadcn / Tailwind style). They are read through getComputedStyle on this page's own
// container, where they are inherited: no scanning of the app's style sheets and no lookups of the app's elements.
const ACCENT_VARIABLES = ['--primary', '--color-primary', '--brand', '--color-brand', '--accent-color', '--ring', '--color-ring', '--highlight', '--link', '--accent', '--color-accent']

// the app's accent: the first of those variables that holds a vivid colour (pale greys of "accent" surfaces are skipped)
function findAccent(node) {
  try {
    const host = node || document.body
    const probe = document.createElement('span')
    host.appendChild(probe)
    let found = null
    for (const name of ACCENT_VARIABLES) {
      probe.style.color = 'var(' + name + ')'
      const hex = toHex(getComputedStyle(probe).color)
      if (isVivid(hex)) {
        found = hex
        break
      }
    }
    host.removeChild(probe)
    return found
  } catch (e) {
    return null
  }
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
    const accent = findAccent(node)
    if (accent) out.accent = accent
    return out
  } catch (e) {
    return {}
  }
}
// ---- settings (Settings > Plugins > Video Editor): kept with ctx.storage, handed to the editor as one JSON value --------
function loadSettings(ctx) {
  try {
    const saved = ctx && ctx.storage ? ctx.storage.get(SETTINGS_KEY, {}) : {}
    return Object.assign({}, DEFAULT_SETTINGS, saved && typeof saved === 'object' ? saved : {})
  } catch (e) {
    return Object.assign({}, DEFAULT_SETTINGS)
  }
}
function saveSettings(ctx, next) {
  try {
    ctx.storage.set(SETTINGS_KEY, next)
  } catch (e) {
    /* storage unavailable: the page keeps the value until it is closed */
  }
  try {
    window.dispatchEvent(new CustomEvent('ve-settings-changed'))
  } catch (e) {
    /* no window events */
  }
}
function withSettings(url, settings) {
  return url + '&cfg=' + encodeURIComponent(JSON.stringify(settings))
}

// ---- hand-over from the agent: lk_open_in_editor queues files, we pick them up and show them in the editor --------------
const handover = { frame: null, queue: [], timer: null, failures: 0 }

function postToFrame(message) {
  const win = handover.frame && handover.frame.contentWindow
  if (win) win.postMessage(message, '*')
  return !!win
}
function flushQueue() {
  if (!handover.queue.length || !handover.frame) return
  const items = handover.queue.splice(0, handover.queue.length)
  if (!postToFrame({ type: 've-open', items })) handover.queue = items.concat(handover.queue)
}
function goToEditor(ctx) {
  const host = sdk.host || ctx.host
  try {
    if (host && typeof host.navigate === 'function') host.navigate(PATH)
    else window.location.hash = '#' + PATH
  } catch (e) {
    /* the user can open the page from the sidebar */
  }
}
function startHandover(ctx) {
  if (handover.timer || typeof setInterval !== 'function' || typeof ctx.rest !== 'function') return
  const poll = () => {
    ctx
      .rest('/pending')
      .then(data => {
        handover.failures = 0
        const items = (data && data.items) || []
        if (!items.length) return
        const settings = loadSettings(ctx)
        handover.queue = handover.queue.concat(items.map(i => ({ path: i.path, kind: i.kind })))
        if (settings.autoOpen && settings.focus && items.some(i => i.focus !== false)) goToEditor(ctx)
        flushQueue()
      })
      .catch(() => {
        handover.failures += 1
        if (handover.failures >= 5) {
          clearInterval(handover.timer) // the plugin route is not there (plugin disabled?): stop asking
          handover.timer = null
        }
      })
  }
  handover.timer = setInterval(poll, POLL_MS)
  if (handover.timer && typeof handover.timer.unref === 'function') handover.timer.unref() // never keeps a script alive (tests, tools)
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
      .then(data => setState({ phase: 'ready', url: withSettings(withTheme(data.url, readTheme(boxRef.current)), loadSettings(ctx)) }))
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
      if (!frame || event.source !== frame.contentWindow || !data) return
      if (data.type === 've-ready') {
        handover.frame = frame
        flushQueue()
      } else if (data.type === 've-open-link' && ALLOWED_LINKS.indexOf(data.url) >= 0) window.open(data.url, '_blank', 'noopener,noreferrer')
    }
    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [])

  // the settings page changed something while the editor is open: post the new values into the frame
  React.useEffect(() => {
    const push = () => postToFrame({ type: 've-settings', cfg: loadSettings(ctx) })
    window.addEventListener('ve-settings-changed', push)
    return () => {
      window.removeEventListener('ve-settings-changed', push)
      if (handover.frame === frameRef.current) handover.frame = null
    }
  }, [ctx])

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

// ---- the settings page ---------------------------------------------------------------------------------------------------
// Plain elements on purpose: they inherit the app's colours and cannot break when a settings component changes its props.
const row = { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '16px', padding: '10px 0', borderBottom: '1px solid rgba(128,128,128,.25)' }
const ctl = { minWidth: '140px', padding: '4px 6px', borderRadius: '6px', border: '1px solid rgba(128,128,128,.5)', background: 'transparent', color: 'inherit' }

function SettingsRow(props) {
  return h('div', {
    style: row,
    children: [
      h('div', {
        key: 'text',
        children: [
          h('div', { key: 't', style: { fontWeight: 500 }, children: props.title }),
          props.hint ? h('div', { key: 'h', style: { fontSize: '12px', opacity: 0.7, maxWidth: '520px' }, children: props.hint }) : null
        ]
      }),
      h('div', { key: 'ctl', children: props.children })
    ]
  })
}

function useSetting(ctx) {
  const [settings, setSettings] = React.useState(loadSettings(ctx))
  const set = (key, value) => {
    const next = Object.assign({}, loadSettings(ctx), { [key]: value }) // always on top of what is saved, never a stale copy
    setSettings(next)
    saveSettings(ctx, next)
  }
  return [settings, set]
}

function Toggle(props) {
  return h('input', { type: 'checkbox', checked: !!props.value, onChange: e => props.onChange(!!e.target.checked), style: { width: '18px', height: '18px' } })
}
function Choice(props) {
  return h('select', {
    value: String(props.value),
    onChange: e => props.onChange(props.number ? Number(e.target.value) : e.target.value),
    style: ctl,
    children: props.options.map(o => h('option', { key: o[0], value: String(o[0]), children: o[1] }))
  })
}
function Page(props) {
  return h('div', {
    style: { display: 'flex', flexDirection: 'column', padding: '4px 2px', maxWidth: '760px' },
    children: [h('div', { key: 'lead', style: { fontSize: '13px', opacity: 0.75, padding: '2px 0 8px' }, children: props.lead })].concat(props.children)
  })
}

function GeneralSettings(props) {
  const [s, set] = useSetting(props.ctx)
  return h(Page, {
    lead: 'How Hermes and the Video Editor work together. Changes apply at once.',
    children: [
      h(SettingsRow, { key: 'a', title: 'Open videos made by Hermes in the editor', hint: 'When the agent hands a finished video over (tool lk_open_in_editor), the editor loads it. Off: you get a note in the editor instead.', children: h(Toggle, { value: s.autoOpen, onChange: v => set('autoOpen', v) }) }),
      h(SettingsRow, { key: 'b', title: 'Bring the editor page to the front', hint: 'Switches to the Video Editor page when something arrives.', children: h(Toggle, { value: s.focus, onChange: v => set('focus', v) }) }),
      h(SettingsRow, { key: 'c', title: 'Show what is new after an update', hint: 'The changelog opens by itself the first time after an update. You can always open it with What\'s new.', children: h(Toggle, { value: s.whatsNew, onChange: v => set('whatsNew', v) }) })
    ]
  })
}

function ProjectSettings(props) {
  const [s, set] = useSetting(props.ctx)
  return h(Page, {
    lead: 'Defaults for a new, empty project. Saved projects keep their own values.',
    children: [
      h(SettingsRow, { key: 'a', title: 'Magnet', hint: 'Items you drag snap to the playhead and to the edges of other items.', children: h(Toggle, { value: s.magnet, onChange: v => set('magnet', v) }) }),
      h(SettingsRow, { key: 'b', title: 'Canvas shape', children: h(Choice, { value: s.aspect, onChange: v => set('aspect', v), options: [['auto', 'Auto (first clip)'], ['16:9', '16:9 landscape'], ['9:16', '9:16 Reels / TikTok / Shorts'], ['1:1', '1:1 square'], ['4:5', '4:5 feed']] }) }),
      h(SettingsRow, { key: 'c', title: 'Resolution (short side)', children: h(Choice, { number: true, value: s.short, onChange: v => set('short', v), options: [[360, '360'], [480, '480'], [720, '720'], [1080, '1080'], [1440, '1440'], [2160, '2160']] }) }),
      h(SettingsRow, { key: 'd', title: 'Background', hint: 'Behind pictures that do not fill the canvas.', children: h(Choice, { value: s.bg, onChange: v => set('bg', v), options: [['blur', 'Blurred picture'], ['black', 'Black'], ['color', 'One colour'], ['gradient', 'Gradient']] }) })
    ]
  })
}

function SubtitleSettings(props) {
  const [s, set] = useSetting(props.ctx)
  return h(Page, {
    lead: 'Automatic subtitles use the optional local package faster-whisper and a speech model that is already on this computer. Nothing is downloaded or uploaded.',
    children: [
      h(SettingsRow, { key: 'a', title: 'Spoken language', children: h(Choice, { value: s.captionLang, onChange: v => set('captionLang', v), options: [['', 'Detect'], ['de', 'Deutsch'], ['en', 'English'], ['fr', 'Fran\u00e7ais'], ['es', 'Espa\u00f1ol'], ['it', 'Italiano'], ['pt', 'Portugu\u00eas'], ['nl', 'Nederlands'], ['pl', 'Polski'], ['tr', 'T\u00fcrk\u00e7e'], ['ru', '\u0420\u0443\u0441\u0441\u043a\u0438\u0439']] }) }),
      h(SettingsRow, { key: 'b', title: 'Model size', hint: 'Bigger is more accurate and slower.', children: h(Choice, { value: s.captionModel, onChange: v => set('captionModel', v), options: [['tiny', 'tiny (fast)'], ['base', 'base'], ['small', 'small'], ['medium', 'medium'], ['large-v3', 'large-v3']] }) })
    ]
  })
}

function AboutSettings(props) {
  const open = url => {
    try {
      if (props.ctx.os && typeof props.ctx.os.openExternal === 'function') props.ctx.os.openExternal(url)
      else window.open(url, '_blank', 'noopener,noreferrer')
    } catch (e) {
      /* ignore */
    }
  }
  const link = (key, text, url) => h('button', { key, onClick: () => open(url), style: Object.assign({}, ctl, { cursor: 'pointer', textAlign: 'left' }), children: text })
  return h(Page, {
    lead: 'Hermes Video Editor, powered by Lokyy.de (German Hermes Engineering). 100% local, no API key. Licence: PolyForm Noncommercial 1.0.0.',
    children: [
      h('div', { key: 'links', style: { display: 'flex', gap: '8px', flexWrap: 'wrap', paddingTop: '8px' }, children: [link('p', 'Official plugin page', 'https://lokyy.de/hermes-video-editor/'), link('g', 'Source and guide', 'https://github.com/oliverhees/hermes-video-editor')] })
    ]
  })
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
    startHandover(ctx)
    if (typeof ctx.registerSettingsPage === 'function') {
      // newer Hermes Desktop: own entry under Settings > Plugins; older versions simply do not have it
      ctx.registerSettingsPage({
        id: 'settings',
        title: 'Video Editor',
        icon: 'device-camera-video',
        order: 40,
        render: () => h(GeneralSettings, { ctx }),
        children: [
          { id: 'project', title: 'New projects', render: () => h(ProjectSettings, { ctx }) },
          { id: 'subtitles', title: 'Subtitles', render: () => h(SubtitleSettings, { ctx }) },
          { id: 'about', title: 'About', render: () => h(AboutSettings, { ctx }) }
        ]
      })
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
