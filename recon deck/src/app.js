'use strict';

/* ============================================================
   Recon Deck — рендерер библиотеки и вкладок
   ============================================================ */

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

const DATA = window.OSINT_DATA;

/* --------------------------------------------------------- helpers */

function hostOf(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return String(url || '').replace(/^https?:\/\//, '').replace(/\/.*$/, '');
  }
}

function faviconFor(host) {
  return 'https://www.google.com/s2/favicons?domain=' + encodeURIComponent(host) + '&sz=64';
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function readStore(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw);
    return parsed ?? fallback;
  } catch {
    return fallback;
  }
}

function writeStore(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* ignore */
  }
}

function plural(n, one, few, many) {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}

/* ----------------------------------------------------------- data */

const CATS = DATA.categories.map((cat) => ({
  ...cat,
  tools: cat.tools.map((tool) => {
    const isApp = /^app:\/\//i.test(tool.u || '');
    const host = isApp ? tool.action || 'module' : hostOf(tool.u);
    return {
      ...tool,
      host,
      color: cat.color,
      catId: cat.id,
      catName: cat.name,
      key: cat.id + '::' + tool.n,
      favicon: isApp ? '' : faviconFor(host),
      isApp,
    };
  }),
}));

const CAT_BY_ID = new Map(CATS.map((cat) => [cat.id, cat]));
const TOOLS = CATS.flatMap((cat) => cat.tools);
const TOOL_BY_KEY = new Map(TOOLS.map((tool) => [tool.key, tool]));
const TOOL_BY_URL = new Map(TOOLS.map((tool) => [tool.u, tool]));

/* ---------------------------------------------------------- state */

const state = {
  view: { type: 'home', catId: null, query: '' },
  tabs: [],
  activeId: null,
  favorites: readStore('recon.favorites', []),
  recents: readStore('recon.recents', []),
  collapsed: readStore('recon.sidebarCollapsed', false) === true,
  versions: { chrome: '—', electron: '—', node: '—' },
  network: {
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
    torAvailable: false,
    proxyTotal: 0,
    ping: null,
  },
  countries: [],
  countriesMeta: null,
  countryQuery: '',
  selectedCountry: '',
  selectedCountryName: '',
  nodes: [],
  nodesMeta: null,
  networkBusy: false,
  ipChecking: false,
  countryPings: new Map(),
  countryPingsLoading: false,
  countryPingsLoaded: false,
  bestServer: null,
};

let statusLockUntil = 0;
let statusTimer = null;

/* ----------------------------------------------------- icon utils */

function iconMarkup(tool) {
  const host = tool.host || '';
  const letter = tool.emoji || host.charAt(0).toUpperCase() || '?';
  const image = tool.emoji
    ? ''
    : `<img data-fav data-host="${escapeHtml(host)}" src="${escapeHtml(
        tool.favicon || faviconFor(host)
      )}" alt="" loading="lazy" />`;
  return `<span class="tile-ico" style="--tint:${tool.color || '#5eead4'}">
    <span class="letter">${escapeHtml(letter)}</span>
    ${image}
  </span>`;
}

function attachIcons(root = document) {
  $$('img[data-fav]', root).forEach((img) => {
    if (img.dataset.bound === '1') return;
    img.dataset.bound = '1';
    img.addEventListener('error', () => {
      if (img.dataset.retry !== '1' && img.dataset.host) {
        img.dataset.retry = '1';
        img.src = 'https://icons.duckduckgo.com/ip3/' + encodeURIComponent(img.dataset.host) + '.ico';
      } else {
        img.remove();
      }
    });
  });
}

/* ------------------------------------------------------- favorites */

function normalizeFavorite(entry) {
  const fromCatalog = TOOL_BY_KEY.get(entry.key) || TOOL_BY_URL.get(entry.u);
  if (fromCatalog) return { ...fromCatalog };
  const host = hostOf(entry.u);
  return {
    key: 'url::' + entry.u,
    n: entry.n || host,
    u: entry.u,
    d: entry.d || 'Сохранённая вкладка',
    host,
    color: entry.color || '#5eead4',
    catName: entry.catName || 'Вкладка',
    catId: entry.catId || 'custom',
    favicon: faviconFor(host),
  };
}

function isFavorite(url) {
  return state.favorites.some((favorite) => favorite.u === url);
}

function toggleFavorite(entry) {
  if (!entry || !entry.u) return;
  const index = state.favorites.findIndex((favorite) => favorite.u === entry.u);
  if (index >= 0) {
    state.favorites.splice(index, 1);
  } else {
    state.favorites.unshift(normalizeFavorite(entry));
    if (state.favorites.length > 60) state.favorites.length = 60;
  }
  writeStore('recon.favorites', state.favorites);
  renderSidebar();

  if (!state.activeId) {
    if (state.view.type === 'favorites') {
      renderLibrary({ preserveScroll: true });
    } else {
      $$('.tile-star').forEach((star) => {
        star.classList.toggle('on', isFavorite(star.dataset.star));
      });
    }
  }
  updateToolbar();
}

function pushRecent(tool) {
  const entry = normalizeFavorite(tool);
  state.recents = [entry, ...state.recents.filter((item) => item.u !== entry.u)].slice(0, 10);
  writeStore('recon.recents', state.recents);
}

function findToolByKey(key) {
  if (!key) return null;
  return (
    TOOL_BY_KEY.get(key) ||
    state.favorites.map(normalizeFavorite).find((tool) => tool.key === key) ||
    state.recents.find((tool) => tool.key === key) ||
    null
  );
}

function openToolEntry(tool, url) {
  if (tool && tool.action === 'tor') {
    if (state.network.mode === 'tor' && state.network.status === 'connected') {
      openTorBrowser();
    } else {
      openNetwork('tor', true);
    }
    return;
  }
  if (tool && tool.action === 'proxy') {
    openNetwork('countries');
    return;
  }
  const entry = tool || {
    key: 'url::' + url,
    n: hostOf(url),
    u: url,
    d: 'Открытый адрес',
    host: hostOf(url),
    catName: 'Вкладка',
  };
  const target = entry.u || url;
  if (!target) return;
  pushRecent(entry);
  window.hub.openTab(target);
}

/* ------------------------------------------------------------ modal */

let modalEntry = null;

function updateInfoFavorite() {
  const button = $('#info-fav');
  if (!button || !modalEntry || modalEntry.type !== 'tool') return;
  const active = isFavorite(modalEntry.tool.u);
  button.textContent = active ? 'В избранном' : 'В избранное';
  button.classList.toggle('on', active);
}

function openInfo(entry) {
  modalEntry = entry;
  const modal = $('#info-modal');
  const icon = $('#info-ico');
  const kicker = $('#info-kicker');
  const title = $('#info-title');
  const host = $('#info-host');
  const desc = $('#info-desc');
  const openBtn = $('#info-open');
  const favBtn = $('#info-fav');
  const copyBtn = $('#info-copy');

  openBtn.style.display = '';
  favBtn.style.display = 'none';
  copyBtn.style.display = 'none';

  if (entry.type === 'app') {
    icon.innerHTML = '<span class="tile-ico" style="--tint:#5eead4"><span class="letter">🛰️</span></span>';
    kicker.textContent = 'О приложении';
    title.textContent = 'Recon Deck';
    host.textContent = `Chromium ${state.versions.chrome} · ${TOOLS.length} инструментов · ${CATS.length} категорий`;
    desc.innerHTML = `<p><b>Recon Deck</b> — настольная консоль для работы с открытыми источниками.
      Внутри ${TOOLS.length} сервисов в ${CATS.length} категориях: поисковые дорки, домены и инфраструктура,
      люди и утечки, соцсети, компании, геолокация, транспорт и анализ связей.</p>
      <p>Кнопка <b>i</b> на каждой плитке объясняет, за что отвечает сервис. Сами сайты открываются
      во встроенном Chromium — с вкладками, историей, адресной строкой и масштабированием.</p>
      <p>В панели <b>Сеть</b> — встроенный Tor и выходные прокси по странам: весь трафик вкладок
      переключается в один клик.</p>
      <ul class="modal-list">
        <li>Избранное и недавние инструменты хранятся локально на этом компьютере.</li>
        <li>Куки и сессии сайтов — в отдельном профиле приложения.</li>
        <li>Никакой телеметрии: приложение не отправляет ваши данные.</li>
      </ul>
      <p class="modal-note">Соблюдайте закон и этику: работа с персональными данными, утечками
      и поиском по лицу допустима только в законных целях.</p>`;
    openBtn.textContent = 'Понятно';
    openBtn.dataset.action = 'close';
  } else {
    const tool = entry.tool;
    icon.innerHTML = iconMarkup(tool);
    attachIcons(icon);
    kicker.textContent = tool.catName || 'Инструмент';
    title.textContent = tool.n;
    host.textContent = tool.isApp
      ? 'Встроенный модуль · ' + tool.action
      : tool.host + (tool.u ? ' · ' + tool.u : '');
    desc.innerHTML = `<p>${escapeHtml(tool.d)}</p>`;
    openBtn.textContent = tool.action
      ? tool.action === 'tor'
        ? 'Открыть Tor-режим'
        : 'Открыть прокси по странам'
      : 'Открыть сайт';
    openBtn.dataset.action = 'open';
    favBtn.style.display = tool.action ? 'none' : '';
    copyBtn.style.display = tool.action ? 'none' : '';
    updateInfoFavorite();
  }

  modal.hidden = false;
  document.body.classList.add('modal-open');
  requestAnimationFrame(() => openBtn.focus());
}

function closeInfo() {
  const modal = $('#info-modal');
  if (!modal || modal.hidden) return;
  modal.hidden = true;
  if ($('#net-modal')?.hidden !== false) document.body.classList.remove('modal-open');
  modalEntry = null;
}

function openAppInfo() {
  if (state.activeId) {
    deactivateTab();
    if (!$('#library').innerHTML.trim()) renderLibrary();
  }
  openInfo({ type: 'app' });
}

/* ----------------------------------------------------------- network UI */

function networkStatusText(net) {
  if (net.status === 'connecting') return net.detail || 'Подключение…';
  if (net.status === 'connected') {
    if (net.mode === 'tor') {
      const via = net.upstream ? ` · через ${net.upstream.countryName || 'VPN'}` : '';
      return net.ip ? `Tor${via} · ${net.ip}` : `Tor${via} активен`;
    }
    if (net.mode === 'proxy') {
      return `${net.countryName || net.label}${net.ip ? ' · ' + net.ip : ''}${
        net.ping ? ' · ' + net.ping + ' мс' : ''
      }`;
    }
  }
  if (net.status === 'error') return 'Ошибка сети';
  return net.ip ? `Прямое подключение · ${net.ip}` : 'Прямое подключение';
}

function networkOrbClasses(net) {
  const kind = net.mode === 'tor' ? 'tor' : net.mode === 'proxy' ? 'proxy' : 'direct';
  if (net.status === 'error') return 'error';
  if (net.status === 'connecting') return `busy ${kind}`;
  return kind;
}

function applyNetworkState(next) {
  if (!next) return;
  const previous = state.network;
  state.network = { ...state.network, ...next };
  if (state.network.mode === 'proxy' && state.network.country) {
    state.selectedCountry = state.network.country;
    if (state.network.countryName) state.selectedCountryName = state.network.countryName;
  }
  if (previous.status !== 'connected' && state.network.status === 'connected') {
    let label = state.network.mode === 'tor' ? 'Tor' : state.network.countryName || 'VPN';
    if (state.network.mode === 'tor' && state.network.upstream) {
      label += ' через VPN ' + (state.network.upstream.countryName || '');
    }
    flashStatus(
      'Подключено: ' + label + (state.network.ip ? ' · IP ' + state.network.ip : ''),
      'success'
    );
  }
  renderNetwork();
}

function renderNetwork() {
  const net = state.network;
  const connecting = net.status === 'connecting';
  const connected = net.status === 'connected';
  const isError = net.status === 'error';
  const text = networkStatusText(net);

  const orb = $('#net-orb');
  if (orb) orb.className = 'net-orb ' + networkOrbClasses(net);
  const value = $('#net-value');
  if (value) value.textContent = text;

  const statusText = $('#net-status-text');
  if (statusText) statusText.textContent = text;
  const statusDot = $('#net-status-dot');
  if (statusDot) statusDot.className = 'net-status-dot ' + networkOrbClasses(net);

  const vpnBadge = $('#nav-vpn-mode');
  if (vpnBadge) {
    vpnBadge.textContent =
      net.status === 'connected'
        ? net.mode === 'tor'
          ? 'Tor'
          : net.country || 'VPN'
        : net.status === 'connecting'
          ? '…'
          : net.status === 'error'
            ? '!'
            : 'выкл';
    vpnBadge.classList.toggle('on', net.status === 'connected' || net.status === 'connecting');
    vpnBadge.title = text;
  }

  const disconnect = $('#net-disconnect');
  if (disconnect) disconnect.hidden = !(connected || connecting);
  const torConnect = $('#tor-connect');
  if (torConnect) {
    torConnect.hidden = net.mode === 'tor' && (connecting || connected);
    torConnect.disabled = connecting;
    torConnect.textContent =
      net.mode === 'proxy' && net.status === 'connected'
        ? 'Подключить Tor через VPN'
        : 'Подключить Tor';
  }
  const torNew = $('#tor-newid');
  if (torNew) torNew.hidden = !(net.mode === 'tor' && connected);
  const torBrowser = $('#tor-open-browser');
  if (torBrowser) torBrowser.hidden = !(net.mode === 'tor' && connected);
  const checkButton = $('#net-check');
  if (checkButton) {
    checkButton.disabled = connecting || state.ipChecking;
    if (state.ipChecking) {
      checkButton.textContent = 'Проверяем…';
      checkButton.classList.remove('has-ip');
    } else if (net.ip) {
      checkButton.textContent = 'IP: ' + net.ip;
      checkButton.classList.add('has-ip');
      checkButton.title = 'Текущий IP · нажмите, чтобы проверить снова';
    } else {
      checkButton.textContent = 'Проверить IP';
      checkButton.classList.remove('has-ip');
      checkButton.title = 'Проверить текущий IP';
    }
  }

  const progress = net.mode === 'tor' ? Math.max(0, Math.min(100, net.progress || 0)) : 0;
  const fill = $('#tor-fill');
  if (fill) fill.style.width = progress + '%';
  const pct = $('#tor-progress-pct');
  if (pct) pct.textContent = progress + '%';
  const progressText = $('#tor-progress-text');
  if (progressText) {
    progressText.textContent =
      net.mode === 'tor'
        ? net.detail || (connected ? 'Соединение установлено' : 'Готов к подключению')
        : 'Готов к подключению';
  }

  const ipNode = $('#tor-ip');
  if (ipNode) ipNode.textContent = net.ip || '—';
  const modeNode = $('#tor-exit-label');
  if (modeNode) {
    modeNode.textContent =
      net.mode === 'tor'
        ? connected
          ? 'Tor активен'
          : connecting
            ? 'Подключение…'
            : 'Не подключён'
        : net.mode === 'proxy'
          ? connected
            ? net.countryName || 'Прокси'
            : connecting
              ? 'Проверка…'
              : 'Не подключён'
          : 'Прямое подключение';
  }

  const errorBox = $('#net-error');
  if (errorBox) {
    if (net.error) {
      errorBox.hidden = false;
      errorBox.textContent = net.error;
    } else {
      errorBox.hidden = true;
    }
  }

  const upstreamBox = $('#net-upstream');
  if (upstreamBox) {
    if (net.upstream) {
      upstreamBox.hidden = false;
      const upstreamText = $('#net-upstream-text');
      if (upstreamText) {
        upstreamText.textContent = `${net.upstream.countryName || 'VPN'} · ${net.upstream.host}:${
          net.upstream.port
        }`;
      }
    } else {
      upstreamBox.hidden = true;
    }
  }

  const banner = $('#conn-banner');
  const bannerText = $('#conn-banner-text');
  if (banner) {
    if (connected) {
      const torLabel =
        net.mode === 'tor'
          ? 'Tor' + (net.upstream ? ' через ' + (net.upstream.countryName || 'VPN') : '')
          : net.countryName || net.label || 'VPN';
      const parts = [torLabel];
      if (net.ip) parts.push('IP ' + net.ip);
      if (net.ping) parts.push('пинг ' + net.ping + ' мс');
      if (net.proxy && net.proxy.host) parts.push(net.proxy.host + ':' + net.proxy.port);
      if (bannerText) bannerText.textContent = ' · ' + parts.join(' · ');
      banner.hidden = false;
    } else {
      banner.hidden = true;
    }
  }

  const proxyStatus = $('#proxy-status');
  if (proxyStatus) {
    proxyStatus.className = 'proxy-status';
    if (net.mode === 'proxy' && net.country) {
      if (connecting) {
        proxyStatus.textContent = `${net.countryName}: ${net.detail || 'подключение…'}`;
      } else if (connected) {
        proxyStatus.textContent = '';
      } else if (isError) {
        proxyStatus.textContent = net.error;
        proxyStatus.classList.add('error');
      }
    }
  }

  const customStatus = $('#custom-status');
  if (customStatus) {
    customStatus.className = 'proxy-status';
    if (net.mode === 'proxy' && !net.country) {
      if (connecting) customStatus.textContent = net.detail || 'Проверка прокси…';
      else if (connected) {
        customStatus.textContent = `Подключено · IP ${net.ip}`;
        customStatus.classList.add('ok');
      } else if (isError) {
        customStatus.textContent = net.error;
        customStatus.classList.add('error');
      }
    }
  }

  $$('.country-card').forEach((card) => {
    card.classList.toggle('active', card.dataset.country === state.selectedCountry);
  });

  if (state.nodes.length && $('#nodes-panel') && !$('#nodes-panel').hidden) renderNodes();
}

function selectNetTab(tab) {
  $$('.net-tab').forEach((button) => {
    button.classList.toggle('active', button.dataset.netTab === tab);
  });
  $$('.net-panel').forEach((panel) => {
    const active = panel.dataset.netPanel === tab;
    panel.hidden = !active;
    panel.classList.toggle('active', active);
  });
  if (tab === 'countries') loadCountries();
}

function openNetwork(tab = 'tor', autostart = false) {
  deactivateTab();
  const modal = $('#net-modal');
  if (!modal) return;
  modal.hidden = false;
  document.body.classList.add('modal-open');
  selectNetTab(tab);
  window.hub
    .netState()
    .then((next) => {
      applyNetworkState(next);
      if (
        autostart &&
        tab === 'tor' &&
        !(next.mode === 'tor' && (next.status === 'connected' || next.status === 'connecting'))
      ) {
        connectTor();
      } else if (!autostart && !next.ip && next.status !== 'connecting') {
        checkCurrentIp();
      }
    })
    .catch(() => {});
  requestAnimationFrame(() => {
    const focus = tab === 'countries' ? $('#country-search') : $('#tor-connect');
    focus?.focus();
  });
}

function closeNetwork() {
  const modal = $('#net-modal');
  if (!modal || modal.hidden) return;
  modal.hidden = true;
  if ($('#info-modal').hidden) document.body.classList.remove('modal-open');
}

async function loadCountries(force = false) {
  if (!force && state.countries.length) {
    renderCountries();
    if (!state.countryPingsLoaded && !state.countryPingsLoading) loadCountryPings();
    return;
  }
  const loading = $('#proxy-loading');
  const note = $('#proxy-note');
  if (loading) loading.hidden = false;
  if (note) note.textContent = 'Загрузка списка узлов…';
  try {
    const result = await window.hub.netCountries(force);
    state.countries = result.countries || [];
    state.countriesMeta = result;
    renderCountries();
    if (!state.countries.length) {
      if (note) note.textContent = result.error ? 'Не удалось загрузить: ' + result.error : 'Список пуст.';
    } else {
      const total = result.total || state.countries.reduce((sum, item) => sum + item.total, 0);
      const time = result.updatedAt
        ? new Date(result.updatedAt).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
        : '';
      if (note) {
        note.textContent = `${total.toLocaleString('ru-RU')} SOCKS5-узлов · ${state.countries.length} стран${
          time ? ' · ' + time : ''
        }${result.cached ? ' · кэш' : ''}${!result.ok && result.error ? ' · ' + result.error : ''}`;
      }
      loadCountryPings(force);
    }
  } catch (error) {
    if (note) note.textContent = 'Ошибка загрузки: ' + error.message;
  } finally {
    if (loading) loading.hidden = true;
  }
}

async function loadCountryPings(force = false) {
  if (!state.countries.length || state.countryPingsLoading) return;
  if (!force && state.countryPingsLoaded) return;
  if (force) state.countryPings.clear();
  state.countryPingsLoading = true;
  renderCountries();
  updateBestServer();
  try {
    const result = await window.hub.countryPings(
      state.countries.map((country) => country.code),
      force
    );
    if (result && result.ok) {
      for (const [code, ms] of Object.entries(result.pings || {})) {
        const existing = state.countryPings.get(code);
        if (ms === null) {
          if (existing === undefined) state.countryPings.set(code, null);
        } else if (existing === undefined || existing === null || ms < existing) {
          state.countryPings.set(code, ms);
        }
      }
      state.countryPingsLoaded = true;
    }
  } catch {
    /* pings are optional */
  } finally {
    state.countryPingsLoading = false;
    renderCountries();
    updateBestServer();
  }
}

function updateBestServer() {
  const card = $('#best-server');
  if (!card) return;

  let best = null;
  for (const country of state.countries) {
    const ms = state.countryPings.get(country.code);
    if (ms === null || ms === undefined) continue;
    if (!best || ms < best.ping) best = { code: country.code, name: country.name, ping: ms };
  }
  state.bestServer = best;

  const meta = $('#best-server-meta');
  const ping = $('#best-server-ping');

  if (!best) {
    card.disabled = true;
    if (meta) {
      meta.textContent = state.countryPingsLoading
        ? 'Проверяем пинги стран…'
        : 'Нет доступных серверов';
    }
    if (ping) {
      if (state.countryPingsLoading) {
        ping.innerHTML = '<span class="ping-spinner"></span>';
      } else {
        ping.textContent = '—';
      }
      ping.className = 'best-ping';
    }
    return;
  }

  card.disabled = false;
  card.title = 'Подключиться к лучшему серверу: ' + best.name;
  if (meta) {
    meta.innerHTML = `<img class="best-flag" src="https://flagcdn.com/w40/${best.code.toLowerCase()}.png" alt="" /> ${escapeHtml(
      best.name
    )} · лучший пинг`;
    const flag = meta.querySelector('img.best-flag');
    if (flag) flag.addEventListener('error', () => flag.remove());
  }
  if (ping) {
    ping.textContent = best.ping + ' мс';
    ping.className =
      'best-ping ' + (best.ping < 350 ? 'good' : best.ping < 900 ? 'mid' : 'bad');
  }
}

function attachFlags(root) {
  $$('img.country-flag-img', root).forEach((img) => {
    img.addEventListener('error', () => img.remove());
  });
}

function renderCountries() {
  const grid = $('#country-grid');
  if (!grid) return;
  const query = state.countryQuery.trim().toLowerCase();
  const list = state.countries.filter(
    (item) =>
      !query || item.name.toLowerCase().includes(query) || item.code.toLowerCase().includes(query)
  );

  list.sort((a, b) => {
    const pingA = state.countryPings.get(a.code);
    const pingB = state.countryPings.get(b.code);
    const rank = (ping) =>
      typeof ping === 'number' ? ping : ping === null ? 1e9 + 1 : 1e9;
    const diff = rank(pingA) - rank(pingB);
    if (diff !== 0) return diff;
    return b.total - a.total;
  });

  if (!list.length) {
    grid.innerHTML = '<div class="proxy-status">Ничего не найдено. Попробуйте другой запрос.</div>';
    return;
  }

  const scroll = grid.scrollTop;
  grid.innerHTML = list
    .slice(0, 160)
    .map((item) => {
      const best = state.countryPings.get(item.code);
      const pingClass =
        best === undefined ? '' : best === null ? 'bad' : best < 350 ? 'good' : best < 900 ? 'mid' : 'bad';
      const pingText =
        best === undefined
          ? state.countryPingsLoading
            ? '<span class="ping-spinner"></span> пинг…'
            : 'пинг…'
          : best === null
            ? 'нет ответа'
            : 'лучший ' + best + ' мс';
      return `<button class="country-card ${
        state.selectedCountry === item.code ? 'active' : ''
      }" data-country="${item.code}" data-name="${escapeHtml(item.name)}" title="Подключиться: ${escapeHtml(
        item.name
      )}">
        <span class="country-flag">
          <img class="country-flag-img" src="https://flagcdn.com/w40/${item.code.toLowerCase()}.png" alt="" loading="lazy" />
          <span class="country-flag-fallback">${item.code}</span>
        </span>
        <span class="country-main">
          <span class="country-name">${escapeHtml(item.name)}</span>
          <span class="country-best ${pingClass}">${pingText}</span>
        </span>
        <span class="country-count">${item.total}</span>
      </button>`;
    })
    .join('');
  grid.scrollTop = scroll;
  attachFlags(grid);
}

function showNodes(code, name) {
  const panel = $('#nodes-panel');
  if (!panel) return;
  state.nodes = [];
  state.nodesMeta = null;
  panel.hidden = false;
  $('#nodes-country').textContent = name || code;
  $('#nodes-meta').textContent = 'Замеряем пинг и доступность…';
  $('#node-list').innerHTML =
    '<div class="node-loading"><span class="net-spinner"></span> Проверяем узлы в реальном времени…</div>';
}

async function loadNodes(code, force = false) {
  if (!code) return;
  try {
    const data = await window.hub.netNodes(code, force);
    if (state.selectedCountry !== code) return;
    state.nodesMeta = data;
    state.nodes = data.nodes || [];
    renderNodes();

    const best = state.nodes
      .filter((node) => node.available)
      .map((node) => node.ping)
      .sort((a, b) => a - b)[0];
    if (best !== undefined) {
      state.countryPings.set(code, best);
      state.countryPingsLoaded = true;
      renderCountries();
      updateBestServer();
    }
  } catch (error) {
    if (state.selectedCountry !== code) return;
    const list = $('#node-list');
    if (list) {
      list.innerHTML = `<div class="node-loading">Не удалось проверить узлы: ${escapeHtml(
        error.message
      )}</div>`;
    }
  }
}

function renderNodes() {
  const panel = $('#nodes-panel');
  const list = $('#node-list');
  if (!panel || panel.hidden || !list) return;

  const meta = state.nodesMeta;
  const nodes = state.nodes;
  const net = state.network;
  const available = nodes.filter((node) => node.available).length;
  const metaNode = $('#nodes-meta');
  if (metaNode) {
    metaNode.textContent = meta?.ok
      ? `${available} из ${nodes.length} доступны · проверено ${new Date(
          meta.checkedAt
        ).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`
      : 'Проверка не удалась';
  }

  if (!nodes.length) {
    list.innerHTML = '<div class="node-loading">Нет узлов для этой страны.</div>';
    return;
  }

  list.innerHTML = nodes
    .map((node, index) => {
      const connected =
        net.status === 'connected' &&
        net.proxy &&
        net.proxy.host === node.host &&
        Number(net.proxy.port) === Number(node.port);
      const pingClass = !node.available
        ? 'bad'
        : node.ping < 350
          ? 'good'
          : node.ping < 900
            ? 'mid'
            : 'bad';
      const pingText = node.available ? node.ping + ' мс' : 'нет ответа';
      return `<div class="node-row ${connected ? 'connected' : ''}">
        <span class="node-ping ${pingClass}">${pingText}</span>
        <span class="node-addr" title="${escapeHtml(node.host)}:${node.port}">${escapeHtml(
          node.host
        )}:${node.port}</span>
        <span class="node-city">${escapeHtml(node.city || '')}</span>
        <button class="btn mini ${connected ? 'on' : ''}" data-node-index="${index}" ${
          !node.available || connected ? 'disabled' : ''
        }>${connected ? 'Активен' : node.available ? 'Подключить' : 'Недоступен'}</button>
      </div>`;
    })
    .join('');
}

function selectCountry(code, name) {
  state.selectedCountry = code;
  state.selectedCountryName = name || code;
  renderCountries();
  showNodes(code, state.selectedCountryName);
  loadNodes(code);
  connectCountryProxy(code, state.selectedCountryName);
}

async function connectSpecificNode(node) {
  if (!node || !node.available) return;
  const status = $('#proxy-status');
  if (status) {
    status.className = 'proxy-status';
    status.textContent = `Подключение: ${node.host}:${node.port}…`;
  }
  try {
    const result = await window.hub.connectNode({
      host: node.host,
      port: node.port,
      code: state.selectedCountry,
      name: state.selectedCountryName,
      ping: node.ping,
    });
    applyNetworkState(result);
    renderNodes();
  } catch (error) {
    if (status) {
      status.className = 'proxy-status error';
      status.textContent = error.message;
    }
  }
}

async function connectCountryProxy(code, name) {
  state.selectedCountry = code;
  state.selectedCountryName = name || code;
  state.networkBusy = true;
  renderCountries();
  const status = $('#proxy-status');
  if (status) {
    status.className = 'proxy-status';
    status.textContent = `Подключение: ${name}…`;
  }
  try {
    const result = await window.hub.proxyConnect({ code, name });
    applyNetworkState(result);
  } catch (error) {
    if (status) {
      status.className = 'proxy-status error';
      status.textContent = error.message;
    }
  } finally {
    state.networkBusy = false;
  }
}

async function connectTor() {
  try {
    applyNetworkState(await window.hub.torConnect(true));
  } catch (error) {
    flashStatus('Не удалось запустить Tor: ' + error.message, 'error');
  }
}

async function newTorRoute() {
  try {
    applyNetworkState(await window.hub.torNewRoute());
  } catch (error) {
    flashStatus('Не удалось обновить маршрут Tor: ' + error.message, 'error');
  }
}

function openTorBrowser() {
  closeNetwork();
  const params = new URLSearchParams();
  if (state.network.ip) params.set('ip', state.network.ip);
  if (state.network.upstream?.countryName) {
    params.set('via', state.network.upstream.countryName);
  }
  const query = params.toString();
  window.hub.openTab('recon://start' + (query ? '?' + query : ''));
  flashStatus(
    'Tor-браузер открыт' + (state.network.ip ? ' · IP ' + state.network.ip : ''),
    'success'
  );
}

async function disconnectNetwork() {
  try {
    applyNetworkState(await window.hub.netDisconnect());
  } catch (error) {
    flashStatus('Не удалось отключить сеть: ' + error.message, 'error');
  }
}

async function connectCustomProxy() {
  const payload = {
    type: $('#proxy-type')?.value || 'socks5',
    host: $('#proxy-host')?.value.trim() || '',
    port: Number($('#proxy-port')?.value || 0),
    username: $('#proxy-user')?.value.trim() || '',
    password: $('#proxy-pass')?.value || '',
  };
  const status = $('#custom-status');
  if (!payload.host || !payload.port) {
    if (status) {
      status.className = 'proxy-status error';
      status.textContent = 'Заполните хост и порт.';
    }
    return;
  }
  if (status) {
    status.className = 'proxy-status';
    status.textContent = 'Проверка прокси…';
  }
  try {
    applyNetworkState(await window.hub.customConnect(payload));
  } catch (error) {
    if (status) {
      status.className = 'proxy-status error';
      status.textContent = error.message;
    }
  }
}

async function checkCurrentIp() {
  if (state.ipChecking) return;
  state.ipChecking = true;
  renderNetwork();
  try {
    const result = await window.hub.checkIp();
    if (result.ok) {
      state.network.ip = result.ip;
      flashStatus('Текущий выходной IP: ' + result.ip, 'success');
    } else {
      flashStatus('Не удалось проверить IP: ' + result.error, 'error');
    }
  } catch (error) {
    flashStatus('Не удалось проверить IP: ' + error.message, 'error');
  } finally {
    state.ipChecking = false;
    renderNetwork();
  }
}

/* ------------------------------------------------------- rendering */

function catCardHTML(cat) {
  return `<button class="cat-card" data-cat="${cat.id}" style="--tint:${cat.color}">
    <span class="cat-card-ico">${cat.icon}</span>
    <span class="cat-card-name">${escapeHtml(cat.name)}</span>
    <span class="cat-card-count">${cat.tools.length}</span>
    <span class="cat-card-note">${escapeHtml(cat.note)}</span>
  </button>`;
}

function tileHTML(tool, options = {}) {
  const favorite = isFavorite(tool.u);
  const infoKey = tool.key || 'url::' + tool.u;
  return `<div class="tile" role="button" tabindex="0" data-key="${escapeHtml(tool.key || '')}" data-url="${escapeHtml(
    tool.u
  )}" style="--tint:${tool.color || '#5eead4'}" title="${escapeHtml(tool.n + ' — ' + tool.d)}">
    <button class="tile-info" data-info="${escapeHtml(infoKey)}" title="Что это за сайт"
            aria-label="Информация: ${escapeHtml(tool.n)}">i</button>
    ${iconMarkup(tool)}
    <span class="tile-body">
      <span class="tile-name">${escapeHtml(tool.n)}</span>
      <span class="tile-host">${
        options.showCat ? `<span class="tile-cat">${escapeHtml(tool.catName || '')}</span>` : ''
      }${escapeHtml(tool.host)}</span>
    </span>
    <button class="tile-star ${favorite ? 'on' : ''}" data-star="${escapeHtml(
      tool.u
    )}" title="Добавить в избранное" aria-label="Добавить в избранное">
      <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M10 2.9l2.2 4.5 4.9.7-3.6 3.5.9 4.9-4.4-2.3-4.4 2.3.9-4.9L2.9 8.1l4.9-.7z" /></svg>
    </button>
  </div>`;
}

function tileShelfHTML(title, items, options = {}) {
  if (!items.length) return '';
  return `<section class="shelf">
    <div class="shelf-head">
      <h2>${escapeHtml(title)}</h2>
      <span class="shelf-count">${items.length}</span>
    </div>
    <div class="tile-grid">${items.map((tool) => tileHTML(tool, options)).join('')}</div>
  </section>`;
}

function opsecHTML() {
  return `<div class="opsec">
    <span class="opsec-ico">🛡️</span>
    <div class="opsec-text">
      <b>OPSEC:</b> работайте в отдельном профиле, не смешивайте расследование с личными аккаунтами,
      проверяйте первоисточники и фиксируйте ссылки с датой. Поиск по лицам, телефонам и утечкам
      регулируется законом — используйте только в законных целях.
    </div>
  </div>`;
}

function homeHTML() {
  const favorites = state.favorites.map(normalizeFavorite);
  const recents = state.recents;
  return `<section class="hero">
      <div class="hero-kicker">collection console · chromium engine</div>
      <h1>Инструменты открытой разведки<br /><span class="grad">в одном окне</span></h1>
      <p>${TOOLS.length} сервисов в ${CATS.length} категориях. Выберите плитку — сайт откроется
         во встроенном браузере, а вкладки останутся под рукой.</p>
      <div class="hero-search">
        <svg class="search-ico" viewBox="0 0 20 20" aria-hidden="true">
          <circle cx="8.8" cy="8.8" r="5.4" />
          <path d="M12.9 12.9l3.8 3.8" />
        </svg>
        <input id="hero-search" type="text" placeholder="Найти инструмент: Shodan, VK, геолокация…"
               autocomplete="off" spellcheck="false" />
        <span class="keyhint">Ctrl K</span>
      </div>
      <div class="hero-stats">
        <span><b>${TOOLS.length}</b> инструментов</span>
        <span class="sep"></span>
        <span><b>${CATS.length}</b> категорий</span>
        <span class="sep"></span>
        <span>Chromium <b id="hero-chrome">${escapeHtml(state.versions.chrome)}</b></span>
        <span class="sep"></span>
        <span>Избранное хранится локально</span>
      </div>
    </section>

    <section class="shelf">
      <div class="shelf-head">
        <h2>Категории</h2>
        <span class="shelf-count">${CATS.length}</span>
      </div>
      <div class="cat-grid">${CATS.map(catCardHTML).join('')}</div>
    </section>

    ${tileShelfHTML('Избранное', favorites)}
    ${tileShelfHTML('Недавние', recents, { showCat: true })}

    ${opsecHTML()}`;
}

function categoryHTML(cat) {
  return `<div class="page-head">
      <button class="crumb" data-home>
        <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M11.5 4.5L6 10l5.5 5.5" /></svg>
        Библиотека
      </button>
      <div class="page-title">
        <span class="page-ico" style="--tint:${cat.color}">${cat.icon}</span>
        <div class="page-title-text">
          <h1>${escapeHtml(cat.name)}</h1>
          <p>${escapeHtml(cat.note)}</p>
        </div>
        <span class="page-pill">${cat.tools.length} ${plural(cat.tools.length, 'инструмент', 'инструмента', 'инструментов')}</span>
      </div>
    </div>
    <div class="tile-grid">${cat.tools.map((tool) => tileHTML(tool)).join('')}</div>`;
}

function favoritesHTML() {
  const favorites = state.favorites.map(normalizeFavorite);
  if (!favorites.length) {
    return `<div class="page-head">
        <span class="page-title">
          <span class="page-ico" style="--tint:#fbbf24">⭐</span>
          <span class="page-title-text"><h1>Избранное</h1><p>Быстрый доступ к нужным сервисам</p></span>
        </span>
      </div>
      <div class="empty">
        <div class="empty-ico">☆</div>
        <h3>Пока пусто</h3>
        <p>Нажмите на звёздочку на плитке инструмента или в адресной строке открытого сайта —
           он появится здесь.</p>
        <button data-home>Перейти к категориям</button>
      </div>`;
  }
  return `<div class="page-head">
      <div class="page-title">
        <span class="page-ico" style="--tint:#fbbf24">⭐</span>
        <div class="page-title-text">
          <h1>Избранное</h1>
          <p>Сохранённые инструменты и вкладки</p>
        </div>
        <span class="page-pill">${favorites.length} ${plural(favorites.length, 'запись', 'записи', 'записей')}</span>
      </div>
    </div>
    <div class="tile-grid">${favorites.map((tool) => tileHTML(tool, { showCat: true })).join('')}</div>`;
}

function scoreTool(tool, query) {
  const name = tool.n.toLowerCase();
  if (name.startsWith(query)) return 0;
  if (name.includes(query)) return 1;
  if (tool.host.includes(query)) return 2;
  if (tool.catName.toLowerCase().includes(query)) return 3;
  return 4;
}

function searchTools(query) {
  const needle = query.trim().toLowerCase();
  if (!needle) return [];
  return TOOLS.filter((tool) =>
    (tool.n + ' ' + tool.d + ' ' + tool.host + ' ' + tool.catName).toLowerCase().includes(needle)
  ).sort((a, b) => scoreTool(a, needle) - scoreTool(b, needle) || a.n.localeCompare(b.n));
}

function searchResultsMarkup(query) {
  const trimmed = query.trim();
  if (!trimmed) {
    return `<div class="empty">
      <div class="empty-ico">⌕</div>
      <h3>Начните вводить запрос</h3>
      <p>Ищите по названию, описанию, домену или категории. Например: «shodan», «telegram», «домены».</p>
    </div>`;
  }
  const results = searchTools(trimmed);
  if (!results.length) {
    return `<div class="empty">
      <div class="empty-ico">🛰️</div>
      <h3>Ничего не найдено</h3>
      <p>По запросу «${escapeHtml(trimmed)}» инструментов нет. Попробуйте другое слово или откройте категорию.</p>
      <button data-home>К категориям</button>
    </div>`;
  }
  return results.map((tool) => tileHTML(tool, { showCat: true })).join('');
}

function searchHTML(query) {
  const trimmed = query.trim();
  const count = trimmed ? searchTools(trimmed).length : 0;
  return `<div class="search-head">
      <div class="search-head-text">
        <h1>Поиск инструментов</h1>
        <p>По названию, описанию, домену или категории</p>
      </div>
      <div class="spacer"></div>
      ${query ? '<button class="clear-query" data-clear-search>Очистить</button>' : ''}
    </div>
    <div class="hero-search flat">
      <svg class="search-ico" viewBox="0 0 20 20" aria-hidden="true">
        <circle cx="8.8" cy="8.8" r="5.4" />
        <path d="M12.9 12.9l3.8 3.8" />
      </svg>
      <input id="hero-search" type="text" value="${escapeHtml(query)}"
             placeholder="Название, домен или задача…" autocomplete="off" spellcheck="false" />
      <span class="keyhint">${trimmed ? count : 'Ctrl K'}</span>
    </div>
    <p class="search-meta" id="search-meta">${
      trimmed
        ? `Найдено <b>${count}</b> из ${TOOLS.length} · запрос «${escapeHtml(trimmed)}»`
        : 'Введите запрос, чтобы отфильтровать каталог'
    }</p>
    <div class="tile-grid" id="search-results">${searchResultsMarkup(query)}</div>`;
}

function renderSidebar() {
  $('#nav-total').textContent = TOOLS.length;
  $('#nav-favs').textContent = state.favorites.length;
  $('#nav-cats').textContent = CATS.length;

  $('#cat-menu').innerHTML = CATS.map(
    (cat) => `<button class="cat-item ${
      state.view.type === 'category' && state.view.catId === cat.id ? 'active' : ''
    }" data-cat="${cat.id}" style="--tint:${cat.color}" title="${escapeHtml(cat.note)}">
      <span class="cat-ico">${cat.icon}</span>
      <span class="cat-item-name">${escapeHtml(cat.name)}</span>
      <span class="cat-item-count">${cat.tools.length}</span>
    </button>`
  ).join('');

  $$('.nav-item').forEach((item) => {
    item.classList.toggle('active', state.view.type === item.dataset.view);
  });
}

function renderLibrary(options = {}) {
  const library = $('#library');
  const scroll = options.preserveScroll ? library.scrollTop : 0;
  let inner = '';

  if (state.view.type === 'category') {
    const cat = CAT_BY_ID.get(state.view.catId);
    inner = cat ? categoryHTML(cat) : homeHTML();
  } else if (state.view.type === 'favorites') {
    inner = favoritesHTML();
  } else if (state.view.type === 'search') {
    inner = searchHTML(state.view.query || '');
  } else {
    inner = homeHTML();
  }

  library.innerHTML = `<div class="library-inner">${inner}</div>`;
  attachIcons(library);
  if (options.preserveScroll) library.scrollTop = scroll;
  else library.scrollTop = 0;
}

function updateSearchResults() {
  const query = state.view.query || '';
  const results = $('#search-results');
  if (!results) return;
  results.innerHTML = searchResultsMarkup(query);
  attachIcons(results);

  const meta = $('#search-meta');
  const trimmed = query.trim();
  if (meta) {
    meta.innerHTML = trimmed
      ? `Найдено <b>${searchTools(trimmed).length}</b> из ${TOOLS.length} · запрос «${escapeHtml(trimmed)}»`
      : 'Введите запрос, чтобы отфильтровать каталог';
  }
  const hint = $('.hero-search .keyhint');
  if (hint) hint.textContent = trimmed ? String(searchTools(trimmed).length) : 'Ctrl K';
}

/* ------------------------------------------------------------ views */

function setView(view, options = {}) {
  state.view = view;
  deactivateTab();
  if (!options.keepSearch) $('#search').value = '';
  renderSidebar();
  renderLibrary();
  if (options.focusSearch) focusSearchPage();
}

function deactivateTab() {
  if (!state.activeId) return;
  state.activeId = null;
  document.body.classList.remove('has-tab');
  renderTabs();
  updateToolbar();
  window.hub.deactivate();
}

function goHome() {
  setView({ type: 'home', catId: null, query: '' });
}

function focusSearchPage() {
  const input = $('#hero-search');
  if (!input) return;
  input.focus();
  const value = input.value;
  try {
    input.setSelectionRange(value.length, value.length);
  } catch {
    /* ignore */
  }
}

function focusSidebarSearch() {
  const input = $('#search');
  if (!input) return;
  input.focus();
  input.select();
}

/* ------------------------------------------------------------ tabs */

function currentTab() {
  return state.tabs.find((tab) => tab.id === state.activeId) || null;
}

function renderTabs() {
  const strip = $('#tabstrip');
  if (!strip) return;
  const scroll = strip.scrollLeft;

  strip.innerHTML = state.tabs
    .map((tab) => {
      const active = tab.id === state.activeId;
      const letter = escapeHtml((hostOf(tab.url) || tab.title || '?').charAt(0).toUpperCase());
      const favicon = tab.favicon
        ? `<img class="tab-fav" src="${escapeHtml(tab.favicon)}" alt="" data-letter="${letter}" />`
        : `<span class="tab-fav-fallback">${letter}</span>`;
      return `<div class="tab ${active ? 'active' : ''}" data-tab="${tab.id}"
                   title="${escapeHtml(tab.title)}\n${escapeHtml(tab.url)}">
        ${tab.loading ? '<span class="tab-spinner"></span>' : favicon}
        <span class="tab-title">${escapeHtml(tab.title)}</span>
        <button class="tab-close" data-close="${tab.id}" title="Закрыть (Ctrl+W)" aria-label="Закрыть вкладку">
          <svg viewBox="0 0 12 12" aria-hidden="true"><path d="M3 3l6 6M9 3l-6 6" /></svg>
        </button>
      </div>`;
    })
    .join('');

  strip.scrollLeft = scroll;

  $$('img.tab-fav', strip).forEach((img) => {
    img.addEventListener('error', () => {
      const fallback = document.createElement('span');
      fallback.className = 'tab-fav-fallback';
      fallback.textContent = img.dataset.letter || '?';
      img.replaceWith(fallback);
    });
  });
}

function updateToolbar() {
  const tab = currentTab();
  const hasTab = !!tab;
  const address = $('#address');
  const secure = $('#secure-dot');
  const back = $('#btn-back');
  const forward = $('#btn-forward');
  const reload = $('#btn-reload');
  const star = $('#btn-star');
  const external = $('#btn-external');

  back.disabled = !hasTab || !tab.canGoBack;
  forward.disabled = !hasTab || !tab.canGoForward;
  reload.disabled = !hasTab;
  star.disabled = !hasTab;
  external.disabled = !hasTab;

  if (document.activeElement !== address) {
    address.value = hasTab ? tab.url : '';
  }

  secure.classList.toggle('library', !hasTab);
  secure.classList.toggle('insecure', hasTab && !tab.secure);

  star.classList.toggle('on', hasTab && isFavorite(tab.url));
  reload.title = hasTab && tab.loading ? 'Остановить загрузку (Esc)' : 'Обновить (Ctrl+R)';

  $('#status-tabs').textContent = `${state.tabs.length} ${plural(
    state.tabs.length,
    'вкладка',
    'вкладки',
    'вкладок'
  )}`;
  updateStatus();
}

function updateStatus() {
  if (Date.now() < statusLockUntil) return;
  const bar = $('.statusbar');
  bar.classList.remove('loading', 'success', 'error');
  const tab = currentTab();
  const text = $('#status-text');
  if (!tab) {
    text.textContent = 'Библиотека инструментов · выберите плитку';
  } else if (tab.loading) {
    bar.classList.add('loading');
    text.textContent = 'Загрузка · ' + hostOf(tab.url);
  } else {
    text.textContent = 'Готово · ' + hostOf(tab.url);
  }
}

function flashStatus(message, kind = 'info') {
  const bar = $('.statusbar');
  bar.classList.remove('loading', 'success', 'error');
  if (kind === 'success') bar.classList.add('success');
  if (kind === 'error') bar.classList.add('error');
  $('#status-text').textContent = message;
  statusLockUntil = Date.now() + 6000;
  clearTimeout(statusTimer);
  statusTimer = setTimeout(updateStatus, 6100);
}

/* ---------------------------------------------------------- events */

function bindEvents() {
  /* окно */
  $('#win-min').addEventListener('click', () => window.hub.minimize());
  $('#win-max').addEventListener('click', () => window.hub.toggleMaximize());
  $('#win-close').addEventListener('click', () => window.hub.closeWindow());
  $('#titlebar').addEventListener('dblclick', (event) => {
    if (event.target.closest('button, .tab, .win-controls')) return;
    window.hub.toggleMaximize();
  });

  const resizeGrip = $('#resize-grip');
  if (resizeGrip) {
    let resizing = false;
    resizeGrip.addEventListener('pointerdown', (event) => {
      event.preventDefault();
      resizing = true;
      try {
        resizeGrip.setPointerCapture(event.pointerId);
      } catch {
        /* ignore */
      }
      window.hub.resizeStart({ x: event.screenX, y: event.screenY });
    });
    resizeGrip.addEventListener('pointermove', (event) => {
      if (!resizing) return;
      window.hub.resizeMove({ x: event.screenX, y: event.screenY });
    });
    const stopResize = (event) => {
      if (!resizing) return;
      resizing = false;
      try {
        resizeGrip.releasePointerCapture(event.pointerId);
      } catch {
        /* ignore */
      }
      window.hub.resizeEnd();
    };
    resizeGrip.addEventListener('pointerup', stopResize);
    resizeGrip.addEventListener('pointercancel', stopResize);
  }

  $('#btn-sidebar').addEventListener('click', () => {
    state.collapsed = !state.collapsed;
    $('#app').classList.toggle('collapsed', state.collapsed);
    writeStore('recon.sidebarCollapsed', state.collapsed);
    $('#btn-sidebar').title = state.collapsed ? 'Показать меню' : 'Свернуть меню';
  });

  $('#brand').addEventListener('click', goHome);
  $('#btn-newtab').addEventListener('click', goHome);

  /* навигация браузера */
  $('#btn-back').addEventListener('click', () => {
    const tab = currentTab();
    if (tab) window.hub.tabAction(tab.id, 'back');
  });
  $('#btn-forward').addEventListener('click', () => {
    const tab = currentTab();
    if (tab) window.hub.tabAction(tab.id, 'forward');
  });
  $('#btn-reload').addEventListener('click', () => {
    const tab = currentTab();
    if (!tab) return;
    window.hub.tabAction(tab.id, tab.loading ? 'stop' : 'reload');
  });
  $('#btn-external').addEventListener('click', () => {
    const tab = currentTab();
    if (tab) window.hub.tabAction(tab.id, 'external');
  });
  $('#btn-star').addEventListener('click', () => {
    const tab = currentTab();
    if (!tab) return;
    toggleFavorite({ key: 'url::' + tab.url, n: tab.title, u: tab.url, d: 'Сохранённая вкладка' });
  });
  $('#btn-menu').addEventListener('click', (event) => {
    const rect = event.currentTarget.getBoundingClientRect();
    window.hub.openMenu('browser', { x: rect.right - 4, y: rect.bottom + 2 }, state.activeId);
  });
  $('#btn-settings').addEventListener('click', (event) => {
    const rect = event.currentTarget.getBoundingClientRect();
    window.hub.openMenu('app', { x: rect.right - 4, y: rect.top - 4 }, null);
  });
  $('#btn-about').addEventListener('click', openAppInfo);

  /* модальное окно информации */
  $$('[data-close-modal]').forEach((element) => element.addEventListener('click', closeInfo));
  $('#info-open').addEventListener('click', () => {
    if (!modalEntry) return;
    if (modalEntry.type === 'tool') {
      const tool = modalEntry.tool;
      closeInfo();
      openToolEntry(tool);
    } else {
      closeInfo();
    }
  });
  $('#info-fav').addEventListener('click', () => {
    if (!modalEntry || modalEntry.type !== 'tool') return;
    toggleFavorite(modalEntry.tool);
    updateInfoFavorite();
  });
  $('#info-copy').addEventListener('click', async () => {
    if (!modalEntry || modalEntry.type !== 'tool') return;
    await window.hub.copy(modalEntry.tool.u);
    flashStatus('Ссылка скопирована в буфер обмена', 'success');
  });

  /* сетевая панель */
  $('#btn-network').addEventListener('click', () => openNetwork('tor'));
  $$('[data-close-net]').forEach((element) => element.addEventListener('click', closeNetwork));
  $$('.net-tab').forEach((button) =>
    button.addEventListener('click', () => selectNetTab(button.dataset.netTab))
  );
  $('#tor-connect').addEventListener('click', connectTor);
  $('#tor-newid').addEventListener('click', newTorRoute);
  $('#tor-open-browser').addEventListener('click', openTorBrowser);
  $('#net-disconnect').addEventListener('click', disconnectNetwork);
  $('#net-check').addEventListener('click', checkCurrentIp);

  $('#country-search').addEventListener('input', (event) => {
    state.countryQuery = event.target.value;
    renderCountries();
  });
  $('#country-refresh').addEventListener('click', () => {
    state.countries = [];
    loadCountries(true);
  });
  $('#best-server').addEventListener('click', () => {
    if (!state.bestServer) return;
    selectCountry(state.bestServer.code, state.bestServer.name);
  });

  $('#country-grid').addEventListener('click', (event) => {
    const card = event.target.closest('[data-country]');
    if (!card) return;
    selectCountry(card.dataset.country, card.dataset.name);
  });

  $('#node-list').addEventListener('click', (event) => {
    const button = event.target.closest('[data-node-index]');
    if (!button) return;
    const node = state.nodes[Number(button.dataset.nodeIndex)];
    if (node) connectSpecificNode(node);
  });

  $('#connect-best').addEventListener('click', () => {
    if (!state.selectedCountry) return;
    connectCountryProxy(state.selectedCountry, state.selectedCountryName);
  });

  $('#nodes-refresh').addEventListener('click', () => {
    if (!state.selectedCountry) return;
    loadNodes(state.selectedCountry, true);
  });

  $('#proxy-custom-connect').addEventListener('click', connectCustomProxy);

  window.hub.onNetwork((next) => applyNetworkState(next));
  window.hub.onTorReady(async () => {
    try {
      applyNetworkState(await window.hub.netState());
    } catch {
      /* ignore */
    }
    openTorBrowser();
  });

  /* адресная строка */
  const address = $('#address');
  address.addEventListener('focus', () => address.select());
  address.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      const value = address.value.trim();
      if (!value) return;
      const tab = currentTab();
      if (tab) {
        window.hub.tabAction(tab.id, 'navigate', value);
      } else {
        window.hub.openTab(value);
      }
      address.blur();
    } else if (event.key === 'Escape') {
      const tab = currentTab();
      address.value = tab ? tab.url : '';
      address.blur();
      if (tab) window.hub.tabAction(tab.id, 'focus');
    }
  });
  address.addEventListener('blur', () => {
    const tab = currentTab();
    if (document.activeElement !== address) address.value = tab ? tab.url : '';
  });

  /* вкладки */
  const strip = $('#tabstrip');
  strip.addEventListener('click', (event) => {
    const close = event.target.closest('[data-close]');
    if (close) {
      event.stopPropagation();
      window.hub.closeTab(close.dataset.close);
      return;
    }
    const tab = event.target.closest('[data-tab]');
    if (!tab) return;
    state.activeId = tab.dataset.tab;
    document.body.classList.add('has-tab');
    renderTabs();
    updateToolbar();
    window.hub.activateTab(tab.dataset.tab);
  });
  strip.addEventListener('auxclick', (event) => {
    if (event.button !== 1) return;
    const tab = event.target.closest('[data-tab]');
    if (!tab) return;
    event.preventDefault();
    window.hub.closeTab(tab.dataset.tab);
  });
  strip.addEventListener(
    'wheel',
    (event) => {
      if (Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return;
      strip.scrollLeft += event.deltaY;
      event.preventDefault();
    },
    { passive: false }
  );

  /* боковое меню */
  $('#side-nav').addEventListener('click', (event) => {
    const nav = event.target.closest('[data-view]');
    if (nav) {
      if (nav.dataset.view === 'home') goHome();
      else if (nav.dataset.view === 'vpn') openNetwork('countries');
      else setView({ type: 'favorites', catId: null, query: '' });
      return;
    }
    const cat = event.target.closest('[data-cat]');
    if (cat) {
      setView({ type: 'category', catId: cat.dataset.cat, query: '' });
    }
  });

  /* поиск в сайдбаре */
  const sideSearch = $('#search');
  sideSearch.addEventListener('input', () => {
    const query = sideSearch.value;
    const wasSearch = state.view.type === 'search';
    deactivateTab();
    state.view = { type: 'search', catId: null, query };
    renderSidebar();
    if (wasSearch) {
      updateSearchResults();
      const pageInput = $('#hero-search');
      if (pageInput && document.activeElement !== pageInput) pageInput.value = query;
    } else {
      renderLibrary();
      const pageInput = $('#hero-search');
      if (pageInput && query) {
        pageInput.value = query;
        pageInput.focus();
        try {
          pageInput.setSelectionRange(query.length, query.length);
        } catch {
          /* ignore */
        }
      }
    }
  });
  sideSearch.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      sideSearch.value = '';
      goHome();
    }
  });

  /* библиотека */
  const library = $('#library');

  library.addEventListener('input', (event) => {
    if (event.target.id !== 'hero-search') return;
    const query = event.target.value;
    const wasSearch = state.view.type === 'search';
    state.view = { type: 'search', catId: null, query };
    renderSidebar();
    if (wasSearch) {
      updateSearchResults();
    } else {
      renderLibrary();
      focusSearchPage();
    }
  });

  library.addEventListener('click', (event) => {
    const star = event.target.closest('[data-star]');
    if (star) {
      event.stopPropagation();
      const url = star.dataset.star;
      const tool = TOOLS.find((item) => item.u === url) || { key: 'url::' + url, n: hostOf(url), u: url, d: '' };
      toggleFavorite(tool);
      return;
    }

    const info = event.target.closest('[data-info]');
    if (info) {
      event.stopPropagation();
      const tool = findToolByKey(info.dataset.info);
      if (tool) openInfo({ type: 'tool', tool });
      return;
    }

    const clear = event.target.closest('[data-clear-search]');
    if (clear) {
      state.view = { type: 'search', catId: null, query: '' };
      $('#search').value = '';
      renderSidebar();
      renderLibrary();
      focusSearchPage();
      return;
    }

    const home = event.target.closest('[data-home]');
    if (home) {
      goHome();
      return;
    }

    const cat = event.target.closest('[data-cat]');
    if (cat) {
      setView({ type: 'category', catId: cat.dataset.cat, query: '' });
      return;
    }

    const tile = event.target.closest('[data-url]');
    if (tile) {
      const tool =
        findToolByKey(tile.dataset.key) || TOOL_BY_URL.get(tile.dataset.url) || null;
      openToolEntry(tool, tile.dataset.url);
    }
  });

  library.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    if (event.target.closest('button')) return;
    const tile = event.target.closest('.tile');
    if (!tile) return;
    event.preventDefault();
    const tool = findToolByKey(tile.dataset.key) || TOOL_BY_URL.get(tile.dataset.url);
    openToolEntry(tool, tile.dataset.url);
  });

  document.addEventListener('contextmenu', (event) => event.preventDefault());

  /* горячие клавиши (когда фокус в интерфейсе) */
  document.addEventListener('keydown', (event) => {
    const infoOpen = !$('#info-modal').hidden;
    const netOpen = !$('#net-modal').hidden;
    if (infoOpen || netOpen) {
      if (event.key === 'Escape') {
        event.preventDefault();
        if (infoOpen) closeInfo();
        if (netOpen) closeNetwork();
      }
      return;
    }

    const ctrl = event.ctrlKey || event.metaKey;
    const key = event.key.toLowerCase();

    if (ctrl && key === 'k') {
      event.preventDefault();
      focusSidebarSearch();
      return;
    }
    if (ctrl && key === 'l') {
      event.preventDefault();
      $('#address').focus();
      return;
    }
    if (ctrl && key === 't') {
      event.preventDefault();
      goHome();
      return;
    }
    if (ctrl && key === 'w' && state.activeId) {
      event.preventDefault();
      window.hub.closeTab(state.activeId);
      return;
    }
    if (ctrl && key === 'd' && state.activeId) {
      event.preventDefault();
      const tab = currentTab();
      if (tab) toggleFavorite({ key: 'url::' + tab.url, n: tab.title, u: tab.url, d: 'Сохранённая вкладка' });
      return;
    }
    if (ctrl && key === 'r' && state.activeId) {
      event.preventDefault();
      window.hub.tabAction(state.activeId, 'reload');
      return;
    }
    if (event.key === 'F5' && state.activeId) {
      event.preventDefault();
      window.hub.tabAction(state.activeId, 'reload');
      return;
    }
    if (event.key === 'Escape') {
      if (document.activeElement === $('#address')) return;
      const search = $('#search');
      if (document.activeElement === search && search.value) {
        search.value = '';
        goHome();
      }
    }
  });

  /* события из main */
  window.hub.onTabs(({ tabs, activeId }) => {
    const hadActive = !!state.activeId;
    state.tabs = tabs;
    state.activeId = activeId;
    document.body.classList.toggle('has-tab', !!activeId);
    renderTabs();
    updateToolbar();
    if (!activeId) {
      if (hadActive) renderLibrary({ preserveScroll: true });
      else if (!$('#library').innerHTML.trim()) renderLibrary();
    }
  });

  window.hub.onWindowState(({ maximized }) => {
    document.body.classList.toggle('maximized', !!maximized);
    $('#win-max').innerHTML = maximized
      ? '<svg viewBox="0 0 12 12" aria-hidden="true"><rect x="2.4" y="3.6" width="6" height="6" rx="1" /><path d="M4.1 3.6V2.4h5.5v5.5H8.4" /></svg>'
      : '<svg viewBox="0 0 12 12" aria-hidden="true"><rect x="2.75" y="2.75" width="6.5" height="6.5" rx="1" /></svg>';
    $('#win-max').title = maximized ? 'Восстановить' : 'Развернуть';
  });

  window.hub.onToast(({ text, kind }) => flashStatus(text, kind));
  window.hub.onFocusSearch(() => focusSidebarSearch());
  window.hub.onFocusAddress(() => {
    const addressInput = $('#address');
    addressInput.focus();
    addressInput.select();
  });
  window.hub.onNewTab(() => goHome());
  window.hub.onToggleFavorite((payload) => {
    if (payload) toggleFavorite({ key: 'url::' + payload.url, n: payload.title, u: payload.url, d: 'Сохранённая вкладка' });
  });
}

/* ------------------------------------------------------- bounds sync */

function setupBounds() {
  const viewport = $('#viewport');
  let frame = 0;

  const send = () => {
    const rect = viewport.getBoundingClientRect();
    if (rect.width < 2 || rect.height < 2) return;
    window.hub.setBounds({
      x: Math.round(rect.x),
      y: Math.round(rect.y),
      width: Math.round(rect.width),
      height: Math.round(rect.height),
    });
  };

  const schedule = () => {
    if (frame) return;
    frame = requestAnimationFrame(() => {
      frame = 0;
      send();
    });
  };

  new ResizeObserver(schedule).observe(viewport);
  window.addEventListener('resize', schedule);
  requestAnimationFrame(send);
  setTimeout(send, 120);
  setTimeout(send, 400);
}

/* ------------------------------------------------------------ init */

async function init() {
  if (state.collapsed) {
    $('#app').classList.add('collapsed');
    $('#btn-sidebar').title = 'Показать меню';
  }

  try {
    state.versions = await window.hub.info();
  } catch {
    /* ignore */
  }

  $('#chrome-ver').textContent = state.versions.chrome || '—';
  $('#status-chrome').textContent = state.versions.chrome || '—';

  try {
    applyNetworkState(await window.hub.netState());
  } catch {
    /* network info is optional */
  }

  bindEvents();
  renderSidebar();
  renderLibrary();
  renderTabs();
  updateToolbar();
  setupBounds();
}

init();
