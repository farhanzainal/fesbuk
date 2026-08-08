# -*- coding: utf-8 -*-
"""fesbuk local dashboard — http://127.0.0.1:8769/dashboard

White theme + sidebar + glassmorphism cards.
Header: connected FB pages + live status.
Body  : stat cards, pending/scheduled posts (SQLite), recent posted.
"""
import json
import urllib.request
import urllib.parse
from datetime import datetime

from flask import Flask, jsonify, render_template_string, request, redirect
from datetime import datetime, timedelta, timezone

import config
import db
import fb_spend
import fb_page

app = Flask(__name__)


@app.template_filter("fmtdate")
def fmtdate(iso_str):
    """'2026-08-08T04:03:08+00:00' -> '08 Aug 2026 12:03 PM' (Malaysia time, UTC+8)."""
    if not iso_str:
        return "-"
    try:
        dt = datetime.fromisoformat(str(iso_str).replace("Z", "+00:00"))
        dt = dt + timedelta(hours=8)  # UTC -> MYT
        return dt.strftime("%d %b %Y %I:%M %p")
    except Exception:
        return str(iso_str)[:16]


@app.template_filter("fmtlocal")
def fmtlocal(iso_str):
    """UTC ISO -> 'YYYY-MM-DDTHH:MM' waktu Malaysia (untuk input datetime-local)."""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(str(iso_str).replace("Z", "+00:00"))
        dt = dt + timedelta(hours=8)  # UTC -> MYT
        return dt.strftime("%Y-%m-%dT%H:%M")
    except Exception:
        return str(iso_str)[:16]

HTML = """<!doctype html>
<html lang="ms">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>fesbuk · Dashboard</title>
<style>
  :root {
    --ink:#1a2332; --muted:#6b7a90; --line:rgba(255,255,255,.55);
    --accent:#4f6ef7; --accent2:#7c5cf0; --good:#16a34a; --warn:#d97706; --bad:#dc2626;
  }
  * { box-sizing:border-box; margin:0; padding:0; }
  body {
    font-family:'Segoe UI', system-ui, -apple-system, sans-serif;
    background:linear-gradient(135deg,#eef2ff 0%,#f8fafc 45%,#e0e7ff 100%);
    min-height:100vh; color:var(--ink); display:flex;
  }
  /* ---------- SIDEBAR ---------- */
  .sidebar {
    width:240px; min-height:100vh; padding:22px 16px; position:sticky; top:0;
    background:rgba(255,255,255,.55); backdrop-filter:blur(16px); -webkit-backdrop-filter:blur(16px);
    border-right:1px solid var(--line);
  }
  .logo { display:flex; align-items:center; gap:10px; padding:4px 8px 20px; font-size:20px; font-weight:800; }
  .logo .dot { width:14px; height:14px; border-radius:6px; background:linear-gradient(135deg,var(--accent),var(--accent2)); box-shadow:0 4px 10px rgba(79,110,247,.4); }
  .nav { display:flex; flex-direction:column; gap:6px; }
  .nav a {
    display:flex; align-items:center; gap:10px; padding:10px 12px; border-radius:12px;
    color:var(--muted); text-decoration:none; font-size:14px; font-weight:600; transition:.15s;
  }
  .nav a:hover { background:rgba(255,255,255,.7); color:var(--ink); }
  .nav a.active { background:#fff; color:var(--accent); box-shadow:0 4px 14px rgba(30,40,90,.08); }
  .side-foot { margin-top:34px; padding:12px; border-radius:14px; background:rgba(255,255,255,.5); font-size:12px; color:var(--muted); }
  /* ---------- MAIN ---------- */
  .main { flex:1; padding:28px 34px; max-width:1100px; }
  .top { display:flex; justify-content:space-between; align-items:center; margin-bottom:24px; }
  .top h1 { font-size:24px; font-weight:800; }
  .top .sub { color:var(--muted); font-size:13px; margin-top:2px; }
  .pill { padding:6px 14px; border-radius:20px; font-size:12px; font-weight:700; background:rgba(255,255,255,.7); border:1px solid var(--line); }
  /* ---------- GLASS CARDS ---------- */
  .glass {
    background:rgba(255,255,255,.55); backdrop-filter:blur(14px); -webkit-backdrop-filter:blur(14px);
    border:1px solid var(--line); border-radius:18px; box-shadow:0 8px 28px rgba(30,40,90,.07);
    padding:18px 20px;
  }
  .stats { display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin-bottom:20px; }
  .stat { padding:16px 18px; }
  .stat .v { font-size:28px; font-weight:800; }
  .stat .l { font-size:12px; color:var(--muted); font-weight:600; margin-top:2px; }
  .stat .i { font-size:18px; margin-bottom:6px; }
  .badge { padding:4px 11px; border-radius:20px; font-size:11px; font-weight:700; }
  .badge.live { background:#dcfce7; color:var(--good); }
  .badge.dead { background:#fee2e2; color:var(--bad); }
  .st-pending { color:var(--warn); font-weight:700; }
  .st-posted { color:var(--good); font-weight:700; }
  h2 { font-size:14px; font-weight:800; text-transform:uppercase; letter-spacing:1px; color:var(--muted); margin:26px 0 10px; }
  .page { display:flex; align-items:center; justify-content:space-between; margin-bottom:10px; }
  .page .name { font-weight:700; font-size:14px; }
  .page .id { color:var(--muted); font-size:12px; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th { text-align:left; color:var(--muted); font-weight:700; padding:8px 10px; border-bottom:1px solid rgba(30,40,90,.08); font-size:11px; text-transform:uppercase; letter-spacing:.5px; }
  td { padding:9px 10px; border-bottom:1px solid rgba(30,40,90,.05); vertical-align:top; }
  .preview { color:#44506b; max-width:400px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  a { color:var(--accent); text-decoration:none; }
  .foot { color:var(--muted); font-size:12px; margin-top:24px; }
  .empty { color:var(--muted); font-size:13px; padding:6px 0; }
  /* ---------- PAGE SETUP NUDGE (token belum sambung) ---------- */
  .setup-nudge { background:rgba(255,255,255,.65); border:1.5px solid rgba(79,110,247,.35); border-radius:16px; padding:18px 20px; margin-bottom:20px; }
  .setup-nudge .t { font-weight:800; font-size:14px; color:var(--accent); margin-bottom:6px; }
  .setup-nudge ol { margin:0 0 12px; padding-left:20px; font-size:13px; line-height:1.9; }
  .setup-nudge code { background:#eef1fb; padding:1px 6px; border-radius:5px; font-size:12px; color:var(--accent); }
  .paste { width:100%; min-height:70px; border:1.5px dashed rgba(79,110,247,.5); border-radius:12px; padding:12px; font-family:monospace; font-size:12px; resize:vertical; margin:6px 0 10px; }
  .err { color:var(--bad); font-size:13px; min-height:18px; font-weight:600; margin-bottom:8px; }
  .btn { padding:7px 14px; border-radius:20px; border:1px solid rgba(79,110,247,.4); background:#fff; color:var(--accent); font-weight:700; font-size:12px; cursor:pointer; text-decoration:none; display:inline-block; }
  .btn:hover { background:var(--accent); color:#fff; }
  .btn.primary { background:var(--accent); color:#fff; border-color:var(--accent); padding:9px 20px; font-size:13px; }
  .btn.primary:hover { background:#3d5ae0; }
  .ok-banner { background:#dcfce7; color:var(--good); font-weight:700; font-size:13px; border-radius:12px; padding:12px 16px; margin-bottom:16px; }
</style>
</head>
<body>

<aside class="sidebar">
  <div class="logo"><span class="dot"></span> fesbuk</div>
  <nav class="nav">
    <a class="active" href="/dashboard">📊 Dashboard</a>
    <a href="/post">📝 Post</a>
    <a href="/pages">📄 Pages</a>
    <a href="/ads">💸 Ads</a>
  </nav>
  <div class="side-foot">
    token: <b>{{ 'OK' if token_ok else 'MISSING' }}</b><br>
    page: <b>{{ config_page or '-' }}</b><br>
    v0.1.0
  </div>
</aside>

<main class="main">
  <div class="top">
    <div>
      <h1>Dashboard</h1>
      <div class="sub">{{ now }} · fesbuk Facebook integration</div>
    </div>
    <span class="pill">{{ pages|length }} page(s)</span>
  </div>

  {% if connected_flag %}
  <div class="ok-banner">✅ Page berjaya disambung! Posting & dashboard sedia digunakan.</div>
  {% endif %}

  {% if page_setup_needed %}
  <div class="setup-nudge">
    <div class="t">🔑 Sambung Facebook Page — token belum aktif</div>
    <ol>
      <li>Buka <a href="https://developers.facebook.com/tools/explorer/" target="_blank">Graph API Explorer</a> → pilih app ID <b>{{ app_id or '-' }}</b></li>
      <li>Mode <b>User Token</b> → Add permission <code>pages_show_list</code>, <code>pages_manage_posts</code>, <code>pages_read_engagement</code></li>
      <li>Klik <b>Generate Access Token</b> → benarkan semua permission</li>
      <li>Salin token (mula dgn <code>EAAT...</code>) dan tampal kat bawah → klik <b>Sambung</b></li>
    </ol>
    <div class="err" id="pErr"></div>
    <textarea class="paste" id="ptok" placeholder="Tampal token user (EAAT...)"></textarea>
    <button class="btn primary" onclick="connectPage(this)">Sambung</button>
  </div>
  {% endif %}

  <div class="stats">
    <div class="glass stat"><div class="i">📄</div><div class="v">{{ pages|length }}</div><div class="l">Pages Connected</div></div>
    <div class="glass stat"><div class="i">🟢</div><div class="v">{{ live_count }}</div><div class="l">Pages Live</div></div>
    <div class="glass stat"><div class="i">⏳</div><div class="v">{{ pending|length }}</div><div class="l">Pending Posts</div></div>
    <div class="glass stat"><div class="i">✅</div><div class="v">{{ posted|length }}</div><div class="l">Posted</div></div>
  </div>

  <h2>Pages</h2>
  <div class="glass">
    {% for p in pages %}
    <div class="page">
      <div>
        <div class="name">{{ p.name }}</div>
        <div class="id">{{ p.id }}{% if p.page_id and p.page_id != p.id %} · config PAGE_ID={{ p.page_id }}{% endif %}</div>
      </div>
      <span class="badge {{ 'live' if p.live else 'dead' }}">{{ 'LIVE' if p.live else 'OFFLINE' }}</span>
    </div>
    {% else %}
    <div class="empty">Tiada page dijumpai. Pastikan token user ada akses pages_show_list.</div>
    {% endfor %}
  </div>

  <div class="foot">fesbuk v0.1.0</div>
</main>

<script>
function connectPage(btn){
  var tok = document.getElementById('ptok').value.trim();
  var err = document.getElementById('pErr');
  if(!tok){ err.textContent = '❌ Tampal token dulu.'; return; }
  btn.disabled = true; btn.textContent = 'Menyambung...';
  fetch('/api/page/activate', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({token: tok})})
    .then(function(r){ return r.json(); })
    .then(function(d){
      if(d.ok){ location.href = '/dashboard?connected=1'; }
      else {
        err.textContent = '❌ ' + (d.error || 'Gagal. Cuba lagi.');
        btn.disabled = false; btn.textContent = 'Sambung';
      }
    })
    .catch(function(e){
      err.textContent = '❌ ' + e;
      btn.disabled = false; btn.textContent = 'Sambung';
    });
}
</script>

</body>
</html>"""

POST_HTML = """<!doctype html>
<html lang="ms">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>fesbuk · Post</title>
<style>
  :root { --ink:#1a2332; --muted:#6b7a90; --line:rgba(255,255,255,.55); --accent:#4f6ef7; --accent2:#7c5cf0; --good:#16a34a; --warn:#d97706; --bad:#dc2626; }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { font-family:'Segoe UI', system-ui, sans-serif; background:linear-gradient(135deg,#eef2ff 0%,#f8fafc 45%,#e0e7ff 100%); min-height:100vh; color:var(--ink); display:flex; }
  .sidebar { width:240px; min-height:100vh; padding:22px 16px; position:sticky; top:0; background:rgba(255,255,255,.55); backdrop-filter:blur(16px); border-right:1px solid var(--line); }
  .logo { display:flex; align-items:center; gap:10px; padding:4px 8px 20px; font-size:20px; font-weight:800; }
  .logo .dot { width:14px; height:14px; border-radius:6px; background:linear-gradient(135deg,var(--accent),var(--accent2)); box-shadow:0 4px 10px rgba(79,110,247,.4); }
  .nav { display:flex; flex-direction:column; gap:6px; }
  .nav a { display:flex; align-items:center; gap:10px; padding:10px 12px; border-radius:12px; color:var(--muted); text-decoration:none; font-size:14px; font-weight:600; transition:.15s; }
  .nav a:hover { background:rgba(255,255,255,.7); color:var(--ink); }
  .nav a.active { background:#fff; color:var(--accent); box-shadow:0 4px 14px rgba(30,40,90,.08); }
  .side-foot { margin-top:34px; padding:12px; border-radius:14px; background:rgba(255,255,255,.5); font-size:12px; color:var(--muted); }
  .main { flex:1; padding:28px 34px; max-width:1100px; }
  .top { display:flex; justify-content:space-between; align-items:center; margin-bottom:24px; }
  .top h1 { font-size:24px; font-weight:800; }
  .top .sub { color:var(--muted); font-size:13px; margin-top:2px; }
  .glass { background:rgba(255,255,255,.55); backdrop-filter:blur(14px); border:1px solid var(--line); border-radius:18px; box-shadow:0 8px 28px rgba(30,40,90,.07); padding:18px 20px; }
  .toolbar { display:flex; justify-content:space-between; align-items:center; margin-bottom:14px; gap:12px; }
  .search { display:flex; gap:8px; }
  .search input { padding:9px 14px; border-radius:12px; border:1px solid rgba(30,40,90,.12); background:#fff; font-size:13px; width:240px; outline:none; }
  .search input:focus { border-color:var(--accent); }
  .btn { padding:9px 16px; border-radius:12px; border:none; background:linear-gradient(135deg,var(--accent),var(--accent2)); color:#fff; font-weight:700; font-size:13px; cursor:pointer; }
  .st-pending { color:var(--warn); font-weight:700; } .st-posted { color:var(--good); font-weight:700; }
  .badge-src { display:inline-block; padding:3px 10px; border-radius:20px; font-size:11px; font-weight:700; white-space:nowrap; }
  .badge-src.user { background:#e0e7ff; color:#4338ca; }
  .badge-src.bot { background:#f3e8ff; color:#7e22ce; }
  .btn.mini { padding:6px 9px; font-size:13px; border-radius:10px; text-decoration:none; display:inline-flex; align-items:center; justify-content:center; line-height:1; border:1px solid rgba(30,40,90,.1); background:#fff; color:var(--muted); cursor:pointer; transition:.15s; }
  .btn.mini:hover { background:#eef2ff; color:var(--accent); border-color:var(--accent); }
  .row-actions { display:flex; gap:5px; align-items:center; white-space:nowrap; }
  .row-actions form { display:inline; }
  /* ---- analysis modal ---- */
  .modal-overlay { position:fixed; inset:0; background:rgba(15,23,42,.45); backdrop-filter:blur(4px); display:flex; align-items:center; justify-content:center; z-index:100; }
  .modal { background:#fff; border-radius:18px; box-shadow:0 20px 60px rgba(15,23,42,.25); width:460px; max-width:92vw; overflow:hidden; }
  .modal-head { display:flex; justify-content:space-between; align-items:center; padding:16px 20px; font-weight:800; font-size:15px; border-bottom:1px solid rgba(30,40,90,.08); }
  .modal-x { border:none; background:#f1f5fb; color:var(--muted); width:30px; height:30px; border-radius:10px; cursor:pointer; font-size:13px; font-weight:700; }
  .modal-x:hover { background:#e2e8f0; color:var(--ink); }
  .modal-body { padding:20px; }
  .stat-grid { display:grid; grid-template-columns:1fr 1fr 1fr; gap:10px; }
  .stat-card { background:#f8fafc; border:1px solid rgba(30,40,90,.07); border-radius:14px; padding:14px 10px; text-align:center; }
  .stat-card .v { font-size:20px; font-weight:800; color:var(--accent); }
  .stat-card .l { font-size:11px; color:var(--muted); font-weight:600; margin-top:3px; }
  .modal-foot { margin-top:16px; text-align:right; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th { text-align:left; color:var(--muted); font-weight:700; padding:8px 10px; border-bottom:1px solid rgba(30,40,90,.08); font-size:11px; text-transform:uppercase; letter-spacing:.5px; }
  td { padding:9px 10px; border-bottom:1px solid rgba(30,40,90,.05); vertical-align:top; }
  .preview { color:#44506b; max-width:380px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  a { color:var(--accent); text-decoration:none; }
  .pager { display:flex; justify-content:space-between; align-items:center; margin-top:16px; font-size:13px; color:var(--muted); }
  .pager .pages a { margin-left:8px; padding:6px 12px; border-radius:10px; background:#fff; border:1px solid rgba(30,40,90,.1); }
  .empty { color:var(--muted); font-size:13px; padding:6px 0; }
</style>
</head>
<body>

<aside class="sidebar">
  <div class="logo"><span class="dot"></span> fesbuk</div>
  <nav class="nav">
    <a href="/dashboard">📊 Dashboard</a>
    <a class="active" href="/post">📝 Post</a>
    <a href="/pages">📄 Pages</a>
    <a href="/ads">💸 Ads</a>
  </nav>
  <div class="side-foot">token: <b>{{ 'OK' if token_ok else 'MISSING' }}</b><br>page: <b>{{ config_page or '-' }}</b><br>v0.1.0</div>
</aside>

<main class="main">
  <div class="top">
    <div>
      <h1>Post</h1>
      <div class="sub">{{ total }} rekod · page {{ page }} dari {{ total_pages }}</div>
    </div>
  </div>

  <div style="display:flex;justify-content:flex-end;margin-bottom:16px;">
    <a href="/post/new" class="btn" style="text-decoration:none;padding:11px 20px;font-size:14px;">➕ Tambah Post</a>
  </div>

  <div class="glass">
    <div class="toolbar">
      <form class="search" method="get" action="/post">
        <input type="text" name="q" value="{{ q }}" placeholder="Cari post...">
        <button class="btn" type="submit">Cari</button>
        {% if q %}<a href="/post" style="align-self:center">✕ clear</a>{% endif %}
      </form>
    </div>
    {% if posts %}
    <table>
      <tr><th>#</th><th>Date Created</th><th>Posted</th><th>Scheduled</th><th>By</th><th>Preview</th><th>Status</th><th>FB post</th><th>Actions</th></tr>
      {% for p in posts %}
      <tr>
        <td>{{ p.id }}</td>
        <td>{{ p.created_at | fmtdate }}</td>
        <td>{{ p.posted_at | fmtdate }}</td>
        <td>{{ p.scheduled_at | fmtdate }}</td>
        <td>{% if p.msg_file and p.msg_file.startswith('manual_') %}<span class="badge-src user">👤 User</span>{% else %}<span class="badge-src bot">🤖 Bot</span>{% endif %}</td>
        <td class="preview">{% if p.image %}🖼️ {% endif %}{{ p.text }}</td>
        <td class="st-{{ p.status }}">{{ p.status }}</td>
        <td>{% if p.fb_post_id %}<a href="https://www.facebook.com/{{ p.fb_post_id }}">link</a>{% else %}-{% endif %}</td>
        <td class="row-actions">
          <a class="btn mini" href="/post/{{ p.id }}/edit" title="Edit">✏️</a>
          <form method="post" action="/post/{{ p.id }}/delete" onsubmit="return confirm('Buang post #{{ p.id }} ni? Tindakan ni tak boleh undo.');">
            <button class="btn mini" type="submit" title="Buang">🗑️</button>
          </form>
          {% if p.status == 'pending' %}
          <form method="post" action="/post/{{ p.id }}/publish">
            <button class="btn mini" type="submit" title="Post sekarang">🚀</button>
          </form>
          {% endif %}
          {% if p.fb_post_id %}
          <button class="btn mini" type="button" title="Analisis" data-pid="{{ p.id }}" data-fbid="{{ p.fb_post_id }}" onclick="showAnalysis(this)">📊</button>
          {% endif %}
        </td>
      </tr>
      {% endfor %}
    </table>
    <div class="pager">
      <span>{{ total }} rekod</span>
      <span class="pages">
        {% if page > 1 %}<a href="/post?page={{ page - 1 }}{% if q %}&q={{ q }}{% endif %}">← Prev</a>{% endif %}
        <span>{{ page }} / {{ total_pages }}</span>
        {% if page < total_pages %}<a href="/post?page={{ page + 1 }}{% if q %}&q={{ q }}{% endif %}">Next →</a>{% endif %}
      </span>
    </div>
    {% else %}<div class="empty">Tiada post dijumpai. 😎</div>{% endif %}
  </div>

  <div class="foot" style="color:var(--muted);font-size:12px;margin-top:20px;">fesbuk v0.1.0</div>
</main>

<div class="modal-overlay" id="analysisModal" style="display:none;" onclick="if(event.target===this)closeAnalysis()">
  <div class="modal">
    <div class="modal-head">
      <span>📊 Analisis Post</span>
      <button class="modal-x" onclick="closeAnalysis()">✕</button>
    </div>
    <div class="modal-body" id="analysisBody"><div class="empty">Memuat data...</div></div>
  </div>
</div>

<script>
function showAnalysis(btn) {
  var pid = btn.getAttribute('data-pid');
  var fbId = btn.getAttribute('data-fbid');
  document.getElementById('analysisModal').style.display = 'flex';
  document.getElementById('analysisBody').innerHTML = '<div class="empty">Memuat data dari Facebook...</div>';
  fetch('/api/post/' + pid + '/analysis')
    .then(r => r.json())
    .then(d => {
      if (d.error) { document.getElementById('analysisBody').innerHTML = '<div class="empty" style="color:var(--bad)">⚠️ ' + d.error + '</div>'; return; }
      var n = function(v) { return (v === null || v === undefined) ? '—' : v; };
      var note = d.insights_ok ? '' : '<div class="empty" style="margin-top:12px;">💡 Views/Reach perlukan permission <code>read_insights</code> pada token — regenerate token kat Graph API Explorer untuk dapat data tu.</div>';
      document.getElementById('analysisBody').innerHTML =
        '<div class="stat-grid">' +
        '<div class="stat-card"><div class="v">' + n(d.views) + '</div><div class="l">👁️ Views</div></div>' +
        '<div class="stat-card"><div class="v">' + n(d.reach) + '</div><div class="l">📡 Reach</div></div>' +
        '<div class="stat-card"><div class="v">' + n(d.reactions) + '</div><div class="l">👍 Reactions</div></div>' +
        '<div class="stat-card"><div class="v">' + n(d.comments) + '</div><div class="l">💬 Komen</div></div>' +
        '<div class="stat-card"><div class="v">' + n(d.shares) + '</div><div class="l">🔁 Share</div></div>' +
        '<div class="stat-card"><div class="v">' + n(d.engaged) + '</div><div class="l">🎯 Engaged</div></div>' +
        '</div>' + note +
        '<div class="modal-foot"><a class="btn" target="_blank" href="https://www.facebook.com/' + fbId + '">Buka di Facebook →</a></div>';
    })
    .catch(e => document.getElementById('analysisBody').innerHTML = '<div class="empty" style="color:var(--bad)">⚠️ Gagal: ' + e + '</div>');
}
function closeAnalysis() { document.getElementById('analysisModal').style.display = 'none'; }
</script>

</body>
</html>"""

PAGES_HTML = """<!doctype html>
<html lang="ms">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>fesbuk · Pages</title>
<style>
  :root { --ink:#1a2332; --muted:#6b7a90; --line:rgba(255,255,255,.55); --accent:#4f6ef7; --accent2:#7c5cf0; --good:#16a34a; --warn:#d97706; --bad:#dc2626; }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { font-family:'Segoe UI', system-ui, sans-serif; background:linear-gradient(135deg,#eef2ff 0%,#f8fafc 45%,#e0e7ff 100%); min-height:100vh; color:var(--ink); display:flex; }
  .sidebar { width:240px; min-height:100vh; padding:22px 16px; position:sticky; top:0; background:rgba(255,255,255,.55); backdrop-filter:blur(16px); border-right:1px solid var(--line); }
  .logo { display:flex; align-items:center; gap:10px; padding:4px 8px 20px; font-size:20px; font-weight:800; }
  .logo .dot { width:14px; height:14px; border-radius:6px; background:linear-gradient(135deg,var(--accent),var(--accent2)); box-shadow:0 4px 10px rgba(79,110,247,.4); }
  .nav { display:flex; flex-direction:column; gap:6px; }
  .nav a { display:flex; align-items:center; gap:10px; padding:10px 12px; border-radius:12px; color:var(--muted); text-decoration:none; font-size:14px; font-weight:600; transition:.15s; }
  .nav a:hover { background:rgba(255,255,255,.7); color:var(--ink); }
  .nav a.active { background:#fff; color:var(--accent); box-shadow:0 4px 14px rgba(30,40,90,.08); }
  .side-foot { margin-top:34px; padding:12px; border-radius:14px; background:rgba(255,255,255,.5); font-size:12px; color:var(--muted); }
  .main { flex:1; padding:28px 34px; max-width:900px; }
  .top { display:flex; justify-content:space-between; align-items:center; margin-bottom:24px; }
  .top h1 { font-size:24px; font-weight:800; }
  .top .sub { color:var(--muted); font-size:13px; margin-top:2px; }
  .glass { background:rgba(255,255,255,.55); backdrop-filter:blur(14px); border:1px solid var(--line); border-radius:18px; box-shadow:0 8px 28px rgba(30,40,90,.07); padding:18px 20px; }
  .page { display:flex; align-items:center; justify-content:space-between; padding:12px 4px; border-bottom:1px solid rgba(30,40,90,.06); }
  .page:last-child { border-bottom:none; }
  .page .name { font-weight:700; font-size:14px; }
  .page .id { color:var(--muted); font-size:12px; }
  .badge { padding:4px 11px; border-radius:20px; font-size:11px; font-weight:700; }
  .badge.live { background:#dcfce7; color:var(--good); }
  .badge.dead { background:#fee2e2; color:var(--bad); }
  .badge.hid { background:#fef3c7; color:var(--warn); }
  .btn { padding:7px 14px; border-radius:12px; border:none; background:linear-gradient(135deg,var(--accent),var(--accent2)); color:#fff; font-weight:700; font-size:12px; cursor:pointer; }
  .btn.ghost { background:#fff; color:var(--muted); border:1px solid rgba(30,40,90,.12); }
  .empty { color:var(--muted); font-size:13px; padding:6px 0; }
  .foot { color:var(--muted); font-size:12px; margin-top:24px; }
</style>
</head>
<body>

<aside class="sidebar">
  <div class="logo"><span class="dot"></span> fesbuk</div>
  <nav class="nav">
    <a href="/dashboard">📊 Dashboard</a>
    <a href="/post">📝 Post</a>
    <a class="active" href="/pages">📄 Pages</a>
    <a href="/ads">💸 Ads</a>
  </nav>
  <div class="side-foot">token: <b>{{ 'OK' if token_ok else 'MISSING' }}</b><br>page: <b>{{ config_page or '-' }}</b><br>v0.1.0</div>
</aside>

<main class="main">
  <div class="top">
    <div>
      <h1>Pages</h1>
      <div class="sub">{{ now }} · page yang connected dengan token</div>
    </div>
  </div>

  <div class="glass">
    {% for p in pages %}
    <div class="page">
      <div>
        <div class="name">{{ p.name }} {% if p.hidden %}<span class="badge hid">HIDDEN</span>{% endif %}</div>
        <div class="id">{{ p.id }}{% if p.page_id and p.page_id == p.id %} · config{% endif %}</div>
      </div>
      <div style="display:flex;gap:8px;align-items:center;">
        <span class="badge {{ 'live' if p.live else 'dead' }}">{{ 'LIVE' if p.live else 'OFFLINE' }}</span>
        <form method="post" action="/pages/toggle/{{ p.id }}" style="display:inline;">
          <button class="btn {{ 'ghost' if not p.hidden }}" type="submit">{{ 'Show' if p.hidden else 'Hide' }}</button>
        </form>
      </div>
    </div>
    {% else %}
    <div class="empty">Tiada page dijumpai. Pastikan token user ada akses pages_show_list.</div>
    {% endfor %}
  </div>

  <div class="foot">Page yang di-hide tak akan muncul dalam Dashboard, tapi kekal dalam senarai ini untuk di-show balik.</div>
</main>

</body>
</html>"""

NEW_POST_HTML = """<!doctype html>
<html lang="ms">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>fesbuk · Tambah Post</title>
<style>
  :root { --ink:#1a2332; --muted:#6b7a90; --line:rgba(255,255,255,.55); --accent:#4f6ef7; --accent2:#7c5cf0; --good:#16a34a; --warn:#d97706; --bad:#dc2626; }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { font-family:'Segoe UI', system-ui, sans-serif; background:linear-gradient(135deg,#eef2ff 0%,#f8fafc 45%,#e0e7ff 100%); min-height:100vh; color:var(--ink); display:flex; }
  .sidebar { width:240px; min-height:100vh; padding:22px 16px; position:sticky; top:0; background:rgba(255,255,255,.55); backdrop-filter:blur(16px); border-right:1px solid var(--line); }
  .logo { display:flex; align-items:center; gap:10px; padding:4px 8px 20px; font-size:20px; font-weight:800; }
  .logo .dot { width:14px; height:14px; border-radius:6px; background:linear-gradient(135deg,var(--accent),var(--accent2)); box-shadow:0 4px 10px rgba(79,110,247,.4); }
  .nav { display:flex; flex-direction:column; gap:6px; }
  .nav a { display:flex; align-items:center; gap:10px; padding:10px 12px; border-radius:12px; color:var(--muted); text-decoration:none; font-size:14px; font-weight:600; transition:.15s; }
  .nav a:hover { background:rgba(255,255,255,.7); color:var(--ink); }
  .nav a.active { background:#fff; color:var(--accent); box-shadow:0 4px 14px rgba(30,40,90,.08); }
  .side-foot { margin-top:34px; padding:12px; border-radius:14px; background:rgba(255,255,255,.5); font-size:12px; color:var(--muted); }
  .main { flex:1; padding:28px 34px; max-width:720px; }
  .top { display:flex; justify-content:space-between; align-items:center; margin-bottom:24px; }
  .top h1 { font-size:24px; font-weight:800; }
  .top .sub { color:var(--muted); font-size:13px; margin-top:2px; }
  .glass { background:rgba(255,255,255,.55); backdrop-filter:blur(14px); border:1px solid var(--line); border-radius:18px; box-shadow:0 8px 28px rgba(30,40,90,.07); padding:22px 24px; }
  label { font-size:12px; font-weight:700; color:var(--muted); text-transform:uppercase; letter-spacing:.5px; display:block; margin:16px 0 6px; }
  input[type=text], textarea, select, input[type=datetime-local] {
    width:100%; padding:10px 14px; border-radius:12px; border:1px solid rgba(30,40,90,.12);
    background:#fff; font-size:14px; font-family:inherit; outline:none;
  }
  input:focus, textarea:focus, select:focus { border-color:var(--accent); }
  textarea { resize:vertical; min-height:140px; }
  .row { display:flex; gap:14px; }
  .row > div { flex:1; }
  /* ---- image dropzone ---- */
  .dropzone { position:relative; border:2px dashed rgba(79,110,247,.35); border-radius:16px; background:rgba(255,255,255,.6); padding:34px 20px; text-align:center; cursor:pointer; transition:.2s; }
  .dropzone:hover, .dropzone.drag { border-color:var(--accent); background:rgba(79,110,247,.06); }
  .dropzone .dz-icon { font-size:34px; line-height:1; }
  .dropzone .dz-title { font-weight:700; font-size:14px; margin-top:8px; }
  .dropzone .dz-sub { color:var(--muted); font-size:12px; margin-top:3px; }
  .dropzone .dz-browse { color:var(--accent); font-weight:700; }
  .dropzone input[type="file"] { position:absolute; inset:0; width:100%; height:100%; opacity:0; cursor:pointer; }
  .dropzone.has-img { border:2px solid rgba(22,163,74,.25); background:#fff; padding:14px; cursor:default; }
  .dropzone.has-img input[type="file"] { cursor:pointer; }
  .dropzone .dz-preview { display:none; }
  .dropzone.has-img .dz-preview { display:block; }
  .dropzone.has-img .dz-empty { display:none; }
  .dz-preview { background:#f1f5fb; border-radius:12px; padding:10px; }
  .dz-preview img { display:block; width:100%; height:220px; object-fit:contain; border-radius:8px; }
  .dz-meta { display:flex; align-items:center; justify-content:center; gap:10px; margin-top:10px; flex-wrap:wrap; }
  .dz-name { font-size:12px; color:var(--muted); font-weight:600; max-width:240px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .dz-actions { display:flex; gap:8px; }
  .dz-actions .btn { padding:6px 14px; font-size:12px; border-radius:10px; }
  .btn.danger { background:#fee2e2; color:var(--bad); }
  .btn.danger:hover { background:#fecaca; }
  .modes { display:flex; gap:10px; }
  .mode { flex:1; padding:14px; border-radius:14px; border:2px solid rgba(30,40,90,.1); background:#fff; cursor:pointer; text-align:center; font-weight:700; font-size:14px; }
  .mode input { display:none; }
  .mode.selected { border-color:var(--accent); background:#eef2ff; color:var(--accent); }
  .actions { display:flex; justify-content:flex-end; gap:10px; margin-top:22px; }
  .btn { padding:11px 22px; border-radius:12px; border:none; background:linear-gradient(135deg,var(--accent),var(--accent2)); color:#fff; font-weight:700; font-size:14px; cursor:pointer; }
  .btn.ghost { background:#fff; color:var(--muted); border:1px solid rgba(30,40,90,.12); text-decoration:none; }
  .note { font-size:12px; color:var(--muted); margin-top:6px; }
  #scheduleWrap { display:none; }
  #scheduleWrap.show { display:block; }
</style>
</head>
<body>

<aside class="sidebar">
  <div class="logo"><span class="dot"></span> fesbuk</div>
  <nav class="nav">
    <a href="/dashboard">📊 Dashboard</a>
    <a class="active" href="/post">📝 Post</a>
    <a href="/pages">📄 Pages</a>
    <a href="/ads">💸 Ads</a>
  </nav>
  <div class="side-foot">token: <b>{{ 'OK' if token_ok else 'MISSING' }}</b><br>page: <b>{{ config_page or '-' }}</b><br>v0.1.0</div>
</aside>

<main class="main">
  <div class="top">
    <div>
      <h1>{% if post %}✏️ Edit Post #{{ post.id }}{% else %}Tambah Post{% endif %}</h1>
      <div class="sub">{% if post %}Ubah content, gambar atau masa — lepas simpan ikut mode yang dipilih{% else %}Pilih page, tulis content, upload gambar, pilih mode{% endif %}</div>
    </div>
  </div>

  <div class="glass">
    <form method="post" action="{% if post %}/post/{{ post.id }}/edit{% else %}/post/new{% endif %}" enctype="multipart/form-data">
      <label>Page</label>
      <select name="page_id">
        {% for p in pages %}
        <option value="{{ p.id }}" {% if (post and post.page_id == p.id) or (not post and p.id == config_page) %}selected{% endif %}>{{ p.name }} ({{ p.id }})</option>
        {% endfor %}
      </select>

      <label>Content</label>
      <textarea name="text" required placeholder="Tulis content post di sini...">{{ post.text if post else '' }}</textarea>

      <label>Gambar (pilihan)</label>
      <div class="dropzone{% if post and post.image %} has-img{% endif %}" id="dz">
        <div class="dz-empty">
          <div class="dz-icon">🖼️</div>
          <div class="dz-title">Tarik &amp; lepas gambar di sini</div>
          <div class="dz-sub">atau <span class="dz-browse">klik untuk pilih</span></div>
        </div>
        <div class="dz-preview">
          <img id="previewImg" alt="preview" {% if post and post.image %}src="/img/{{ post.image }}"{% endif %}>
          <div class="dz-meta">
            <span class="dz-name" id="dzName">{% if post and post.image %}{{ post.image }}{% endif %}</span>
            <span class="dz-actions">
              <button type="button" class="btn ghost" onclick="pickImage()">🔄 Tukar</button>
              <button type="button" class="btn danger" onclick="clearImage()">🗑️ Buang</button>
            </span>
          </div>
        </div>
        <input type="file" name="image" accept="image/*" id="imageInput" onchange="previewImage(event)">
        <input type="hidden" name="remove_image" id="removeImage" value="">
      </div>

      <label>Mode</label>
      <div class="modes">
        <label class="mode{% if not (post and post.scheduled_at) %} selected{% endif %}"><input type="radio" name="mode" value="instant" {% if not (post and post.scheduled_at) %}checked{% endif %} onchange="modeSel(this)">⚡ Instant Post</label>
        <label class="mode{% if post and post.scheduled_at %} selected{% endif %}"><input type="radio" name="mode" value="schedule" {% if post and post.scheduled_at %}checked{% endif %} onchange="modeSel(this)">📅 Schedule</label>
      </div>
      <div id="scheduleWrap"{% if post and post.scheduled_at %} class="show"{% endif %}>
        <label>Tarikh &amp; Masa</label>
        <input type="datetime-local" name="scheduled_at" value="{{ post.scheduled_at | fmtlocal if post else '' }}">
      </div>

      <div class="actions">
        <a class="btn ghost" href="/post">Batal</a>
        <button class="btn" type="submit">🚀 Hantar</button>
      </div>
    </form>
  </div>
</main>

<script>
const dz = document.getElementById('dz');
const input = document.getElementById('imageInput');

function previewImage(e) {
  const file = e.target.files[0];
  if (!file) return;
  if (!file.type.startsWith('image/')) { alert('Fail tu bukan gambar!'); e.target.value = ''; return; }
  const url = URL.createObjectURL(file);
  document.getElementById('previewImg').src = url;
  document.getElementById('dzName').textContent = file.name;
  dz.classList.add('has-img');
}
function pickImage() { input.click(); }
function clearImage() {
  input.value = '';
  document.getElementById('removeImage').value = '1';
  document.getElementById('previewImg').removeAttribute('src');
  document.getElementById('dzName').textContent = '';
  dz.classList.remove('has-img');
}
function modeSel(el) {
  document.querySelectorAll('.mode').forEach(m => m.classList.remove('selected'));
  el.closest('.mode').classList.add('selected');
  document.getElementById('scheduleWrap').classList.toggle('show', el.value === 'schedule');
}
// drag & drop
['dragenter', 'dragover'].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.add('drag'); }));
['dragleave', 'drop'].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.remove('drag'); }));
dz.addEventListener('drop', e => {
  const f = e.dataTransfer.files[0];
  if (f && f.type.startsWith('image/')) {
    const dt = new DataTransfer(); dt.items.add(f); input.files = dt.files;
    previewImage({ target: input });
  }
});
</script>

</body>
</html>"""

ADS_HTML = """<!doctype html>
<html lang="ms">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>fesbuk · Ads Manager</title>
<style>
  :root {
    --ink:#1a2332; --muted:#6b7a90; --line:rgba(255,255,255,.55);
    --accent:#4f6ef7; --accent2:#7c5cf0; --good:#16a34a; --warn:#d97706; --bad:#dc2626;
  }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { font-family:'Segoe UI', system-ui, -apple-system, sans-serif; background:linear-gradient(135deg,#eef1fb,#e7ecfa); min-height:100vh; color:var(--ink); display:flex; }
  .sidebar { width:230px; background:rgba(255,255,255,.7); backdrop-filter:blur(14px); border-right:1px solid var(--line); padding:22px 16px; min-height:100vh; display:flex; flex-direction:column; }
  .logo { font-weight:800; font-size:17px; display:flex; align-items:center; gap:8px; margin-bottom:26px; }
  .dot { width:9px; height:9px; border-radius:50%; background:var(--accent); display:inline-block; }
  .nav { display:flex; flex-direction:column; gap:4px; }
  .nav a { padding:10px 12px; border-radius:12px; color:var(--ink); text-decoration:none; font-weight:600; font-size:14px; }
  .nav a:hover { background:rgba(79,110,247,.08); }
  .nav a.active { background:var(--accent); color:#fff; }
  .side-foot { margin-top:auto; color:var(--muted); font-size:12px; line-height:1.7; }
  .main { flex:1; padding:26px 30px; max-width:980px; }
  .top { display:flex; align-items:flex-start; justify-content:space-between; margin-bottom:20px; }
  h1 { font-size:22px; }
  .sub { color:var(--muted); font-size:13px; margin-top:2px; }
  .pill { padding:6px 14px; border-radius:20px; font-size:12px; font-weight:700; background:rgba(255,255,255,.7); border:1px solid var(--line); }
  .glass { background:rgba(255,255,255,.55); backdrop-filter:blur(14px); -webkit-backdrop-filter:blur(14px); border:1px solid var(--line); border-radius:18px; box-shadow:0 8px 28px rgba(30,40,90,.07); padding:18px 20px; margin-bottom:20px; }
  h2 { font-size:14px; font-weight:800; text-transform:uppercase; letter-spacing:1px; color:var(--muted); margin:26px 0 10px; }
  .stat-grid { display:grid; grid-template-columns:repeat(5,1fr); gap:10px; }
  .stat-card { background:#f8fafc; border:1px solid rgba(30,40,90,.07); border-radius:14px; padding:14px 10px; text-align:center; }
  .stat-card .v { font-size:20px; font-weight:800; color:var(--accent); }
  .stat-card .l { font-size:11px; color:var(--muted); font-weight:600; margin-top:3px; }
  .btn { padding:7px 14px; border-radius:20px; border:1px solid rgba(79,110,247,.4); background:#fff; color:var(--accent); font-weight:700; font-size:12px; cursor:pointer; }
  .btn:hover { background:var(--accent); color:#fff; }
  .btn.primary { background:var(--accent); color:#fff; border-color:var(--accent); padding:10px 22px; font-size:14px; }
  .btn.primary:hover { background:#3d5ae0; }
  .meta { color:var(--muted); font-size:12px; margin-top:8px; }
  .steps { counter-reset:step; list-style:none; }
  .steps li { position:relative; padding:10px 0 10px 42px; font-size:14px; line-height:1.5; }
  .steps li::before { counter-increment:step; content:counter(step); position:absolute; left:0; top:12px; width:26px; height:26px; border-radius:50%; background:var(--accent); color:#fff; font-weight:800; font-size:13px; display:flex; align-items:center; justify-content:center; }
  .steps code { background:#eef1fb; padding:2px 8px; border-radius:6px; font-size:13px; color:var(--accent); }
  .paste { width:100%; min-height:90px; border:1.5px dashed rgba(79,110,247,.5); border-radius:12px; padding:12px; font-family:monospace; font-size:12px; resize:vertical; margin:6px 0 12px; }
  .err { color:var(--bad); font-size:13px; margin-bottom:10px; min-height:18px; font-weight:600; }
  .ok-banner { background:#dcfce7; color:var(--good); font-weight:700; font-size:13px; border-radius:12px; padding:12px 16px; margin-bottom:16px; }
  .empty { color:var(--muted); font-size:13px; padding:6px 0; }
  .note { color:var(--warn); font-size:12px; margin-top:8px; }
  /* ---------- BOOSTED POSTS TABLE ---------- */
  .table-wrap { overflow-x:auto; }
  .ad-table { width:100%; border-collapse:collapse; font-size:13px; }
  .ad-table th { text-align:left; color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.4px; padding:8px 10px; border-bottom:2px solid rgba(30,40,90,.08); }
  .ad-table td { padding:10px; border-bottom:1px solid rgba(30,40,90,.05); vertical-align:middle; }
  .ad-table tr:hover td { background:rgba(79,110,247,.04); }
  .td-name { font-weight:600; max-width:280px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .st { display:inline-block; padding:2px 10px; border-radius:12px; font-size:11px; font-weight:700; }
  .st-active { background:#dcfce7; color:var(--good); }
  .st-paused { background:#fef3c7; color:#b45309; }
  .st-archived, .st-deleted, .st-completed, .st-inactive { background:#e5e7eb; color:#4b5563; }
  .st-pending_review, .st-in_review, .st-in_process, .st-pending_engagement { background:#fef3c7; color:#b45309; }
  .st-with_issues, .st-error, .st-disapproved, .st-rejected { background:#fee2e2; color:var(--bad); }
  .detail-status { display:flex; gap:10px; margin:10px 0 4px; flex-wrap:wrap; }
  .ds-row { display:flex; align-items:center; gap:8px; background:rgba(30,40,90,.04); border-radius:10px; padding:8px 12px; font-size:13px; }
  .ds-row span { color:var(--muted); font-weight:600; }
  .detail-sub { font-size:12px; color:var(--muted); margin:4px 0; }
  /* ---------- MODAL ---------- */
  .modal { display:none; position:fixed; inset:0; background:rgba(15,23,42,.55); z-index:50; align-items:center; justify-content:center; padding:20px; }
  .modal.open { display:flex; }
  .modal-box { background:#fff; border-radius:18px; max-width:860px; width:100%; max-height:86vh; overflow-y:auto; padding:22px 24px; box-shadow:0 20px 60px rgba(15,23,42,.35); }
  .modal-head { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; margin-bottom:8px; }
  .modal-head h3 { margin:0; font-size:17px; }
  .modal-x { background:none; border:none; font-size:22px; cursor:pointer; color:var(--muted); line-height:1; padding:4px 8px; }
  .modal-x:hover { color:var(--bad); }
  .day-table { width:100%; border-collapse:collapse; font-size:12.5px; margin-top:10px; }
  .day-table th { text-align:right; color:var(--muted); font-size:10.5px; text-transform:uppercase; letter-spacing:.3px; padding:6px 8px; border-bottom:2px solid rgba(30,40,90,.08); }
  .day-table th:first-child { text-align:left; }
  .day-table td { text-align:right; padding:6px 8px; border-bottom:1px solid rgba(30,40,90,.05); font-variant-numeric:tabular-nums; }
  .day-table td:first-child { text-align:left; font-weight:600; }
  .day-table tr.total td { font-weight:800; border-top:2px solid rgba(30,40,90,.12); border-bottom:none; background:rgba(79,110,247,.05); }
  .ad-meta { display:flex; flex-wrap:wrap; gap:6px 18px; font-size:12px; color:var(--muted); margin:4px 0 2px; }
  .ad-meta b { color:var(--ink); }
  .ad-link { display:inline-block; margin-top:10px; font-size:13px; font-weight:700; color:var(--accent); text-decoration:none; }
  .ad-link:hover { text-decoration:underline; }
  /* ---------- BOOST FORM ---------- */
  .boost-form { display:flex; flex-direction:column; gap:14px; }
  .bf-row { display:flex; flex-direction:column; gap:6px; }
  .bf-row label { font-size:12px; font-weight:700; color:var(--muted); }
  .bf-row select, .bf-row input { padding:9px 12px; border:1.5px solid rgba(79,110,247,.35); border-radius:10px; font-size:13px; background:#fff; }
  .bf-row select:focus, .bf-row input:focus { outline:none; border-color:var(--accent); }
  .bf-grid { display:grid; grid-template-columns:repeat(2,1fr); gap:12px; }
  .bf-hint { font-size:11px; color:var(--muted); }
  .bf-search { display:flex; gap:8px; }
  .bf-search input { flex:1; }
  .int-list { display:flex; flex-direction:column; gap:6px; margin-top:6px; }
  .int-item { display:flex; align-items:center; justify-content:space-between; gap:10px; padding:8px 12px; border:1px solid rgba(79,110,247,.2); border-radius:10px; cursor:pointer; font-size:13px; background:#f8fafc; }
  .int-item:hover { border-color:var(--accent); background:#eef1fb; }
  .int-item.sel { border-color:var(--accent); background:#eef1fb; font-weight:700; }
  .int-item .aud { font-size:11px; color:var(--muted); }
</style>
</head>
<body>

<aside class="sidebar">
  <div class="logo"><span class="dot"></span> fesbuk</div>
  <nav class="nav">
    <a href="/dashboard">📊 Dashboard</a>
    <a href="/post">📝 Post</a>
    <a href="/pages">📄 Pages</a>
    <a class="active" href="/ads">💸 Ads</a>
  </nav>
  <div class="side-foot">
    token: <b>{{ 'OK' if token_ok else 'MISSING' }}</b><br>
    page: <b>{{ config_page or '-' }}</b><br>
    v0.1.0
  </div>
</aside>

<main class="main">
  <div class="top">
    <div>
      <h1>Ads Manager</h1>
      <div class="sub">{{ now }} · Spend tracking dari FB Ads API</div>
    </div>
    {% if activated %}<span class="pill">🟢 Aktif</span>{% else %}<span class="pill">🔴 Belum aktif</span>{% endif %}
  </div>

  {% if activated_flag %}
  <div class="ok-banner">✅ Token berjaya diaktifkan! Total spend di bawah.</div>
  {% endif %}

  {% if activated %}
  <h2>💰 Total Spent</h2>
  <div class="glass">
    <div class="stat-grid">
      <div class="stat-card"><div class="v">RM{{ '%.2f'|format(spend.spend_month) }}</div><div class="l">Bulan Ini</div></div>
      <div class="stat-card"><div class="v">RM{{ '%.2f'|format(spend.spend_7d) }}</div><div class="l">7 Hari Terakhir</div></div>
      <div class="stat-card"><div class="v">{{ '{:,}'.format(spend.imps) }}</div><div class="l">👁️ Impressions</div></div>
      <div class="stat-card"><div class="v">{{ spend.clicks }}</div><div class="l">🖱️ Clicks</div></div>
      <div class="stat-card"><div class="v">{{ '%.2f'|format(spend.ctr) }}%</div><div class="l">CTR</div></div>
    </div>
    <div class="meta">📡 Dikemaskini: {{ spend.fetched_at|fmtdate }} · {{ spend.acct }}
      <button class="btn" style="float:right" onclick="refreshSpend(this)">⟳ Refresh</button>
    </div>
    {% if spend.error %}<div class="note">⚠️ {{ spend.error }}</div>{% endif %}
  </div>

  <h2>📊 Boosted Posts</h2>
  <div class="glass">
    {% if ads_view.ads %}
    <div class="table-wrap">
    <table class="ad-table">
      <thead>
        <tr>
          <th>Post</th>
          <th>Status</th>
          <th>Hari Aktif</th>
          <th>Spend</th>
          <th>👁️ Imps</th>
          <th>👍💬🔗</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
      {% for ad in ads_view.ads %}
        <tr>
          <td class="td-name">{{ ad.name }}</td>
          <td><span class="st st-{{ (ad.campaign_status or ad.status)|lower }}">{{ ad.campaign_status or ad.status }}</span></td>
          <td>{{ ad.days_active }}<br><small>{{ ad.first_day }} → {{ ad.last_day }}</small></td>
          <td><b>RM{{ '%.2f'|format(ad.totals.spend) }}</b></td>
          <td>{{ '{:,}'.format(ad.totals.impressions) }}</td>
          <td>{{ ad.totals.likes }}👍 {{ ad.totals.comments }}💬 {{ ad.totals.shares }}🔗</td>
          <td><button class="btn" onclick="viewAd('{{ ad.id }}')">Detail</button></td>
        </tr>
      {% endfor %}
      </tbody>
    </table>
    </div>
    <div class="meta">📡 Ads breakdown: {{ ads_view.fetched_at|fmtdate }} · tempoh 7 hari terakhir</div>
    {% else %}
    <div class="empty">Belum ada data boosted posts. Tekan ⟳ Refresh untuk tarik senarai ads dari FB.</div>
    {% endif %}
  </div>

  <h2>🚀 Running Ads / Campaign</h2>
  <div class="glass">
    <div class="boost-form">
      <div class="bf-row">
        <label>Post nak boost:</label>
        <select id="bfPost">
          <option value="">— pilih post —</option>
          {% for p in page_posts %}
          <option value="{{ p.id }}">{{ p.created }} · {{ p.label }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="bf-row">
        <label>Objective (matlamat ads):</label>
        <select id="bfObjective">
          <option selected>Traffic (klik link)</option>
          <option>Reach (jangkauan)</option>
        </select>
        <span class="bf-hint">Engagement/Leads tak disokong FB untuk boost post via API (error Performance goal).</span>
      </div>
      <div class="bf-grid">
        <div class="bf-row">
          <label>Budget harian (RM):</label>
          <input type="number" id="bfBudget" value="20" min="1" step="1">
        </div>
        <div class="bf-row">
          <label>Tempoh (hari):</label>
          <input type="number" id="bfDays" value="3" min="1" max="30" step="1">
        </div>
      </div>
      <div class="bf-grid">
        <div class="bf-row">
          <label>Kawasan:</label>
          <select id="bfArea">
            <option>Semua (KL/Sel/JB/Penang)</option>
            <option>KL & Selangor</option>
            <option>Johor Bahru</option>
            <option>Penang</option>
          </select>
        </div>
        <div class="bf-row">
          <label>Umur:</label>
          <select id="bfAge">
            <option>18-24</option>
            <option>25-34</option>
            <option selected>25-45</option>
            <option>35-44</option>
            <option>45-54</option>
            <option>55+</option>
            <option>Semua (18-65)</option>
          </select>
        </div>
      </div>
      <div class="bf-row">
        <label>Minat (taip & cari — contoh: kereta, makanan, travel, hartanah...):</label>
        <div class="bf-search">
          <input type="text" id="bfInterestQ" placeholder="Taip minat contoh: kereta / travel / kekal sihat" onkeydown="if(event.key==='Enter'){searchInterests();return false;}">
          <button class="btn" onclick="searchInterests()">🔍 Cari</button>
        </div>
        <div id="interestResults"></div>
        <input type="hidden" id="bfInterest" value="">
        <span class="bf-hint" id="interestHint">Belum pilih minat — target broad (semua).</span>
      </div>
      <div class="bf-row">
        <div class="err" id="boostErr"></div>
        <button class="btn primary" onclick="createBoost(this)">🚀 Boost Sekarang</button>
      </div>
    </div>
  </div>
  {% else %}

  <h2>🔑 Aktifkan Token Ads</h2>
  <div class="glass">
    <div class="err" id="actErr">{{ error or '' }}</div>
    <ol class="steps">
      <li>Buka <a href="https://developers.facebook.com/tools/explorer/" target="_blank">Graph API Explorer</a> dan login dgn akaun FB yang ada akses Ads Manager.</li>
      <li>Pilih app yang betul: <b>ID {{ app_id or '-' }}</b> (app mesti LIVE).</li>
      <li>Pastikan mode pilih <b>"User Token"</b> — BUKAN "Page Token".</li>
      <li>Kalau <code>ads_read</code> TAK muncul dalam senarai permission: pergi <a href="https://developers.facebook.com/apps/{{ app_id or '' }}/" target="_blank">My Apps</a> → pilih app → <b>Use Case</b> → tambah <b>Marketing API</b> — kat situ <code>ads_read</code> & <code>ads_management</code> tersedia. Lepas tambah, balik ke langkah 4.</li>
      <li>Klik <b>"Add a permission"</b> → taip <code>ads_read</code> → pilih.</li>
      <li>Klik <b>"Generate Access Token"</b> → benarkan semua permission.</li>
      <li>Salin token (mula dgn <code>EAAT...</code>) dan tampal kat bawah, lepas tu klik <b>Aktifkan</b>.</li>
    </ol>
    <textarea class="paste" id="tok" placeholder="Tampal token kat sini (EAAT...)"></textarea>
    <button class="btn primary" onclick="activateAds(this)">Aktifkan</button>
  </div>
  {% endif %}

  <div class="modal" id="adModal">
    <div class="modal-box">
      <div class="modal-head">
        <div>
          <h3 id="mName">-</h3>
          <div class="ad-meta" id="mMeta"></div>
        </div>
        <button class="modal-x" onclick="closeModal()">✕</button>
      </div>
      <div id="mBody"></div>
    </div>
  </div>
</main>

<script>
var ADS_DATA = {{ ads_view.ads|tojson }};
function activateAds(btn){
  var tok = document.getElementById('tok').value.trim();
  var err = document.getElementById('actErr');
  if(!tok){ err.textContent = '❌ Tampal token dulu.'; return; }
  btn.disabled = true; btn.textContent = 'Mengaktifkan...';
  fetch('/api/ads/activate', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({token: tok})})
    .then(function(r){ return r.json(); })
    .then(function(d){
      if(d.ok){ location.href = '/ads?activated=1'; }
      else {
        err.textContent = '❌ ' + (d.error || 'Gagal. Cuba lagi.');
        btn.disabled = false; btn.textContent = 'Aktifkan';
      }
    })
    .catch(function(e){
      err.textContent = '❌ ' + e;
      btn.disabled = false; btn.textContent = 'Aktifkan';
    });
}
function refreshSpend(btn){
  if(!btn) return;
  btn.disabled = true; btn.textContent = 'Mengambil...';
  fetch('/api/ads/refresh', {method:'POST'}).then(function(r){ return r.json(); }).then(function(d){
    if(d.ok || d.ad_count !== undefined){ location.reload(); return; }
    alert('Gagal tarik: ' + (d.error || '?'));
    btn.disabled = false; btn.textContent = '⟳ Refresh';
  }).catch(function(e){
    alert('Ralat: ' + e);
    btn.disabled = false; btn.textContent = '⟳ Refresh';
  });
}
function fmtRM(v){ return 'RM' + Number(v||0).toFixed(2); }
function fmtN(v){ return Number(v||0).toLocaleString('en-MY'); }
var INTEREST_ITEMS = [];
function searchInterests(){
  var q = document.getElementById('bfInterestQ').value.trim();
  var box = document.getElementById('interestResults');
  if(q.length < 2){ box.innerHTML = '<span class="bf-hint">Taip sekurang-kurangnya 2 huruf.</span>'; return; }
  box.innerHTML = '<span class="bf-hint">Mencari...</span>';
  fetch('/api/ads/interests?q=' + encodeURIComponent(q))
    .then(function(r){ return r.json(); })
    .then(function(d){
      if(!d.ok){ box.innerHTML = '<span class="bf-hint">❌ ' + (d.error || 'Gagal cari.') + '</span>'; return; }
      if(!d.items.length){ box.innerHTML = '<span class="bf-hint">Tiada hasil untuk "' + q + '". Cuba perkataan lain.</span>'; return; }
      INTEREST_ITEMS = d.items;
      var html = '<div class="int-list">';
      for(var i=0;i<d.items.length;i++){
        var it = d.items[i];
        var aud = it.audience ? it.audience.toLocaleString('en-MY') + ' org' : '';
        html += '<div class="int-item" onclick="pickInterest(' + i + ',this)">' +
                '<span>' + it.name + '</span><span class="aud">' + aud + '</span></div>';
      }
      html += '</div>';
      box.innerHTML = html;
    })
    .catch(function(e){ box.innerHTML = '<span class="bf-hint">Ralat: ' + e + '</span>'; });
}
function pickInterest(idx, el){
  var it = INTEREST_ITEMS[idx];
  if(!it) return;
  document.getElementById('bfInterest').value = it.id;
  document.getElementById('interestHint').textContent = '✅ Minat dipilih: ' + it.name;
  var items = document.querySelectorAll('.int-item');
  for(var i=0;i<items.length;i++){ items[i].classList.remove('sel'); }
  if(el){ el.classList.add('sel'); }
}
function createBoost(btn){
  var post = document.getElementById('bfPost').value;
  var err = document.getElementById('boostErr');
  if(!post){ err.textContent = '❌ Pilih post dulu.'; return; }
  var budget = parseFloat(document.getElementById('bfBudget').value);
  var days = parseInt(document.getElementById('bfDays').value, 10);
  var area = document.getElementById('bfArea').value;
  var age = document.getElementById('bfAge').value;
  var interest = document.getElementById('bfInterest').value;
  var objective = document.getElementById('bfObjective').value;
  if(!budget || budget < 1){ err.textContent = '❌ Budget kena sekurang-kurangnya RM1.'; return; }
  if(!days || days < 1){ err.textContent = '❌ Tempoh kena sekurang-kurangnya 1 hari.'; return; }
  var total = (budget * days).toFixed(2);
  var intLabel = interest ? (document.getElementById('interestHint').textContent.replace('✅ Minat dipilih: ','')) : 'Broad (semua)';
  if(!confirm('Boost post ni?\\n\\nObjective: ' + objective + '\\nBudget: RM' + budget + '/hari x ' + days + ' hari = RM' + total + '\\nKawasan: ' + area + '\\nUmur: ' + age + '\\nMinat: ' + intLabel + '\\n\\nTeruskan?')) return;
  btn.disabled = true; btn.textContent = 'Mencipta campaign...';
  fetch('/api/ads/boost', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({post_id: post, budget: budget, days: days, area: area, age: age, interest: interest, objective: objective})})
    .then(function(r){ return r.json(); })
    .then(function(d){
      if(d.ok){
        alert('✅ Campaign dicipta!\\n\\nCampaign: ' + d.campaign_id + '\\nAd: ' + d.ad_id + '\\n\\nSedia untuk review di Ads Manager.');
        location.href = '/ads';
      } else {
        err.textContent = '❌ ' + (d.error || 'Gagal. Cuba lagi.');
        btn.disabled = false; btn.textContent = '🚀 Boost Sekarang';
      }
    })
    .catch(function(e){
      err.textContent = '❌ ' + e;
      btn.disabled = false; btn.textContent = '🚀 Boost Sekarang';
    });
}
function stBadge(s){
  if(!s) return '<span class="st">-</span>';
  return '<span class="st st-' + String(s).toLowerCase() + '">' + s + '</span>';
}
function viewAd(id){
  var ad = null;
  for(var i=0;i<ADS_DATA.length;i++){ if(ADS_DATA[i].id === id){ ad = ADS_DATA[i]; break; } }
  if(!ad) return;
  document.getElementById('mName').textContent = ad.name || ad.id;
  var meta = 'Hari aktif: <b>' + ad.days_active + '</b>';
  if(ad.first_day && ad.last_day){ meta += ' · Tempoh: <b>' + ad.first_day + ' → ' + ad.last_day + '</b>'; }
  if(ad.created_time){ meta += ' · Dibuat: <b>' + ad.created_time.slice(0,10) + '</b>'; }
  document.getElementById('mMeta').innerHTML = meta;
  var html = '<div class="detail-status">';
  html += '<div class="ds-row"><span>📣 Campaign</span>' + stBadge(ad.campaign_status) + '</div>';
  html += '<div class="ds-row"><span>🎯 AdSet</span>' + stBadge(ad.adset_status) + '</div>';
  html += '<div class="ds-row"><span>📄 Ad</span>' + stBadge(ad.status) + '</div>';
  html += '</div>';
  if(ad.campaign_name){ html += '<div class="detail-sub">Campaign: <b>' + ad.campaign_name + '</b> · ' + ad.campaign_id + '</div>'; }
  if(ad.adset_name){ html += '<div class="detail-sub">AdSet: <b>' + ad.adset_name + '</b> · ' + ad.adset_id + '</div>'; }
  html += '<div class="detail-sub">Ad ID: <b>' + ad.id + '</b></div>';
  var head = '<table class="day-table"><thead><tr>' +
    '<th>Tarikh</th><th>💸 Spend</th><th>👁️ Imps</th><th>📡 Reach</th><th>🖱️ Clicks</th>' +
    '<th>CTR</th><th>👍 Likes</th><th>💬 Cmt</th><th>🔗 Shares</th></tr></thead><tbody>';
  var body = '';
  for(var j=0;j<ad.days.length;j++){
    var d = ad.days[j];
    body += '<tr><td>' + d.date + '</td><td>' + fmtRM(d.spend) + '</td><td>' + fmtN(d.impressions) +
      '</td><td>' + fmtN(d.reach) + '</td><td>' + d.clicks + '</td><td>' + Number(d.ctr||0).toFixed(2) + '%</td>' +
      '<td>' + d.likes + '</td><td>' + d.comments + '</td><td>' + d.shares + '</td></tr>';
  }
  var t = ad.totals || {};
  body += '<tr class="total"><td>Total</td><td>' + fmtRM(t.spend) + '</td><td>' + fmtN(t.impressions) +
    '</td><td>' + fmtN(t.reach) + '</td><td>' + t.clicks + '</td><td>' + Number(t.ctr||0).toFixed(2) + '%</td>' +
    '<td>' + t.likes + '</td><td>' + t.comments + '</td><td>' + t.shares + '</td></tr>';
  var link = ad.post_url ? '<a class="ad-link" href="' + ad.post_url + '" target="_blank">Buka post di Facebook →</a>' : '';
  document.getElementById('mBody').innerHTML = html + head + body + '</tbody></table>' + link;
  document.getElementById('adModal').classList.add('open');
}
function closeModal(){
  document.getElementById('adModal').classList.remove('open');
}
document.getElementById('adModal').addEventListener('click', function(e){
  if(e.target === this){ closeModal(); }
});
</script>

</body>
</html>"""


def _graph(path, token, fields=None):
    url = f"{config.GRAPH}/{path}?" + urllib.parse.urlencode(
        {"access_token": token, **({"fields": fields} if fields else {})}
    )
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def _page_live(page_id, page_token):
    try:
        info = _graph(page_id, page_token, "id,name")
        return bool(info.get("id"))
    except Exception:
        return False


def connected_pages():
    """All pages visible to the user token, with live status + hidden flag."""
    token = config.load_user_token()
    if not token:
        return [], False
    hidden = set(db.hidden_pages())
    try:
        data = _graph("me/accounts", token, "id,name,access_token")
        pages = []
        for p in data.get("data", []):
            pages.append({
                "id": p["id"],
                "name": p.get("name", "?"),
                "live": _page_live(p["id"], p.get("access_token", "")),
                "hidden": p["id"] in hidden,
                "page_id": config.PAGE_ID,
            })
        # Hanya page yang dikonfigurasi dalam .env (PAGE_ID) dipapar.
        # Page lain (idahamway, Panthera, Family Frozen Food, dsb.) dibuang
        # terus dari SEMUA paparan — dashboard, dropdown Post, halaman Pages.
        if config.PAGE_ID:
            pages = [p for p in pages if p["id"] == config.PAGE_ID]
        return pages, True
    except Exception as e:
        return [{"id": "-", "name": f"Error: {e}", "live": False, "hidden": False}], True


def _spend_view():
    """Latest spend snapshot; auto-pull bila tiada data atau dah >6 jam. Tak pernah raise."""
    snap = db.latest_snapshot()
    err = None
    stale = True
    if snap:
        try:
            t = datetime.fromisoformat(snap["fetched_at"].replace("Z", "+00:00"))
            stale = (datetime.now(timezone.utc) - t) > timedelta(hours=6)
        except Exception:
            stale = True
    if not snap or stale:
        try:
            res = fb_spend.pull_and_store()
            if res.get("ok"):
                snap = db.latest_snapshot()
            else:
                err = res.get("error")
                # Token tak berkenan (ads_read hilang / expired) → papar step activate,
                # walau ada data lama. User spec: belum activate = tunjuk step.
                if "ads_read" in (err or "") or "permission" in (err or "").lower():
                    return {"ok": False, "error": err, "acct": "", "fetched_at": "",
                            "spend_month": 0, "spend_7d": 0, "imps": 0, "clicks": 0, "ctr": 0}
        except Exception as e:
            err = str(e)
    if not snap:
        return {"ok": False, "error": err or "Belum ada data spend.", "acct": "",
                "fetched_at": "", "spend_month": 0, "spend_7d": 0, "imps": 0, "clicks": 0, "ctr": 0}
    rows = snap.get("rows", {})
    r7 = rows.get("last_7d", {}) or {}
    rm = rows.get("this_month", {}) or {}
    base = r7 or rm
    return {
        "ok": True,
        "error": err,
        "acct": base.get("account_name", "") or base.get("ad_account", ""),
        "fetched_at": snap["fetched_at"],
        "spend_month": rm.get("spend", 0),
        "spend_7d": r7.get("spend", 0),
        "imps": r7.get("impressions", 0),
        "clicks": r7.get("clicks", 0),
        "ctr": r7.get("ctr", 0),
    }


@app.route("/")
def index():
    return {"service": "fesbuk dashboard", "dashboard": "/dashboard"}


@app.route("/dashboard")
def dashboard():
    db.seed_from_msgs()
    pages, token_ok = connected_pages()
    visible = [p for p in pages if not p.get("hidden")]
    try:
        app_id = config.load_app_token().split("|")[0]
    except Exception:
        app_id = ""
    connected_flag = request.args.get("connected") == "1"
    return render_template_string(
        HTML,
        pages=visible,
        live_count=sum(1 for p in visible if p.get("live")),
        pending=db.get_posts("pending"),
        posted=db.get_posts("posted"),
        page_setup_needed=fb_page.page_token_status() != "ok",
        app_id=app_id,
        connected_flag=connected_flag,
        now=datetime.now().strftime("%d %b %Y %H:%M"),
        token_ok=token_ok,
        config_page=config.PAGE_ID or "-",
    )


@app.route("/api/page/activate", methods=["POST"])
def api_page_activate():
    try:
        data = request.get_json(silent=True) or {}
        res = fb_page.activate_page_token(data.get("token", ""))
        if res.get("ok"):
            return jsonify(res)
        return jsonify(res), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/spend/refresh", methods=["POST"])
def api_spend_refresh():
    try:
        res = fb_spend.pull_and_store()
        if res.get("ok"):
            return jsonify(res)
        return jsonify(res), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/ads")
def ads_page():
    db.init_db()
    try:
        app_id = config.load_app_token().split("|")[0]
    except Exception:
        app_id = ""
    activated_flag = request.args.get("activated") == "1"
    view = _spend_view()  # panggil sekali sahaja (elak API dipukul 3x)
    ads = fb_spend.load_ads_view()
    # Senarai post page untuk dropdown boost
    page_posts = []
    pt = config.load_token()
    if pt:
        try:
            data = _graph(config.PAGE_ID + "/posts", pt, "id,message,created_time")
            for p in data.get("data", [])[:10]:
                page_posts.append({
                    "id": p["id"],
                    "label": (p.get("message") or "(tanpa teks)").replace("\n", " ")[:60],
                    "created": (p.get("created_time") or "")[:10],
                })
        except Exception:
            page_posts = []
    return render_template_string(
        ADS_HTML,
        activated=bool(view.get("ok")),
        spend=view,
        error=view.get("error", ""),
        app_id=app_id,
        activated_flag=activated_flag,
        ads_view=ads,
        page_posts=page_posts,
        now=datetime.now().strftime("%d %b %Y %H:%M"),
        token_ok=True,
        config_page=config.PAGE_ID or "-",
    )


@app.route("/api/ads/refresh", methods=["POST"])
def api_ads_refresh():
    """Tarik semula spend + senarai boosted posts (breakdown harian)."""
    try:
        res = fb_spend.pull_and_store()
        res2 = fb_spend.pull_ads()
        ok = bool(res.get("ok")) or bool(res2.get("ok"))
        errs = [e for e in (res.get("error"), res2.get("error")) if e]
        return jsonify({
            "ok": ok,
            "error": "; ".join(errs) if errs else "",
            "spend": res.get("ok", False),
            "ads": res2.get("ok", False),
            "ad_count": res2.get("count", 0),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/ads/interests", methods=["GET"])
def api_ads_interests():
    """Search FB ad interests (flexible targeting). ?q=perkataan."""
    try:
        q = (request.args.get("q") or "").strip()
        if not q or len(q) < 2:
            return jsonify({"ok": False, "error": "Taip sekurang-kurangnya 2 huruf."}), 400
        token = config.load_ads_token()
        if not token:
            return jsonify({"ok": False, "error": "Tiada ads token."}), 400
        data = fb_spend._graph("search", token,
                               {"type": "adinterest", "q": q, "limit": 8})
        items = []
        for it in data.get("data", []):
            if it.get("id"):
                items.append({
                    "id": it["id"],
                    "name": it.get("name", "?"),
                    "audience": it.get("audience_size") or 0,
                })
        return jsonify({"ok": True, "items": items})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/ads/boost", methods=["POST"])
def api_ads_boost():
    """Create boosted-post campaign terus dari dashboard."""
    try:
        data = request.get_json(silent=True) or {}
        post_id = (data.get("post_id") or "").strip()
        if not post_id:
            return jsonify({"ok": False, "error": "Pilih post dulu."}), 400
        try:
            budget = float(data.get("budget", 20))
            days = int(data.get("days", 3))
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "Budget/hari tak sah."}), 400
        area = (data.get("area") or "Semua (KL/Sel/JB/Penang)").strip()
        age_range = (data.get("age") or fb_spend.DEFAULT_AGE).strip()
        interest = (data.get("interest") or fb_spend.DEFAULT_INTEREST).strip()
        objective = (data.get("objective") or fb_spend.DEFAULT_OBJECTIVE).strip()
        res = fb_spend.create_boost(post_id, budget, days, area, age_range,
                                    interest, objective)
        if res.get("ok"):
            # Tarik semula senarai ads supaya nampak campaign baru
            fb_spend.pull_ads()
            return jsonify(res)
        return jsonify(res), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/ads/activate", methods=["POST"])
def api_ads_activate():
    try:
        data = request.get_json(silent=True) or {}
        res = fb_spend.activate_token(data.get("token", ""))
        if res.get("ok"):
            return jsonify(res)
        return jsonify(res), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/pages")
def pages_page():
    db.init_db()
    pages, token_ok = connected_pages()
    return render_template_string(
        PAGES_HTML,
        pages=pages,
        now=datetime.now().strftime("%d %b %Y %H:%M"),
        token_ok=token_ok,
        config_page=config.PAGE_ID or "-",
    )


@app.route("/pages/toggle/<page_id>", methods=["POST"])
def pages_toggle(page_id):
    now_hidden = db.toggle_hidden_page(page_id)
    return redirect(f"/pages?{'hidden' if now_hidden else 'shown'}=1")


@app.route("/post", )
def post_page():
    db.init_db()
    q = request.args.get("q", "").strip()
    page = max(1, request.args.get("page", 1, type=int))
    per_page = 10
    posts, total = db.search_posts(q=q or None, page=page, per_page=per_page)
    total_pages = max(1, (total + per_page - 1) // per_page)
    return render_template_string(
        POST_HTML,
        posts=posts,
        total=total,
        total_pages=total_pages,
        page=page,
        q=q,
        now=datetime.now().strftime("%d %b %Y %H:%M"),
        token_ok=True,
        config_page=config.PAGE_ID or "-",
    )


@app.route("/post/new", methods=["GET", "POST"])
def post_new():
    if request.method == "GET":
        pages, token_ok = connected_pages()
        return render_template_string(
            NEW_POST_HTML, pages=pages, token_ok=token_ok,
            config_page=config.PAGE_ID or "-",
        )
    # POST — create post
    text = request.form.get("text", "").strip()
    page_id = request.form.get("page_id") or config.PAGE_ID
    mode = request.form.get("mode", "instant")
    if not text:
        return "ERROR: text kosong", 400
    image = None
    f = request.files.get("image")
    if f and f.filename:
        ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else "jpg"
        if ext not in ("jpg", "jpeg", "png", "webp", "gif"):
            return "ERROR: format gambar tak disokong", 400
        from datetime import datetime as _dt
        name = f"{_dt.now().strftime('%Y%m%d%H%M%S')}_{f.filename.replace(' ', '_')}"
        img_dir = db.DB_DIR / "images"
        img_dir.mkdir(parents=True, exist_ok=True)
        f.save(img_dir / name)
        image = name
    scheduled_at = None
    if mode == "schedule":
        s = request.form.get("scheduled_at", "").strip()
        if not s:
            return "ERROR: pilih tarikh & masa untuk schedule", 400
        from datetime import datetime as _dt, timedelta as _td
        local = _dt.fromisoformat(s)  # datetime-local = waktu Malaysia
        scheduled_at = (local - _td(hours=8)).isoformat() + "Z"  # simpan UTC
    pid = db.create_post(text, image, page_id, scheduled_at)
    if mode == "instant":
        try:
            from fesbuk import fb_post
        except ImportError:
            import fb_post
        if image:
            result = fb_post.post_photo_file(str(db.DB_DIR / "images" / image), text, page_id)
        else:
            result = fb_post.post_message(text, page_id)
        if "id" not in result:
            return f"ERROR posting: {result}", 500
        db.mark_posted_by_id(pid, result["id"])
        return redirect(f"/post?posted={result['id']}")
    return redirect(f"/post?scheduled={pid}")


@app.route("/post/<int:pid>/publish", methods=["POST"])
def post_publish(pid):
    row = db.get_post_by_id(pid)
    if not row:
        return "ERROR: post tak jumpa", 404
    if row["status"] == "posted":
        return redirect("/post?already=1")
    try:
        from fesbuk import fb_post
    except ImportError:
        import fb_post
    page_id = row.get("page_id") or config.PAGE_ID
    if row.get("image"):
        img_path = db.DB_DIR / "images" / row["image"]
        result = fb_post.post_photo_file(str(img_path), row["text"], page_id)
    else:
        result = fb_post.post_message(row["text"], page_id)
    if "id" not in result:
        return f"ERROR posting: {result}", 500
    db.mark_posted_by_id(pid, result["id"])
    return redirect(f"/post?posted={result['id']}")


@app.route("/post/<int:pid>/delete", methods=["POST"])
def post_delete(pid):
    row = db.get_post_by_id(pid)
    if not row:
        return "ERROR: post tak jumpa", 404
    # buang file gambar sekali kalau ada
    if row.get("image"):
        img = db.DB_DIR / "images" / row["image"]
        if img.exists():
            try:
                img.unlink()
            except OSError:
                pass
    db.delete_post(pid)
    return redirect("/post?deleted=1")


@app.route("/post/<int:pid>/edit", methods=["GET", "POST"])
def post_edit(pid):
    row = db.get_post_by_id(pid)
    if not row:
        return "ERROR: post tak jumpa", 404
    if request.method == "GET":
        pages, token_ok = connected_pages()
        return render_template_string(
            NEW_POST_HTML, pages=pages, token_ok=token_ok,
            config_page=config.PAGE_ID or "-", post=row,
        )
    # POST — simpan perubahan
    text = request.form.get("text", "").strip()
    page_id = request.form.get("page_id") or config.PAGE_ID
    mode = request.form.get("mode", "instant")
    if not text:
        return "ERROR: text kosong", 400
    image = row.get("image")
    f = request.files.get("image")
    if f and f.filename:
        ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else "jpg"
        if ext not in ("jpg", "jpeg", "png", "webp", "gif"):
            return "ERROR: format gambar tak disokong", 400
        from datetime import datetime as _dt
        name = f"{_dt.now().strftime('%Y%m%d%H%M%S')}_{f.filename.replace(' ', '_')}"
        img_dir = db.DB_DIR / "images"
        img_dir.mkdir(parents=True, exist_ok=True)
        f.save(img_dir / name)
        image = name  # gambar baru ganti lama (lama kekal dlm disk utk rujukan)
    elif request.form.get("remove_image") == "1" and image:
        # user klik "Buang" — padam gambar lama dari DB + disk
        old = db.DB_DIR / "images" / image
        if old.exists():
            try:
                old.unlink()
            except OSError:
                pass
        image = None
    scheduled_at = None
    if mode == "schedule":
        s = request.form.get("scheduled_at", "").strip()
        if not s:
            return "ERROR: pilih tarikh & masa untuk schedule", 400
        from datetime import datetime as _dt, timedelta as _td
        local = _dt.fromisoformat(s)
        scheduled_at = (local - _td(hours=8)).isoformat() + "Z"
    db.update_post(pid, text, image, page_id, scheduled_at, status="pending")
    if mode == "instant":
        try:
            from fesbuk import fb_post
        except ImportError:
            import fb_post
        if image:
            result = fb_post.post_photo_file(str(db.DB_DIR / "images" / image), text, page_id)
        else:
            result = fb_post.post_message(text, page_id)
        if "id" not in result:
            return f"ERROR posting: {result}", 500
        db.mark_posted_by_id(pid, result["id"])
        return redirect(f"/post?posted={result['id']}")
    return redirect(f"/post?scheduled={pid}")


@app.route("/img/<path:name>")
def img_file(name):
    """Serve uploaded post image from database/images (local dashboard preview)."""
    from flask import send_from_directory, abort
    img_dir = db.DB_DIR / "images"
    if not (img_dir / name).exists():
        abort(404)
    return send_from_directory(str(img_dir), name)


@app.route("/api/post/<int:pid>/analysis")
def api_post_analysis(pid):
    """Fetch FB insights for a posted post: views, reach, comments, shares, reactions."""
    row = db.get_post_by_id(pid)
    if not row:
        return jsonify({"error": "post tak jumpa"}), 404
    if not row.get("fb_post_id"):
        return jsonify({"error": "post belum live di FB (tiada fb_post_id)"}), 400
    try:
        token = config.load_token()
        fb_id = row["fb_post_id"]
        # normalise: photo posts simpan photo id je (cth 122094478419440123),
        # tapi Graph API perlukan format page_post (cth 1155303784344068_122094478419440123)
        if "_" not in fb_id and config.PAGE_ID:
            fb_id = f"{config.PAGE_ID}_{fb_id}"
        # insights: impressions (views), unique impressions (reach), engaged users
        # Perlu read_insights permission — kalau token takde, FB tolak dgn
        # "(#100) The value must be a valid insights metric"; kita fallback.
        views = reach = engaged = None
        try:
            ins_url = f"{config.GRAPH}/{fb_id}/insights?metric=post_impressions,post_impressions_unique,post_engaged_users&access_token={token}"
            with urllib.request.urlopen(ins_url, timeout=30) as r:
                ins = json.loads(r.read().decode()).get("data", [])
            metrics = {m["name"]: (m["values"][-1]["value"] if m.get("values") else 0) for m in ins}
            views = metrics.get("post_impressions", 0)
            reach = metrics.get("post_impressions_unique", 0)
            engaged = metrics.get("post_engaged_users", 0)
        except urllib.error.HTTPError:
            # tiada read_insights — views/reach kekal None (modal papar "—")
            pass
        # reactions/comments/shares (pages_read_engagement cukup)
        eng_url = f"{config.GRAPH}/{fb_id}?fields=reactions.summary(true),comments.summary(true),shares&access_token={token}"
        with urllib.request.urlopen(eng_url, timeout=30) as r:
            eng = json.loads(r.read().decode())
        return jsonify({
            "views": views,
            "reach": reach,
            "engaged": engaged,
            "reactions": (eng.get("reactions", {}) or {}).get("summary", {}).get("total_count", 0),
            "comments": (eng.get("comments", {}) or {}).get("summary", {}).get("total_count", 0),
            "shares": (eng.get("shares", {}) or {}).get("count", 0),
            "fb_id": fb_id,
            "insights_ok": views is not None,
        })
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:300]
        return jsonify({"error": f"FB API {e.code}: {body}"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/posts")
def api_posts():
    return jsonify(db.get_posts())


def main():
    db.seed_from_msgs()
    print("Dashboard: http://127.0.0.1:8769/dashboard")
    app.run(host="127.0.0.1", port=8769, debug=False)


if __name__ == "__main__":
    main()
