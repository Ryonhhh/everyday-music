/* 共用工具：转义、日期、Markdown 渲染、乐谱进度图、本地进度存储。
   全部为纯静态逻辑，不依赖任何后端。 */

export function $(id) { return document.getElementById(id); }

export function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

export function fmtDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const p = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export function todayStr() {
  const d = new Date();
  const p = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/* 所有数据都是相对路径，GitHub Pages 的项目子路径下也能正常工作 */
export async function fetchJson(path) {
  const res = await fetch(path, { cache: 'no-store' });
  if (!res.ok) throw new Error(`HTTP ${res.status}：${path}`);
  return res.json();
}

export async function fetchText(path) {
  const res = await fetch(path, { cache: 'no-store' });
  if (!res.ok) throw new Error(`HTTP ${res.status}：${path}`);
  return res.text();
}

/* ---------- 进度（localStorage） ---------- */
const PROGRESS_KEY = 'music-everyday:progress:v1';

export function loadProgress() {
  try {
    const raw = localStorage.getItem(PROGRESS_KEY);
    if (!raw) return { completed: {}, lastDay: 0 };
    const parsed = JSON.parse(raw);
    return {
      completed: parsed.completed && typeof parsed.completed === 'object' ? parsed.completed : {},
      lastDay: Number(parsed.lastDay) || 0,
    };
  } catch {
    return { completed: {}, lastDay: 0 };
  }
}

export function saveProgress(p) {
  try { localStorage.setItem(PROGRESS_KEY, JSON.stringify(p)); } catch { /* 隐私模式下忽略 */ }
}

export function markDayComplete(day) {
  const p = loadProgress();
  if (!p.completed[String(day)]) p.completed[String(day)] = todayStr();
  p.lastDay = day;
  saveProgress(p);
  return p;
}

export function completedCount(p, total) {
  return Object.keys(p.completed).filter(d => Number(d) >= 1 && Number(d) <= total).length;
}

/* ---------- 安全的 Markdown 渲染（先转义再转换） ---------- */
export function renderMarkdown(src) {
  const lines = esc(src || '').split('\n');
  const out = [];
  let list = null;
  let items = [];
  const quote = [];
  let inCode = false;
  let codeBuf = [];
  let table = [];

  const inline = text => text
    .replace(/`([^`]+)`/g, (_, c) => `<code>${c}</code>`)
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, '$1<em>$2</em>')
    // URL 里允许出现一层成对括号（维基条目常见，如 Xx_(The_xx_album)）
    .replace(/\[([^\]]+)\]\((https?:(?:[^()\s]|\([^()\s]*\))+)\)/g, '<a href="$2" rel="noopener noreferrer" target="_blank">$1</a>');

  const flushList = () => {
    if (list) { out.push(`<${list}>${items.join('')}</${list}>`); list = null; items = []; }
  };
  const flushQuote = () => {
    if (quote.length) { out.push(`<blockquote>${quote.join('<br>')}</blockquote>`); quote.length = 0; }
  };
  const flushTable = () => {
    if (!table.length) return;
    let html = '<table>';
    table.forEach((row, i) => {
      const cells = row.replace(/^\s*\|/, '').replace(/\|\s*$/, '').split('|').map(c => c.trim());
      const tag = i === 0 ? 'th' : 'td';
      html += `<tr>${cells.map(c => `<${tag}>${inline(c)}</${tag}>`).join('')}</tr>`;
    });
    out.push(`${html}</table>`);
    table = [];
  };
  const flushAll = () => { flushList(); flushQuote(); flushTable(); };

  for (const raw of lines) {
    const line = raw.replace(/\s+$/, '');
    if (inCode) {
      if (/^```/.test(line.trim())) { out.push(`<pre><code>${codeBuf.join('\n')}</code></pre>`); inCode = false; codeBuf = []; }
      else codeBuf.push(line);
      continue;
    }
    if (/^```/.test(line.trim())) { flushAll(); inCode = true; continue; }
    const h = line.match(/^(#{1,4})\s+(.*)$/);
    if (h) { flushAll(); out.push(`<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`); continue; }
    if (/^\s*[-*]\s+/.test(line)) {
      flushQuote(); flushTable();
      if (list !== 'ul') { flushList(); list = 'ul'; }
      items.push(`<li>${inline(line.replace(/^\s*[-*]\s+/, ''))}</li>`);
      continue;
    }
    const ol = line.match(/^\s*(\d+)[.)]\s+(.*)$/);
    if (ol) {
      flushQuote(); flushTable();
      if (list !== 'ol') { flushList(); list = 'ol'; }
      items.push(`<li>${inline(ol[2])}</li>`);
      continue;
    }
    // 注意：源文本已做过 HTML 转义，">" 此时是 "&gt;"
    const bq = line.match(/^\s*(?:&gt;|>)\s?(.*)$/);
    if (bq) { flushList(); flushTable(); quote.push(inline(bq[1])); continue; }
    if (/^\s*(-{3,}|\*{3,})\s*$/.test(line)) { flushAll(); out.push('<hr>'); continue; }
    // 独占一行的图片成为 figure，图注用 alt
    const fig = line.match(/^!\[([^\]]*)\]\(([^)\s]+)\)\s*$/);
    if (fig) {
      flushAll();
      const alt = fig[1];
      out.push(`<figure class="figure"><img src="${fig[2]}" alt="${alt}" loading="lazy" decoding="async">`
        + (alt ? `<figcaption>${alt}</figcaption>` : '') + '</figure>');
      continue;
    }
    if (/^\s*\|.*\|\s*$/.test(line)) {
      flushList(); flushQuote();
      if (/^\s*\|[\s:|-]+\|\s*$/.test(line)) continue;
      table.push(line);
      continue;
    }
    if (!line.trim()) { flushAll(); continue; }
    flushList(); flushQuote();
    out.push(`<p>${inline(line)}</p>`);
  }
  if (inCode) out.push(`<pre><code>${codeBuf.join('\n')}</code></pre>`);
  flushAll();
  return out.join('\n');
}

/* ---------- 乐谱式进度（签名元素，保留原有视觉语言） ---------- */
export function drawStaff(label, total, done) {
  const W = 720, H = 58, padL = 10, padR = 10;
  const usable = W - padL - padR;
  const step = usable / Math.max(total - 1, 1);
  const yBase = H - 12;
  let lines = '';
  for (let i = 0; i < 5; i++) {
    const y = yBase - i * 5;
    lines += `<line x1="0" y1="${y}" x2="${W}" y2="${y}" stroke="#dedcd6" stroke-width="1"/>`;
  }
  let notes = '';
  for (let i = 0; i < total; i++) {
    const x = padL + i * step;
    const y = yBase - (i % 5) * 5;
    const r = total > 30 ? 3 : 3.8;
    if (i < done) {
      notes += `<ellipse cx="${x}" cy="${y}" rx="${r}" ry="${r * 0.78}" fill="#b45309" transform="rotate(-20 ${x} ${y})"/>`;
    } else if (i === done) {
      notes += `<ellipse cx="${x}" cy="${y}" rx="${r}" ry="${r * 0.78}" fill="none" stroke="#1f201d" stroke-width="1.6" transform="rotate(-20 ${x} ${y})"/>`;
    } else {
      notes += `<circle cx="${x}" cy="${y}" r="1.6" fill="#cfcec8"/>`;
    }
  }
  return `<div class="staff">
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(label)}进度 ${done}/${total}">${lines}${notes}</svg>
    <div class="staff-caption"><span>${esc(label)}</span><span class="num">${done} / ${total}</span></div>
  </div>`;
}
