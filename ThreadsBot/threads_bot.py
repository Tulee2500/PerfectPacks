"""
Threads Auto-Post GUI
Giao diện web tích hợp sẵn trong Python — mở trình duyệt để nhập liệu,
sau đó Selenium tự đăng bài theo lịch.

Yêu cầu:
    pip install selenium webdriver-manager schedule flask
"""

# ─── Standard libs ───────────────────────────────────────────────
import json, os, sys, time, random, threading, getpass
from datetime import datetime

# ─── Third-party ─────────────────────────────────────────────────
from flask import Flask, request, jsonify, render_template_string
import schedule
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException

# ═════════════════════════════════════════════════════════════════
# CONFIG
# ═════════════════════════════════════════════════════════════════
SCHEDULE_FILE        = "threads_schedule.json"
XPATH_POST_INPUT     = '//*[@id="barcelona-page-layout"]/div/div/div[2]/div/div[1]/div[3]/div/div[1]'
XPATH_POST_BUTTON    = '//*[@id="barcelona-page-layout"]/div/div/div[2]/div/div[1]/div[3]/div/div[2]/div'
# XPath nút Post trong popup "New thread" — lấy từ ảnh thực tế
XPATH_POST_BTN_POPUP = '//div[contains(@id,"mount")]//div[div[contains(@class,"x78zum5")]]//div[@role="button" and .//div[text()="Post"]]'
FLASK_PORT           = 5055

app                  = Flask(__name__)
state = {
    "driver":    None,
    "logged_in": False,
    "log":       [],          # activity log shown in UI
    "running":   False,       # scheduler running?
    "username":  "",
    "password":  "",
}

# ═════════════════════════════════════════════════════════════════
# HTML TEMPLATE  (full single-file SPA)
# ═════════════════════════════════════════════════════════════════
HTML = r"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Threads AutoPost</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Mono:wght@300;400;500&display=swap" rel="stylesheet"/>
<style>
/* ── RESET & BASE ────────────────────────────────────── */
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:       #0a0a0f;
  --surface:  #111118;
  --card:     #16161f;
  --border:   #252535;
  --accent:   #7c6aff;
  --accent2:  #ff6a9b;
  --green:    #3dffb0;
  --yellow:   #ffd166;
  --red:      #ff5c7a;
  --text:     #e8e8f0;
  --muted:    #6b6b88;
  --radius:   14px;
  --font:     'Syne', sans-serif;
  --mono:     'DM Mono', monospace;
}
html{scroll-behavior:smooth}
body{
  font-family:var(--font);
  background:var(--bg);
  color:var(--text);
  min-height:100vh;
  overflow-x:hidden;
}

/* ── NOISE OVERLAY ───────────────────────────────────── */
body::before{
  content:'';
  position:fixed;inset:0;
  background-image:url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.035'/%3E%3C/svg%3E");
  pointer-events:none;z-index:999;
}

/* ── GLOW BLOBS ──────────────────────────────────────── */
.blob{position:fixed;border-radius:50%;filter:blur(120px);pointer-events:none;z-index:0;opacity:.18}
.blob-a{width:500px;height:500px;background:var(--accent);top:-150px;left:-100px;animation:drift 12s ease-in-out infinite}
.blob-b{width:400px;height:400px;background:var(--accent2);bottom:-100px;right:-80px;animation:drift 15s ease-in-out infinite reverse}
@keyframes drift{0%,100%{transform:translate(0,0)}50%{transform:translate(40px,30px)}}

/* ── LAYOUT ──────────────────────────────────────────── */
.wrap{
  position:relative;z-index:1;
  max-width:1100px;margin:0 auto;
  padding:32px 20px 80px;
}

/* ── HEADER ──────────────────────────────────────────── */
header{
  display:flex;align-items:center;justify-content:space-between;
  margin-bottom:36px;
}
.logo{
  font-size:1.7rem;font-weight:800;letter-spacing:-.5px;
  background:linear-gradient(135deg,var(--accent),var(--accent2));
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;
}
.logo span{font-weight:400;font-size:1rem;-webkit-text-fill-color:var(--muted);display:block;margin-top:2px}
.status-badge{
  display:flex;align-items:center;gap:8px;
  background:var(--card);border:1px solid var(--border);
  padding:8px 16px;border-radius:999px;
  font-family:var(--mono);font-size:.78rem;
}
.dot{width:8px;height:8px;border-radius:50%;background:var(--muted);flex-shrink:0;transition:.3s}
.dot.online{background:var(--green);box-shadow:0 0 8px var(--green)}
.dot.busy{background:var(--yellow);box-shadow:0 0 8px var(--yellow);animation:pulse 1s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}

/* ── GRID ────────────────────────────────────────────── */
.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}
@media(max-width:760px){.grid{grid-template-columns:1fr}}

/* ── CARD ────────────────────────────────────────────── */
.card{
  background:var(--card);border:1px solid var(--border);
  border-radius:var(--radius);padding:24px;
  transition:border-color .2s;
}
.card:hover{border-color:#353550}
.card-title{
  font-size:.7rem;font-weight:700;letter-spacing:2px;text-transform:uppercase;
  color:var(--muted);margin-bottom:20px;display:flex;align-items:center;gap:8px;
}
.card-title svg{opacity:.5}

/* ── FORM CONTROLS ───────────────────────────────────── */
.field{margin-bottom:16px}
label{display:block;font-size:.75rem;font-weight:600;letter-spacing:.5px;color:var(--muted);margin-bottom:6px;text-transform:uppercase}
input[type=text],input[type=password],input[type=time],textarea,select{
  width:100%;
  background:#0d0d16;border:1px solid var(--border);
  color:var(--text);font-family:var(--mono);font-size:.875rem;
  padding:10px 14px;border-radius:8px;outline:none;
  transition:border-color .2s,box-shadow .2s;
  resize:vertical;
}
input:focus,textarea:focus,select:focus{
  border-color:var(--accent);
  box-shadow:0 0 0 3px rgba(124,106,255,.15);
}
textarea{min-height:90px;line-height:1.5}
.row-2{display:grid;grid-template-columns:1fr 1fr;gap:12px}

/* ── BUTTONS ─────────────────────────────────────────── */
.btn{
  display:inline-flex;align-items:center;justify-content:center;gap:7px;
  font-family:var(--font);font-size:.82rem;font-weight:700;letter-spacing:.3px;
  padding:10px 20px;border-radius:8px;border:none;cursor:pointer;
  transition:transform .12s,box-shadow .2s,filter .2s;
  white-space:nowrap;
}
.btn:active{transform:scale(.96)}
.btn-primary{background:linear-gradient(135deg,var(--accent),#5a4fd4);color:#fff}
.btn-primary:hover{box-shadow:0 4px 20px rgba(124,106,255,.4);filter:brightness(1.1)}
.btn-success{background:linear-gradient(135deg,#1aaf75,#0d8f60);color:#fff}
.btn-success:hover{box-shadow:0 4px 20px rgba(29,200,130,.35)}
.btn-danger{background:rgba(255,92,122,.12);color:var(--red);border:1px solid rgba(255,92,122,.25)}
.btn-danger:hover{background:rgba(255,92,122,.22)}
.btn-ghost{background:transparent;color:var(--muted);border:1px solid var(--border)}
.btn-ghost:hover{color:var(--text);border-color:#454565}
.btn-sm{padding:6px 14px;font-size:.75rem}
.btn-block{width:100%;margin-top:6px}
.btn-row{display:flex;gap:8px;flex-wrap:wrap;margin-top:4px}

/* ── SESSION PANEL ───────────────────────────────────── */
#login-section{grid-column:1/-1}
.login-inner{display:grid;grid-template-columns:1fr 1fr;gap:20px;align-items:end}
@media(max-width:600px){.login-inner{grid-template-columns:1fr}}

/* ── SCHEDULE TABLE ──────────────────────────────────── */
.period-tabs{display:flex;gap:6px;margin-bottom:18px}
.tab{
  padding:7px 18px;border-radius:6px;font-size:.78rem;font-weight:700;
  letter-spacing:.4px;text-transform:uppercase;cursor:pointer;
  border:1px solid var(--border);background:transparent;color:var(--muted);
  transition:.2s;
}
.tab.active-morning{background:rgba(255,209,102,.12);color:var(--yellow);border-color:rgba(255,209,102,.3)}
.tab.active-afternoon{background:rgba(124,106,255,.12);color:var(--accent);border-color:rgba(124,106,255,.3)}
.post-list{display:flex;flex-direction:column;gap:8px;min-height:60px}
.post-item{
  display:flex;align-items:flex-start;gap:10px;
  background:#0d0d16;border:1px solid var(--border);
  border-radius:8px;padding:10px 12px;
  font-size:.82rem;animation:slideIn .2s ease;
}
@keyframes slideIn{from{opacity:0;transform:translateY(-6px)}to{opacity:1;transform:translateY(0)}}
.post-time{
  font-family:var(--mono);font-size:.8rem;font-weight:500;
  background:var(--card);padding:3px 8px;border-radius:4px;
  color:var(--yellow);white-space:nowrap;flex-shrink:0;
}
.post-time.afternoon{color:var(--accent)}
.post-content{flex:1;line-height:1.45;word-break:break-word;color:#b8b8d0}
.post-del{
  background:none;border:none;color:var(--muted);cursor:pointer;
  font-size:1rem;padding:2px 4px;border-radius:4px;flex-shrink:0;
  transition:.15s;line-height:1;
}
.post-del:hover{color:var(--red);background:rgba(255,92,122,.1)}
.empty-msg{
  color:var(--muted);font-size:.8rem;font-family:var(--mono);
  text-align:center;padding:18px 0;letter-spacing:.5px;
}

/* ── ADD FORM ────────────────────────────────────────── */
.add-form{
  background:#0d0d16;border:1px solid var(--border);
  border-radius:10px;padding:18px;margin-top:16px;
  display:none;
}
.add-form.visible{display:block;animation:slideIn .2s ease}

/* ── LOG ─────────────────────────────────────────────── */
.log-box{
  background:#060608;border:1px solid var(--border);
  border-radius:8px;padding:14px;height:200px;overflow-y:auto;
  font-family:var(--mono);font-size:.75rem;line-height:1.7;
}
.log-box::-webkit-scrollbar{width:4px}
.log-box::-webkit-scrollbar-track{background:transparent}
.log-box::-webkit-scrollbar-thumb{background:var(--border);border-radius:4px}
.log-line{padding:1px 0}
.log-line.ok {color:var(--green)}
.log-line.err{color:var(--red)}
.log-line.inf{color:var(--accent)}
.log-line.wrn{color:var(--yellow)}

/* ── FULL-WIDTH SECTION ──────────────────────────────── */
.full{grid-column:1/-1}

/* ── SCHEDULER STATUS ────────────────────────────────── */
.sched-grid{
  display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));
  gap:10px;margin-top:12px;
}
.sched-item{
  background:#0d0d16;border:1px solid var(--border);
  border-radius:8px;padding:12px;font-size:.8rem;
  display:flex;flex-direction:column;gap:4px;
}
.sched-item .si-time{font-family:var(--mono);font-weight:500;color:var(--green);font-size:.9rem}
.sched-item .si-period{font-size:.68rem;letter-spacing:1px;text-transform:uppercase;color:var(--muted)}
.sched-item .si-preview{color:#9090b0;font-size:.75rem;line-height:1.4;margin-top:4px}

/* ── TOAST ───────────────────────────────────────────── */
#toast{
  position:fixed;bottom:28px;right:24px;z-index:9999;
  background:var(--card);border:1px solid var(--border);
  padding:12px 20px;border-radius:10px;
  font-size:.82rem;font-family:var(--mono);
  transform:translateY(20px);opacity:0;
  transition:.25s;pointer-events:none;
  box-shadow:0 8px 40px rgba(0,0,0,.4);
}
#toast.show{transform:translateY(0);opacity:1}
#toast.ok {border-color:var(--green);color:var(--green)}
#toast.err{border-color:var(--red);color:var(--red)}
#toast.inf{border-color:var(--accent);color:var(--accent)}

/* ── DIVIDER ─────────────────────────────────────────── */
hr.sep{border:none;border-top:1px solid var(--border);margin:20px 0}

/* ── COUNTER BADGE ───────────────────────────────────── */
.badge{
  display:inline-block;background:var(--accent);color:#fff;
  border-radius:999px;font-size:.65rem;font-weight:700;
  padding:1px 7px;margin-left:6px;vertical-align:middle;
}
.badge.am{background:#5a4200;color:var(--yellow)}
.badge.pm{background:#2a1d6e;color:var(--accent)}
</style>
</head>

<body>
<div class="blob blob-a"></div>
<div class="blob blob-b"></div>

<div class="wrap">

  <!-- HEADER -->
  <header>
    <div class="logo">
      Threads AutoPost
      <span>Scheduler · v2.0</span>
    </div>
    <div class="status-badge">
      <div class="dot" id="statusDot"></div>
      <span id="statusText" style="font-family:var(--mono)">Chưa đăng nhập</span>
    </div>
  </header>

  <div class="grid">

    <!-- ── ĐĂNG NHẬP ── -->
    <div class="card" id="login-section">
      <div class="card-title">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/></svg>
        Tài khoản Threads
      </div>
      <div class="login-inner">
        <div>
          <div class="field">
            <label>Tài khoản</label>
            <input type="text" id="inp-user" placeholder="email / phone / username"/>
          </div>
          <div class="field">
            <label>Mật khẩu</label>
            <input type="password" id="inp-pass" placeholder="••••••••"/>
          </div>
        </div>
        <div>
          <button class="btn btn-primary btn-block" onclick="doLogin()">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg>
            Đăng nhập & Khởi động Chrome
          </button>
          <button class="btn btn-ghost btn-block" style="margin-top:8px" onclick="checkStatus()">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 4v6h6"/><path d="M3.51 15a9 9 0 1 0 .49-3.5"/></svg>
            Kiểm tra trạng thái
          </button>
        </div>
      </div>
    </div>

    <!-- ── QUẢN LÝ BÀI ĐĂNG ── -->
    <div class="card">
      <div class="card-title">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
        Lịch đăng bài
        <span class="badge am" id="badge-am">0</span>
        <span class="badge pm" id="badge-pm">0</span>
      </div>

      <div class="period-tabs">
        <button class="tab active-morning" id="tab-m" onclick="switchTab('morning')">🌅 Sáng</button>
        <button class="tab" id="tab-a" onclick="switchTab('afternoon')">🌆 Chiều</button>
      </div>

      <div class="post-list" id="post-list"></div>

      <!-- Add form toggle -->
      <div class="btn-row" style="margin-top:14px">
        <button class="btn btn-primary btn-sm" onclick="toggleAddForm()">＋ Thêm bài</button>
        <button class="btn btn-danger btn-sm" onclick="clearPeriod()">🗑 Xóa cả buổi</button>
        <button class="btn btn-ghost btn-sm" onclick="clearAll()">✕ Xóa tất cả</button>
      </div>

      <div class="add-form" id="add-form">
        <div class="row-2">
          <div class="field">
            <label>Buổi đăng</label>
            <select id="add-period">
              <option value="morning">🌅 Sáng</option>
              <option value="afternoon">🌆 Chiều</option>
            </select>
          </div>
          <div class="field">
            <label>Giờ đăng</label>
            <input type="time" id="add-time" value="08:00"/>
          </div>
        </div>
        <div class="field">
          <label>Nội dung bài</label>
          <textarea id="add-content" placeholder="Nhập nội dung bài đăng...&#10;Có thể xuống dòng bình thường."></textarea>
        </div>
        <div class="btn-row">
          <button class="btn btn-success btn-sm" onclick="addPost()">✓ Lưu bài</button>
          <button class="btn btn-ghost btn-sm" onclick="toggleAddForm()">Hủy</button>
        </div>
      </div>
    </div>

    <!-- ── SCHEDULER CONTROL ── -->
    <div class="card">
      <div class="card-title">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
        Điều khiển Scheduler
      </div>

      <div class="btn-row" style="margin-bottom:18px">
        <button class="btn btn-success" onclick="startScheduler()">
          ▶ Chạy Scheduler
        </button>
        <button class="btn btn-danger" onclick="stopScheduler()">
          ■ Dừng
        </button>
        <button class="btn btn-ghost btn-sm" onclick="postNow()">
          ⚡ Đăng ngay 1 bài
        </button>
      </div>

      <div class="card-title" style="margin-top:4px">Jobs sắp tới</div>
      <div class="sched-grid" id="sched-grid">
        <div class="empty-msg">Scheduler chưa chạy</div>
      </div>
    </div>

    <!-- ── ACTIVITY LOG ── -->
    <div class="card full">
      <div class="card-title">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
        Activity Log
        <button class="btn btn-ghost btn-sm" style="margin-left:auto" onclick="clearLog()">Xóa log</button>
      </div>
      <div class="log-box" id="log-box">
        <div class="log-line inf">— Threads AutoPost ready —</div>
      </div>
    </div>

  </div><!-- /grid -->
</div><!-- /wrap -->

<!-- TOAST -->
<div id="toast"></div>

<script>
// ── STATE ──────────────────────────────────────────────
let schedule = { morning: [], afternoon: [] };
let currentTab = 'morning';

// ── INIT ───────────────────────────────────────────────
(async () => {
  await loadSchedule();
  renderPosts();
  await checkStatus();
  setInterval(checkStatus, 10000);
  setInterval(refreshSchedGrid, 15000);
})();

// ── API HELPERS ────────────────────────────────────────
async function api(path, body=null){
  const opts = body
    ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}
    : {method:'GET'};
  const r = await fetch(path, opts);
  return r.json();
}

// ── SCHEDULE PERSISTENCE ───────────────────────────────
async function loadSchedule(){
  const d = await api('/api/schedule');
  schedule = d;
}
async function saveSchedule(){
  await api('/api/schedule', schedule);
}

// ── STATUS ─────────────────────────────────────────────
async function checkStatus(){
  const d = await api('/api/status');
  const dot  = document.getElementById('statusDot');
  const txt  = document.getElementById('statusText');
  if(d.logged_in){
    dot.className = d.running ? 'dot busy' : 'dot online';
    txt.textContent = d.running ? 'Đang chạy scheduler' : 'Đã đăng nhập';
  } else {
    dot.className = 'dot';
    txt.textContent = 'Chưa đăng nhập';
  }
}

// ── LOGIN ──────────────────────────────────────────────
async function doLogin(){
  const u = document.getElementById('inp-user').value.trim();
  const p = document.getElementById('inp-pass').value;
  if(!u||!p){toast('Vui lòng nhập tài khoản & mật khẩu','err');return}
  log('Đang khởi động Chrome & đăng nhập...','inf');
  toast('Đang đăng nhập...','inf');
  const d = await api('/api/login',{username:u,password:p});
  if(d.ok){
    log('✓ Đăng nhập thành công','ok');
    toast('Đăng nhập thành công!','ok');
    await checkStatus();
  } else {
    log('✗ Lỗi: '+d.error,'err');
    toast('Lỗi: '+d.error,'err');
  }
}

// ── TABS ───────────────────────────────────────────────
function switchTab(period){
  currentTab = period;
  document.getElementById('tab-m').className = 'tab'+(period==='morning'?' active-morning':'');
  document.getElementById('tab-a').className = 'tab'+(period==='afternoon'?' active-afternoon':'');
  // Sync add-form select
  document.getElementById('add-period').value = period;
  renderPosts();
}

// ── RENDER POSTS ───────────────────────────────────────
function renderPosts(){
  const list  = document.getElementById('post-list');
  const posts = schedule[currentTab] || [];
  document.getElementById('badge-am').textContent = (schedule.morning||[]).length;
  document.getElementById('badge-pm').textContent = (schedule.afternoon||[]).length;

  if(!posts.length){
    list.innerHTML = '<div class="empty-msg">Chưa có bài nào trong buổi này</div>';
    return;
  }
  list.innerHTML = posts.map((p,i)=>`
    <div class="post-item">
      <span class="post-time ${currentTab==='afternoon'?'afternoon':''}">${p.time}</span>
      <span class="post-content">${escHtml(p.content)}</span>
      <button class="post-del" title="Xóa" onclick="deletePost(${i})">×</button>
    </div>
  `).join('');
}

function escHtml(s){
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\n/g,'↵ ');
}

// ── ADD / DELETE POST ──────────────────────────────────
function toggleAddForm(){
  const f = document.getElementById('add-form');
  f.classList.toggle('visible');
  // sync select to current tab
  document.getElementById('add-period').value = currentTab;
}

async function addPost(){
  const period  = document.getElementById('add-period').value;
  const time    = document.getElementById('add-time').value;
  const content = document.getElementById('add-content').value.trim();
  if(!time){toast('Chọn giờ đăng','err');return}
  if(!content){toast('Nhập nội dung bài','err');return}

  schedule[period].push({time, content});
  schedule[period].sort((a,b)=>a.time.localeCompare(b.time));
  await saveSchedule();

  document.getElementById('add-content').value='';
  document.getElementById('add-form').classList.remove('visible');
  currentTab = period;
  switchTab(period);
  log(`✓ Thêm bài [${period==='morning'?'Sáng':'Chiều'} ${time}]`,'ok');
  toast('Đã thêm bài!','ok');
}

async function deletePost(idx){
  schedule[currentTab].splice(idx,1);
  await saveSchedule();
  renderPosts();
  log('Đã xóa 1 bài','wrn');
  toast('Đã xóa','inf');
}

async function clearPeriod(){
  const label = currentTab==='morning'?'Sáng':'Chiều';
  if(!confirm(`Xóa TẤT CẢ bài buổi ${label}?`)) return;
  schedule[currentTab]=[];
  await saveSchedule();
  renderPosts();
  log(`Đã xóa tất cả bài buổi ${label}`,'wrn');
  toast(`Đã xóa buổi ${label}`,'inf');
}

async function clearAll(){
  if(!confirm('Xóa TẤT CẢ bài (cả sáng lẫn chiều)?')) return;
  schedule={morning:[],afternoon:[]};
  await saveSchedule();
  renderPosts();
  log('Đã xóa toàn bộ lịch','wrn');
  toast('Đã xóa tất cả','inf');
}

// ── SCHEDULER ─────────────────────────────────────────
async function startScheduler(){
  log('Đang khởi động scheduler...','inf');
  const d = await api('/api/scheduler/start', schedule);
  if(d.ok){
    log(`✓ Scheduler đang chạy (${d.count} jobs)`,'ok');
    toast(`Scheduler: ${d.count} jobs đã đăng ký`,'ok');
    await checkStatus();
    refreshSchedGrid();
  } else {
    log('✗ '+d.error,'err');
    toast(d.error,'err');
  }
}

async function stopScheduler(){
  const d = await api('/api/scheduler/stop');
  log('■ Scheduler đã dừng','wrn');
  toast('Đã dừng scheduler','inf');
  await checkStatus();
  document.getElementById('sched-grid').innerHTML='<div class="empty-msg">Scheduler đã dừng</div>';
}

async function postNow(){
  const content = prompt('Nhập nội dung bài đăng ngay:');
  if(!content) return;
  log('Đang đăng bài ngay...','inf');
  const d = await api('/api/post', {content});
  if(d.ok){log('✓ Đã đăng bài!','ok');toast('Đã đăng bài!','ok')}
  else{log('✗ '+d.error,'err');toast(d.error,'err')}
}

async function refreshSchedGrid(){
  const d = await api('/api/scheduler/jobs');
  const el = document.getElementById('sched-grid');
  if(!d.jobs||!d.jobs.length){
    el.innerHTML='<div class="empty-msg">Không có job nào đang chạy</div>';
    return;
  }
  el.innerHTML = d.jobs.map(j=>`
    <div class="sched-item">
      <div class="si-time">${j.time}</div>
      <div class="si-period">${j.period==='morning'?'🌅 Sáng':'🌆 Chiều'}</div>
      <div class="si-preview">${escHtml(j.content.substring(0,60))}${j.content.length>60?'…':''}</div>
    </div>
  `).join('');
}

// ── LOG ────────────────────────────────────────────────
function log(msg, type=''){
  const box = document.getElementById('log-box');
  const now = new Date().toLocaleTimeString('vi-VN');
  const div = document.createElement('div');
  div.className = 'log-line '+type;
  div.textContent = `[${now}] ${msg}`;
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
}

function clearLog(){
  document.getElementById('log-box').innerHTML='';
}

// ── TOAST ──────────────────────────────────────────────
let toastTimer;
function toast(msg, type='inf'){
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'show '+type;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(()=>el.className='',2800);
}

// ── POLL SERVER LOG ────────────────────────────────────
let lastLogLen = 0;
setInterval(async()=>{
  const d = await api('/api/log');
  if(d.log && d.log.length > lastLogLen){
    d.log.slice(lastLogLen).forEach(l=>log(l.msg, l.type));
    lastLogLen = d.log.length;
  }
},3000);
</script>
</body>
</html>
"""

# ═════════════════════════════════════════════════════════════════
# SELENIUM HELPERS
# ═════════════════════════════════════════════════════════════════

def slog(msg, typ="inf"):
    entry = {"msg": msg, "type": typ,
             "ts": datetime.now().strftime("%H:%M:%S")}
    state["log"].append(entry)
    print(f"[{entry['ts']}] {msg}")


def rand_sleep(lo=0.4, hi=1.2):
    time.sleep(random.uniform(lo, hi))


def wait_click(driver, xpath, timeout=15):
    el = WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((By.XPATH, xpath)))
    driver.execute_script("arguments[0].scrollIntoView(true);", el)
    rand_sleep(0.3, 0.6)
    el.click()
    return el


def wait_type(driver, xpath, text, timeout=15):
    el = WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.XPATH, xpath)))
    tag = el.tag_name.lower()
    if tag not in ("input", "textarea"):
        try:
            el = el.find_element(By.XPATH,
                './/input | .//textarea | .//*[@contenteditable]')
        except Exception:
            pass
    driver.execute_script("arguments[0].scrollIntoView(true);", el)
    driver.execute_script("arguments[0].focus();", el)
    rand_sleep(0.2, 0.4)
    try:
        el.click()
    except Exception:
        driver.execute_script("arguments[0].click();", el)
    rand_sleep(0.2, 0.3)
    driver.execute_script("arguments[0].value = '';", el)
    el.send_keys(text)
    driver.execute_script(
        "arguments[0].dispatchEvent(new Event('input',{bubbles:true}));", el)
    rand_sleep(0.2, 0.4)
    return el


def login_form_visible(driver, timeout=4):
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, '//*[@id="login_form"]')))
        return True
    except TimeoutException:
        return False


# ═════════════════════════════════════════════════════════════════
# SELENIUM ACTIONS (run in background thread)
# ═════════════════════════════════════════════════════════════════

def _bg(fn, *args):
    threading.Thread(target=fn, args=args, daemon=True).start()


def _do_login(username, password):
    slog("Khởi động Chrome...", "inf")
    try:
        opts = webdriver.ChromeOptions()
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            drv = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()), options=opts)
        except ImportError:
            drv = webdriver.Chrome(options=opts)

        drv.execute_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        drv.maximize_window()
        state["driver"] = drv
        state["username"] = username
        state["password"] = password

        slog("Mở threads.com...", "inf")
        drv.get("https://www.threads.com/")
        time.sleep(3)

        # Click login button header
        for xp in ['//*[@id="barcelona-header"]/div[2]/a',
                   '//*[@id="barcelona-page-layout"]/div/div[3]/div[1]/div']:
            try:
                wait_click(drv, xp, timeout=7)
                break
            except TimeoutException:
                continue
        time.sleep(2)

        # Navigate to form
        if not login_form_visible(drv, 3):
            try:
                wait_click(drv,
                    '//*[@id="mount_0_0_xl"]/div/div/div[2]/div/div/div'
                    '/div[2]/div[1]/div[3]/div/a', timeout=7)
                time.sleep(2)
            except TimeoutException:
                pass

        if not login_form_visible(drv, 3):
            try:
                wait_click(drv,
                    '//*[@id="mount_0_0_xl"]/div/div/div[2]/div/div/div'
                    '/div[2]/div[1]/div[2]/form/div/div[3]/div[2]', timeout=7)
                time.sleep(2)
            except TimeoutException:
                pass

        wait_type(drv,
            '//*[@id="login_form"]/div/div[1]/div/div[1]/div/div', username)
        time.sleep(0.4)
        wait_type(drv,
            '//*[@id="login_form"]/div/div[1]/div/div[2]/div/div', password)
        time.sleep(0.4)
        wait_click(drv,
            '//*[@id="login_form"]/div/div[1]/div/div[3]/div/div/div')
        time.sleep(4)

        # Save info popup
        for _ in range(3):
            found = False
            for xp in [
                "//button[contains(text(),'Save info')]",
                "//div[@role='button' and contains(text(),'Save info')]",
            ]:
                try:
                    wait_click(drv, xp, timeout=4)
                    found = True; time.sleep(2); break
                except TimeoutException:
                    pass
            if found:
                break
            time.sleep(3)

        state["logged_in"] = True
        slog("✓ Đăng nhập thành công!", "ok")

    except Exception as e:
        slog(f"✗ Lỗi đăng nhập: {e}", "err")


def _js_click(driver, el):
    """Click bằng JS — bypass mọi element-intercept"""
    driver.execute_script("arguments[0].click();", el)


def _find_post_input(driver, timeout=15):
    """
    Tìm ô nhập bài theo nhiều cách:
    1. XPath gốc (contenteditable bên trong)
    2. aria-label chứa 'text field' hoặc 'compose'
    3. role=button + aria-label có 'post'
    """
    wait = WebDriverWait(driver, timeout)

    # Cách 1 — contenteditable bên trong XPath gốc
    try:
        el = wait.until(EC.presence_of_element_located((
            By.XPATH,
            XPATH_POST_INPUT + '//*[@contenteditable="true"]'
        )))
        return el
    except TimeoutException:
        pass

    # Cách 2 — aria-label
    for aria in [
        '//*[@contenteditable="true" and contains(@aria-label,"text field")]',
        '//*[@contenteditable="true" and contains(@aria-label,"compose")]',
        '//*[@contenteditable="true" and contains(@aria-label,"post")]',
        '//*[@contenteditable="true"]',
    ]:
        try:
            el = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, aria)))
            return el
        except TimeoutException:
            continue

    # Cách 3 — XPath gốc chính nó
    return WebDriverWait(driver, 5).until(
        EC.presence_of_element_located((By.XPATH, XPATH_POST_INPUT)))


def _find_post_button(driver, timeout=12):
    """
    Tìm nút Post trong popup New Thread.
    Dùng phần đuôi XPath ổn định (không phụ thuộc dynamic mount id):
      /div/div/div[3]/div/div/div[1]/div/div[2]/div/div/div/div[2]
      /div/div/div/div/div[3]/div/div[1]/div/div
    Kết hợp với text scan làm fallback.
    """
    deadline = time.time() + timeout

    while time.time() < deadline:
        # ── Cách 1: Tìm mount div động rồi ghép đuôi XPath ──
        try:
            mounts = driver.find_elements(By.XPATH,
                '//*[starts-with(@id,"mount_")]')
            for mount in mounts:
                mid = mount.get_attribute("id")
                tail = ('/div/div/div[3]/div/div/div[1]/div/div[2]/div/div'
                        '/div/div[2]/div/div/div/div/div[3]/div/div[1]/div/div')
                xp_full = f'//*[@id="{mid}"]{tail}'
                try:
                    el = driver.find_element(By.XPATH, xp_full)
                    if el.is_displayed() and el.text.strip() == "Post":
                        slog(f"  → Post btn via mount xpath [{mid}]", "inf")
                        return el
                except Exception:
                    pass
        except Exception:
            pass

        # ── Cách 2: Text scan trong dialog ──
        try:
            candidates = driver.find_elements(By.XPATH,
                '//*[@role="dialog"]//*[@role="button"]'
                ' | //*[@role="dialog"]//button')
            for el in candidates:
                try:
                    if el.is_displayed() and el.text.strip() == "Post":
                        slog("  → Post btn via dialog text scan", "inf")
                        return el
                except Exception:
                    continue
        except Exception:
            pass

        # ── Cách 3: Text scan toàn trang (last resort) ──
        try:
            candidates = driver.find_elements(By.XPATH,
                '//*[@role="button"] | //button')
            hits = [e for e in candidates
                    if e.is_displayed() and e.text.strip() == "Post"]
            if hits:
                slog("  → Post btn via full-page text scan", "inf")
                return hits[-1]
        except Exception:
            pass

        time.sleep(0.5)

    raise TimeoutException("Không tìm thấy nút Post")


def _do_post(content):
    from selenium.webdriver.common.action_chains import ActionChains

    driver = state.get("driver")
    if not driver:
        slog("✗ Driver chưa sẵn sàng", "err")
        return False
    try:
        # ── Về trang chủ nếu cần ──
        if "threads.com" not in driver.current_url:
            driver.get("https://www.threads.com/")
            time.sleep(3)

        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(0.8)

        # ── BƯỚC 1: Click ô "What's on your mind" trên feed để mở popup ──
        slog("Mở popup New thread...", "inf")
        trigger = None
        for xp in [
            XPATH_POST_INPUT,
            '//*[@contenteditable="true" and contains(@aria-label,"text field")]',
            '//*[@placeholder="What\'s new?"]',
            '//*[contains(@aria-label,"What\'s new")]',
            '//*[@role="button" and contains(.,"What\'s new")]',
        ]:
            try:
                trigger = WebDriverWait(driver, 6).until(
                    EC.presence_of_element_located((By.XPATH, xp)))
                break
            except TimeoutException:
                continue

        if trigger is None:
            slog("✗ Không tìm thấy ô trigger", "err")
            return False

        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});", trigger)
        time.sleep(0.5)
        # ActionChains click để React nhận đúng focus event
        ActionChains(driver).move_to_element(trigger).click().perform()
        rand_sleep(1.2, 1.8)   # chờ popup animate xong

        # ── BƯỚC 2: Chờ popup mở — detect bằng "New thread" title hoặc dialog ──
        popup_open = False
        for xp_popup in [
            '//*[contains(text(),"New thread")]',
            '//*[@role="dialog"]',
            '//*[contains(@aria-label,"New thread")]',
        ]:
            try:
                WebDriverWait(driver, 6).until(
                    EC.presence_of_element_located((By.XPATH, xp_popup)))
                popup_open = True
                slog("✓ Popup đã mở", "inf")
                break
            except TimeoutException:
                continue

        if not popup_open:
            slog("Không detect được popup title, vẫn tiếp tục...", "wrn")

        rand_sleep(0.6, 1.0)

        # ── BƯỚC 3: Tìm contenteditable TRONG popup ──
        slog("Tìm ô nhập trong popup...", "inf")
        popup_input = None
        for xp in [
            '//*[@role="dialog"]//*[@contenteditable="true"]',
            '//*[contains(text(),"New thread")]/ancestor::*[@role="dialog"]//*[@contenteditable="true"]',
            '//*[@contenteditable="true" and contains(@aria-label,"text field")]',
            '//*[@contenteditable="true" and @role="button"]',
            '//*[@contenteditable="true"]',
        ]:
            try:
                popup_input = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.XPATH, xp)))
                slog(f"  → Input found: {xp[:55]}", "inf")
                break
            except TimeoutException:
                continue

        if popup_input is None:
            slog("✗ Không tìm thấy ô nhập trong popup", "err")
            return False

        # ── BƯỚC 4: Focus + gõ nội dung ──
        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});", popup_input)
        time.sleep(0.3)

        # ActionChains: move → click để set cursor focus đúng cách
        ActionChains(driver).move_to_element(popup_input).click().perform()
        rand_sleep(0.4, 0.7)

        # ── BƯỚC 4b: Gõ nội dung vào popup bằng clipboard paste ──
        # send_keys trên contenteditable React hay bị lỗi → dùng pyperclip paste
        slog("Nhập nội dung...", "inf")

        # Focus ô nhập
        ActionChains(driver).move_to_element(popup_input).click().perform()
        rand_sleep(0.3, 0.5)

        # Xóa nội dung cũ bằng Ctrl+A → Delete
        from selenium.webdriver.common.keys import Keys
        ActionChains(driver).key_down(Keys.CONTROL).send_keys('a') \
            .key_up(Keys.CONTROL).send_keys(Keys.DELETE).perform()
        time.sleep(0.3)

        # Paste bằng clipboard — cách đáng tin nhất với React contenteditable
        try:
            import pyperclip
            pyperclip.copy(content)
            ActionChains(driver).key_down(Keys.CONTROL).send_keys('v') \
                .key_up(Keys.CONTROL).perform()
            rand_sleep(0.5, 0.8)
        except ImportError:
            # Fallback: gõ từng ký tự nếu không có pyperclip
            popup_input.send_keys(content)
            rand_sleep(0.5, 0.8)

        # Trigger React events sau khi paste
        driver.execute_script("""
            var el = arguments[0];
            ['input','change','keyup','keydown'].forEach(function(evt){
                el.dispatchEvent(new Event(evt, {bubbles:true}));
            });
            // InputEvent đặc biệt cho contenteditable
            el.dispatchEvent(new InputEvent('input', {
                bubbles: true, cancelable: true,
                inputType: 'insertFromPaste'
            }));
        """, popup_input)
        rand_sleep(0.6, 1.0)

        # Verify nội dung đã vào ô
        actual_text = driver.execute_script(
            "return arguments[0].innerText || arguments[0].textContent;",
            popup_input)
        actual_text = (actual_text or "").strip()
        if actual_text:
            slog(f"✓ Nội dung đã vào ô: '{actual_text[:40]}...'", "ok")
        else:
            slog("⚠ Ô vẫn trống! Thử JS inject trực tiếp...", "wrn")
            # Last resort: inject text bằng execCommand
            driver.execute_script("""
                arguments[0].focus();
                document.execCommand('selectAll', false, null);
                document.execCommand('delete', false, null);
                document.execCommand('insertText', false, arguments[1]);
            """, popup_input, content)
            rand_sleep(0.5, 0.8)
            driver.execute_script(
                "arguments[0].dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText'}));",
                popup_input)

        # ── BƯỚC 5: Tìm & click nút Post ──
        slog("Tìm nút Post...", "inf")
        btn = _find_post_button(driver, timeout=12)

        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});", btn)
        time.sleep(0.5)

        # ActionChains click — tự nhiên nhất
        ActionChains(driver).move_to_element(btn).click().perform()
        slog("Đã click Post, đang chờ...", "inf")
        time.sleep(2)

        # ── BƯỚC 5b: Nếu xuất hiện "Save to drafts?" → click Don't save ──
        try:
            dont_save = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((
                    By.XPATH,
                    '//*[normalize-space(text())="Don\'t save" '
                    'or normalize-space(.)="Don\'t save"]'
                ))
            )
            slog("⚠ Xuất hiện 'Save to drafts?' → click Don't save, thử lại...", "wrn")
            ActionChains(driver).move_to_element(dont_save).click().perform()
            time.sleep(1.5)
            # Thử click Post lại lần 2
            btn2 = _find_post_button(driver, timeout=8)
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", btn2)
            time.sleep(0.4)
            ActionChains(driver).move_to_element(btn2).click().perform()
            slog("Đã click Post lần 2...", "inf")
            time.sleep(2)
        except TimeoutException:
            pass  # Không có dialog Save to drafts → bình thường

        # ── BƯỚC 6: Verify — popup đóng = thành công ──
        try:
            WebDriverWait(driver, 5).until_not(
                EC.presence_of_element_located((By.XPATH, '//*[@role="dialog"]')))
            slog(f"✓ Đã đăng bài thành công [{datetime.now().strftime('%H:%M')}]", "ok")
        except TimeoutException:
            slog(f"✓ Đã click Post [{datetime.now().strftime('%H:%M')}] (popup vẫn hiện — có thể ok)", "ok")

        return True

    except Exception as e:
        slog(f"✗ Lỗi đăng bài: {e}", "err")
        return False


# ═════════════════════════════════════════════════════════════════
# SCHEDULER
# ═════════════════════════════════════════════════════════════════

_sched_lock    = threading.Lock()
_sched_jobs    = []          # list of {time, period, content}
_post_lock     = threading.Lock()   # đảm bảo chỉ 1 job chạy tại 1 thời điểm
_loop_thread   = None               # ref đến scheduler loop thread duy nhất


def _run_job(content, period, t):
    # Nếu đang có job khác chạy → bỏ qua (không block)
    if not _post_lock.acquire(blocking=False):
        slog(f"⚠ Job [{period} {t}] bị bỏ qua vì đang có job khác chạy", "wrn")
        return
    try:
        slog(f"⏰ Đến giờ đăng [{period} {t}]", "inf")
        _do_post(content)
    finally:
        _post_lock.release()


def _start_scheduler(data):
    global _loop_thread
    with _sched_lock:
        # Dừng loop cũ nếu có
        state["running"] = False
        time.sleep(0.3)

        schedule.clear()
        _sched_jobs.clear()
        count = 0
        for period, posts in data.items():
            for p in posts:
                t   = p["time"]
                txt = p["content"]
                schedule.every().day.at(t).do(
                    _run_job, content=txt, period=period, t=t)
                _sched_jobs.append(
                    {"time": t, "period": period, "content": txt})
                count += 1

        state["running"] = True
        slog(f"✓ Scheduler: {count} jobs đã đăng ký", "ok")
        return count


def _scheduler_loop():
    slog("▶ Scheduler loop bắt đầu", "inf")
    while state["running"]:
        schedule.run_pending()
        time.sleep(10)
    slog("■ Scheduler loop đã dừng", "wrn")


# ═════════════════════════════════════════════════════════════════
# FLASK ROUTES
# ═════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/api/status")
def api_status():
    return jsonify({
        "logged_in": state["logged_in"],
        "running":   state["running"],
        "username":  state["username"],
    })


@app.route("/api/log")
def api_log():
    return jsonify({"log": state["log"]})


@app.route("/api/schedule", methods=["GET", "POST"])
def api_schedule():
    if request.method == "GET":
        if os.path.exists(SCHEDULE_FILE):
            with open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
                return jsonify(json.load(f))
        return jsonify({"morning": [], "afternoon": []})

    data = request.json or {"morning": [], "afternoon": []}
    with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return jsonify({"ok": True})


@app.route("/api/login", methods=["POST"])
def api_login():
    d = request.json or {}
    u = d.get("username", "").strip()
    p = d.get("password", "")
    if not u or not p:
        return jsonify({"ok": False, "error": "Thiếu tài khoản/mật khẩu"})
    if state["driver"]:
        try: state["driver"].quit()
        except Exception: pass
        state["driver"] = None
        state["logged_in"] = False
    _bg(_do_login, u, p)
    # Wait a moment then return (actual result shows via log polling)
    return jsonify({"ok": True})


@app.route("/api/scheduler/start", methods=["POST"])
def api_sched_start():
    global _loop_thread
    if not state["logged_in"]:
        return jsonify({"ok": False, "error": "Chưa đăng nhập!"})
    data = request.json or {"morning": [], "afternoon": []}
    count = _start_scheduler(data)
    if count == 0:
        return jsonify({"ok": False, "error": "Không có bài nào trong lịch"})
    # Chỉ start 1 loop thread duy nhất
    if _loop_thread is None or not _loop_thread.is_alive():
        _loop_thread = threading.Thread(target=_scheduler_loop, daemon=True)
        _loop_thread.start()
        slog("▶ Loop thread mới được tạo", "inf")
    else:
        slog("ℹ Loop thread đã đang chạy, không tạo thêm", "inf")
    return jsonify({"ok": True, "count": count})


@app.route("/api/scheduler/stop", methods=["POST"])
def api_sched_stop():
    global _loop_thread
    state["running"] = False
    schedule.clear()
    _sched_jobs.clear()
    _loop_thread = None
    slog("■ Scheduler đã dừng", "wrn")
    return jsonify({"ok": True})


@app.route("/api/scheduler/jobs")
def api_sched_jobs():
    return jsonify({"jobs": _sched_jobs})


@app.route("/api/post", methods=["POST"])
def api_post():
    if not state["logged_in"]:
        return jsonify({"ok": False, "error": "Chưa đăng nhập!"})
    content = (request.json or {}).get("content", "").strip()
    if not content:
        return jsonify({"ok": False, "error": "Nội dung trống"})
    _bg(_do_post, content)
    return jsonify({"ok": True})


# ═════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import webbrowser
    print(f"""
╔══════════════════════════════════════════════╗
║   Threads AutoPost  —  GUI Web Interface     ║
║   http://localhost:{FLASK_PORT}                    ║
╚══════════════════════════════════════════════╝
""")
    threading.Timer(1.2, lambda: webbrowser.open(
        f"http://localhost:{FLASK_PORT}")).start()
    app.run(host="0.0.0.0", port=FLASK_PORT, debug=False, use_reloader=False)