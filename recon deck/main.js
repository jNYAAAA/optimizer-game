'use strict';

const { app, BrowserWindow, WebContentsView, ipcMain, shell, session, Menu, clipboard, dialog, net, protocol } = require('electron');
const path = require('node:path');
const fs = require('node:fs');
const crypto = require('node:crypto');
const nodeNet = require('node:net');
const { spawn } = require('node:child_process');

const APP_DIR = __dirname;
const PARTITION = 'persist:recon-deck';
const IS_DEV = process.argv.includes('--dev');
const SHOT_ARG = process.argv.find((a) => a.startsWith('--shot'));
const SHOT_TAB = process.argv.includes('--shot-tab');
const SHOT_UI = process.argv.includes('--shot-ui');
const SHOT_NET = process.argv.includes('--shot-net');
const SHOT_TOR = process.argv.includes('--shot-tor');
const SHOT_DARK = process.argv.includes('--shot-dark');
const SHOT_TOR_VPN = process.argv.includes('--shot-tor-vpn');

const HOME_URL = 'https://example.com';

protocol.registerSchemesAsPrivileged([
  {
    scheme: 'recon',
    privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true },
  },
]);

let mainWindow = null;
let appSession = null;
let activeTabId = null;
let viewBounds = { x: 0, y: 0, width: 0, height: 0 };

/** @type {Map<string, {id:string, view:WebContentsView, title:string, displayUrl:string, favicon:string, loading:boolean, canGoBack:boolean, canGoForward:boolean, errorUrl:string|null}>} */
const tabs = new Map();

const CHROME_UA = (() => {
  const platform =
    process.platform === 'win32'
      ? 'Windows NT 10.0; Win64; x64'
      : process.platform === 'darwin'
        ? 'Macintosh; Intel Mac OS X 10_15_7'
        : 'X11; Linux x86_64';
  return `Mozilla/5.0 (${platform}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/${process.versions.chrome} Safari/537.36`;
})();

/* ---------------------------------------------------------------- utils */

function stateFile() {
  return path.join(app.getPath('userData'), 'window-state.json');
}

function loadWindowState() {
  try {
    const raw = JSON.parse(fs.readFileSync(stateFile(), 'utf8'));
    if (!raw || typeof raw !== 'object') return null;
    return raw;
  } catch {
    return null;
  }
}

function saveWindowState() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  try {
    const maximized = mainWindow.isMaximized();
    const b = maximized ? mainWindow.getNormalBounds() : mainWindow.getBounds();
    fs.writeFileSync(stateFile(), JSON.stringify({ ...b, maximized }, null, 2));
  } catch {
    /* ignore */
  }
}

function hostOf(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

function toast(text, kind = 'info') {
  send('app:toast', { text, kind, at: Date.now() });
}

function send(channel, payload) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send(channel, payload);
  }
}

function normalizeUrl(input) {
  const value = String(input || '').trim();
  if (!value) return null;
  if (/^https?:\/\//i.test(value)) return value;
  if (/^recon:\/\//i.test(value)) return value;
  if (/^(about|data|file):/i.test(value)) return null;
  if (/^[\w-]+(\.[\w-]+)+(\/.*)?$/.test(value) || /^localhost(:\d+)?(\/.*)?$/i.test(value)) {
    return 'https://' + value;
  }
  return 'https://www.google.com/search?q=' + encodeURIComponent(value);
}

function handleReconProtocol(request) {
  try {
    const requestUrl = new URL(request.url);
    if (requestUrl.hostname === 'start') {
      const html = fs.readFileSync(path.join(APP_DIR, 'src', 'tor-start.html'), 'utf8');
      return new Response(html, {
        headers: { 'content-type': 'text/html; charset=utf-8' },
      });
    }
  } catch {
    /* ignore */
  }
  return new Response('Not found', {
    status: 404,
    headers: { 'content-type': 'text/plain; charset=utf-8' },
  });
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/* --------------------------------------------------------------- tabs */

function tabState(tab) {
  return {
    id: tab.id,
    title: tab.title || hostOf(tab.displayUrl) || 'Новая вкладка',
    url: tab.displayUrl,
    favicon: tab.favicon || '',
    loading: tab.loading,
    canGoBack: tab.canGoBack,
    canGoForward: tab.canGoForward,
    secure: /^https:/i.test(tab.displayUrl),
  };
}

function broadcast() {
  send('tabs:state', {
    tabs: [...tabs.values()].map(tabState),
    activeId: activeTabId,
  });
}

function applyBounds(view) {
  if (!view) return;
  if (viewBounds.width > 0 && viewBounds.height > 0) {
    view.setBounds({
      x: Math.round(viewBounds.x),
      y: Math.round(viewBounds.y),
      width: Math.round(viewBounds.width),
      height: Math.round(viewBounds.height),
    });
  }
}

function refreshNav(tab) {
  try {
    tab.canGoBack = tab.view.webContents.navigationHistory.canGoBack();
    tab.canGoForward = tab.view.webContents.navigationHistory.canGoForward();
  } catch {
    tab.canGoBack = false;
    tab.canGoForward = false;
  }
}

function setActiveTab(id) {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  for (const [tid, tab] of tabs) {
    if (tid === id) {
      try {
        mainWindow.contentView.removeChildView(tab.view);
      } catch {
        /* not attached */
      }
      mainWindow.contentView.addChildView(tab.view);
      applyBounds(tab.view);
    } else {
      try {
        mainWindow.contentView.removeChildView(tab.view);
      } catch {
        /* not attached */
      }
    }
  }
  activeTabId = id;
  broadcast();
  if (id && tabs.has(id)) {
    tabs.get(id).view.webContents.focus();
  } else if (mainWindow) {
    mainWindow.webContents.focus();
  }
}

function createTab(url, { activate = true } = {}) {
  if (!mainWindow || mainWindow.isDestroyed()) return null;
  const normalized = normalizeUrl(url);
  if (!normalized) return null;

  const id = 'tab_' + crypto.randomUUID();
  const view = new WebContentsView({
    webPreferences: {
      partition: PARTITION,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      spellcheck: false,
      userAgent: CHROME_UA,
      autoplayPolicy: 'user-gesture-required',
    },
  });
  view.setBackgroundColor('#0a0d15');

  const tab = {
    id,
    view,
    title: 'Загрузка…',
    displayUrl: normalized,
    favicon: '',
    loading: true,
    canGoBack: false,
    canGoForward: false,
    errorUrl: null,
  };

  tabs.set(id, tab);
  wireTab(tab);

  mainWindow.contentView.addChildView(view);
  applyBounds(view);
  if (activate) {
    activeTabId = id;
    broadcast();
  }

  view.webContents.loadURL(normalized).catch(() => {});
  return id;
}

function wireTab(tab) {
  const wc = tab.view.webContents;

  const update = () => broadcast();

  wc.on('page-title-updated', (_event, title) => {
    if (title) tab.title = title;
    update();
  });

  wc.on('page-favicon-updated', (_event, icons) => {
    if (Array.isArray(icons) && icons.length) {
      tab.favicon = icons[0];
      update();
    }
  });

  wc.on('did-start-loading', () => {
    tab.loading = true;
    refreshNav(tab);
    update();
  });

  wc.on('did-stop-loading', () => {
    tab.loading = false;
    refreshNav(tab);
    update();
  });

  wc.on('did-navigate', (_event, url, httpResponseCode, httpStatusText) => {
    if (!url.startsWith('data:')) {
      tab.displayUrl = url.startsWith('recon://start') ? 'recon://start' : url;
      tab.errorUrl = null;
    }
    if (!tab.title || tab.title === 'Загрузка…') tab.title = hostOf(tab.displayUrl);
    tab.loading = false;
    refreshNav(tab);
    update();
    if (IS_DEV) console.log('[tab] navigate', httpResponseCode, httpStatusText, url);
  });

  wc.on('did-navigate-in-page', (_event, url, isMainFrame) => {
    if (!isMainFrame) return;
    tab.displayUrl = url.startsWith('recon://start') ? 'recon://start' : url;
    refreshNav(tab);
    update();
  });

  wc.on('did-fail-load', (_event, code, description, failedUrl, isMainFrame) => {
    if (!isMainFrame || code === -3) return;
    showErrorPage(tab, failedUrl || tab.displayUrl, code, description);
  });

  wc.on('render-process-gone', () => {
    tab.title = 'Страница упала';
    tab.loading = false;
    update();
  });

  wc.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//i.test(url)) {
      createTab(url);
    } else if (url && url !== 'about:blank') {
      shell.openExternal(url).catch(() => {});
    }
    return { action: 'deny' };
  });

  wc.on('context-menu', (_event, params) => openContextMenu(tab, params));

  wc.on('before-input-event', (event, input) => {
    if (input.type !== 'keyDown') return;
    const ctrl = input.control || input.meta;
    const key = String(input.key || '').toLowerCase();

    if (ctrl && input.shift && key === 'i') {
      event.preventDefault();
      wc.openDevTools({ mode: 'detach' });
      return;
    }
    if (ctrl && key === 'w') {
      event.preventDefault();
      closeTab(tab.id);
      return;
    }
    if (ctrl && key === 't') {
      event.preventDefault();
      mainWindow.webContents.focus();
      send('app:new-tab');
      return;
    }
    if (ctrl && key === 'l') {
      event.preventDefault();
      mainWindow.webContents.focus();
      send('app:focus-address');
      return;
    }
    if (ctrl && key === 'k') {
      event.preventDefault();
      mainWindow.webContents.focus();
      send('app:focus-search');
      return;
    }
    if (ctrl && (key === 'r' || input.key === 'F5')) {
      event.preventDefault();
      reloadTab(tab);
      return;
    }
    if (ctrl && key === 'd') {
      event.preventDefault();
      send('app:toggle-favorite', { url: tab.displayUrl, title: tab.title });
      return;
    }
    if (input.key === 'F5') {
      event.preventDefault();
      reloadTab(tab);
      return;
    }
    if (input.key === 'F11') {
      event.preventDefault();
      if (mainWindow) mainWindow.setFullScreen(!mainWindow.isFullScreen());
      return;
    }
    if (input.alt && key === 'arrowleft') {
      event.preventDefault();
      goBack(tab);
      return;
    }
    if (input.alt && key === 'arrowright') {
      event.preventDefault();
      goForward(tab);
      return;
    }
  });
}

function showErrorPage(tab, url, code, description) {
  tab.errorUrl = url;
  tab.displayUrl = url;
  tab.title = 'Не удалось открыть';
  tab.loading = false;
  const html = `<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>Ошибка загрузки</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin:0; min-height:100vh; display:grid; place-items:center; background:#0a0d15; color:#e7ecf7;
         font:15px/1.6 "Segoe UI", system-ui, sans-serif; padding:40px; }
  .card { max-width:560px; width:100%; background:linear-gradient(160deg,#111726,#0c111c); border:1px solid #232b3d;
          border-radius:18px; padding:34px 36px; box-shadow:0 30px 80px rgba(0,0,0,.45); }
  .kicker { font-size:11px; letter-spacing:.18em; text-transform:uppercase; color:#5eead4; margin-bottom:12px; }
  h1 { font-size:24px; margin:0 0 10px; }
  p { color:#98a4bd; margin:0 0 8px; }
  .url { font-family:"Cascadia Code",Consolas,monospace; font-size:12px; color:#c7d2e5; background:#0b1019;
         border:1px solid #1f2738; border-radius:9px; padding:10px 12px; word-break:break-all; margin:16px 0; }
  .code { color:#f472b6; font-family:Consolas,monospace; font-size:12px; }
  a { display:inline-block; margin-top:18px; padding:10px 18px; border-radius:10px; text-decoration:none;
      color:#051016; font-weight:600; background:linear-gradient(135deg,#5eead4,#38bdf8); }
  a:hover { filter:brightness(1.08); }
</style></head>
<body><div class="card">
  <div class="kicker">RECON DECK · СЕТЕВАЯ ОШИБКА</div>
  <h1>Страница не открылась</h1>
  <p>Сайт недоступен, блокирует соединение или адрес указан неверно.</p>
  <div class="url">${escapeHtml(url)}</div>
  <p class="code">${escapeHtml(String(code))} · ${escapeHtml(description || 'unknown error')}</p>
  <a href="${escapeHtml(url)}">Повторить</a>
</div></body></html>`;
  tab.view.webContents
    .loadURL('data:text/html;charset=UTF-8,' + encodeURIComponent(html))
    .catch(() => {});
}

function closeTab(id) {
  const tab = tabs.get(id);
  if (!tab) return;
  const wasActive = activeTabId === id;
  try {
    mainWindow.contentView.removeChildView(tab.view);
  } catch {
    /* ignore */
  }
  try {
    tab.view.webContents.close();
  } catch {
    /* ignore */
  }
  tabs.delete(id);

  if (wasActive) {
    const nextId = [...tabs.keys()].pop() || null;
    activeTabId = nextId;
    if (nextId) {
      setActiveTab(nextId);
    } else {
      mainWindow.webContents.focus();
      broadcast();
    }
  } else {
    broadcast();
  }
}

function reloadTab(tab) {
  const wc = tab.view.webContents;
  if (tab.errorUrl && wc.getURL().startsWith('data:')) {
    wc.loadURL(tab.errorUrl).catch(() => {});
  } else {
    wc.reload();
  }
}

function goBack(tab) {
  try {
    tab.view.webContents.navigationHistory.goBack();
  } catch {
    /* ignore */
  }
}

function goForward(tab) {
  try {
    tab.view.webContents.navigationHistory.goForward();
  } catch {
    /* ignore */
  }
}

function openContextMenu(tab, params) {
  const wc = tab.view.webContents;
  const template = [];

  if (params.linkURL) {
    template.push(
      { label: 'Открыть ссылку в новой вкладке', click: () => createTab(params.linkURL) },
      { label: 'Копировать ссылку', click: () => clipboard.writeText(params.linkURL) },
      { type: 'separator' }
    );
  }

  if (params.selectionText) {
    const snippet = params.selectionText.length > 28 ? params.selectionText.slice(0, 28) + '…' : params.selectionText;
    template.push(
      { label: 'Копировать', role: 'copy' },
      {
        label: `Искать «${snippet}»`,
        click: () => createTab('https://www.google.com/search?q=' + encodeURIComponent(params.selectionText)),
      },
      { type: 'separator' }
    );
  }

  if (params.isEditable) {
    template.push(
      { label: 'Отменить', role: 'undo' },
      { label: 'Повторить', role: 'redo' },
      { type: 'separator' },
      { label: 'Вырезать', role: 'cut' },
      { label: 'Копировать', role: 'copy' },
      { label: 'Вставить', role: 'paste' },
      { label: 'Выделить всё', role: 'selectAll' },
      { type: 'separator' }
    );
  }

  template.push(
    { label: 'Назад', enabled: tab.canGoBack, click: () => goBack(tab) },
    { label: 'Вперёд', enabled: tab.canGoForward, click: () => goForward(tab) },
    { label: 'Обновить', click: () => reloadTab(tab) },
    { type: 'separator' },
    { label: 'Копировать адрес', click: () => clipboard.writeText(tab.displayUrl) },
    { label: 'Открыть в системном браузере', click: () => shell.openExternal(tab.displayUrl).catch(() => {}) },
    { type: 'separator' },
    { label: 'Инспектировать элемент', click: () => wc.inspectElement(params.x, params.y) }
  );

  Menu.buildFromTemplate(template).popup({ window: mainWindow });
}

/* -------------------------------------------------------------- window */

function createWindow() {
  const saved = loadWindowState();
  const bounds = saved
    ? {
        width: Math.max(1080, Math.min(saved.width || 1460, 3840)),
        height: Math.max(680, Math.min(saved.height || 920, 2160)),
        x: saved.x,
        y: saved.y,
      }
    : { width: 1460, height: 920 };

  mainWindow = new BrowserWindow({
    ...bounds,
    minWidth: 1080,
    minHeight: 680,
    frame: false,
    thickFrame: true,
    resizable: true,
    maximizable: true,
    show: false,
    backgroundColor: '#070a11',
    title: 'Recon Deck',
    icon: path.join(APP_DIR, 'assets', 'icon.png'),
    webPreferences: {
      preload: path.join(APP_DIR, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      spellcheck: false,
      backgroundThrottling: false,
    },
  });

  mainWindow.setMenuBarVisibility(false);
  mainWindow.loadFile(path.join(APP_DIR, 'src', 'index.html'));

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    send('window:state', { maximized: mainWindow.isMaximized(), fullScreen: mainWindow.isFullScreen() });
  });

  mainWindow.webContents.on('did-finish-load', () => {
    send('window:state', {
      maximized: mainWindow.isMaximized(),
      fullScreen: mainWindow.isFullScreen(),
    });
  });

  mainWindow.on('maximize', () => send('window:state', { maximized: true, fullScreen: mainWindow.isFullScreen() }));
  mainWindow.on('unmaximize', () => send('window:state', { maximized: false, fullScreen: mainWindow.isFullScreen() }));
  mainWindow.on('enter-full-screen', () => send('window:state', { maximized: mainWindow.isMaximized(), fullScreen: true }));
  mainWindow.on('leave-full-screen', () => send('window:state', { maximized: mainWindow.isMaximized(), fullScreen: false }));
  mainWindow.on('resize', () => {
    if (activeTabId && tabs.has(activeTabId)) applyBounds(tabs.get(activeTabId).view);
  });
  mainWindow.on('close', saveWindowState);
  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  mainWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  mainWindow.webContents.on('will-navigate', (event, url) => {
    if (!/^file:/i.test(url)) event.preventDefault();
  });

  if (SHOT_ARG) runScreenshotHarness();
}

/* ---------------------------------------------------------------- ipc */

ipcMain.handle('tab:open', (_event, url) => {
  const normalized = normalizeUrl(url);
  if (!normalized) return null;
  const isStart = normalized.startsWith('recon://start');
  const existing = [...tabs.values()].find(
    (tab) =>
      tab.displayUrl === normalized ||
      tab.errorUrl === normalized ||
      (isStart && tab.displayUrl === 'recon://start')
  );
  if (existing) {
    if (isStart) {
      existing.view.webContents.loadURL(normalized).catch(() => {});
    }
    setActiveTab(existing.id);
    return existing.id;
  }
  return createTab(normalized);
});

ipcMain.on('tab:close', (_event, id) => closeTab(id));

ipcMain.on('tab:activate', (_event, id) => {
  if (tabs.has(id)) setActiveTab(id);
});

ipcMain.on('tab:deactivate', () => {
  setActiveTab(null);
});

ipcMain.on('tab:action', (_event, payload) => {
  const { id, action, value } = payload || {};
  const tab = tabs.get(id);
  if (!tab) return;
  const wc = tab.view.webContents;

  switch (action) {
    case 'back':
      goBack(tab);
      break;
    case 'forward':
      goForward(tab);
      break;
    case 'reload':
      reloadTab(tab);
      break;
    case 'stop':
      wc.stop();
      break;
    case 'navigate': {
      const normalized = normalizeUrl(value);
      if (normalized) wc.loadURL(normalized).catch(() => {});
      break;
    }
    case 'devtools':
      wc.openDevTools({ mode: 'detach' });
      break;
    case 'external':
      shell.openExternal(tab.displayUrl).catch(() => {});
      break;
    case 'zoom-in':
      wc.setZoomLevel(Math.min(3, wc.getZoomLevel() + 0.5));
      break;
    case 'zoom-out':
      wc.setZoomLevel(Math.max(-3, wc.getZoomLevel() - 0.5));
      break;
    case 'zoom-reset':
      wc.setZoomLevel(0);
      break;
    case 'print':
      wc.print();
      break;
    default:
      break;
  }
});

ipcMain.on('view:bounds', (_event, rect) => {
  if (!rect || typeof rect !== 'object') return;
  const next = {
    x: Number(rect.x) || 0,
    y: Number(rect.y) || 0,
    width: Math.max(0, Number(rect.width) || 0),
    height: Math.max(0, Number(rect.height) || 0),
  };
  if (
    Math.round(next.x) === Math.round(viewBounds.x) &&
    Math.round(next.y) === Math.round(viewBounds.y) &&
    Math.round(next.width) === Math.round(viewBounds.width) &&
    Math.round(next.height) === Math.round(viewBounds.height)
  ) {
    return;
  }
  viewBounds = next;
  if (activeTabId && tabs.has(activeTabId)) applyBounds(tabs.get(activeTabId).view);
});

ipcMain.on('window:minimize', () => mainWindow && mainWindow.minimize());
ipcMain.on('window:toggle-maximize', () => {
  if (!mainWindow) return;
  if (mainWindow.isMaximized()) mainWindow.unmaximize();
  else mainWindow.maximize();
});
ipcMain.on('window:close', () => mainWindow && mainWindow.close());

let resizeState = null;
ipcMain.on('window:resize-start', (_event, point) => {
  if (!mainWindow) return;
  if (mainWindow.isMaximized()) {
    mainWindow.unmaximize();
    resizeState = null;
    return;
  }
  resizeState = {
    startX: Number(point && point.x) || 0,
    startY: Number(point && point.y) || 0,
    bounds: mainWindow.getBounds(),
  };
});
ipcMain.on('window:resize-move', (_event, point) => {
  if (!mainWindow || !resizeState) return;
  const dx = (Number(point && point.x) || 0) - resizeState.startX;
  const dy = (Number(point && point.y) || 0) - resizeState.startY;
  const width = Math.max(1080, Math.min(3840, resizeState.bounds.width + dx));
  const height = Math.max(680, Math.min(2160, resizeState.bounds.height + dy));
  mainWindow.setBounds({ x: resizeState.bounds.x, y: resizeState.bounds.y, width, height });
});
ipcMain.on('window:resize-end', () => {
  resizeState = null;
});

ipcMain.on('app:open-external', (_event, url) => {
  if (/^https?:\/\//i.test(String(url))) shell.openExternal(url).catch(() => {});
});

ipcMain.handle('app:copy', (_event, text) => {
  clipboard.writeText(String(text ?? ''));
  return true;
});

ipcMain.handle('app:clear-session', async () => {
  if (!appSession) return false;
  await appSession.clearStorageData();
  await appSession.clearCache();
  for (const tab of tabs.values()) {
    if (tab.errorUrl) continue;
    try {
      tab.view.webContents.reload();
    } catch {
      /* ignore */
    }
  }
  return true;
});

ipcMain.handle('app:info', () => ({
  chrome: process.versions.chrome,
  electron: process.versions.electron,
  node: process.versions.node,
  platform: process.platform,
  userData: app.getPath('userData'),
  partition: PARTITION,
}));

ipcMain.on('app:menu', (_event, payload) => {
  if (!mainWindow) return;
  const { kind, point, tabId } = payload || {};
  const tab = tabs.get(tabId) || tabs.get(activeTabId) || null;
  const wc = tab ? tab.view.webContents : null;
  const items = [];

  if (kind === 'browser') {
    items.push(
      { label: 'Библиотека инструментов', click: () => setActiveTab(null) },
      { type: 'separator' },
      { label: 'Обновить', enabled: !!tab, click: () => tab && reloadTab(tab) },
      {
        label: 'Инструменты разработчика',
        enabled: !!wc,
        click: () => wc && wc.openDevTools({ mode: 'detach' }),
      },
      { type: 'separator' },
      {
        label: 'Масштаб: увеличить',
        enabled: !!wc,
        click: () => wc && wc.setZoomLevel(Math.min(3, wc.getZoomLevel() + 0.5)),
      },
      {
        label: 'Масштаб: уменьшить',
        enabled: !!wc,
        click: () => wc && wc.setZoomLevel(Math.max(-3, wc.getZoomLevel() - 0.5)),
      },
      {
        label: 'Масштаб: 100%',
        enabled: !!wc,
        click: () => wc && wc.setZoomLevel(0),
      },
      { type: 'separator' },
      {
        label: 'Печать…',
        enabled: !!wc,
        click: () => wc && wc.print(),
      },
      {
        label: 'Открыть в системном браузере',
        enabled: !!tab,
        click: () => tab && shell.openExternal(tab.displayUrl).catch(() => {}),
      },
      { type: 'separator' },
      { label: 'Очистить данные браузера…', click: clearBrowserData }
    );
  } else {
    items.push(
      { label: 'Очистить данные браузера…', click: clearBrowserData },
      { label: 'Открыть папку профиля', click: () => shell.openPath(app.getPath('userData')) },
      { type: 'separator' },
      {
        label: 'О приложении',
        click: () =>
          dialog.showMessageBox(mainWindow, {
            type: 'info',
            title: 'Recon Deck',
            message: 'Recon Deck 1.0.0',
            detail:
              'Браузер-консоль для работы с открытыми источниками.\n\n' +
              `Chromium ${process.versions.chrome}\nElectron ${process.versions.electron}\nNode ${process.versions.node}\n\n` +
              'Инструменты открываются во встроенном браузере. Данные профиля хранятся локально.',
            buttons: ['OK'],
          }),
      },
      {
        label: 'Инструменты разработчика приложения',
        click: () => mainWindow.webContents.openDevTools({ mode: 'detach' }),
      }
    );
  }

  const x = point && Number.isFinite(point.x) ? Math.round(point.x) : undefined;
  const y = point && Number.isFinite(point.y) ? Math.round(point.y) : undefined;
  Menu.buildFromTemplate(items).popup({ window: mainWindow, x, y });
});

async function clearBrowserData() {
  if (!mainWindow) return;
  const answer = await dialog.showMessageBox(mainWindow, {
    type: 'warning',
    title: 'Очистить данные браузера',
    message: 'Удалить cookies, кэш и данные сайтов?',
    detail: 'Все вкладки будут перезагружены. Избранное и настройки приложения сохранятся.',
    buttons: ['Отмена', 'Очистить'],
    defaultId: 0,
    cancelId: 0,
  });
  if (answer.response !== 1 || !appSession) return;
  await appSession.clearStorageData();
  await appSession.clearCache();
  for (const tab of tabs.values()) {
    if (tab.errorUrl) continue;
    try {
      tab.view.webContents.reload();
    } catch {
      /* ignore */
    }
  }
  toast('Данные браузера очищены', 'success');
}

ipcMain.on('app:window-focus', () => {
  if (mainWindow) mainWindow.webContents.focus();
});

/* ------------------------------------------------------ network ipc */

ipcMain.handle('net:state', () => networkState());

ipcMain.handle('net:countries', async (_event, force) => {
  try {
    const data = await ensureProxyData(!!force);
    return { ok: true, ...data };
  } catch (error) {
    return {
      ok: false,
      error: error.message,
      countries: proxyCountries(),
      total: proxyTotal(),
      updatedAt: proxyUpdatedAt,
      cached: proxyIndex.size > 0,
    };
  }
});

ipcMain.handle('net:tor-connect', (_event, openBrowser) => connectTor(!!openBrowser));
ipcMain.handle('net:new-route', () => connectTor(false));
ipcMain.handle('net:proxy-connect', (_event, payload) => connectCountry(payload || {}));
ipcMain.handle('net:connect-node', (_event, payload) => connectNode(payload || {}));
ipcMain.handle('net:nodes', async (_event, code, force) => {
  try {
    return await probeCountryNodes(code, 30, !!force);
  } catch (error) {
    return { ok: false, error: error.message, code, name: countryName(code), nodes: [] };
  }
});
ipcMain.handle('net:country-pings', async (_event, codes, force) => {
  try {
    return await probeCountryPings(Array.isArray(codes) ? codes : [], !!force);
  } catch (error) {
    return { ok: false, error: error.message, pings: {} };
  }
});
ipcMain.handle('net:custom-connect', (_event, payload) => connectCustom(payload || {}));
ipcMain.handle('net:disconnect', () => disconnectNetwork());
ipcMain.handle('net:check-ip', () => checkCurrentIp());

/* ------------------------------------------------------- network engine */

const PROXY_SOURCE =
  'https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/all/data.json';
const PROXY_TTL = 6 * 60 * 60 * 1000;
const TOR_BOOTSTRAP_TIMEOUT = 90000;

const network = {
  mode: 'direct',
  status: 'idle',
  label: 'Прямое подключение',
  country: '',
  countryName: '',
  ip: '',
  progress: 0,
  detail: '',
  error: '',
  isTor: false,
  proxy: null,
  ping: null,
  upstream: null,
};

let proxyIndex = new Map(); // code -> { code, name, total, items }
let proxyUpdatedAt = 0;
let proxyLoadPromise = null;
let proxyAuth = null;
const nodeProbeCache = new Map();
const nodeProbeInFlight = new Map();
const countryPingCache = new Map();

let torProc = null;
let torPort = 9050;
let torTimeout = null;
let torFinalizing = false;
let torOpenBrowser = false;

let netGeneration = 0;

const regionNames =
  typeof Intl.DisplayNames === 'function' ? new Intl.DisplayNames(['ru'], { type: 'region' }) : null;

function countryName(code) {
  try {
    return regionNames?.of(code) || code;
  } catch {
    return code;
  }
}

function torRoot() {
  return app.isPackaged
    ? path.join(process.resourcesPath, 'tor')
    : path.join(APP_DIR, 'resources', 'tor');
}

function torExePath() {
  return path.join(torRoot(), 'tor.exe');
}

function torAvailable() {
  try {
    return fs.existsSync(torExePath());
  } catch {
    return false;
  }
}

function proxyTotal() {
  let total = 0;
  for (const bucket of proxyIndex.values()) total += bucket.total;
  return total;
}

function networkState() {
  return {
    ...network,
    torAvailable: torAvailable(),
    proxyTotal: proxyTotal(),
    proxyUpdatedAt,
  };
}

function sendNetwork() {
  send('net:state', networkState());
}

function resetNetwork(patch = {}) {
  Object.assign(network, {
    mode: 'direct',
    status: 'idle',
    label: 'Прямое подключение',
    country: '',
    countryName: '',
    ip: '',
    progress: 0,
    detail: '',
    error: '',
    isTor: false,
    proxy: null,
    ping: null,
    upstream: null,
    ...patch,
  });
  sendNetwork();
}

async function setProxyOnly(rules) {
  if (!appSession) return;
  if (rules) {
    await appSession.setProxy({
      mode: 'fixed_servers',
      proxyRules: rules,
      proxyBypassRules: '<local>',
    });
  } else {
    await appSession.setProxy({ mode: 'direct' });
  }
  try {
    await appSession.closeAllConnections();
  } catch {
    /* ignore */
  }
}

function reloadAllTabs() {
  for (const tab of tabs.values()) {
    if (tab.errorUrl) continue;
    try {
      tab.view.webContents.reload();
    } catch {
      /* ignore */
    }
  }
}

async function applyProxy(rules) {
  await setProxyOnly(rules);
  reloadAllTabs();
}

function netJson(url, timeoutMs = 10000) {
  return new Promise((resolve, reject) => {
    let settled = false;
    let request;
    const finish = (fn, value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      fn(value);
    };
    const timer = setTimeout(() => {
      try {
        request?.abort();
      } catch {
        /* ignore */
      }
      finish(reject, new Error('Тайм-аут соединения'));
    }, timeoutMs);

    try {
      request = net.request({ url, session: appSession });
    } catch (error) {
      finish(reject, error);
      return;
    }

    request.on('response', (response) => {
      let body = '';
      response.on('data', (chunk) => {
        body += chunk;
      });
      response.on('end', () => {
        try {
          finish(resolve, JSON.parse(body));
        } catch {
          finish(reject, new Error('Некорректный ответ сервера'));
        }
      });
      response.on('error', (error) => finish(reject, error));
    });
    request.on('error', (error) => finish(reject, error));
    request.end();
  });
}

async function fetchExitIp(timeoutMs = 9000) {
  const data = await netJson('https://api.ipify.org?format=json', timeoutMs);
  if (!data || !data.ip) throw new Error('Не удалось определить IP');
  return String(data.ip);
}

async function fetchTorExit(timeoutMs = 15000) {
  try {
    const data = await netJson('https://check.torproject.org/api/ip', timeoutMs);
    if (data && data.IP) return { ip: String(data.IP), isTor: !!data.IsTor };
  } catch {
    /* fall through */
  }
  return { ip: await fetchExitIp(timeoutMs), isTor: false };
}

/* ------------------------------------------------------------- proxies */

const COMMON_PROXY_PORTS = new Set([
  1080, 1081, 1085, 1086, 1087, 10808, 10809, 9050, 9150, 3128, 8000, 8001, 8080, 8081, 8443,
  8888, 443,
]);

function proxyRank(proxy) {
  const anon =
    proxy.anon === 'elite' ? 3 : proxy.anon === 'anonymous' ? 2 : proxy.anon === 'transparent' ? 1 : 0;
  const commonPort = COMMON_PROXY_PORTS.has(proxy.port) ? 8 : 0;
  return anon * 10 + commonPort + (proxy.https ? 4 : 0) + Math.min(proxy.score || 0, 5);
}

function buildProxyIndex(raw) {
  const seen = new Set();
  const buckets = new Map();

  for (const item of raw) {
    if (String(item.protocol || '').toLowerCase() !== 'socks5') continue;
    const geo = item.geolocation || {};
    const code = String(geo.country || '').toUpperCase();
    if (!/^[A-Z]{2}$/.test(code) || code === 'ZZ') continue;
    const host = String(item.ip || '').trim();
    const port = Number(item.port);
    if (!host || !Number.isInteger(port) || port < 1 || port > 65535) continue;
    const key = host + ':' + port;
    if (seen.has(key)) continue;
    seen.add(key);

    let bucket = buckets.get(code);
    if (!bucket) {
      bucket = { code, name: countryName(code), total: 0, items: [] };
      buckets.set(code, bucket);
    }
    bucket.total += 1;
    bucket.items.push({
      host,
      port,
      city: String(geo.city || ''),
      anon: String(item.anonymity || ''),
      score: Number(item.score) || 0,
      https: !!item.https,
    });
  }

  for (const bucket of buckets.values()) {
    bucket.items.sort((a, b) => proxyRank(b) - proxyRank(a) || b.score - a.score);
    bucket.items = bucket.items.slice(0, 200);
  }

  return [...buckets.values()].sort((a, b) => b.total - a.total);
}

function proxyCountries() {
  return [...proxyIndex.values()].map((bucket) => ({
    code: bucket.code,
    name: bucket.name,
    total: bucket.total,
  }));
}

async function ensureProxyData(force = false) {
  if (!force && proxyIndex.size && Date.now() - proxyUpdatedAt < PROXY_TTL) {
    return { countries: proxyCountries(), total: proxyTotal(), updatedAt: proxyUpdatedAt, cached: true };
  }
  if (proxyLoadPromise) return proxyLoadPromise;

  const cacheFile = path.join(app.getPath('userData'), 'proxy-cache.json');

  proxyLoadPromise = (async () => {
    if (!force) {
      try {
        const cached = JSON.parse(await fs.promises.readFile(cacheFile, 'utf8'));
        if (cached && Array.isArray(cached.countries) && Date.now() - Number(cached.at) < PROXY_TTL) {
          proxyIndex = new Map(cached.countries.map((bucket) => [bucket.code, bucket]));
          proxyUpdatedAt = Number(cached.at) || Date.now();
          return {
            countries: proxyCountries(),
            total: proxyTotal(),
            updatedAt: proxyUpdatedAt,
            cached: true,
          };
        }
      } catch {
        /* no cache */
      }
    }

    const doFetch = typeof fetch === 'function' ? fetch : net.fetch;
    const response = await doFetch(PROXY_SOURCE, {
      signal: AbortSignal.timeout(180000),
      headers: { 'user-agent': CHROME_UA },
    });
    if (!response.ok) throw new Error('Источник прокси вернул HTTP ' + response.status);
    const raw = await response.json();
    if (!Array.isArray(raw) || !raw.length) throw new Error('Пустой список прокси');

    const countries = buildProxyIndex(raw);
    proxyIndex = new Map(countries.map((bucket) => [bucket.code, bucket]));
    proxyUpdatedAt = Date.now();

    try {
      await fs.promises.writeFile(cacheFile, JSON.stringify({ at: proxyUpdatedAt, countries }));
    } catch {
      /* cache is optional */
    }

    return {
      countries: proxyCountries(),
      total: proxyTotal(),
      updatedAt: proxyUpdatedAt,
      cached: false,
    };
  })();

  try {
    return await proxyLoadPromise;
  } finally {
    proxyLoadPromise = null;
  }
}

function tcpProbe(host, port, timeoutMs = 2500) {
  return new Promise((resolve) => {
    let done = false;
    const socket = nodeNet.createConnection({ host, port });
    const finish = (ok) => {
      if (done) return;
      done = true;
      socket.destroy();
      resolve(ok);
    };
    socket.setTimeout(timeoutMs);
    socket.once('connect', () => finish(true));
    socket.once('timeout', () => finish(false));
    socket.once('error', () => finish(false));
  });
}

function findFreePort(start = 9050) {
  return new Promise((resolve) => {
    const attempt = (port) => {
      if (port > start + 120) {
        resolve(start);
        return;
      }
      const server = nodeNet.createServer();
      server.once('error', () => attempt(port + 1));
      server.once('listening', () => {
        server.close(() => resolve(port));
      });
      server.listen(port, '127.0.0.1');
    };
    attempt(start);
  });
}

function tcpPing(host, port, timeoutMs = 2500) {
  return new Promise((resolve) => {
    const started = process.hrtime.bigint();
    let settled = false;
    const socket = nodeNet.createConnection({ host, port });
    const finish = (ok) => {
      if (settled) return;
      settled = true;
      const elapsed = Number(process.hrtime.bigint() - started) / 1e6;
      socket.destroy();
      resolve({ ok, ms: ok ? Math.max(1, Math.round(elapsed)) : 0 });
    };
    socket.setTimeout(timeoutMs);
    socket.once('connect', () => finish(true));
    socket.once('timeout', () => finish(false));
    socket.once('error', () => finish(false));
  });
}

async function probeCountryNodes(code, limit = 30, force = false) {
  if (!proxyIndex.size) await ensureProxyData();
  const bucket = proxyIndex.get(code);
  if (!bucket || !bucket.items.length) {
    return { ok: false, error: 'Для этой страны нет узлов.', code, name: countryName(code), nodes: [] };
  }

  const cacheKey = code + ':' + limit;
  const cached = nodeProbeCache.get(cacheKey);
  if (!force && cached && Date.now() - cached.at < 25000) return cached.data;
  if (nodeProbeInFlight.has(cacheKey)) return nodeProbeInFlight.get(cacheKey);

  const task = (async () => {
    const candidates = bucket.items.slice(0, limit);
    const nodes = await Promise.all(
      candidates.map(async (proxy) => {
        const result = await tcpPing(proxy.host, proxy.port, 2500);
        return {
          host: proxy.host,
          port: proxy.port,
          city: proxy.city,
          anon: proxy.anon,
          ping: result.ms,
          available: result.ok,
        };
      })
    );

    nodes.sort(
      (a, b) =>
        Number(b.available) - Number(a.available) ||
        (a.available ? a.ping : 999999) - (b.available ? b.ping : 999999)
    );

    const data = {
      ok: true,
      code,
      name: bucket.name,
      total: bucket.total,
      nodes,
      checkedAt: Date.now(),
    };
    nodeProbeCache.set(cacheKey, { at: Date.now(), data });
    return data;
  })();

  nodeProbeInFlight.set(cacheKey, task);
  try {
    return await task;
  } finally {
    nodeProbeInFlight.delete(cacheKey);
  }
}

async function probeCountryPings(codes, force = false) {
  if (!proxyIndex.size) await ensureProxyData();
  const result = {};
  const tasks = [];
  const now = Date.now();

  for (const code of codes) {
    const cached = countryPingCache.get(code);
    if (!force && cached && now - cached.at < 60000) {
      result[code] = cached.ms;
      continue;
    }
    const bucket = proxyIndex.get(code);
    if (!bucket || !bucket.items.length) {
      result[code] = null;
      continue;
    }
    for (const proxy of bucket.items.slice(0, 3)) {
      tasks.push({ code, proxy });
    }
  }

  const best = new Map();
  let cursor = 0;
  const workerCount = Math.min(60, tasks.length);
  const workers = Array.from({ length: workerCount }, async () => {
    while (true) {
      const index = cursor;
      cursor += 1;
      if (index >= tasks.length) return;
      const { code, proxy } = tasks[index];
      const ping = await tcpPing(proxy.host, proxy.port, 1800);
      if (!ping.ok) continue;
      const current = best.get(code);
      if (current === undefined || ping.ms < current) best.set(code, ping.ms);
    }
  });
  await Promise.all(workers);

  for (const code of codes) {
    if (Object.prototype.hasOwnProperty.call(result, code)) continue;
    const ms = best.has(code) ? best.get(code) : null;
    result[code] = ms;
    countryPingCache.set(code, { at: Date.now(), ms });
  }

  return { ok: true, pings: result, checkedAt: Date.now() };
}

async function failProxy(message) {
  proxyAuth = null;
  await setProxyOnly(null);
  reloadAllTabs();
  resetNetwork({ mode: 'direct', status: 'error', error: message });
}

async function connectCountry({ code, name }) {
  const generation = ++netGeneration;
  stopTor();
  proxyAuth = null;
  await setProxyOnly(null);

  if (!proxyIndex.size) {
    try {
      await ensureProxyData();
    } catch (error) {
      resetNetwork({
        mode: 'direct',
        status: 'error',
        error: 'Не удалось загрузить список прокси: ' + error.message,
      });
      return networkState();
    }
  }

  if (generation !== netGeneration) return networkState();

  const bucket = proxyIndex.get(code);
  if (!bucket || !bucket.items.length) {
    resetNetwork({
      mode: 'direct',
      status: 'error',
      error: 'Для этой страны пока нет доступных прокси.',
    });
    return networkState();
  }

  const label = name || bucket.name;
  Object.assign(network, {
    mode: 'proxy',
    status: 'connecting',
    label,
    country: code,
    countryName: label,
    ip: '',
    progress: 4,
    detail: 'Проверка доступности узлов…',
    error: '',
    isTor: false,
    proxy: null,
  });
  sendNetwork();

  Object.assign(network, { detail: 'Замер пинга узлов…', progress: 8 });
  sendNetwork();
  let probe;
  try {
    probe = await probeCountryNodes(code, 30);
  } catch (error) {
    if (generation !== netGeneration) return networkState();
    await failProxy('Не удалось проверить узлы: ' + error.message);
    return networkState();
  }

  if (generation !== netGeneration) return networkState();
  const reachable = probe.nodes.filter((node) => node.available);
  if (!reachable.length) {
    await failProxy('Все узлы этой страны не отвечают. Попробуйте другую страну.');
    return networkState();
  }

  const attempts = reachable.slice(0, 8);
  for (let index = 0; index < attempts.length; index += 1) {
    if (generation !== netGeneration) return networkState();
    const proxy = attempts[index];
    Object.assign(network, {
      progress: 15 + Math.round((index / attempts.length) * 80),
      detail: `Подключение: ${proxy.host}:${proxy.port} · ${proxy.ping} мс`,
    });
    sendNetwork();

    try {
      await setProxyOnly(`socks5://${proxy.host}:${proxy.port}`);
      const ip = await fetchExitIp(7000);
      if (generation !== netGeneration) return networkState();
      Object.assign(network, {
        mode: 'proxy',
        status: 'connected',
        label,
        country: code,
        countryName: label,
        ip,
        ping: proxy.ping,
        progress: 100,
        detail: '',
        error: '',
        isTor: false,
        proxy: { type: 'socks5', host: proxy.host, port: proxy.port, city: proxy.city },
      });
      sendNetwork();
      reloadAllTabs();
      return networkState();
    } catch {
      /* try next proxy */
    }
  }

  if (generation !== netGeneration) return networkState();
  await failProxy('Не удалось пробиться ни через один узел. Бесплатные прокси нестабильны — выберите другую страну.');
  return networkState();
}

async function connectNode({ host, port, code, name, ping }) {
  const generation = ++netGeneration;
  stopTor();
  proxyAuth = null;
  await setProxyOnly(null);

  const numericPort = Number(port);
  if (!host || !Number.isInteger(numericPort) || numericPort < 1 || numericPort > 65535) {
    resetNetwork({ mode: 'direct', status: 'error', error: 'Некорректный адрес узла.' });
    return networkState();
  }

  const label = name || countryName(code) || 'VPN';
  Object.assign(network, {
    mode: 'proxy',
    status: 'connecting',
    label,
    country: code || '',
    countryName: label,
    ip: '',
    ping: Number(ping) || null,
    progress: 55,
    detail: 'Проверка узла по HTTPS…',
    error: '',
    isTor: false,
    proxy: null,
  });
  sendNetwork();

  try {
    await setProxyOnly(`socks5://${host}:${numericPort}`);
    const ip = await fetchExitIp(8000);
    if (generation !== netGeneration) return networkState();
    Object.assign(network, {
      status: 'connected',
      ip,
      ping: Number(ping) || null,
      progress: 100,
      detail: '',
      error: '',
      proxy: { type: 'socks5', host, port: numericPort, city: '' },
    });
    sendNetwork();
    reloadAllTabs();
  } catch {
    if (generation === netGeneration) {
      await failProxy('Узел не прошёл проверку HTTPS. Выберите другой узел.');
    }
  }
  return networkState();
}

async function connectCustom({ type, host, port, username, password }) {
  const generation = ++netGeneration;
  stopTor();
  proxyAuth = null;
  await setProxyOnly(null);

  const protocol = type === 'http' ? 'http' : 'socks5';
  const numericPort = Number(port);
  if (!host || !Number.isInteger(numericPort) || numericPort < 1 || numericPort > 65535) {
    resetNetwork({ mode: 'direct', status: 'error', error: 'Укажите корректный хост и порт.' });
    return networkState();
  }

  Object.assign(network, {
    mode: 'proxy',
    status: 'connecting',
    label: 'Свой прокси',
    country: '',
    countryName: 'Свой прокси',
    ip: '',
    progress: 20,
    detail: 'Проверка прокси…',
    error: '',
    isTor: false,
    proxy: null,
    ping: null,
  });
  sendNetwork();

  if (username) proxyAuth = { username: String(username), password: String(password || '') };

  try {
    await setProxyOnly(`${protocol}://${host}:${numericPort}`);
    const ip = await fetchExitIp(9000);
    if (generation !== netGeneration) return networkState();
    Object.assign(network, {
      status: 'connected',
      progress: 100,
      detail: '',
      ip,
      error: '',
      proxy: { type: protocol, host, port: numericPort },
    });
    sendNetwork();
    reloadAllTabs();
  } catch {
    if (generation === netGeneration) {
      await failProxy('Прокси не ответил. Проверьте адрес, порт и тип (SOCKS5/HTTP).');
    }
  }
  return networkState();
}

/* ----------------------------------------------------------------- Tor */

function stopTor() {
  if (torTimeout) {
    clearTimeout(torTimeout);
    torTimeout = null;
  }
  torFinalizing = false;
  torOpenBrowser = false;
  if (torProc) {
    const proc = torProc;
    torProc = null;
    try {
      proc.kill();
    } catch {
      /* ignore */
    }
  }
}

function handleTorOutput(buffer, generation) {
  const text = buffer.toString('utf8');
  if (IS_DEV) console.log('[tor]', text.trim());
  const matches = [...text.matchAll(/Bootstrapped (\d+)%/g)];
  if (matches.length) {
    const progress = Number(matches[matches.length - 1][1]);
    if (progress > network.progress) {
      network.progress = progress;
      network.detail = `Загрузка цепочки: ${progress}%`;
      sendNetwork();
    }
    if (progress >= 100 && network.status === 'connecting' && !torFinalizing) {
      finalizeTor(generation);
    }
  }
}

async function finalizeTor(generation) {
  if (torFinalizing || generation !== netGeneration) return;
  torFinalizing = true;
  if (torTimeout) {
    clearTimeout(torTimeout);
    torTimeout = null;
  }
  const upstream = network.upstream ? { ...network.upstream } : null;

  try {
    await setProxyOnly(`socks5://127.0.0.1:${torPort}`);
    const exit = await fetchTorExit(15000);
    if (generation !== netGeneration) return;
    Object.assign(network, {
      mode: 'tor',
      status: 'connected',
      label: upstream ? 'Tor через VPN' : 'Tor',
      progress: 100,
      detail: '',
      ip: exit.ip,
      isTor: exit.isTor,
      error: '',
      country: '',
      countryName: '',
      proxy: null,
      ping: null,
      upstream,
    });
    sendNetwork();
    reloadAllTabs();
    if (torOpenBrowser) {
      torOpenBrowser = false;
      send('net:tor-ready', { ip: exit.ip, upstream });
    }
  } catch (error) {
    await restoreAfterTorFailure(
      upstream,
      'Tor подключился, но проверка выхода не удалась: ' + error.message
    );
  } finally {
    torFinalizing = false;
  }
}

async function restoreAfterTorFailure(upstream, message) {
  stopTor();
  if (upstream && upstream.host) {
    proxyAuth = upstream.username
      ? { username: upstream.username, password: upstream.password }
      : null;
    try {
      await setProxyOnly(
        `${upstream.type === 'http' ? 'http' : 'socks5'}://${upstream.host}:${upstream.port}`
      );
      reloadAllTabs();
      resetNetwork({
        mode: 'proxy',
        status: 'connected',
        label: upstream.countryName || 'VPN',
        country: upstream.country || '',
        countryName: upstream.countryName || 'VPN',
        error: message,
        proxy: { type: upstream.type, host: upstream.host, port: upstream.port },
      });
      return;
    } catch {
      /* fall through to direct */
    }
  }
  await setProxyOnly(null);
  resetNetwork({ mode: 'direct', status: 'error', error: message });
}

async function connectTor(openBrowser = false) {
  const generation = ++netGeneration;
  stopTor();
  torOpenBrowser = openBrowser;

  const upstream =
    network.mode === 'proxy' && network.status === 'connected' && network.proxy
      ? {
          type: network.proxy.type === 'http' ? 'http' : 'socks5',
          host: network.proxy.host,
          port: network.proxy.port,
          username: proxyAuth?.username || '',
          password: proxyAuth?.password || '',
          country: network.country || '',
          countryName: network.countryName || network.label || 'VPN',
        }
      : network.upstream
        ? { ...network.upstream }
        : null;

  if (!upstream) {
    proxyAuth = null;
    await setProxyOnly(null);
  }

  Object.assign(network, {
    mode: 'tor',
    status: 'connecting',
    label: upstream ? 'Tor через VPN' : 'Tor',
    country: '',
    countryName: '',
    ip: '',
    progress: 0,
    detail: upstream ? `Tor через VPN: ${upstream.countryName}` : 'Запуск Tor…',
    error: '',
    isTor: false,
    proxy: null,
    ping: null,
    upstream,
  });
  sendNetwork();

  if (!torAvailable()) {
    await restoreAfterTorFailure(
      upstream,
      'Компонент Tor не найден. Переустановите приложение или соберите его заново.'
    );
    return networkState();
  }

  const dataDir = path.join(app.getPath('userData'), 'tor-data');
  const torrcPath = path.join(app.getPath('userData'), 'torrc');
  torPort = await findFreePort(9050);
  try {
    fs.mkdirSync(dataDir, { recursive: true });
    const slash = (value) => value.replace(/\\/g, '/');
    const torrc = [
      `SocksPort 127.0.0.1:${torPort}`,
      `DataDirectory "${slash(dataDir)}"`,
      'Log notice stdout',
      'AvoidDiskWrites 1',
      'ClientOnly 1',
    ];
    if (upstream) {
      if (upstream.type === 'http') {
        torrc.push(`HTTPSProxy ${upstream.host}:${upstream.port}`);
        if (upstream.username) {
          torrc.push(`HTTPSProxyAuthenticator ${upstream.username}:${upstream.password}`);
        }
      } else {
        torrc.push(`Socks5Proxy ${upstream.host}:${upstream.port}`);
        if (upstream.username) {
          torrc.push(`Socks5ProxyUsername ${upstream.username}`);
          torrc.push(`Socks5ProxyPassword ${upstream.password}`);
        }
      }
    }
    fs.writeFileSync(torrcPath, torrc.join('\n'), 'utf8');
  } catch (error) {
    await restoreAfterTorFailure(upstream, 'Не удалось подготовить Tor: ' + error.message);
    return networkState();
  }

  try {
    torProc = spawn(torExePath(), ['-f', torrcPath], {
      cwd: torRoot(),
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
  } catch (error) {
    await restoreAfterTorFailure(upstream, 'Не удалось запустить Tor: ' + error.message);
    return networkState();
  }

  network.detail = upstream
    ? `Tor через VPN ${upstream.countryName}: подключение…`
    : 'Подключение к сети Tor…';
  sendNetwork();

  torProc.stdout.on('data', (chunk) => handleTorOutput(chunk, generation));
  torProc.stderr.on('data', (chunk) => handleTorOutput(chunk, generation));
  torProc.on('error', (error) => {
    if (generation !== netGeneration) return;
    restoreAfterTorFailure(upstream, 'Tor: ' + error.message);
  });
  torProc.on('exit', (code) => {
    if (generation !== netGeneration) return;
    if (network.status === 'connecting' || network.status === 'connected') {
      restoreAfterTorFailure(
        upstream,
        'Процесс Tor завершился (код ' + code + '). VPN-соединение сохранено.'
      );
    }
  });

  if (torTimeout) clearTimeout(torTimeout);
  torTimeout = setTimeout(() => {
    if (generation !== netGeneration || network.status !== 'connecting') return;
    restoreAfterTorFailure(
      upstream,
      upstream
        ? 'Tor не подключился через VPN за 90 секунд. VPN-соединение сохранено — попробуйте другой узел.'
        : 'Tor не подключился за 90 секунд. Возможно, провайдер блокирует сеть Tor — подключитесь к VPN и повторите.'
    );
  }, TOR_BOOTSTRAP_TIMEOUT);

  return networkState();
}

async function disconnectNetwork() {
  netGeneration += 1;
  stopTor();
  proxyAuth = null;
  await applyProxy(null);
  resetNetwork();
  return networkState();
}

async function checkCurrentIp() {
  try {
    const ip = network.isTor ? (await fetchTorExit(12000)).ip : await fetchExitIp(10000);
    network.ip = ip;
    sendNetwork();
    return { ok: true, ip };
  } catch (error) {
    return { ok: false, error: error.message };
  }
}

/* ---------------------------------------------------------------- boot */

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.show();
      mainWindow.focus();
    }
  });

  app.whenReady().then(() => {
    app.setAppUserModelId('com.recondeck.app');
    appSession = session.fromPartition(PARTITION);
    appSession.setUserAgent(CHROME_UA);
    appSession.protocol.handle('recon', handleReconProtocol);

    appSession.on('login', (event, _contents, _details, authInfo, callback) => {
      if (!authInfo || !authInfo.isProxy) return;
      if (proxyAuth) {
        event.preventDefault();
        callback(proxyAuth.username, proxyAuth.password);
      }
    });

    const allowed = new Set(['fullscreen', 'clipboard-sanitized-write']);
    appSession.setPermissionRequestHandler((_wc, permission, callback) => {
      callback(allowed.has(permission));
    });
    appSession.setPermissionCheckHandler((_wc, permission) => allowed.has(permission));

    appSession.on('will-download', (_event, item) => {
      const name = item.getFilename();
      toast('Скачивание: ' + name, 'info');
      item.once('done', (_e, status) => {
        if (status === 'completed') toast('Сохранено: ' + item.getSavePath(), 'success');
        else if (status === 'interrupted') toast('Загрузка прервана: ' + name, 'error');
      });
    });

    app.on('web-contents-created', (_event, contents) => {
      if (contents.getType() === 'window') {
        contents.setWindowOpenHandler(() => ({ action: 'deny' }));
      }
    });

    createWindow();
  });

  app.on('window-all-closed', () => {
    app.quit();
  });

  app.on('before-quit', () => {
    netGeneration += 1;
    stopTor();
  });

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
}

/* ------------------------------------------------------ screenshot mode */

function runScreenshotHarness() {
  const arg = SHOT_ARG;
  const outPath = arg.includes('=') ? arg.split('=')[1] : path.join(APP_DIR, 'shot.png');
  const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  mainWindow.webContents.once('did-finish-load', () => {
    setTimeout(async () => {
      try {
        const shot = async (suffix = '') => {
          const image = await mainWindow.webContents.capturePage();
          const file = suffix ? outPath.replace(/\.png$/i, suffix + '.png') : outPath;
          fs.writeFileSync(file, image.toPNG());
          console.log('[shot] saved', file);
        };

        await shot();

        if (SHOT_TOR_VPN) {
          await mainWindow.webContents.executeJavaScript(
            `document.querySelector('#btn-network').click(); true;`
          );
          await delay(700);
          const vpn = await mainWindow.webContents.executeJavaScript(
            `window.hub.proxyConnect({ code: 'US', name: 'США' })`
          );
          console.log('[shot] vpn', JSON.stringify(vpn));

          if (vpn && vpn.status === 'connected') {
            await mainWindow.webContents.executeJavaScript(
              `window.hub.openTab('https://ipinfo.io/json')`
            );
            await delay(7000);
            const vpnTabInfo = await mainWindow.webContents.executeJavaScript(
              `({ address: document.querySelector('#address').value,
                  tabs: document.querySelectorAll('.tab').length })`
            );
            console.log('[shot] vpn tab', JSON.stringify(vpnTabInfo));
            if (activeTabId && tabs.has(activeTabId)) {
              const vpnTab = tabs.get(activeTabId);
              const body = await vpnTab.view.webContents
                .executeJavaScript('document.body.innerText.slice(0, 800)')
                .catch((error) => 'ERR ' + error.message);
              console.log('[shot] vpn page', String(body).replace(/\s+/g, ' ').slice(0, 400));
              try {
                const image = await vpnTab.view.webContents.capturePage();
                fs.writeFileSync(outPath.replace(/\.png$/i, '-vpn-site.png'), image.toPNG());
              } catch {
                /* ignore */
              }
            }

            const torStarted = await mainWindow.webContents.executeJavaScript(
              `window.hub.torConnect(true)`
            );
            console.log('[shot] tor start', JSON.stringify(torStarted));
            await delay(95000);
            const torState = await mainWindow.webContents.executeJavaScript(
              `window.hub.netState()`
            );
            console.log('[shot] tor over vpn', JSON.stringify(torState));

            const browserInfo = await mainWindow.webContents.executeJavaScript(
              `({ hasTab: document.body.classList.contains('has-tab'),
                  tabs: document.querySelectorAll('.tab').length,
                  modalHidden: document.querySelector('#net-modal').hidden,
                  address: document.querySelector('#address').value })`
            );
            console.log('[shot] tor browser', JSON.stringify(browserInfo));

            if (activeTabId && tabs.has(activeTabId)) {
              const active = tabs.get(activeTabId);
              await delay(3000);
              const text = await active.view.webContents
                .executeJavaScript('document.body.innerText.slice(0, 1000)')
                .catch((error) => 'ERR ' + error.message);
              console.log('[shot] tor page', String(text).replace(/\s+/g, ' ').slice(0, 400));
              try {
                const image = await active.view.webContents.capturePage();
                fs.writeFileSync(outPath.replace(/\.png$/i, '-tor-browser.png'), image.toPNG());
              } catch {
                /* ignore */
              }
            }

            await shot('-tor-vpn');
          }
          app.quit();
          return;
        }

        if (SHOT_DARK) {
          await mainWindow.webContents.executeJavaScript(
            `document.querySelector('[data-cat="dark"]').click(); true;`
          );
          await delay(700);
          await shot('-dark');

          await mainWindow.webContents.executeJavaScript(
            `document.querySelector('.tile[data-url="app://tor"]').click(); true;`
          );
          await delay(6000);
          const darkState = await mainWindow.webContents.executeJavaScript(
            `(async () => {
               const s = await window.hub.netState();
               return {
                 modal: !document.querySelector('#net-modal').hidden,
                 mode: s.mode,
                 status: s.status,
                 progress: s.progress
               };
             })()`
          );
          console.log('[shot] dark tor', JSON.stringify(darkState));
          await shot('-dark-tor');
          app.quit();
          return;
        }

        if (SHOT_TOR) {
          await mainWindow.webContents.executeJavaScript(
            `document.querySelector('#btn-network').click(); true;`
          );
          await delay(500);
          await mainWindow.webContents.executeJavaScript(`window.hub.torConnect(); true;`);
          await delay(18000);
          const torState = await mainWindow.webContents.executeJavaScript(`window.hub.netState()`);
          console.log('[shot] tor state', JSON.stringify(torState));
          await shot('-tor');
          app.quit();
          return;
        }

        if (SHOT_NET) {
          await mainWindow.webContents.executeJavaScript(
            `document.querySelector('#btn-network').click(); true;`
          );
          await delay(900);
          await shot('-net');

          await mainWindow.webContents.executeJavaScript(
            `document.querySelector('[data-net-tab="countries"]').click(); true;`
          );
          for (let index = 0; index < 45; index += 1) {
            const ready = await mainWindow.webContents.executeJavaScript(
              `document.querySelectorAll('.country-card').length > 0`
            );
            if (ready) break;
            await delay(1000);
          }
          await delay(600);
          await shot('-countries');

          await mainWindow.webContents.executeJavaScript(
            `document.querySelector('[data-country="US"]').click(); true;`
          );
          await delay(20000);
          const result = await mainWindow.webContents.executeJavaScript(`window.hub.netState()`);
          console.log('[shot] proxy result', JSON.stringify(result));
          await shot('-proxy');

          app.quit();
          return;
        }

        if (SHOT_UI) {
          await mainWindow.webContents.executeJavaScript(
            `document.querySelector('[data-cat="people"]').click(); true;`
          );
          await delay(700);
          await shot('-category');

          await mainWindow.webContents.executeJavaScript(
            `document.querySelector('.tile-info').click(); true;`
          );
          await delay(500);
          await shot('-info');

          await mainWindow.webContents.executeJavaScript(
            `document.querySelector('[data-close-modal]').click(); true;`
          );
          await delay(300);

          await mainWindow.webContents.executeJavaScript(`
            const input = document.querySelector('#search');
            input.value = 'shodan';
            input.dispatchEvent(new Event('input', { bubbles: true }));
            true;
          `);
          await delay(700);
          await shot('-search');

          await mainWindow.webContents.executeJavaScript(
            `document.querySelector('.tile[data-url]').click(); true;`
          );
          await delay(1800);
          const check = await mainWindow.webContents.executeJavaScript(
            `({ hasTab: document.body.classList.contains('has-tab'),
                tabs: document.querySelectorAll('.tab').length,
                active: document.querySelectorAll('.tab.active').length })`
          );
          console.log('[shot] open check', JSON.stringify(check));

          app.quit();
          return;
        }

        if (SHOT_TAB) {
          const id = createTab(HOME_URL);
          const tab = tabs.get(id);
          const wc = tab.view.webContents;
          const done = async () => {
            await new Promise((resolve) => setTimeout(resolve, 1200));
            try {
              const tabImage = await wc.capturePage();
              const tabOut = outPath.replace(/\.png$/i, '-tab.png');
              fs.writeFileSync(tabOut, tabImage.toPNG());
              console.log('[shot] saved', tabOut);
            } catch (err) {
              console.error('[shot] tab capture failed', err);
            }
            app.quit();
          };
          wc.once('did-finish-load', done);
          setTimeout(() => {
            app.quit();
          }, 15000);
        } else {
          app.quit();
        }
      } catch (err) {
        console.error('[shot] failed', err);
        app.quit();
      }
    }, 2200);
  });
}

if (SHOT_ARG) {
  app.commandLine.appendSwitch('disable-gpu');
}
