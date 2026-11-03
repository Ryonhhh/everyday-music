/* 每日音乐学习 · 纯静态前端
   数据全部来自 data/*.json，不依赖任何后端、登录或数据库。 */
import {
  $, esc, fmtDate, fetchJson, fetchText, loadProgress, markDayComplete,
  completedCount, drawStaff, renderMarkdown,
} from './core.js';

const VIEW_NAMES = { today: '今日学习', lessons: '课程目录', albums: '专辑解析', library: '资料库' };
const isDetail = /detail\.html/.test(location.pathname);

let CURRICULUM = null;
let LESSONS = [];     // [{day,title,summary,minutes,units}]
let ALBUMS = [];      // [{id,title,artist,year,summary,addedAt}]

/* ---------- 数据加载 ---------- */
async function loadData() {
  CURRICULUM = await fetchJson('data/curriculum.json');
  LESSONS = await optionalJson('data/lessons/index.json', 'lessons');
  ALBUMS = await optionalJson('data/albums/index.json', 'albums');
}

/* 正文可能还没生成：404 视为空，而不是报错 */
async function optionalJson(path, key) {
  try {
    const data = await fetchJson(path);
    return Array.isArray(data[key]) ? data[key] : [];
  } catch {
    return [];
  }
}

function lessonByDay(day) { return LESSONS.find(l => Number(l.day) === Number(day)) || null; }

/* ---------- 今日学习 ---------- */
function currentDay(progress, total) {
  for (let d = 1; d <= total; d++) {
    if (!progress.completed[String(d)]) return d;
  }
  return total;
}

function renderToday() {
  const total = CURRICULUM.totalDays;
  const progress = loadProgress();
  const done = completedCount(progress, total);
  const allDone = done >= total;
  const day = currentDay(progress, total);
  const dayData = CURRICULUM.days.find(d => d.day === day);

  $('scopeDay').textContent = done;
  $('scopeTotal').textContent = total;

  let theoryDone = 0;
  let historyDone = 0;
  for (const d of CURRICULUM.days) {
    if (!progress.completed[String(d.day)]) continue;
    for (const u of d.units) {
      if (u.track === 'theory') theoryDone++;
      else if (u.track === 'history') historyDone++;
    }
  }
  const theoryTotal = CURRICULUM.tracks?.theory || 26;
  const historyTotal = CURRICULUM.tracks?.history || 36;

  $('kpiDays').innerHTML = `${done}<span class="unit" style="font-size:var(--fs-small);color:var(--faint);font-weight:400"> / ${total}</span>`;
  $('kpiTheory').innerHTML = `${theoryDone}<span class="unit" style="font-size:var(--fs-small);color:var(--faint);font-weight:400"> / ${theoryTotal}</span>`;
  $('kpiHistory').innerHTML = `${historyDone}<span class="unit" style="font-size:var(--fs-small);color:var(--faint);font-weight:400"> / ${historyTotal}</span>`;

  if (allDone) {
    $('dayFigure').innerHTML = '课程已完成';
    $('greetingH1').textContent = `${total} 天课程，全部完成`;
    $('todaySub').textContent = '可以回顾任意一课。';
    $('nextUnits').innerHTML = '<div class="empty" style="grid-column:1/-1">课程已全部完成 🎉</div>';
    $('learnAction').style.display = 'none';
  } else {
    $('dayFigure').innerHTML = `第 <span class="num">${day}</span> 天<span class="unit">/ ${total}</span>`;
    $('greetingH1').textContent = `今天是第 ${day} 天`;
    const firstUnit = dayData?.units?.[0];
    $('todaySub').textContent = firstUnit ? `今日主题：${firstUnit.title}` : '今日课程';
    $('nextUnits').innerHTML = (dayData?.units || []).map(u => `
      <div class="next-unit">
        <span class="track-label">${u.track === 'theory' ? '乐理' : '音乐史'} · ${esc(u.book)}</span>
        <span class="unit-title">${esc(u.title)}</span>
        ${u.source?.lecture ? `<span class="unit-src">${esc(u.source.lecture)}</span>` : ''}
        ${u.source?.chapter ? `<span class="unit-src">${esc(u.source.chapter)}</span>` : ''}
      </div>`).join('') || '<div class="empty" style="grid-column:1/-1">这一天没有排课</div>';
    const has = !!lessonByDay(day);
    const btn = $('startBtn');
    btn.href = `detail.html?type=lesson&day=${day}`;
    btn.textContent = has ? `开始第 ${day} 天学习` : `查看第 ${day} 天大纲`;
  }

  $('staffs').innerHTML = drawStaff('乐理', theoryTotal, theoryDone)
    + drawStaff('音乐史', historyTotal, historyDone);

  const lastDone = Object.entries(progress.completed)
    .map(([d, at]) => ({ day: Number(d), at }))
    .sort((a, b) => (a.day < b.day ? 1 : -1))[0];
  if (lastDone) {
    $('lastRow').style.display = 'flex';
    const l = lessonByDay(lastDone.day);
    $('lastLessonLink').textContent = `第 ${lastDone.day} 天${l ? ' · ' + l.title : ''} · ${fmtDate(lastDone.at)}`;
    $('lastLessonLink').href = `detail.html?type=lesson&day=${lastDone.day}`;
  }

  renderRows($('recentLessons'), CURRICULUM.days.slice(0, 6), d => ({
    href: `detail.html?type=lesson&day=${d.day}`,
    title: `第 ${d.day} 天 · ${d.units.map(u => u.title).join(' / ')}`,
    sub: d.units.map(u => u.track === 'theory' ? '乐理' : '音乐史').join(' + '),
    meta: progress.completed[String(d.day)] ? '✓ ' + fmtDate(progress.completed[String(d.day)]) : '未开始',
  }), '还没有学习记录');

  renderRows($('recentAlbums'), ALBUMS.slice(0, 6), a => ({
    href: `detail.html?type=album&id=${encodeURIComponent(a.id)}`,
    title: a.title,
    sub: [a.artist, a.year].filter(Boolean).join(' · '),
    meta: fmtDate(a.addedAt),
    thumb: a.cover,
  }), '还没有专辑解析');
}

function renderRows(el, items, mapper, emptyText) {
  if (!el) return;
  if (!items || !items.length) {
    el.innerHTML = `<div class="empty">${esc(emptyText)}</div>`;
    return;
  }
  el.innerHTML = items.map(it => {
    const r = mapper(it);
    return `<div class="row${r.thumb ? ' has-thumb' : ''}">
      ${r.thumb ? `<img class="row-thumb" src="${esc(r.thumb)}" alt="" loading="lazy">` : ''}
      <div class="row-main">
        <a class="row-title" href="${r.href}">${esc(r.title)}</a>
        ${r.sub ? `<div class="row-sub">${esc(r.sub)}</div>` : ''}
      </div>
      <div class="row-meta">${esc(r.meta || '')}</div>
    </div>`;
  }).join('');
}

/* ---------- 课程目录 ---------- */
function renderLessons() {
  const progress = loadProgress();
  const total = CURRICULUM.totalDays;
  const done = completedCount(progress, total);
  $('lessonsStamp').textContent = `共 ${total} 天 · 已学 ${done} 天 · 进度存在本机浏览器`;

  const el = $('allLessons');
  el.innerHTML = CURRICULUM.days.map(d => {
    const has = lessonByDay(d.day);
    const isDone = !!progress.completed[String(d.day)];
    const units = d.units.map(u => `${u.track === 'theory' ? '乐理' : '音乐史'}：${esc(u.title)}`).join('　');
    const status = isDone ? `✓ 已学 ${fmtDate(progress.completed[String(d.day)])}`
      : (has ? '待学习' : '正文待生成');
    return `<div class="row">
      <div class="row-main">
        <a class="row-title" href="detail.html?type=lesson&day=${d.day}">第 ${d.day} 天 · ${esc(d.units[0]?.title || '')}</a>
        <div class="row-sub">${units}</div>
      </div>
      <div class="row-meta">${esc(status)}</div>
    </div>`;
  }).join('');
}

/* ---------- 专辑 ---------- */
function renderAlbums() {
  $('albumsStamp').textContent = `${ALBUMS.length} 张专辑`;
  renderRows($('allAlbums'), ALBUMS, a => ({
    href: `detail.html?type=album&id=${encodeURIComponent(a.id)}`,
    title: a.title,
    sub: [a.artist, a.year].filter(Boolean).join(' · '),
    meta: fmtDate(a.addedAt),
    thumb: a.cover,
  }), '还没有专辑解析');
}

/* ---------- 资料库 ---------- */
function renderLibrary() {
  const books = CURRICULUM.books || [];
  const el = $('libraryBooks');
  if (!books.length) {
    el.innerHTML = '<div class="empty">还没有资料</div>';
    return;
  }
  el.innerHTML = books.map(b => `<div class="row">
    <div class="row-main">
      <div class="row-title">${esc(b.title)}</div>
      <div class="row-sub">${esc(b.author)}${b.publisher ? ' · ' + esc(b.publisher) : ''}${b.note ? ' · ' + esc(b.note) : ''}</div>
    </div>
    <div class="row-meta">${b.pages ? `${b.pages} 页` : ''}${b.pages ? ` · ${b.chunks} 段` : ''}</div>
  </div>`).join('');

  $('libraryNote').innerHTML = renderMarkdown([
    '这个网站是**纯静态**的：没有服务器、没有数据库、没有登录，所有内容都是已经生成好的 JSON 文件，随仓库一起发布。',
    '',
    '**所以它永远不会「跑不起来」。**',
    '',
    '课程内容由本地知识库（RAG）从上述两本书中检索原文段落，再整理成讲稿。全文检索与书库管理在本地运行，不占用网站空间，也不上传书籍原文：',
    '',
    '```',
    'python rag/run.py search "五度相生律"',
    'python rag/run.py add "新书.pdf" --title "书名" --author "作者"',
    'python rag/run.py serve        # 打开本地管理界面，可拖拽上传新书',
    '```',
  ].join('\n'));
}

/* ---------- 视图切换 ---------- */
function showView(name) {
  const target = VIEW_NAMES[name] ? name : 'today';
  for (const key of Object.keys(VIEW_NAMES)) {
    const el = $(`view-${key}`);
    if (el) el.hidden = key !== target;
  }
  $('viewName').textContent = VIEW_NAMES[target];
  document.querySelectorAll('.nav-item, .sheet a[data-view]').forEach(a => {
    if (a.dataset.view === target) a.setAttribute('aria-current', 'page');
    else a.removeAttribute('aria-current');
  });
  $('navSheet').classList.remove('open');
}

/* ---------- 详情页 ---------- */
async function renderDetail() {
  const params = new URLSearchParams(location.search);
  const type = params.get('type');
  const skeleton = $('skeleton');
  const fail = () => { skeleton.hidden = true; $('error').hidden = false; };

  if (type === 'lesson') {
    const day = Number(params.get('day'));
    const dayData = CURRICULUM.days.find(d => d.day === day);
    if (!dayData) return fail();
    const metaInfo = lessonByDay(day);
    let md = '';
    // 先查清单再取文件：避免对尚未生成的课文产生 404 请求（会在控制台留红字）
    if (metaInfo) {
      try {
        md = await fetchText(`data/lessons/day-${String(day).padStart(2, '0')}.md`);
      } catch { md = ''; }
    }

    const mainUnit = dayData.units[0];
    const secondUnit = dayData.units[1];
    document.title = `第 ${day} 天 · ${mainUnit?.title || ''} · 每日音乐学习`;
    $('detailKicker').textContent = `课程日 ${String(day).padStart(2, '0')}`
      + (metaInfo?.minutes ? ` · 约 ${metaInfo.minutes} 分钟` : '');
    // 单元标题多为「A；B；C」的递进结构，只在第一个分号处断行：
    // 两行标题比三行碎句稳定，后面几项仍留在第二行里
    const fullTitle = (mainUnit?.title || `第 ${day} 天`).trim();
    const cut = fullTitle.indexOf('；');
    const titleHtml = cut > 0
      ? `${esc(fullTitle.slice(0, cut))}<br>${esc(fullTitle.slice(cut + 1))}`
      : esc(fullTitle);
    $('detailTitle').innerHTML = titleHtml;
    const byline = $('detailByline');
    if (secondUnit) {
      byline.textContent = `并读 · ${secondUnit.track === 'theory' ? '乐理' : '音乐史'}「${secondUnit.title}」`;
    } else if (mainUnit?.book) {
      byline.textContent = mainUnit.book;
    } else {
      byline.hidden = true;
    }
    $('detailFacts').hidden = true;

    let html = '';
    if (md.trim()) {
      html += renderMarkdown(md);
    } else {
      html += renderMarkdown([
        `> 这一天的正文还没有生成。下面是课程大纲，可以先看要学什么。`,
        '',
        ...dayData.units.map(u => [
          `## ${u.track === 'theory' ? '乐理' : '音乐史'} · ${u.title}`,
          '',
          `**出处**：${u.book}${u.source.lecture ? ' · ' + u.source.lecture : ''}${u.source.chapter ? ' · ' + u.source.chapter : ''}`,
          '',
          ...(u.source.sections || []).map(s => `- ${s}`),
          '',
        ].join('\n')),
      ].join('\n'));
    }
    const wrap = document.createElement('div');
    wrap.className = 'progress-action';
    wrap.innerHTML = '<button class="btn btn-primary" id="markDone" type="button">标记本课已学完</button>';
    $('detailBody').innerHTML = html;
    $('detailBody').appendChild(wrap);
    decorateArticle($('detailBody'));
    buildLessonNav(day);

    const progress = loadProgress();
    const btn = $('markDone');
    if (progress.completed[String(day)]) {
      btn.textContent = '✓ 已学完（点击取消）';
      btn.disabled = false;
    }
    btn.addEventListener('click', () => {
      const p = loadProgress();
      if (p.completed[String(day)]) {
        delete p.completed[String(day)];
        saveProgressSafe(p);
        btn.textContent = '标记本课已学完';
      } else {
        markDayComplete(day);
        btn.textContent = '✓ 已学完（点击取消）';
      }
    });

    skeleton.hidden = true;
    $('content').hidden = false;
    initReadProgress();
    return;
  }

  if (type === 'album') {
    const id = params.get('id');
    if (!id) return fail();
    const info = ALBUMS.find(a => a.id === id) || null;
    let md = '';
    try {
      md = await fetchText(`data/albums/${encodeURIComponent(id)}.md`);
    } catch { return fail(); }
    const title = info?.title || id;
    document.title = `${title} · 每日音乐学习`;
    $('detailKicker').textContent = info?.kicker || '专辑解析';
    $('detailTitle').textContent = title;
    const byline = $('detailByline');
    const bylineText = info?.byline || [info?.artist, info?.year].filter(Boolean).join(' · ');
    if (bylineText) byline.textContent = bylineText;
    else byline.hidden = true;

    const factsEl = $('detailFacts');
    if (info?.facts?.length) {
      factsEl.innerHTML = info.facts
        .map(f => `<div class="fact"><dt>${esc(f.k)}</dt><dd>${esc(f.v)}</dd></div>`)
        .join('');
      factsEl.hidden = false;
    } else {
      factsEl.hidden = true;
    }

    // 封面：专辑页的视觉锚点
    const head = $('detailHead');
    const coverFig = $('albumCover');
    if (info?.cover) {
      const img = $('albumCoverImg');
      img.src = info.cover;
      img.alt = info.coverAlt || `${title} 专辑封面`;
      const cap = $('albumCoverCaption');
      cap.textContent = info.coverCaption || '';
      cap.hidden = !info.coverCaption;
      coverFig.hidden = false;
      head.classList.add('has-cover');
    } else {
      coverFig.hidden = true;
      head.classList.remove('has-cover');
    }

    // 在线收听与资料链接
    const listenEl = $('albumListen');
    const listen = info?.listen || [];
    const more = info?.more || [];
    if (listen.length || more.length) {
      const pill = (item, kind) =>
        `<a class="listen-pill listen-pill--${kind}" href="${esc(item.url)}"
            target="_blank" rel="noopener noreferrer">${esc(item.platform)}</a>`;
      const row = (label, items, kind) => (items.length
        ? `<div class="listen-row"><span class="listen-label">${label}</span>
             <span class="listen-items">${items.map(i => pill(i, kind)).join('')}</span></div>`
        : '');
      listenEl.innerHTML = row('在线收听', listen, 'stream') + row('资料', more, 'ref');
      listenEl.hidden = false;
    } else {
      listenEl.hidden = true;
    }

    $('detailBody').innerHTML = renderMarkdown(md);
    decorateArticle($('detailBody'));
    $('lessonNav').hidden = true;
    skeleton.hidden = true;
    $('content').hidden = false;
    initReadProgress();
    return;
  }

  fail();
}

/* 把「出处」引注降级成贴边细注；开篇那条做成导语 */
function decorateArticle(root) {
  if (!root) return;
  root.querySelectorAll('blockquote').forEach(bq => {
    const t = bq.textContent.trim();
    if (t.startsWith('出处')) bq.classList.add('cite');
  });
  const first = root.firstElementChild;
  if (first && first.tagName === 'BLOCKQUOTE' && !first.classList.contains('cite')) {
    first.classList.add('lede');
  }
}

/* 上下课导航 */
function buildLessonNav(day) {
  const nav = $('lessonNav');
  if (!nav) return;
  const total = CURRICULUM.totalDays;
  const prev = day > 1 ? day - 1 : null;
  const next = day < total ? day + 1 : null;
  if (!prev && !next) { nav.hidden = true; return; }
  const titleOf = d => CURRICULUM.days.find(x => x.day === d)?.units[0]?.title || '';
  const card = (d, dir) => d
    ? `<a class="nav-card" href="detail.html?type=lesson&day=${d}">
         <span class="nav-dir">${dir}</span>
         <span class="nav-title">第 ${d} 天 · ${esc(titleOf(d))}</span>
       </a>`
    : '<span class="nav-card nav-card--empty" aria-hidden="true"></span>';
  nav.innerHTML = card(prev, '上一课') + card(next, '下一课');
  nav.hidden = false;
}

/* 顶部阅读进度 */
function initReadProgress() {
  const bar = $('readProgress');
  if (!bar) return;
  const update = () => {
    const el = document.documentElement;
    const max = el.scrollHeight - el.clientHeight;
    const p = max > 12 ? Math.min(1, el.scrollTop / max) : 0;
    bar.style.transform = `scaleX(${p})`;
  };
  update();
  addEventListener('scroll', update, { passive: true });
  addEventListener('resize', update);
}

function saveProgressSafe(p) {
  try { localStorage.setItem('music-everyday:progress:v1', JSON.stringify(p)); } catch { /* ignore */ }
}

/* ---------- 启动 ---------- */
async function boot() {
  try {
    await loadData();
  } catch (err) {
    $('todaySub').textContent = '课程数据读取失败。';
    const el = $('nextUnits');
    if (el) el.innerHTML = `<div class="empty" style="grid-column:1/-1">无法读取 data/curriculum.json。<br>${esc(err.message)}<br><br>如果是本地打开文件，请用 HTTP 服务器访问（浏览器不允许 file:// 读取 JSON）。</div>`;
    return;
  }

  const bookLabel = $('bookLabel');
  if (bookLabel && CURRICULUM.books?.length) {
    bookLabel.innerHTML = CURRICULUM.books
      .map(b => esc(b.label || `${b.author}《${b.title}》`))
      .join('<br>');
  }

  if (isDetail) {
    renderDetail();
  } else {
    renderToday();
    renderLessons();
    renderAlbums();
    renderLibrary();
    showView(location.hash.replace('#/', '') || 'today');

    window.addEventListener('hashchange', () => showView(location.hash.replace('#/', '') || 'today'));
    $('menuBtn')?.addEventListener('click', () => $('navSheet').classList.toggle('open'));
    $('skipBtn')?.addEventListener('click', () => {
      const total = CURRICULUM.totalDays;
      const day = currentDay(loadProgress(), total);
      markDayComplete(day);
      renderToday();
      renderLessons();
    });
  }
}

boot();
