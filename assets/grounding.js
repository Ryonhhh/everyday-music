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

/* ---------- 汇总 ---------- */
export async function gatherMaterials(album) {
  const title = album?.collectionName || '';
  const artist = album?.artistName || '';
  const jobs = [
    gatherMusicBrainz(title, artist).catch(() => null),
    gatherWiki('en', title, artist).catch(() => null),
    gatherWiki('zh', title, artist).catch(() => null),
  ];
  const results = await Promise.all(jobs);
  const sources = results.filter(Boolean);
  return { sources, digest: formatDigest(sources) };
}

export function formatDigest(sources) {
  if (!sources.length) return '';
  return sources.map(s => `### 来源：${s.name}\n链接：${s.url}\n\n${s.text}`).join('\n\n---\n\n');
}
