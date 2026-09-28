// Gut (all ages) explorer — curated scope gut_all: DuckDB-WASM over data/gut_sample_metadata_wide.parquet (+ gut_studies.parquet for
// titles), fully client-side, one row per sample. Same boot / failure pattern as registry_explorer.js. Values shown with their route
// (R1 archive attribute, R2 supplementary table, R3 paper prose, R4 abstract) and confidence; the verbatim evidence quotes live in
// gut_sample_determinations.parquet (package download) — too large for the browser.
const DUCKDB_URL = 'https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm@1.29.0/+esm';
const CFG = window.GUT_CFG;
const PAGE = 50;
const FIELDS = ['age_at_collection_days', 'sex', 'bmi', 'country', 'health_condition', 'antibiotic_exposure', 'subject_id', 'timepoint_label'];
const SHOW = ['sample_key', 'study_accession', 'age_category', 'age_at_collection_days', 'sex', 'bmi', 'country', 'health_condition', 'antibiotic_exposure', 'body_site_class', 'curated_source'];
const SORTABLE = new Set(['sample_key', 'study_accession', 'age_category', 'age_at_collection_days', 'sex', 'bmi', 'country', 'health_condition', 'n_fields_with_value']);
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/'/g, "''");
const h = s => String(s === null || s === undefined ? '' : s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const fmtV = v => { if (v === null || v === undefined) return ''; if (typeof v === 'bigint') return v.toString(); if (typeof v === 'number') return Number.isInteger(v) ? v.toLocaleString() : v.toFixed(1); return String(v); };
let duckdb, db, conn, page = 0, total = 0, sortCol = 'study_accession', sortDir = 'ASC', lastFocus = null;

function setBoot(msg) { $('boot-msg').textContent = msg; }
function bootFail(e) { $('boot').innerHTML = '<b>The explorer could not start.</b> ' + h(e && e.message || e) + '<br>DuckDB-WASM (pinned 1.29.0) is loaded from cdn.jsdelivr.net; the tables are plain parquet files under data/ and can be opened with any parquet reader.'; console.error(e); }

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
    setBoot('fetching the gut sample table…');
    for (const [name, url] of [['samples.parquet', CFG.samples], ['studies.parquet', CFG.studies]]) {
      const resp = await fetch(url); if (!resp.ok) throw new Error('fetch of ' + url + ' failed: HTTP ' + resp.status);
      await db.registerFileBuffer(name, new Uint8Array(await resp.arrayBuffer()));
    }
    conn = await db.connect();
    await conn.query(`CREATE VIEW s AS SELECT * FROM read_parquet('samples.parquet')`);
    await conn.query(`CREATE VIEW st AS SELECT study_accession, study_title FROM read_parquet('studies.parquet')`);
    window.__gutReady = true;
    $('boot').style.display = 'none'; $('exp').style.display = '';
    readUrl();
    await run();
    const k = new URLSearchParams(location.search).get('sample'); if (k) showDetail(k);
  } catch (e) { bootFail(e); }
}

function whereClause() {
  const w = [];
  const q = $('f-q').value.trim();
  if (q) {
    if (/^PRJ[A-Z]*\d+$/i.test(q)) w.push(`s.study_accession = '${esc(q.toUpperCase())}'`);
    else if (/^SAM[NED]A?\d+$/i.test(q)) w.push(`s.sample_key = '${esc(q.toUpperCase())}'`);
    else w.push(`(st.study_title ILIKE '%${esc(q)}%' OR s.study_accession ILIKE '%${esc(q)}%')`);
  }
  for (const sel of document.querySelectorAll('select[data-field]')) { const v = sel.value; if (!v) continue; w.push(v === '__null__' ? `s."${sel.dataset.field}" IS NULL` : `s."${sel.dataset.field}" = '${esc(v)}'`); }
  if ($('f-infant').checked) w.push(`s.infant_scope`);
  if ($('f-has_age').checked) w.push(`s.age_at_collection_days IS NOT NULL`);
  const mn = $('f-min_fields').value; if (mn !== '') w.push(`s.n_fields_with_value >= ${parseInt(mn)}`);
  return w.length ? 'WHERE ' + w.join(' AND ') : '';
}
const FROM = 'FROM s LEFT JOIN st USING (study_accession)';

function writeUrl() {
  const p = new URLSearchParams();
  if ($('f-q').value.trim()) p.set('q', $('f-q').value.trim());
  for (const sel of document.querySelectorAll('select[data-field]')) if (sel.value) p.set(sel.id.replace(/^f-/, ''), sel.value);
  if ($('f-infant').checked) p.set('infant', '1'); if ($('f-has_age').checked) p.set('has_age', '1');
  if ($('f-min_fields').value !== '') p.set('min_fields', $('f-min_fields').value);
  if (page) p.set('page', page + 1);
  if (sortCol !== 'study_accession' || sortDir !== 'ASC') p.set('sort', sortCol + ':' + sortDir);
  const keep = new URLSearchParams(location.search).get('sample'); if (keep && $('detail').classList.contains('open')) p.set('sample', keep);
  history.replaceState(null, '', location.pathname + (p.toString() ? '?' + p.toString() : '') + location.hash);
}
function readUrl() {
  const p = new URLSearchParams(location.search);
  if (p.get('q')) $('f-q').value = p.get('q');
  for (const sel of document.querySelectorAll('select[data-field]')) { const v = p.get(sel.id.replace(/^f-/, '')); if (v) sel.value = v; }
  if (p.get('infant')) $('f-infant').checked = true; if (p.get('has_age')) $('f-has_age').checked = true;
  if (p.get('min_fields')) $('f-min_fields').value = p.get('min_fields');
  if (p.get('page')) page = Math.max(0, parseInt(p.get('page')) - 1);
  if (p.get('sort')) { const [c, d] = p.get('sort').split(':'); if (SORTABLE.has(c)) { sortCol = c; sortDir = d === 'DESC' ? 'DESC' : 'ASC'; } }
}
function routeBadge(r, c) { return r ? `<span class="tag ${h(r)}" title="route ${h(r)}, confidence ${fmtV(c)}">${h(r)}</span>` : ''; }

async function run() {
  const where = whereClause();
  $('count').textContent = 'counting…';
  const c = await conn.query(`SELECT COUNT(*) AS n, COUNT(DISTINCT s.study_accession) AS k ${FROM} ${where}`);
  const c0 = c.toArray()[0].toJSON(); total = Number(c0.n);
  const maxPage = Math.max(0, Math.ceil(total / PAGE) - 1); if (page > maxPage) page = maxPage;
  const r = await conn.query(`SELECT s.* ${FROM} ${where} ORDER BY "${sortCol}" ${sortDir} NULLS LAST, sample_key LIMIT ${PAGE} OFFSET ${page * PAGE}`);
  const rows = r.toArray().map(x => x.toJSON());
  const thead = $('result-table').querySelector('thead'), tbody = $('result-table').querySelector('tbody');
  thead.innerHTML = '<tr>' + SHOW.map(col => SORTABLE.has(col)
    ? `<th data-col="${col}" tabindex="0" role="columnheader button" aria-sort="${col === sortCol ? (sortDir === 'ASC' ? 'ascending' : 'descending') : 'none'}" title="sort by ${col}" style="cursor:pointer">${col}${col === sortCol ? (sortDir === 'ASC' ? ' ▲' : ' ▼') : ''}</th>`
    : `<th>${col}</th>`).join('') + '</tr>';
  tbody.innerHTML = rows.map(row => `<tr data-key="${h(row.sample_key)}" tabindex="0" role="button" aria-label="open details for ${h(row.sample_key)}">` +
    `<td class="mono">${h(row.sample_key)}</td><td>${studyLink(row)}</td><td>${h(row.age_category)}</td><td class="num">${fmtV(row.age_at_collection_days)} ${routeBadge(row.age_at_collection_days__route, row.age_at_collection_days__confidence)}</td>` +
    `<td>${h(row.sex)}</td><td class="num">${fmtV(row.bmi)}</td><td>${h(row.country)}</td><td>${h(row.health_condition)} ${routeBadge(row.health_condition__route, row.health_condition__confidence)}</td><td>${h(row.antibiotic_exposure)}</td><td class="small">${h(row.body_site_class)}</td><td class="small">${h(row.curated_source)}</td></tr>`).join('');
  $('count').textContent = `${total.toLocaleString()} samples in ${Number(c0.k).toLocaleString()} studies match`;
  $('pageinfo').textContent = total ? `page ${page + 1} / ${maxPage + 1}` : '';
  $('prev').disabled = page <= 0; $('next').disabled = page >= maxPage;
  writeUrl();
}
function studyLink(row) {
  const acc = row.study_accession;
  return (row.in_infant_catalog && CFG.includedStudies.includes(acc)) ? `<a href="${CFG.studiesUrl}${h(acc)}.html">${h(acc)}</a>` : `<a class="mono" href="${CFG.registryUrl}?study=${h(acc)}">${h(acc)}</a>`;
}

async function download() {
  const where = whereClause(), fname = 'gut_samples_slice.csv';
  $('dl-status').textContent = `preparing ${fname} (${total.toLocaleString()} rows)…`;
  try {
    await conn.query(`COPY (SELECT s.*, st.study_title ${FROM} ${where} ORDER BY s.study_accession, s.sample_key) TO '${fname}' (HEADER, DELIMITER ',')`);
    const buf = await db.copyFileToBuffer(fname); await db.dropFile(fname);
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([buf], {type: 'text/csv'})); a.download = fname; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    $('dl-status').textContent = `${fname}: ${(buf.length / 1e6).toFixed(1)} MB`;
  } catch (e) { $('dl-status').textContent = 'download failed: ' + (e.message || e); console.error(e); }
}

async function showDetail(key) {
  const box = $('detail'), body = $('detail-body');
  if (!box.classList.contains('open')) lastFocus = document.activeElement;
  box.classList.add('open'); body.innerHTML = '<p class="status">loading…</p>'; box.focus();
  const r = await conn.query(`SELECT s.*, st.study_title ${FROM} WHERE s.sample_key = '${esc(key)}'`);
  const rows = r.toArray(); if (!rows.length) { body.innerHTML = `<p>No sample <b>${h(key)}</b>.</p>`; return; }
  const s = rows[0].toJSON();
  const p = new URLSearchParams(location.search); p.set('sample', key); history.replaceState(null, '', location.pathname + '?' + p.toString() + location.hash);
  let html = `<h2 style="margin-top:0">${h(key)}</h2><p>${studyLink(s)} · ${h(s.study_title)}</p>
  <p class="small"><a href="${CFG.enaSampleUrl}${h(s.biosample_accession || key)}">ENA BioSample</a> · unit ${h(s.sample_unit)} · body site ${h(s.body_site_code)} (${h(s.body_site_class)}) · source ${h(s.curated_source)}${s.infant_scope ? ' · <b>infant catalog scope</b>' : ''}</p>
  <h3>Age category</h3><p><b>${h(s.age_category)}</b> <span class="small">(basis: ${h(s.age_category_basis)})</span></p>
  <h3>Fields</h3><table class="tbl kv">`;
  for (const f of FIELDS) html += `<tr><td>${f}</td><td>${fmtV(s[f])} ${routeBadge(s[f + '__route'], s[f + '__confidence'])}</td></tr>`;
  if (s.health_condition_detail) html += `<tr><td>health_condition_detail</td><td class="small">${h(s.health_condition_detail)}</td></tr>`;
  html += '</table>';
  const inf = ['delivery_mode', 'feeding_mode', 'preterm_status', 'gestational_age_weeks', 'birth_weight_grams', 'maternal_antibiotics', 'probiotic_exposure', 'hmo_supplementation', 'nec_status'].filter(f => s[f] !== null && s[f] !== undefined);
  if (inf.length) html += '<h3>Infant-catalog fields</h3><table class="tbl kv">' + inf.map(f => `<tr><td>${f}</td><td>${fmtV(s[f])}</td></tr>`).join('') + '</table>';
  html += `<p class="small">Evidence quotes (verbatim, ≤ 12 words, with source and locator) for every value are in <span class="mono">gut_sample_determinations.parquet</span> (Downloads); the infant-catalog samples also have them in the <a href="${CFG.samplesUrl}?study=${h(s.study_accession)}">infant sample explorer</a>.</p>`;
  body.innerHTML = html;
}

$('apply').addEventListener('click', () => { page = 0; run(); });
$('reset').addEventListener('click', () => { history.replaceState(null, '', location.pathname + location.hash); for (const el of document.querySelectorAll('.filters select, .filters input')) { if (el.type === 'checkbox') el.checked = false; else el.value = ''; } page = 0; sortCol = 'study_accession'; sortDir = 'ASC'; run(); });
$('prev').addEventListener('click', () => { page = Math.max(0, page - 1); run(); });
$('next').addEventListener('click', () => { page++; run(); });
$('dl-csv').addEventListener('click', download);
$('detail-close').addEventListener('click', closeDetail);
function activate(e) {
  const th = e.target.closest('th[data-col]'); if (th) { const c = th.dataset.col; if (sortCol === c) sortDir = sortDir === 'ASC' ? 'DESC' : 'ASC'; else { sortCol = c; sortDir = 'ASC'; } page = 0; run(); return; }
  if (e.target.closest('a')) return;
  const tr = e.target.closest('tr[data-key]'); if (tr) showDetail(tr.dataset.key);
}
$('result-table').addEventListener('click', activate);
$('result-table').addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { if (e.target.closest('th[data-col], tr[data-key]')) { e.preventDefault(); activate(e); } } });
function closeDetail() { $('detail').classList.remove('open'); const p = new URLSearchParams(location.search); p.delete('sample'); history.replaceState(null, '', location.pathname + (p.toString() ? '?' + p.toString() : '') + location.hash); if (lastFocus) lastFocus.focus(); }
document.addEventListener('keydown', e => { if (e.key === 'Escape' && $('detail').classList.contains('open')) closeDetail(); });
for (const el of document.querySelectorAll('.filters input')) el.addEventListener('keydown', e => { if (e.key === 'Enter') { page = 0; run(); } });
for (const el of document.querySelectorAll('.filters select, .filters input[type=checkbox]')) el.addEventListener('change', () => { page = 0; run(); });

init();
