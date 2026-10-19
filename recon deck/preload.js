'use strict';

const { contextBridge, ipcRenderer } = require('electron');

function subscribe(channel) {
  return (callback) => {
    const handler = (_event, payload) => callback(payload);
    ipcRenderer.on(channel, handler);
    return () => ipcRenderer.removeListener(channel, handler);
  };
}

contextBridge.exposeInMainWorld('hub', {
  /* вкладки */
  openTab: (url) => ipcRenderer.invoke('tab:open', url),
  closeTab: (id) => ipcRenderer.send('tab:close', id),
  activateTab: (id) => ipcRenderer.send('tab:activate', id),
  deactivate: () => ipcRenderer.send('tab:deactivate'),
  tabAction: (id, action, value) => ipcRenderer.send('tab:action', { id, action, value }),
  setBounds: (rect) => ipcRenderer.send('view:bounds', rect),

  /* окно */
  minimize: () => ipcRenderer.send('window:minimize'),
  toggleMaximize: () => ipcRenderer.send('window:toggle-maximize'),
  closeWindow: () => ipcRenderer.send('window:close'),
  resizeStart: (point) => ipcRenderer.send('window:resize-start', point),
  resizeMove: (point) => ipcRenderer.send('window:resize-move', point),
  resizeEnd: () => ipcRenderer.send('window:resize-end'),
  focusWindow: () => ipcRenderer.send('app:window-focus'),

  /* меню и системные действия */
  openMenu: (kind, point, tabId) => ipcRenderer.send('app:menu', { kind, point, tabId }),
  openExternal: (url) => ipcRenderer.send('app:open-external', url),
  copy: (text) => ipcRenderer.invoke('app:copy', text),
  clearSession: () => ipcRenderer.invoke('app:clear-session'),
  info: () => ipcRenderer.invoke('app:info'),

  /* сеть: Tor и прокси */
  netState: () => ipcRenderer.invoke('net:state'),
  netCountries: (force) => ipcRenderer.invoke('net:countries', !!force),
  netNodes: (code, force) => ipcRenderer.invoke('net:nodes', code, !!force),
  countryPings: (codes, force) => ipcRenderer.invoke('net:country-pings', codes, !!force),
  torConnect: (openBrowser) => ipcRenderer.invoke('net:tor-connect', !!openBrowser),
  torNewRoute: () => ipcRenderer.invoke('net:new-route'),
  proxyConnect: (payload) => ipcRenderer.invoke('net:proxy-connect', payload),
  connectNode: (payload) => ipcRenderer.invoke('net:connect-node', payload),
  customConnect: (payload) => ipcRenderer.invoke('net:custom-connect', payload),
  netDisconnect: () => ipcRenderer.invoke('net:disconnect'),
  checkIp: () => ipcRenderer.invoke('net:check-ip'),

  /* события */
  onTabs: subscribe('tabs:state'),
  onWindowState: subscribe('window:state'),
  onToast: subscribe('app:toast'),
  onFocusSearch: subscribe('app:focus-search'),
  onFocusAddress: subscribe('app:focus-address'),
  onNewTab: subscribe('app:new-tab'),
  onToggleFavorite: subscribe('app:toggle-favorite'),
  onNetwork: subscribe('net:state'),
  onTorReady: subscribe('net:tor-ready'),
});
