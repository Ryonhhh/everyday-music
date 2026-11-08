/**
 * 创作台的资料抓取：只用开放跨域、无需密钥的公开接口。
 *  - Wikipedia（en / zh）摘要
 *  - MusicBrainz 发行信息与曲目表
 * 抓到的内容会拼成「参考材料」塞进 prompt，模型据此写作。
 */

const WIKI_LIMIT = 6000;   // 每种语言最多取多少字
const MB_DELAY = 1100;     // MusicBrainz 限速：每秒最多一个请求

const sleep = ms => new Promise(r => setTimeout(r, ms));

function trimAtSentence(text, limit) {
  if (text.length <= limit) return text;
  const cut = text.slice(0, limit);
  const end = Math.max(cut.lastIndexOf('。'), cut.lastIndexOf('. '), cut.lastIndexOf('\n'));
  return (end > limit * 0.6 ? cut.slice(0, end + 1) : cut) + '……';
}

async function getJson(url) {
  const res = await fetch(url, { headers: { Accept: 'application/json' } });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

/* ---------- Wikipedia ---------- */
async function wikiSearch(lang, term) {
  const url = `https://${lang}.wikipedia.org/w/api.php?`
    + new URLSearchParams({
      action: 'query', list: 'search', srsearch: term, srlimit: '5',
      format: 'json', origin: '*',
    });
  const data = await getJson(url);
  return (data.query?.search || []).map(x => x.title);
}

async function wikiExtract(lang, title) {
  const url = `https://${lang}.wikipedia.org/w/api.php?`
    + new URLSearchParams({
      action: 'query', prop: 'extracts', explaintext: '1', redirects: '1',
      format: 'json', origin: '*', titles: title,
    });
  const data = await getJson(url);
  const pages = data.query?.pages || {};
  const page = Object.values(pages)[0];
  if (!page || page.missing !== undefined || !page.extract) return null;
  return {
    title: page.title,
    url: `https://${lang}.wikipedia.org/wiki/${encodeURIComponent(page.title.replace(/ /g, '_'))}`,
    text: page.extract,
  };
}

function pickTitle(titles, albumTitle) {
  const norm = s => String(s).toLowerCase().replace(/[^\p{L}\p{N}]+/gu, '');
  const want = norm(albumTitle);
  if (!want) return null;
  // 只接受标题里确实含专辑名的条目；宁可不要，也不能把《Yellow Submarine》塞进 Soul Mining 的材料里
  const exact = titles.find(t => norm(t) === want);
  if (exact) return exact;
  const partial = titles.find(t => norm(t).includes(want) && norm(t).length <= want.length + 12);
  return partial || null;
}

async function gatherWiki(lang, albumTitle, artist) {
  const queries = [`${albumTitle} ${artist} album`, `${albumTitle} album`, albumTitle];
  for (const q of queries) {
    try {
      const titles = await wikiSearch(lang, q);
      const title = pickTitle(titles, albumTitle);
      if (!title) continue;
      const page = await wikiExtract(lang, title);
      if (page && page.text.length > 400) {
        return {
          name: `Wikipedia（${lang}）：${page.title}`,
          url: page.url,
          text: trimAtSentence(page.text, WIKI_LIMIT),
        };
      }
    } catch (e) { /* 换下一个查询 */ }
  }
  return null;
}

/* ---------- MusicBrainz ---------- */
async function gatherMusicBrainz(albumTitle, artist) {
  const esc = s => String(s || '').replace(/["\\]/g, ' ').trim();
  // 只用标题查：MusicBrainz 的艺人字段是拼接串（如 "Lou ReedJohn Cale"），带 artist 过滤会漏
  const search = await getJson('https://musicbrainz.org/ws/2/release-group/?'
    + new URLSearchParams({ query: `releasegroup:"${esc(albumTitle)}"`, fmt: 'json', limit: '10' }));

  const groups = search['release-groups'] || [];
  if (!groups.length) return null;
  const norm = s => String(s || '').toLowerCase().replace(/[^\p{L}\p{N}]+/gu, '');
  const want = norm(albumTitle);
  const isAlbum = g => String(g['primary-type'] || '').toLowerCase() === 'album';
  const dateOf = g => g['first-release-date'] || '9999';
  const artistOf = g => norm((g['artist-credit'] || []).map(a => a.name).join(''));
  const artistWant = norm(artist);

  const sameName = groups.filter(g => norm(g.title) === want);
  const pool = (sameName.length ? sameName : groups).filter(isAlbum);
  if (!pool.length) return null;

  // 专辑优先、艺人能对上再加分、同分取最早发行
  const ranked = pool
    .map(g => ({
      g,
      score: (artistWant && artistOf(g).includes(artistWant.slice(0, 6)) ? 2 : 0)
        + (artistWant && artistOf(g).includes(artistWant) ? 2 : 0),
    }))
    .sort((a, b) => (b.score - a.score) || dateOf(a.g).localeCompare(dateOf(b.g)));
  const group = ranked[0].g;
  if (!group) return null;

  await sleep(MB_DELAY);
  let releases = [];
  try {
    const rel = await getJson('https://musicbrainz.org/ws/2/release/?'
      + new URLSearchParams({
        'release-group': group.id,
        inc: 'recordings+labels+artist-credits',
        fmt: 'json', limit: '5',
      }));
    releases = rel.releases || [];
  } catch (e) { /* 曲目拿不到就只给发行信息 */ }

  const lines = [];
  lines.push(`标题：${group.title}`);
  if (group['primary-type']) lines.push(`类型：${group['primary-type']}`);
  if (group['secondary-types']?.length) lines.push(`次级类型：${group['secondary-types'].join(' / ')}`);
  if (group['first-release-date']) lines.push(`首次发行：${group['first-release-date']}`);
  if (group['artist-credit']?.length) {
    lines.push(`艺人：${group['artist-credit'].map(a => a.name + (a.joinphrase || '')).join('')}`);
  }

  // 取最早、且有曲目表的那一版：先用原版发行信息，避免把 1987 年的 CD 重发当成首发
  const withTracks = releases.filter(r => (r.media || []).some(m => (m.tracks || []).length));
  const releasePool = withTracks.length ? withTracks : releases;
  const release = releasePool.slice().sort((a, b) => String(a.date || '9999').localeCompare(String(b.date || '9999')))[0];
  if (release) {
    if (release.date) lines.push(`该版本发行日期：${release.date}`);
    if (release.country) lines.push(`发行地：${release.country}`);
    const labels = (release['label-info'] || [])
      .map(l => [l.label?.name, l['catalog-number']].filter(Boolean).join(' / '))
      .filter(Boolean);
    if (labels.length) lines.push(`厂牌：${[...new Set(labels)].join('；')}`);

    const media = release.media || [];
    const all = [];
    media.forEach(m => (m.tracks || []).forEach(t => all.push(t)));
    if (all.length) {
      lines.push('');
      lines.push('曲目表（按官方顺序）：');
      all.forEach((t, i) => {
        const len = t.length ? `（${Math.floor(t.length / 60000)}:${String(Math.round((t.length % 60000) / 1000)).padStart(2, '0')}）` : '';
        lines.push(`${String(i + 1).padStart(2, '0')}. ${t.title}${len}`);
      });
    }
  }

  return {
    name: 'MusicBrainz：' + group.title,
    url: `https://musicbrainz.org/release-group/${group.id}`,
    text: lines.join('\n'),
  };
}

/* ---------- 乐评原文（经 r.jina.ai 转文本，绕过 CORS） ---------- */
const READER = 'https://r.jina.ai/';
const REVIEW_HOSTS = [
  'theguardian.com', 'allmusic.com', 'pitchfork.com', 'rollingstone.com', 'nme.com',
  'bbc.co.uk', 'popmatters.com', 'thequietus.com', 'uncut.co.uk', 'stereogum.com',
  'consequence.net', 'spin.com', 'metacritic.com', 'discogs.com', 'rateyourmusic.com',
  'thelineofbestfit.com', 'drownedinsound.com', 'musicomh.com', 'clashmusic.com',
  'loudersound.com', 'recordcollectormag.com', 'paste magazine.com', 'pastemagazine.com',
];

function hostOf(url) {
  try { return new URL(url).hostname.replace(/^www\./, ''); } catch (e) { return ''; }
}

function isReviewHost(url) {
  const h = hostOf(url);
  return !!h && REVIEW_HOSTS.some(d => h === d || h.endsWith('.' + d));
}

async function readPage(url) {
  const res = await fetch(READER + url, { headers: { Accept: 'text/plain' } });
  if (res.status === 429) {
    const e = new Error('RATE_LIMIT');
    e.code = 'RATE_LIMIT';
    throw e;
  }
  if (!res.ok) throw new Error(`reader HTTP ${res.status}`);
  let text = await res.text();
  // jina 会在开头加几行元信息，去掉
  text = text.replace(/^(Title|URL Source|Published Time|Markdown Content):.*\n/gm, '').trim();
  // Cloudflare 拦截页的特征：内容极短且以 Just a moment 开头
  if (/^Just a moment\.\.\./.test(text) || text.length < 500) return '';
  return text;
}

function extractUrls(text) {
  return [...new Set([...text.matchAll(/https?:\/\/[^\s)\]"'<>,]+/g)].map(m => m[0].replace(/[.。]$/, '')))];
}

/** 从维基页面里挑出乐评站外链 */
async function reviewLinksFromWiki(wikiUrl) {
  if (!wikiUrl) return [];
  const page = await readPage(wikiUrl);
  const links = extractUrls(page).filter(isReviewHost);
  const seen = new Set();
  return links.filter(u => {
    const key = hostOf(u) + new URL(u).pathname;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).slice(0, 4);
}

/** 没有维基外链时，用 DuckDuckGo 结果页兜底 */
async function reviewLinksFromSearch(albumTitle, artist) {
  const q = encodeURIComponent(`${albumTitle} ${artist} album review`);
  const page = await readPage(`https://html.duckduckgo.com/html/?q=${q}`);
  const raw = [...page.matchAll(/uddg=([^&\s]+)/g)].map(m => decodeURIComponent(m[1]));
  const direct = extractUrls(page);
  const all = [...raw, ...direct].filter(isReviewHost);
  const seen = new Set();
  return all.filter(u => {
    const key = hostOf(u) + new URL(u).pathname;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).slice(0, 3);
}

async function gatherReviews(album, wikiUrl, maxPages = 2) {
  let links = [];
  try {
    links = await reviewLinksFromWiki(wikiUrl);
  } catch (e) {
    if (e.code === 'RATE_LIMIT') return { reviews: [], note: 'rate-limit' };
  }
  if (!links.length) {
    try {
      links = await reviewLinksFromSearch(album.collectionName || '', album.artistName || '');
    } catch (e) {
      return { reviews: [], note: e.code === 'RATE_LIMIT' ? 'rate-limit' : 'search-failed' };
    }
  }
  const out = [];
  let rateLimited = false;
  for (const url of links.slice(0, maxPages)) {
    try {
      const text = await readPage(url);
      if (!text) continue;
      out.push({ name: `乐评：${hostOf(url)}`, url, text: trimAtSentence(text, 4000) });
    } catch (e) {
      if (e.code === 'RATE_LIMIT') { rateLimited = true; break; }
    }
  }
  return { reviews: out, note: rateLimited ? 'rate-limit' : '' };
}

/* ---------- 汇总 ---------- */
export async function gatherMaterials(album, options = {}) {
  const title = album?.collectionName || '';
  const artist = album?.artistName || '';
  const jobs = [
    gatherMusicBrainz(title, artist).catch(() => null),
    gatherWiki('en', title, artist).catch(() => null),
    gatherWiki('zh', title, artist).catch(() => null),
  ];
  const results = await Promise.all(jobs);
  const sources = results.filter(Boolean);

  if (options.reviews) {
    const wiki = sources.find(s => s.name.startsWith('Wikipedia（en）'));
    const got = await gatherReviews(album, wiki?.url, options.maxReviews ?? 2).catch(() => ({ reviews: [], note: '' }));
    sources.push(...got.reviews);
    return { sources, digest: formatDigest(sources), reviewNote: got.note || '', reviewCount: got.reviews.length };
  }

  return { sources, digest: formatDigest(sources), reviewNote: '', reviewCount: 0 };
}

export function formatDigest(sources) {
  if (!sources.length) return '';
  return sources.map(s => `### 来源：${s.name}\n链接：${s.url}\n\n${s.text}`).join('\n\n---\n\n');
}
