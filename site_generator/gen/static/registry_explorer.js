// Registry explorer (scale-up S1): DuckDB-WASM over data/registry_studies.parquet, fully client-side.
// Same boot / failure pattern as explorer.js (samples). One row per ENA study; list columns (body_sites, life_stages,
// scope_memberships) are ';'-joined codes and are matched with a delimited LIKE. Detail panel shows every column, the
// evidence rows behind host / body site / life stage (JSON lists of {source, quote}); catalog studies link to their study page.
const DUCKDB_URL = 'https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm@1.29.0/+esm';
const CFG = window.REGISTRY_CFG;
const PAGE = 50;
const SHOW_COLS = ['study_accession', 'study_title', 'n_runs', 'n_samples', 'body_sites', 'life_stages', 'assay', 'classification_stage', 'ena'];
const SORTABLE = new Set(['study_accession', 'study_title', 'n_runs', 'n_samples', 'assay', 'classification_stage', 'body_site_primary', 'life_stage_primary', 'first_public_min']);
const LIST_COLS = ['body_sites', 'life_stages', 'scope_memberships', 'population_flags'];
const EVIDENCE_COLS = [['host_evidence', 'host_human'], ['body_site_evidence', 'body_sites'], ['life_stage_evidence', 'life_stages']];
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/'/g, "''");
const h = s => String(s === null || s === undefined ? '' : s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const fmtV = v => { if (v === null || v === undefined) return ''; if (typeof v === 'bigint') return v.toString(); if (typeof v === 'number') return Number.isInteger(v) ? String(v) : (Math.round(v * 100) / 100).toString(); return String(v); };
const INCLUDED = new Set(CFG.includedStudies || []);
const STAGE_CLASS = {deterministic_prior: 'R4', deterministic_rule: 'R1', sonnet_x2: 'R2', opus_adjudicated: 'R3', pending: ''};

let duckdb, db, conn, page = 0, total = 0, sortCol = 'n_samples', sortDir = 'DESC', lastFocus = null;

function setBoot(msg) { $('boot-msg').textContent = msg; }
function bootFail(e) {
  $('boot').innerHTML = '<b>The explorer could not start.</b> ' + h(e && e.message || e) + '<br>DuckDB-WASM (pinned 1.29.0) is loaded from cdn.jsdelivr.net; this message means the browser blocks WebAssembly/Workers or the CDN is unreachable. The table is downloadable: <a href="' + CFG.parquet + '">registry_studies.parquet</a>.';
  console.error(e);
}

async function init() {
  try {
    setBoot('loading DuckDB-WASM module…');
    duckdb = await import(DUCKDB_URL);
    const bundle = await duckdb.selectBundle(duckdb.getJsDelivrBundles());
    const workerUrl = URL.createObjectURL(new Blob([`importScripts("${bundle.mainWorker}");`], {type: 'text/javascript'}));
    const worker = new Worker(workerUrl);
    db = new duckdb.AsyncDuckDB(new duckdb.ConsoleLogger(duckdb.LogLevel.WARNING), worker);
    await db.instantiate(bundle.mainModule, bundle.pthreadWorker);
    URL.revokeObjectURL(workerUrl);
    setBoot('fetching registry table…');
    const resp = await fetch(CFG.parquet);
    if (!resp.ok) throw new Error('fetch of parquet failed: HTTP ' + resp.status);
    await db.registerFileBuffer('registry.parquet', new Uint8Array(await resp.arrayBuffer()));
    conn = await db.connect();
    await conn.query(`CREATE VIEW registry AS SELECT * FROM read_parquet('registry.parquet')`);
    await conn.query(`CREATE TABLE catalog_studies (study_accession VARCHAR)`);
    const accs = [...INCLUDED]; for (let i = 0; i < accs.length; i += 500) await conn.query(`INSERT INTO catalog_studies VALUES ${accs.slice(i, i + 500).map(a => `('${esc(a)}')`).join(',')}`);
    window.__registryReady = true;
    $('boot').style.display = 'none'; $('exp').style.display = '';
    const acc = new URLSearchParams(location.search).get('study');   // read BEFORE run(): writeUrl() drops the param while the panel is still closed (the old bug)
    readUrl();
    if (acc && !$('f-q').value.trim()) { $('f-q').value = acc; setHost(['yes', 'mixed', 'unknown', 'no']); }   // the record must be findable whatever its host class
    await run();
    if (acc) { await showDetail(acc); $('detail').scrollIntoView({block: 'start'}); }
  } catch (e) { bootFail(e); }
}

// WHERE clause — the SQL replayed by tests/test_registry_pages.py (keep the shapes below in sync with REGISTRY_SQL there)
function whereClause() {
  const w = [];
  const q = $('f-q').value.trim();
  if (q) {
    if (/^PRJ[A-Z]*\d+$/i.test(q)) w.push(`study_accession = '${esc(q.toUpperCase())}'`);
    else w.push(`(study_title ILIKE '%${esc(q)}%' OR study_accession ILIKE '%${esc(q)}%')`);
  }
  for (const sel of document.querySelectorAll('select[data-list]')) {
    const v = sel.value; if (!v) continue;
    w.push(`(';' || COALESCE("${sel.dataset.list}", '') || ';') LIKE '%;${esc(v)};%'`);
  }
  for (const sel of document.querySelectorAll('select[data-field]')) {
    const v = sel.value; if (!v) continue;
    w.push(`"${sel.dataset.field}" = '${esc(v)}'`);
  }
  const hosts = hostValues();   // item 2: default = human studies (yes + mixed); checkboxes add unknown / no
  if (hosts.length && hosts.length < HOST_ALL.length) w.push(`host_human IN (${hosts.map(x => `'${esc(x)}'`).join(', ')})`);
  const mr = $('f-min_runs').value; if (mr !== '') w.push(`n_runs >= ${parseInt(mr)}`);
  if ($('f-catalog') && $('f-catalog').checked) w.push(`study_accession IN (SELECT study_accession FROM catalog_studies)`);
  return w.length ? 'WHERE ' + w.join(' AND ') : '';
}

const HOST_ALL = ['yes', 'mixed', 'unknown', 'no'], HOST_DEFAULT = ['yes', 'mixed'];
function hostValues() { return HOST_ALL.filter(v => { const el = $('f-host_' + v); return el && el.checked; }); }
function setHost(vals) { for (const v of HOST_ALL) { const el = $('f-host_' + v); if (el) el.checked = vals.includes(v); } }

function writeUrl() {
  const p = new URLSearchParams();
  const hv = hostValues(); if (hv.join(',') !== HOST_DEFAULT.join(',')) p.set('host', hv.join(','));
  if ($('f-q').value.trim()) p.set('q', $('f-q').value.trim());
  for (const sel of document.querySelectorAll('select[data-list], select[data-field]')) if (sel.value) p.set(sel.id.replace(/^f-/, ''), sel.value);
  if ($('f-min_runs').value !== '') p.set('min_runs', $('f-min_runs').value);
  if ($('f-catalog') && $('f-catalog').checked) p.set('catalog', '1');
  if (page) p.set('page', page + 1);
  if (sortCol !== 'n_samples' || sortDir !== 'DESC') p.set('sort', sortCol + ':' + sortDir);
  const keep = new URLSearchParams(location.search).get('study'); if (keep && $('detail').classList.contains('open')) p.set('study', keep);
  history.replaceState(null, '', location.pathname + (p.toString() ? '?' + p.toString() : '') + location.hash);
}
function readUrl() {
  const p = new URLSearchParams(location.search);
  if (p.get('q')) $('f-q').value = p.get('q');
  for (const sel of document.querySelectorAll('select[data-list], select[data-field]')) { const v = p.get(sel.id.replace(/^f-/, '')); if (v) sel.value = v; }
  if (p.get('min_runs')) $('f-min_runs').value = p.get('min_runs');
  if (p.get('host')) setHost(p.get('host').split(',').filter(v => HOST_ALL.includes(v)));
  else if (p.get('host_human') && HOST_ALL.includes(p.get('host_human'))) setHost([p.get('host_human')]);   // old links with the former select
  if (p.get('catalog') && $('f-catalog')) $('f-catalog').checked = true;
  if (p.get('page')) page = Math.max(0, parseInt(p.get('page')) - 1);
  if (p.get('sort')) { const [c, d] = p.get('sort').split(':'); if (SORTABLE.has(c)) { sortCol = c; sortDir = d === 'ASC' ? 'ASC' : 'DESC'; } }
}

function stageBadge(v) { return v ? `<span class="tag ${STAGE_CLASS[v] || ''}" title="${h(CFG.stageLabels[v] || v)}">${h(v)}</span>` : ''; }
function accLink(acc, verdict) {
  const ena = `<a class="small" href="${CFG.enaUrl}${h(acc)}">ENA</a>`;
  return INCLUDED.has(acc) ? `<a href="${CFG.studiesUrl}${h(acc)}.html">${h(acc)}</a> ${ena}` : `<span class="mono">${h(acc)}</span> ${ena}`;
}

async function run() {
  const where = whereClause();
  $('count').textContent = 'counting…';
  const c = await conn.query(`SELECT COUNT(*) AS n, COALESCE(SUM(n_runs),0) AS r FROM registry ${where}`);
  const c0 = c.toArray()[0].toJSON(); total = Number(c0.n);
  const maxPage = Math.max(0, Math.ceil(total / PAGE) - 1); if (page > maxPage) page = maxPage;
  const r = await conn.query(`SELECT study_accession, study_title, n_runs, n_samples, body_sites, life_stages, assay, classification_stage, in_infant_catalog FROM registry ${where} ORDER BY "${sortCol}" ${sortDir} NULLS LAST, study_accession LIMIT ${PAGE} OFFSET ${page * PAGE}`);
  const rows = r.toArray().map(x => x.toJSON());
  const thead = $('result-table').querySelector('thead'), tbody = $('result-table').querySelector('tbody');
  thead.innerHTML = '<tr>' + SHOW_COLS.map(col => SORTABLE.has(col)
    ? `<th data-col="${col}" tabindex="0" role="columnheader button" aria-sort="${col === sortCol ? (sortDir === 'ASC' ? 'ascending' : 'descending') : 'none'}" title="sort by ${col}" style="cursor:pointer">${col}${col === sortCol ? (sortDir === 'ASC' ? ' ▲' : ' ▼') : ''}</th>`
    : `<th>${col === 'ena' ? 'link' : col}</th>`).join('') + '</tr>';
  tbody.innerHTML = rows.map(row => `<tr data-key="${h(row.study_accession)}" tabindex="0" role="button" aria-label="open details for ${h(row.study_accession)}">` +
    `<td>${accLink(row.study_accession, row.in_infant_catalog)}</td><td>${h(row.study_title)}</td><td class="num">${fmtV(row.n_runs)}</td><td class="num">${fmtV(row.n_samples)}</td>` +
    `<td class="small">${h(row.body_sites)}</td><td class="small">${h(row.life_stages)}</td><td class="mono small">${h(row.assay)}</td><td>${stageBadge(row.classification_stage)}</td>` +
    `<td><a class="small" href="${CFG.enaUrl}${h(row.study_accession)}">ENA</a></td></tr>`).join('');
  const hv = hostValues(); const hostNote = hv.length && hv.length < HOST_ALL.length ? ` (host human: ${hv.join(', ')})` : '';
  $('count').textContent = `${total.toLocaleString()} studies · ${Number(c0.r).toLocaleString()} runs match${hostNote}`;
  $('pageinfo').textContent = total ? `page ${page + 1} / ${maxPage + 1}` : '';
  $('prev').disabled = page <= 0; $('next').disabled = page >= maxPage;
  writeUrl();
}

async function download() {
  const where = whereClause(), fname = 'registry_slice.csv';
  $('dl-status').textContent = `preparing ${fname} (${total.toLocaleString()} rows)…`;
  try {
    await conn.query(`COPY (SELECT * FROM registry ${where} ORDER BY study_accession) TO '${fname}' (HEADER, DELIMITER ',')`);
    const buf = await db.copyFileToBuffer(fname); await db.dropFile(fname);
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([buf], {type: 'text/csv'})); a.download = fname; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    $('dl-status').textContent = `${fname}: ${(buf.length / 1e6).toFixed(1)} MB`;
  } catch (e) { $('dl-status').textContent = 'download failed: ' + (e.message || e); console.error(e); }
}

function evidenceTable(json) {
  let ev = []; try { ev = JSON.parse(json || '[]'); } catch (e) { ev = []; }
  if (!Array.isArray(ev) || !ev.length) return '<span class="small">no evidence row (pending or not applicable)</span>';
  return '<table class="tbl small"><thead><tr><th>source</th><th>quote</th></tr></thead><tbody>' + ev.map(e => `<tr><td class="mono">${h(e.source)}</td><td class="quote">“${h(e.quote)}”</td></tr>`).join('') + '</tbody></table>';
}

async function showDetail(acc) {
  const box = $('detail'), body = $('detail-body');
  if (!box.classList.contains('open')) lastFocus = document.activeElement;
  box.classList.add('open'); body.innerHTML = '<p class="status">loading…</p>'; box.focus();
  const r = await conn.query(`SELECT * FROM registry WHERE study_accession = '${esc(acc)}'`);
  const rows = r.toArray();
  if (!rows.length) { body.innerHTML = `<p>No registry study <b>${h(acc)}</b>.</p>`; return; }
  const s = rows[0].toJSON();
  const p = new URLSearchParams(location.search); p.set('study', acc); history.replaceState(null, '', location.pathname + '?' + p.toString() + location.hash);
  const inc = INCLUDED.has(acc);
  const scopes = (s.scope_memberships || '').split(';').filter(Boolean);
  let html = `<h2 style="margin-top:0">${h(acc)} ${stageBadge(s.classification_stage)}</h2>
  <p class="small"><a href="${CFG.enaUrl}${h(acc)}">ENA study</a>${inc ? ` · <a href="${CFG.studiesUrl}${h(acc)}.html">catalog study page</a>` : ' · registry-only study (not in the curated catalog)'}</p>
  <p>${h(s.study_title)}</p>${s.description_short ? `<p class="small">${h(s.description_short)}</p>` : ''}
  <h3>Classification</h3><table class="tbl kv">
  <tr><td>Host human</td><td>${h(s.host_human)} <span class="small">signal rule ${h(s.human_signal_rule)}${s.ambiguous ? ' · ambiguous' : ''}</span></td></tr>
  <tr><td>Body sites</td><td>${h(s.body_sites)} <span class="small">(primary ${h(s.body_site_primary)}${s.body_site_primary && CFG.siteLabels[s.body_site_primary] ? ' — ' + h(CFG.siteLabels[s.body_site_primary]) : ''})</span></td></tr>
  <tr><td>Life stages</td><td>${h(s.life_stages)} <span class="small">(primary ${h(s.life_stage_primary)})</span></td></tr>
  <tr><td>Assay / access</td><td class="mono">${h(s.assay)} / ${h(s.access)}</td></tr>
  <tr><td>Population flags</td><td>${h(s.population_flags)}</td></tr>
  <tr><td>Health context</td><td>${h(s.health_context)}</td></tr>
  <tr><td>Scopes</td><td>${scopes.map(x => `<a href="scopes/${h(x)}.html">${h(CFG.scopeLabels[x] || x)}</a>`).join(' · ')}</td></tr>
  <tr><td>Stage · confidence · model</td><td>${stageBadge(s.classification_stage)} ${fmtV(s.classification_confidence)} ${h(s.classification_model)}</td></tr>
  </table>
  <h3>Evidence</h3><p class="small">Every committed host / site / stage value carries a labelled source and a ≤ 12-word quote; confidence is the classifier's tier, not a calibrated probability.</p>`;
  for (const [col, label] of EVIDENCE_COLS) html += `<h4>${label}</h4>${evidenceTable(s[col])}`;
  html += `<h3>Archive summary (ENA read_run aggregates)</h3><table class="tbl kv">
  <tr><td>Secondary accession · center</td><td>${h(s.secondary_study_accession)} · ${h(s.center_name)}</td></tr>
  <tr><td>First public</td><td>${h(s.first_public_min)}${s.first_public_max ? ' – ' + h(s.first_public_max) : ''}</td></tr>
  <tr><td>Runs / samples / BioSamples</td><td>${fmtV(s.n_runs)} / ${fmtV(s.n_samples)} / ${fmtV(s.n_biosamples)}</td></tr>
  <tr><td>Runs with Sandpiper profiles</td><td>${fmtV(s.n_runs_sandpiper)}</td></tr>
  <tr><td>Library strategies / sources</td><td class="mono">${h(s.library_strategies)} / ${h(s.library_sources)}</td></tr>
  <tr><td>Instrument platforms</td><td class="mono">${h(s.instrument_platforms)}</td></tr>
  <tr><td>Top scientific names</td><td class="small">${h(s.scientific_names_top)}</td></tr>
  <tr><td>Host tax ids</td><td class="mono">${h(s.host_tax_ids)} <span class="small">(${fmtV(s.n_runs_host_9606)} runs host 9606, ${fmtV(s.n_runs_nonhuman_host)} non-human host)</span></td></tr>
  <tr><td>Universe slice · release added</td><td class="mono">${h(s.universe_slice)} · ${h(s.release_added)}</td></tr>
  </table>`;
  body.innerHTML = html;
}

// wiring
$('apply').addEventListener('click', () => { page = 0; run(); });
$('reset').addEventListener('click', () => { history.replaceState(null, '', location.pathname + location.hash); for (const el of document.querySelectorAll('.filters select, .filters input')) { if (el.type === 'checkbox') el.checked = false; else el.value = ''; } setHost(HOST_DEFAULT); page = 0; sortCol = 'n_samples'; sortDir = 'DESC'; run(); });
$('prev').addEventListener('click', () => { page = Math.max(0, page - 1); run(); });
$('next').addEventListener('click', () => { page++; run(); });
$('dl-csv').addEventListener('click', download);
$('detail-close').addEventListener('click', closeDetail);
function activate(e) {
  const th = e.target.closest('th[data-col]'); if (th) { const c = th.dataset.col; if (sortCol === c) sortDir = sortDir === 'ASC' ? 'DESC' : 'ASC'; else { sortCol = c; sortDir = c === 'study_title' || c === 'study_accession' ? 'ASC' : 'DESC'; } page = 0; run(); return; }
  if (e.target.closest('a')) return;
  const tr = e.target.closest('tr[data-key]'); if (tr) showDetail(tr.dataset.key);
}
$('result-table').addEventListener('click', activate);
$('result-table').addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { if (e.target.closest('th[data-col], tr[data-key]')) { e.preventDefault(); activate(e); } } });
function closeDetail() { $('detail').classList.remove('open'); const p = new URLSearchParams(location.search); p.delete('study'); history.replaceState(null, '', location.pathname + (p.toString() ? '?' + p : '') + location.hash); if (lastFocus && document.body.contains(lastFocus)) lastFocus.focus(); }
document.addEventListener('keydown', e => { if (e.key === 'Escape' && $('detail').classList.contains('open')) closeDetail(); });
for (const el of document.querySelectorAll('.filters input')) el.addEventListener('keydown', e => { if (e.key === 'Enter') { page = 0; run(); } });
for (const el of document.querySelectorAll('.filters select, .filters input[type=checkbox]')) el.addEventListener('change', () => { page = 0; run(); });

init();
