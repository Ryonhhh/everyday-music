import { $, esc, renderMarkdown, fetchText } from './core.js';

/* ---------- 常量 ---------- */
const LS = {
  provider: 'studio.provider',
  base: 'studio.base',
  model: 'studio.model',
  key: 'studio.key',
  remember: 'studio.remember',
};

const PRESETS = {
  openai: [
    { label: 'DeepSeek', base: 'https://api.deepseek.com/v1', model: 'deepseek-chat' },
    { label: 'OpenAI', base: 'https://api.openai.com/v1', model: 'gpt-4o' },
    { label: 'Moonshot', base: 'https://api.moonshot.cn/v1', model: 'kimi-k2-0905-preview' },
    { label: 'OpenRouter', base: 'https://openrouter.ai/api/v1', model: 'anthropic/claude-sonnet-4' },
  ],
  anthropic: [
    { label: 'Claude Sonnet', base: 'https://api.anthropic.com', model: 'claude-sonnet-4-20250514' },
    { label: 'Claude Haiku', base: 'https://api.anthropic.com', model: 'claude-3-5-haiku-latest' },
  ],
};

const state = {
  album: null,
  prompt: '',
  controller: null,
  markdown: '',
  busy: false,
};

/* ---------- 搜索 ---------- */
function art(r, size = 300) {
  const raw = r.artworkUrl100 || '';
  return raw.replace(/\/\d+x\d+bb\./, `/${size}x${size}bb.`);
}

async function searchAlbums(term) {
  const url = 'https://itunes.apple.com/search?'
    + new URLSearchParams({ term, entity: 'album', limit: '12' });
  const res = await fetch(url, { mode: 'cors' });
  if (!res.ok) throw new Error(`搜索失败（HTTP ${res.status}）`);
  const data = await res.json();
  return (data.results || []).filter(r => r.collectionName);
}

function renderResults(items) {
  const ul = $('results');
  if (!items.length) {
    ul.hidden = true;
    $('searchHint').textContent = '没搜到。换个写法：加上艺人名，或用英文原名。';
    return;
  }
  ul.innerHTML = items.map((r, i) => `
    <li>
      <button class="result" type="button" data-i="${i}">
        ${r.artworkUrl100 ? `<img src="${esc(art(r, 100))}" alt="" loading="lazy">` : ''}
        <span class="result-main">
          <span class="result-title">${esc(r.collectionName)}</span>
          <span class="result-sub">${esc(r.artistName || '')}${r.releaseDate ? ' · ' + esc(String(r.releaseDate).slice(0, 4)) : ''}${r.trackCount ? ' · ' + r.trackCount + ' 首' : ''}</span>
        </span>
      </button>
    </li>`).join('');
  ul.hidden = false;
  $('searchHint').textContent = `找到 ${items.length} 个结果，点一个继续。`;
  ul.querySelectorAll('.result').forEach(btn => {
    btn.addEventListener('click', () => pick(items[Number(btn.dataset.i)]));
  });
}

function pick(r) {
  state.album = r;
  const year = r.releaseDate ? String(r.releaseDate).slice(0, 4) : '';
  $('fYear').value = year;
  $('fLabel').value = '';

  const links = [
    r.collectionViewUrl ? `<a class="link" href="${esc(r.collectionViewUrl)}" target="_blank" rel="noopener">Apple Music 页面 ↗</a>` : '',
    r.artistViewUrl ? `<a class="link" href="${esc(r.artistViewUrl)}" target="_blank" rel="noopener">艺人页面 ↗</a>` : '',
  ].filter(Boolean).join('　');

  $('picked').innerHTML = `
    <img src="${esc(art(r, 300))}" alt="${esc(r.collectionName)} 封面">
    <div>
      <h3>${esc(r.collectionName)}</h3>
      <p class="byline">${esc(r.artistName || '')}${year ? ' · ' + esc(year) : ''}${r.trackCount ? ' · ' + r.trackCount + ' 首' : ''}${r.primaryGenreName ? ' · ' + esc(r.primaryGenreName) : ''}</p>
      ${links}
    </div>`;

  $('stepPick').hidden = false;
  $('results').hidden = true;
  $('searchHint').textContent = `已选中《${r.collectionName}》。年份与厂牌可以改，拿不准就留空。`;
  $('genBtn').disabled = false;
  $('stepPick').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

/* ---------- 设置 ---------- */
function applyProviderDefaults() {
  const p = $('fProvider').value;
  const list = PRESETS[p] || [];
  const row = $('presetRow');
  row.innerHTML = list.map(c =>
    `<button class="link-btn" type="button" data-base="${esc(c.base)}" data-model="${esc(c.model)}">${esc(c.label)}</button>`
  ).join('');
  row.querySelectorAll('button').forEach(b => b.addEventListener('click', () => {
    $('fBase').value = b.dataset.base;
    $('fModel').value = b.dataset.model;
    saveSettings();
  }));
  if (list[0]) {
    $('fBase').placeholder = list[0].base;
    $('fModel').placeholder = list[0].model;
  }
}

function saveSettings() {
  try {
    localStorage.setItem(LS.provider, $('fProvider').value);
    localStorage.setItem(LS.base, $('fBase').value);
    localStorage.setItem(LS.model, $('fModel').value);
    localStorage.setItem(LS.remember, String($('fRemember').checked));
    if ($('fRemember').checked) localStorage.setItem(LS.key, $('fKey').value);
    else localStorage.removeItem(LS.key);
  } catch (e) { /* 隐私模式忽略 */ }
}

function loadSettings() {
  $('fProvider').value = localStorage.getItem(LS.provider) || 'openai';
  $('fBase').value = localStorage.getItem(LS.base) || 'https://api.deepseek.com/v1';
  $('fModel').value = localStorage.getItem(LS.model) || 'deepseek-chat';
  $('fKey').value = localStorage.getItem(LS.key) || '';
  $('fRemember').checked = localStorage.getItem(LS.remember) !== 'false';
}

/* ---------- prompt 拼装 ---------- */
function buildPrompt() {
  const a = state.album || {};
  const year = $('fYear').value.trim();
  const label = $('fLabel').value.trim();
  const note = $('fNote').value.trim();

  const facts = [
    `专辑：${a.collectionName || ''}`,
    `艺人：${a.artistName || ''}`,
    year ? `年份：${year}` : '',
    label ? `厂牌：${label}` : '',
    a.trackCount ? `曲目数：${a.trackCount}` : '',
    a.primaryGenreName ? `风格标签：${a.primaryGenreName}` : '',
  ].filter(Boolean).join('\n');

  const extra = note ? `\n\n作者希望重点涉及：${note}` : '';

  return state.prompt
    + '\n\n---\n\n现在请为下面这张唱片写一篇解析：\n\n' + facts + extra
    + '\n\n以上元数据可能不完整或有误；与你确知的可靠事实冲突时以可靠事实为准，但任何不确证的内容一律不写。';
}

/* ---------- 流式读取 ---------- */
async function* readSSE(res, pickText) {
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const lines = buf.split('\n');
    buf = lines.pop() || '';
    for (const line of lines) {
      const t = line.trim();
      if (!t.startsWith('data:')) continue;
      const payload = t.slice(5).trim();
      if (payload === '[DONE]') return;
      try {
        const s = pickText(JSON.parse(payload));
        if (s) yield s;
      } catch (e) { /* 忽略心跳与非 JSON 行 */ }
    }
  }
}

async function errorText(res) {
  try {
    const j = await res.json();
    return j.error?.message || j.message || JSON.stringify(j).slice(0, 300);
  } catch (e) {
    return `HTTP ${res.status}`;
  }
}

async function* streamOpenAI(cfg, prompt, signal) {
  const url = cfg.base.replace(/\/+$/, '') + '/chat/completions';
  const res = await fetch(url, {
    method: 'POST',
    signal,
    headers: { 'content-type': 'application/json', Authorization: `Bearer ${cfg.key}` },
    body: JSON.stringify({
      model: cfg.model,
      stream: true,
      temperature: 0.75,
      messages: [
        { role: 'system', content: '你是一位严谨的中文音乐写作者，只写确证的事实。' },
        { role: 'user', content: prompt },
      ],
    }),
  });
  if (!res.ok) throw new Error(await errorText(res));
  yield* readSSE(res, j => j.choices?.[0]?.delta?.content || '');
}

async function* streamAnthropic(cfg, prompt, signal) {
  const url = cfg.base.replace(/\/+$/, '') + '/v1/messages';
  const res = await fetch(url, {
    method: 'POST',
    signal,
    headers: {
      'content-type': 'application/json',
      'x-api-key': cfg.key,
      'anthropic-version': '2023-06-01',
      'anthropic-dangerous-direct-browser-access': 'true',
    },
    body: JSON.stringify({
      model: cfg.model,
      max_tokens: 8192,
      stream: true,
      messages: [{ role: 'user', content: prompt }],
    }),
  });
  if (!res.ok) throw new Error(await errorText(res));
  yield* readSSE(res, j => (j.type === 'content_block_delta' ? (j.delta?.text || '') : ''));
}

/* ---------- 生成 ---------- */
function setStatus(msg, isError = false) {
  const el = $('status');
  el.textContent = msg;
  el.classList.toggle('is-error', isError);
}

async function generate() {
  if (state.busy) return;
  const provider = $('fProvider').value;
  const base = $('fBase').value.trim();
  const model = $('fModel').value.trim();
  const key = $('fKey').value.trim();

  if (!state.album) return setStatus('先搜索并选中一张专辑。', true);
  if (!base) return setStatus('填写 Base URL。', true);
  if (!model) return setStatus('填写模型名。', true);
  if (!key) return setStatus('填写 API Key（只存在本机）。', true);
  if (!state.prompt) return setStatus('prompt 还没载入，刷新页面重试。', true);

  const prompt = buildPrompt();
  state.controller = new AbortController();
  state.markdown = '';
  state.busy = true;

  $('genBtn').disabled = true;
  $('stopBtn').hidden = false;
  $('outActions').hidden = true;
  $('output').hidden = false;
  $('output').innerHTML = '';
  setStatus('连接中…');

  let lastPaint = 0;
  const paint = force => {
    const now = performance.now();
    if (!force && now - lastPaint < 500) return;
    lastPaint = now;
    $('output').innerHTML = renderMarkdown(state.markdown);
  };

  try {
    const stream = provider === 'anthropic'
      ? streamAnthropic({ base, model, key }, prompt, state.controller.signal)
      : streamOpenAI({ base, model, key }, prompt, state.controller.signal);

    for await (const delta of stream) {
      state.markdown += delta;
      paint(false);
      setStatus(`生成中… ${state.markdown.length} 字`);
    }
    paint(true);
    setStatus(`完成，共 ${state.markdown.length} 字。复制或下载后放进 data/albums/。`);
    $('outActions').hidden = false;
  } catch (err) {
    if (err.name === 'AbortError') {
      paint(true);
      setStatus('已停止。');
      if (state.markdown) $('outActions').hidden = false;
    } else {
      const msg = /Failed to fetch|NetworkError|Load failed/i.test(err.message)
        ? '网络请求失败：可能是断网、被防火墙拦截，或该服务商不允许浏览器直接调用（CORS）。'
          + '可以换一个服务商，或检查 Base URL 是否写错。'
        : err.message;
      setStatus(`失败：${msg}`, true);
    }
  } finally {
    state.busy = false;
    $('genBtn').disabled = false;
    $('stopBtn').hidden = true;
    state.controller = null;
  }
}

/* ---------- 输出动作 ---------- */
function slugOf(name) {
  return (name || 'album').toLowerCase()
    .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'album';
}

function download() {
  const a = state.album || {};
  const blob = new Blob([state.markdown], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const el = document.createElement('a');
  el.href = url;
  el.download = `${slugOf(a.collectionName)}.md`;
  el.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
  setStatus('已下载。把它放到 data/albums/<slug>.md。');
}

async function copyText(text, okMsg) {
  try {
    await navigator.clipboard.writeText(text);
    setStatus(okMsg);
  } catch (e) {
    setStatus('复制失败，请手动选择文本。', true);
  }
}

function jsonEntry() {
  const a = state.album || {};
  const id = slugOf(a.collectionName);
  const year = $('fYear').value.trim();
  const label = $('fLabel').value.trim();
  const entry = {
    id,
    title: a.collectionName || '',
    artist: a.artistName || '',
    year,
    kicker: '专辑解析',
    byline: [a.artistName, year].filter(Boolean).join(' · '),
    cover: `data/albums/${id}/cover.jpg`,
    coverAlt: `${a.collectionName} 专辑封面`,
    facts: [
      { k: '艺人', v: a.artistName || '' },
      { k: '发行', v: year },
      a.trackCount ? { k: '曲目', v: `${a.trackCount} 首` } : null,
      label ? { k: '厂牌', v: label } : null,
    ].filter(Boolean),
    listen: [
      a.collectionViewUrl ? { platform: 'Apple Music', url: a.collectionViewUrl } : null,
    ].filter(Boolean),
    more: [],
    summary: '',
    addedAt: new Date().toISOString().slice(0, 10),
  };
  return JSON.stringify(entry, null, 2);
}

/* ---------- 事件与初始化 ---------- */
function wire() {
  $('searchForm').addEventListener('submit', async e => {
    e.preventDefault();
    const q = $('q').value.trim();
    if (!q) return;
    $('searchHint').textContent = '搜索中…';
    try {
      renderResults(await searchAlbums(q));
    } catch (err) {
      $('searchHint').textContent = `搜索失败：${err.message}`;
    }
  });

  $('fProvider').addEventListener('change', () => {
    applyProviderDefaults();
    saveSettings();
  });
  ['fBase', 'fModel', 'fKey', 'fRemember'].forEach(id => {
    $(id).addEventListener('change', saveSettings);
  });
  $('clearKey').addEventListener('click', () => {
    localStorage.removeItem(LS.key);
    $('fKey').value = '';
    setStatus('已清除本机保存的密钥。');
  });

  $('genBtn').addEventListener('click', generate);
  $('stopBtn').addEventListener('click', () => state.controller?.abort());
  $('downloadBtn').addEventListener('click', download);
  $('copyBtn').addEventListener('click', () => copyText(state.markdown, '正文已复制。'));
  $('jsonBtn').addEventListener('click', () => copyText(jsonEntry(), 'index.json 条目已复制，粘到 albums 数组里即可。'));
}

async function init() {
  loadSettings();
  applyProviderDefaults();
  wire();
  $('fKey').value = localStorage.getItem(LS.key) || $('fKey').value;
  try {
    state.prompt = await fetchText('data/prompts/album-analysis.md');
    $('promptBox').textContent = state.prompt;
  } catch (e) {
    $('promptBox').textContent = 'prompt 载入失败：' + e.message;
    setStatus('prompt 载入失败，生成会不可用。', true);
  }
}

init();

