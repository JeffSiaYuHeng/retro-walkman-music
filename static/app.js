// ── State ─────────────────────────────────────
const songInput = document.getElementById('songInput');
const downloadBtn = document.getElementById('downloadBtn');
const toastContainer = document.getElementById('toastContainer');

// Load persisted tasks from localStorage
let tasks = JSON.parse(localStorage.getItem('tasks') || '{}');
let allSongs = [];
let visibleSongs = [];
let songsLoaded = false;
let currentPlayingFile = '';

// Save tasks to localStorage whenever they change
function saveTasks() {
  localStorage.setItem('tasks', JSON.stringify(tasks));
}

// ── Utilities ─────────────────────────────────
function esc(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function setButtonLoading(btn, loading, label) {
  if (!btn) return;
  btn.disabled = loading;
  btn.classList.toggle('loading', loading);
  const labelEl = btn.querySelector('.btn-label');
  if (labelEl && label) labelEl.textContent = label;
  if (!labelEl && label) btn.textContent = label;
}

function createRipple(e, btn) {
  if (!e || !btn) return;
  const circle = document.createElement('span');
  const diameter = Math.max(btn.clientWidth, btn.clientHeight);
  const radius = diameter / 2;
  const rect = btn.getBoundingClientRect();
  const x = typeof e.clientX === 'number' && e.clientX ? e.clientX - rect.left : rect.width / 2;
  const y = typeof e.clientY === 'number' && e.clientY ? e.clientY - rect.top : rect.height / 2;
  circle.style.width = circle.style.height = `${diameter}px`;
  circle.style.left = `${x - radius}px`;
  circle.style.top = `${y - radius}px`;
  circle.classList.add('ripple');
  btn.appendChild(circle);
  setTimeout(() => circle.remove(), 600);
}

// ── Toast System ──────────────────────────────
function showToast(msg, type = 'success', duration = 3000) {
  const icons = { success: '&#10003;', error: '&#10007;', warning: '&#9888;', info: '&#8505;' };
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <span class="toast-icon">${icons[type] || '&#8505;'}</span>
    <span class="toast-msg">${esc(msg)}</span>
    <button class="toast-close" onclick="removeToast(this.parentElement)">&times;</button>
  `;
  toastContainer.appendChild(toast);
  if (duration > 0) setTimeout(() => removeToast(toast), duration);
}

function removeToast(el) {
  if (!el || el.classList.contains('removing')) return;
  el.classList.add('removing');
  setTimeout(() => el.remove(), 300);
}

// ── Tab Switching ─────────────────────────────
function switchTab(name) {
  document.querySelectorAll('.sub-tab, .nav-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('#panel-downloader, #panel-library').forEach(p => p.style.display = 'none');
  const tab = document.getElementById('tab-' + name);
  if (tab) tab.classList.add('active');
  const panel = document.getElementById('panel-' + name);
  if (panel) panel.style.display = '';
  if (name === 'library') loadSongs({ silent: songsLoaded });
  const btn = document.getElementById('navHamburger');
  if (btn) btn.classList.remove('open');
  const navLinksEl = document.querySelector('.global-nav .nav-links');
  if (navLinksEl) navLinksEl.classList.remove('show');
}

// ── Mobile Nav ────────────────────────────────
function toggleMobileNav() {
  const btn = document.getElementById('navHamburger');
  const links = document.querySelector('.global-nav .nav-links');
  if (btn) btn.classList.toggle('open');
  if (links) links.classList.toggle('show');
}

// ── Textarea auto-resize ──────────────────────
function adjustTextarea() {
  songInput.style.height = '44px'; // Reset to min height
  const newHeight = Math.min(songInput.scrollHeight, 200);
  songInput.style.height = newHeight + 'px';
}

songInput.addEventListener('input', adjustTextarea);
songInput.addEventListener('paste', () => {
  setTimeout(adjustTextarea, 10);
});
songInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    startDownload(e);
  }
});

// Initial adjustment
adjustTextarea();

// ── Duplicate Modal ───────────────────────────
function showModal(title, msg, duplicates, onConfirm) {
  document.getElementById('modalTitle').textContent = title;
  document.getElementById('modalMsg').textContent = msg;
  document.getElementById('dupList').innerHTML = duplicates
    .map(d => `<div class="dup-item">&#9888; ${esc(d)}</div>`).join('');
  document.getElementById('modal').classList.add('show');
  document.getElementById('modalConfirm').onclick = () => { closeModal(); onConfirm(); };
}

function closeModal() {
  document.getElementById('modal').classList.remove('show');
}
document.getElementById('modal').addEventListener('click', e => {
  if (e.target === e.currentTarget) closeModal();
});

// ── Download Flow ─────────────────────────────
async function startDownload(e) {
  const song = songInput.value.trim();
  if (!song) {
    songInput.focus();
    songInput.style.borderColor = 'var(--red)';
    setTimeout(() => songInput.style.borderColor = '', 1000);
    return;
  }
  createRipple(e, downloadBtn);
  setButtonLoading(downloadBtn, true, 'Checking');
  const lines = song.split('\n').map(l => l.trim()).filter(Boolean);
  try {
    const res = await fetch('/api/check-duplicate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ songs: lines }),
    });
    const data = await res.json();
    if (data.duplicates && data.duplicates.length > 0) {
      setButtonLoading(downloadBtn, false, 'Download');
      showModal(
        'Duplicate Songs Found',
        `${data.duplicates.length} song(s) may already exist in your library:`,
        data.duplicates,
        () => doDownload(song)
      );
      return;
    }
  } catch (err) { /* non-critical, proceed */ }
  doDownload(song);
}

async function doDownload(song) {
  songInput.value = '';
  songInput.style.height = 'auto';
  setButtonLoading(downloadBtn, true, 'Queueing');
  try {
    const res = await fetch('/api/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ song }),
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    const items = Array.isArray(data) ? data : [data];
    items.forEach(item => {
      tasks[item.id] = { id: item.id, song: item.song, input_type: item.input_type, method: '', status: 'queued', message: 'Queued...', toastShown: {} };
      pollStatus(item.id);
    });
    saveTasks();
    renderQueue();
    if (items.length > 1) {
      showToast(`Queued ${items.length} songs`, 'info');
    } else {
      showToast(`Starting download: ${items[0].song}`, 'info', 2000);
    }
  } catch (e) {
    showToast('Error: ' + e.message, 'error');
  } finally {
    setButtonLoading(downloadBtn, false, 'Download');
  }
}

// ── Poll Status ───────────────────────────────
async function pollStatus(id) {
  const poll = async () => {
    try {
      const res = await fetch(`/api/status/${id}`);
      const data = await res.json();
      tasks[id] = { ...tasks[id], ...data };
      saveTasks();
      
      // Show toast for status changes
      if (!tasks[id].toastShown) tasks[id].toastShown = {};
      
      if (data.status === 'downloading' && !tasks[id].toastShown.downloading) {
        tasks[id].toastShown.downloading = true;
        showToast(`Downloading: ${data.song}`, 'info', 2000);
      } else if (data.status === 'generating' && !tasks[id].toastShown.generating) {
        tasks[id].toastShown.generating = true;
        showToast(`Processing: ${data.song}`, 'info', 2000);
      }
      
      renderQueue();
      if (data.status === 'done' || data.status === 'failed') {
        loadSongs({ silent: true, force: true });
        if (data.status === 'done') {
          showToast(data.message || `Downloaded: ${data.song}`, data.push_status === 'failed' ? 'warning' : 'success', 5000);
        } else {
          showToast(`Failed: ${data.message}`, 'error');
        }
        return;
      }
      setTimeout(poll, 800);
    } catch (e) {
      setTimeout(poll, 2000);
    }
  };
  poll();
}

// ── Render Queue ──────────────────────────────
function renderQueue() {
  const queue = document.getElementById('queue');
  const arr = Object.values(tasks).reverse();
  const active = arr.filter(t => ['downloading', 'generating'].includes(t.status)).length;
  const done = arr.filter(t => t.status === 'done').length;
  const failed = arr.filter(t => t.status === 'failed').length;

  document.getElementById('statTotal').textContent = arr.length + ' total';
  document.getElementById('statActive').textContent = active + ' active';
  document.getElementById('statDone').textContent = done + ' done';
  document.getElementById('statFailed').textContent = failed + ' failed';
  document.getElementById('queueTitle').textContent = arr.length ? `Downloads (${arr.length})` : 'Downloads';

  if (!arr.length) {
    queue.innerHTML = '<div class="empty">No downloads yet.<br>Paste a song name, YouTube URL, or Spotify URL above.</div>';
    return;
  }
  const typeIcons = { youtube: '&#9654;', spotify: '&#127925;', search: '&#128269;' };
  const statusIcons = { queued: '&#9203;', downloading: '', generating: '', done: '&#10003;', failed: '&#10007;' };

  queue.innerHTML = arr.map(t => {
    const typeIcon = typeIcons[t.input_type] || '&#127925;';
    const isBusy = ['downloading', 'generating'].includes(t.status);
    const isFinal = ['done', 'failed'].includes(t.status);
    const msgClass = t.status === 'done' ? 'success' : t.status === 'failed' ? 'error' : '';
    const rowClass = t.status === 'done' ? 'done-row' : t.status === 'failed' ? 'failed-row' : isBusy ? 'active-row' : '';
    const methodBadge = t.method === 'yt-dlp'
      ? '<span class="method-badge fallback">yt-dlp</span>'
      : t.method === 'ytmdl' ? '<span class="method-badge">ytmdl</span>' : '';
    
    // For completed downloads, show metadata section if available
    const isDone = t.status === 'done';
    const metadataSection = isDone && t.filename ? `
      <div class="download-metadata" id="metadata-${t.id}">
        <div class="metadata-loading">Loading metadata...</div>
      </div>` : '';
    
    return `
      <div class="row ${rowClass}" id="row-${t.id}">
        <div class="row-icon ${t.status}">${isFinal ? statusIcons[t.status] : typeIcon}</div>
        <div class="row-body">
          <div class="row-title">${esc(t.song)}</div>
          <div class="row-meta">${methodBadge}</div>
          <div class="row-msg ${msgClass}">${isBusy ? `<span class="row-loading">${esc(t.message)}</span>` : esc(t.message)}</div>
          <div class="progress-bar">
            <div class="fill ${t.status} ${isBusy ? 'indeterminate' : ''}"
                 style="width:${t.status === 'done' ? '100' : isBusy ? '40' : '0'}%"></div>
          </div>
          ${metadataSection}
        </div>
        <button class="row-remove" onclick="removeTask('${t.id}')" data-tooltip="Remove" aria-label="Remove download">&times;</button>
      </div>`;
  }).join('');
  
  // Load metadata for completed downloads
  arr.forEach(t => {
    if (t.status === 'done' && t.filename && !t.metadataLoaded) {
      t.metadataLoaded = true;
      loadDownloadMetadata(t.id, t.filename);
    }
  });
}

function removeTask(id) {
  delete tasks[id];
  saveTasks();
  const el = document.getElementById('row-' + id);
  if (el) {
    el.style.animation = 'fadeUp .2s ease forwards';
    setTimeout(() => { renderQueue(); }, 200);
  } else {
    renderQueue();
  }
}

function clearDone() {
  const toRemove = Object.keys(tasks).filter(id => tasks[id].status === 'done' || tasks[id].status === 'failed');
  if (!toRemove.length) return;
  toRemove.forEach(id => {
    delete tasks[id];
    const el = document.getElementById('row-' + id);
    if (el) el.style.animation = 'fadeUp .2s ease forwards';
  });
  saveTasks();
  setTimeout(() => { renderQueue(); }, 200);
}

// ── Download Metadata ─────────────────────────
async function loadDownloadMetadata(taskId, filename) {
  const metadataEl = document.getElementById('metadata-' + taskId);
  if (!metadataEl) return;
  
  try {
    const res = await fetch(`/api/download-metadata/${encodeURIComponent(filename)}`);
    if (!res.ok) throw new Error('Failed to load metadata');
    const meta = await res.json();
    
    // Build metadata display
    let cover = '';
    if (meta.cover) {
     cover = `<div class="metadata-cover"><img src="${meta.cover}" alt="Album cover"></div>`;
    } else {
     cover = '<div class="metadata-cover placeholder">♪</div>';
    }
    
    metadataEl.innerHTML = `
     ${cover}
     <div class="metadata-info">
       <div class="metadata-field">
         <label>Title:</label>
         <span>${esc(meta.title || '(No title)')}</span>
       </div>
       <div class="metadata-field">
         <label>Artist:</label>
         <span>${esc(meta.artist || '(No artist)')}</span>
       </div>
       <div class="metadata-field">
         <label>Album:</label>
         <span>${esc(meta.album || '(No album)')}</span>
       </div>
     </div>
     <button class="btn btn-sm btn-ghost" onclick="openEditMetadataModal('${taskId}', '${encodeURIComponent(filename)}')" data-tooltip="Edit metadata">✎ Edit</button>
    `;
  } catch (e) {
    metadataEl.innerHTML = `<div class="metadata-error">Failed to load metadata</div>`;
  }
}

function openEditMetadataModal(taskId, filename) {
  const decodedFilename = decodeURIComponent(filename);
  const task = Object.values(tasks).find(t => t.id === taskId);
  
  // Create modal HTML
  const modal = document.createElement('div');
  modal.id = 'editMetadataModal';
  modal.className = 'modal-overlay';
  modal.innerHTML = `
    <div class="modal-content">
     <div class="modal-header">
       <h2>Edit Metadata</h2>
       <button class="modal-close" onclick="closeEditMetadataModal()">&times;</button>
     </div>
     <div class="modal-body">
       <div class="form-group">
         <label for="editTitle">Title:</label>
         <input type="text" id="editTitle" placeholder="Song title">
       </div>
       <div class="form-group">
         <label for="editArtist">Artist:</label>
         <input type="text" id="editArtist" placeholder="Artist name">
       </div>
       <div class="form-group">
         <label for="editAlbum">Album:</label>
         <input type="text" id="editAlbum" placeholder="Album name">
       </div>
     </div>
     <div class="modal-footer">
       <button class="btn btn-ghost" onclick="closeEditMetadataModal()">Cancel</button>
       <button class="btn btn-primary" onclick="saveMetadata('${taskId}', '${filename}')">Save</button>
     </div>
    </div>
  `;
  
  document.body.appendChild(modal);
  
  // Load current metadata
  fetch(`/api/download-metadata/${filename}`)
    .then(r => r.json())
    .then(meta => {
     document.getElementById('editTitle').value = meta.title || '';
     document.getElementById('editArtist').value = meta.artist || '';
     document.getElementById('editAlbum').value = meta.album || '';
     document.getElementById('editTitle').focus();
    })
    .catch(() => {});
  
  // Close on overlay click
  modal.addEventListener('click', e => {
    if (e.target === modal) closeEditMetadataModal();
  });
  
  // Close on Escape key
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeEditMetadataModal();
  }, { once: true });
}

function closeEditMetadataModal() {
  const modal = document.getElementById('editMetadataModal');
  if (modal) modal.remove();
}

async function saveMetadata(taskId, filename) {
  const title = document.getElementById('editTitle')?.value || '';
  const artist = document.getElementById('editArtist')?.value || '';
  const album = document.getElementById('editAlbum')?.value || '';
  
  try {
    const res = await fetch(`/api/update-metadata/${filename}`, {
     method: 'POST',
     headers: { 'Content-Type': 'application/json' },
     body: JSON.stringify({ title, artist, album }),
    });
    
    if (!res.ok) throw new Error('Failed to save metadata');
    
    closeEditMetadataModal();
    showToast('Metadata updated successfully', 'success');
    
    // Reload metadata display
    tasks[taskId].metadataLoaded = false;
    renderQueue();
  } catch (e) {
    showToast('Error: ' + e.message, 'error');
  }
}

async function pushToGitHub() {
  const btn = document.getElementById('pushBtn');
  const icon = btn.querySelector('.icon');
  btn.disabled = true;
  btn.classList.add('loading');
  if (icon) icon.textContent = '...';
  try {
    const res = await fetch('/api/push', { method: 'POST' });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    if (!res.ok || data.ok === false) throw new Error(data.message || 'Push failed');
    showToast(data.message || 'Pushed to GitHub', data.status === 'clean' ? 'info' : 'success');
  } catch (e) {
    showToast('Push failed: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.classList.remove('loading');
    if (icon) icon.innerHTML = '&#8679;';
  }
}

// ── Library ───────────────────────────────────
let songsMetadata = {}; // Store file metadata for sorting

function showSkeleton() {
  const grid = document.getElementById('songGrid');
  grid.innerHTML = Array(10).fill(0).map(() => `
    <div class="skeleton">
      <div class="sk-cover"></div>
      <div class="sk-info">
        <div class="sk-line w80"></div>
        <div class="sk-line w50"></div>
      </div>
    </div>
  `).join('');
}

async function loadSongs(options = {}) {
  const { silent = false, force = false } = options;
  const grid = document.getElementById('songGrid');
  if (songsLoaded && !force) { filterLibrary(); return; }
  if (!silent) showSkeleton();
  try {
    const res = await fetch('/api/songs');
    allSongs = await res.json();
    
    // Load metadata for sorting by date
    try {
      const metaRes = await fetch('/api/songs-metadata');
      songsMetadata = await metaRes.json();
    } catch (e) {
      songsMetadata = {};
    }
    
    songsLoaded = true;
    filterLibrary();
  } catch (e) {
    if (!silent) grid.innerHTML = '<div class="empty">Failed to load songs</div>';
    showToast('Failed to refresh library', 'error');
  }
}

function sortSongs(songs) {
  const sortBy = document.getElementById('sortBy').value || 'name-asc';
  const sorted = [...songs];
  
  if (sortBy === 'name-asc') {
    sorted.sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase()));
  } else if (sortBy === 'name-desc') {
    sorted.sort((a, b) => b.toLowerCase().localeCompare(a.toLowerCase()));
  } else if (sortBy === 'date-newest') {
    sorted.sort((a, b) => {
      const timeA = songsMetadata[a]?.modified || 0;
      const timeB = songsMetadata[b]?.modified || 0;
      return timeB - timeA;
    });
  } else if (sortBy === 'date-oldest') {
    sorted.sort((a, b) => {
      const timeA = songsMetadata[a]?.modified || 0;
      const timeB = songsMetadata[b]?.modified || 0;
      return timeA - timeB;
    });
  }
  
  return sorted;
}

function renderLibrary(songs) {
  const grid = document.getElementById('songGrid');
  visibleSongs = sortSongs(songs);
  if (!visibleSongs.length) {
    grid.innerHTML = '<div class="empty">No songs yet</div>';
    return;
  }
  grid.innerHTML = visibleSongs.map((s, i) => {
    const name = s.replace(/\.mp3$/i, '');
    const parts = name.split(' - ');
    const artist = parts.length > 1 ? parts[0].trim() : '';
    const title = parts.length > 1 ? parts.slice(1).join(' - ').trim() : name;
    const coverUrl = `/songs/${encodeURIComponent(name)}.jpg`;
    const isPlaying = currentPlayingFile === s && typeof audio !== 'undefined' && !audio.paused;
    return `
      <div class="song-card ${isPlaying ? 'is-playing' : ''}" id="card-${i}" data-filename="${esc(s)}" style="animation-delay:${Math.min(i * 12, 120)}ms">
        <div class="song-cover-wrapper">
          <div class="song-actions">
            <button class="song-action-btn edit" onclick="openEditModal(${i})" aria-label="Edit metadata for ${esc(title)}">&#9881;</button>
            <button class="song-action-btn delete" onclick="confirmDelete('${esc(s)}')" aria-label="Delete ${esc(title)}">&#128465;</button>
          </div>
          <button class="play-overlay ${isPlaying ? 'playing' : ''}" onclick="playSongFile(${i}, '${esc(s)}')" data-tooltip="${isPlaying ? 'Pause' : 'Play'}" aria-label="${isPlaying ? 'Pause' : 'Play'} ${esc(title)}">${isPlaying ? '\u23F8' : '\u25B6'}</button>
          <div class="song-cover">
            <img src="${coverUrl}" alt="${esc(title)}" onerror="this.parentElement.innerHTML='<div class=no-cover>&#127925;</div>'" loading="lazy">
          </div>
        </div>
        <div class="song-info" id="info-${i}">
          <div class="song-title-row">
            <div class="song-name" title="${esc(title)}">${esc(title)}</div>
            <div class="playing-indicator" aria-hidden="true"><span></span><span></span><span></span></div>
          </div>
          ${artist ? `<div class="song-artist" title="${esc(artist)}">${esc(artist)}</div>` : ''}
        </div>
      </div>`;
  }).join('');
}

function filterLibrary() {
  const q = document.getElementById('searchBox').value.trim().toLowerCase();
  let filtered = allSongs;
  
  if (q) {
    filtered = allSongs.filter(s => s.toLowerCase().includes(q));
    document.getElementById('libraryCount').textContent = `${filtered.length} of ${allSongs.length} songs`;
  } else {
    document.getElementById('libraryCount').textContent = `${allSongs.length} songs in library`;
  }
  
  renderLibrary(filtered);
}

// ── Delete ────────────────────────────────────
function confirmDelete(filename) {
  const modal = document.getElementById('confirmModal');
  document.getElementById('confirmTitle').textContent = 'Delete Song';
  document.getElementById('confirmMsg').textContent = `Delete "${filename.replace(/\.mp3$/i, '')}"? This cannot be undone.`;
  const btn = document.getElementById('confirmBtn');
  btn.textContent = 'Delete';
  btn.className = 'btn-modal-danger';
  btn.onclick = () => { closeConfirm(); deleteSong(filename); };
  modal.classList.add('show');
}

function closeConfirm() {
  document.getElementById('confirmModal').classList.remove('show');
}
document.getElementById('confirmModal').addEventListener('click', e => {
  if (e.target === e.currentTarget) closeConfirm();
});

async function deleteSong(filename) {
  try {
    const res = await fetch('/api/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: filename }),
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    showToast('Deleted: ' + filename.replace(/\.mp3$/i, ''), 'success');
    loadSongs({ silent: true, force: true });
  } catch (e) {
    showToast('Delete failed: ' + e.message, 'error');
  }
}

// ── Enrich ────────────────────────────────────
// ── Upload Modal ──────────────────────────────
function openUploadModal() {
  document.getElementById('uploadMp3Input').value = '';
  document.getElementById('uploadJpgInput').value = '';
  document.getElementById('mp3Chosen').textContent = 'Choose .mp3 file…';
  document.getElementById('jpgChosen').textContent = 'Choose .jpg file…';
  document.getElementById('mp3Err').classList.remove('show');
  document.getElementById('jpgErr').classList.remove('show');
  document.getElementById('uploadError').classList.remove('show');
  document.getElementById('uploadModal').classList.add('show');
}

function closeUploadModal() {
  document.getElementById('uploadModal').classList.remove('show');
}
document.getElementById('uploadModal').addEventListener('click', e => {
  if (e.target === e.currentTarget) closeUploadModal();
});

function onMp3Pick() {
  const input = document.getElementById('uploadMp3Input');
  const chosen = document.getElementById('mp3Chosen');
  const errEl = document.getElementById('mp3Err');
  if (!input.files.length) return;
  const file = input.files[0];
  if (!file.name.toLowerCase().endsWith('.mp3')) {
    errEl.textContent = 'File must be a .mp3';
    errEl.classList.add('show');
    input.value = '';
    chosen.textContent = 'Choose .mp3 file…';
    return;
  }
  if (file.size > 50 * 1024 * 1024) {
    errEl.textContent = 'File exceeds the 50 MB limit';
    errEl.classList.add('show');
    input.value = '';
    chosen.textContent = 'Choose .mp3 file…';
    return;
  }
  errEl.classList.remove('show');
  chosen.textContent = file.name;
}

function onJpgPick() {
  const input = document.getElementById('uploadJpgInput');
  const chosen = document.getElementById('jpgChosen');
  const errEl = document.getElementById('jpgErr');
  if (!input.files.length) return;
  const file = input.files[0];
  if (!file.name.toLowerCase().match(/\.jpe?g$/)) {
    errEl.textContent = 'Cover must be a .jpg file';
    errEl.classList.add('show');
    input.value = '';
    chosen.textContent = 'Choose .jpg file…';
    return;
  }
  if (file.size > 10 * 1024 * 1024) {
    errEl.textContent = 'Cover exceeds the 10 MB limit';
    errEl.classList.add('show');
    input.value = '';
    chosen.textContent = 'Choose .jpg file…';
    return;
  }
  errEl.classList.remove('show');
  chosen.textContent = file.name;
}

async function submitUpload() {
  const mp3Input = document.getElementById('uploadMp3Input');
  const jpgInput = document.getElementById('uploadJpgInput');
  const errBanner = document.getElementById('uploadError');
  const saveBtn = document.getElementById('uploadSaveBtn');
  const mp3Err = document.getElementById('mp3Err');

  if (!mp3Input.files.length) {
    mp3Err.textContent = 'Please select an MP3 file';
    mp3Err.classList.add('show');
    return;
  }
  mp3Err.classList.remove('show');
  errBanner.classList.remove('show');

  const formData = new FormData();
  formData.append('mp3', mp3Input.files[0]);
  if (jpgInput.files.length) formData.append('jpg', jpgInput.files[0]);

  saveBtn.disabled = true;
  saveBtn.classList.add('loading');
  try {
    const res = await fetch('/api/upload', { method: 'POST', body: formData });
    const data = await res.json();
    if (!res.ok) {
      errBanner.textContent = data.error || 'Upload failed';
      errBanner.classList.add('show');
      return;
    }
    closeUploadModal();
    const stem = data.filename || mp3Input.files[0].name.replace(/\.mp3$/i, '');
    if (data.push_status === 'failed') {
      showToast(`Uploaded "${stem}" (push failed: ${data.message})`, 'warning', 5000);
    } else {
      showToast(`Uploaded: ${stem}`, 'success', 4000);
    }
    loadSongs({ silent: true, force: true });
  } catch (e) {
    errBanner.textContent = 'Network error: ' + e.message;
    errBanner.classList.add('show');
  } finally {
    saveBtn.disabled = false;
    saveBtn.classList.remove('loading');
  }
}

// ── Edit Metadata Modal ───────────────────────
let _editOriginalStem = '';

function openEditModal(idx) {
  const filename = visibleSongs[idx];
  if (!filename) return;
  _editOriginalStem = filename.replace(/\.mp3$/i, '');
  const parts = _editOriginalStem.split(' - ');
  const artist = parts.length > 1 ? parts[0].trim() : '';
  const title = parts.length > 1 ? parts.slice(1).join(' - ').trim() : _editOriginalStem;

  document.getElementById('editTitle').value = title;
  document.getElementById('editArtist').value = artist;
  document.getElementById('editAlbum').value = '';
  document.getElementById('editYear').value = '';
  document.getElementById('editGenre').value = '';
  document.getElementById('editCoverInput').value = '';
  document.getElementById('editCoverChosen').textContent = 'Choose .jpg file…';

  ['editTitleErr', 'editArtistErr', 'editYearErr', 'editCoverErr'].forEach(id =>
    document.getElementById(id).classList.remove('show'));
  ['editTitle', 'editArtist', 'editYear'].forEach(id =>
    document.getElementById(id).classList.remove('field-error'));
  document.getElementById('editError').classList.remove('show');
  document.getElementById('editModalTitle').textContent = `Edit: ${title}`;
  document.getElementById('editModal').classList.add('show');
  _prefillFromCatalog(filename);
}

function _prefillFromCatalog(filename) {
  const stemAtCall = filename.replace(/\.mp3$/i, '');
  fetch('/songs.json')
    .then(r => r.json())
    .then(catalog => {
      if (_editOriginalStem !== stemAtCall) return;
      const entry = catalog.find(s => s.id === stemAtCall);
      if (!entry) return;
      const albumEl = document.getElementById('editAlbum');
      if (entry.album && entry.album !== 'Unknown Album' && !albumEl.value)
        albumEl.value = entry.album;
    })
    .catch(() => {});
}

function closeEditModal() {
  document.getElementById('editModal').classList.remove('show');
}
document.getElementById('editModal').addEventListener('click', e => {
  if (e.target === e.currentTarget) closeEditModal();
});

function onEditCoverPick() {
  const input = document.getElementById('editCoverInput');
  const chosen = document.getElementById('editCoverChosen');
  const errEl = document.getElementById('editCoverErr');
  if (!input.files.length) return;
  const file = input.files[0];
  if (!file.name.toLowerCase().match(/\.jpe?g$/)) {
    errEl.classList.add('show');
    input.value = '';
    chosen.textContent = 'Choose .jpg file…';
    return;
  }
  if (file.size > 10 * 1024 * 1024) {
    errEl.textContent = 'Cover exceeds the 10 MB limit';
    errEl.classList.add('show');
    input.value = '';
    chosen.textContent = 'Choose .jpg file…';
    return;
  }
  errEl.classList.remove('show');
  chosen.textContent = file.name;
}

async function submitEdit() {
  const title = document.getElementById('editTitle').value.trim();
  const artist = document.getElementById('editArtist').value.trim();
  const year = document.getElementById('editYear').value.trim();
  const coverInput = document.getElementById('editCoverInput');
  const errBanner = document.getElementById('editError');
  const saveBtn = document.getElementById('editSaveBtn');

  let valid = true;
  const ILLEGAL = /[<>:"/\\|?*]/;

  if (!title || ILLEGAL.test(title)) {
    document.getElementById('editTitleErr').textContent = !title ? 'Title is required' : 'Title contains invalid characters';
    document.getElementById('editTitleErr').classList.add('show');
    document.getElementById('editTitle').classList.add('field-error');
    valid = false;
  } else {
    document.getElementById('editTitleErr').classList.remove('show');
    document.getElementById('editTitle').classList.remove('field-error');
  }
  if (!artist || ILLEGAL.test(artist)) {
    document.getElementById('editArtistErr').textContent = !artist ? 'Artist is required' : 'Artist contains invalid characters';
    document.getElementById('editArtistErr').classList.add('show');
    document.getElementById('editArtist').classList.add('field-error');
    valid = false;
  } else {
    document.getElementById('editArtistErr').classList.remove('show');
    document.getElementById('editArtist').classList.remove('field-error');
  }
  if (year && !/^\d{4}$/.test(year)) {
    document.getElementById('editYearErr').classList.add('show');
    document.getElementById('editYear').classList.add('field-error');
    valid = false;
  } else {
    document.getElementById('editYearErr').classList.remove('show');
    document.getElementById('editYear').classList.remove('field-error');
  }
  if (!valid) return;
  errBanner.classList.remove('show');

  const formData = new FormData();
  formData.append('original_stem', _editOriginalStem);
  formData.append('title', document.getElementById('editTitle').value.trim());
  formData.append('artist', document.getElementById('editArtist').value.trim());
  formData.append('album', document.getElementById('editAlbum').value.trim());
  formData.append('year', year);
  formData.append('genre', document.getElementById('editGenre').value.trim());
  if (coverInput.files.length) formData.append('jpg', coverInput.files[0]);

  saveBtn.disabled = true;
  saveBtn.classList.add('loading');
  try {
    const res = await fetch('/api/edit', { method: 'POST', body: formData });
    const data = await res.json();
    if (res.status === 409) {
      errBanner.textContent = data.error || 'A song with that artist and title already exists';
      errBanner.classList.add('show');
      return;
    }
    if (!res.ok) {
      errBanner.textContent = data.error || 'Edit failed';
      errBanner.classList.add('show');
      return;
    }
    closeEditModal();
    showToast(`Saved: ${data.filename || ''}`, 'success', 4000);
    loadSongs({ silent: true, force: true });
  } catch (e) {
    errBanner.textContent = 'Network error: ' + e.message;
    errBanner.classList.add('show');
  } finally {
    saveBtn.disabled = false;
    saveBtn.classList.remove('loading');
  }
}

// ── Mini Audio Player ─────────────────────────
var audio = new Audio();
var currentPlayIndex = -1;

function syncPlayingCards(isPlaying) {
  document.querySelectorAll('.song-card.is-playing').forEach(card => card.classList.remove('is-playing'));
  document.querySelectorAll('.play-overlay.playing').forEach(btn => {
    btn.classList.remove('playing');
    btn.textContent = '\u25B6';
    btn.setAttribute('data-tooltip', 'Play');
  });
  if (!isPlaying || !currentPlayingFile) return;
  const card = document.querySelector('#card-' + currentPlayIndex);
  if (!card) return;
  card.classList.add('is-playing');
  const btn = card.querySelector('.play-overlay');
  if (btn) {
    btn.classList.add('playing');
    btn.textContent = '\u23F8';
    btn.setAttribute('data-tooltip', 'Pause');
  }
}

function playSongFile(index, filename) {
  if (currentPlayIndex === index && !audio.paused) {
    audio.pause();
    return;
  }
  currentPlayIndex = index;
  currentPlayingFile = filename;
  audio.src = '/songs/' + encodeURIComponent(filename);
  audio.play().catch(e => {
    showToast('Playback failed: ' + e.message, 'error');
    syncPlayingCards(false);
  });
  syncPlayingCards(true);
  const parts = filename.replace(/\.mp3$/i, '').split(' - ');
  const artist = parts.length > 1 ? parts[0].trim() : '';
  const title = parts.length > 1 ? parts.slice(1).join(' - ').trim() : filename;
  document.getElementById('miniTitle').textContent = title;
  document.getElementById('miniArtist').textContent = artist || 'Unknown';
  document.getElementById('miniCover').src = '/songs/' + encodeURIComponent(filename.replace(/\.mp3$/i, '.jpg'));
  document.getElementById('miniCover').onerror = function () { this.src = ''; };
  document.getElementById('miniPlayer').classList.add('show');
  document.getElementById('miniPlay').textContent = '\u23F8';
}

audio.addEventListener('ended', () => {
  if (currentPlayIndex < visibleSongs.length - 1) {
    playSongFile(currentPlayIndex + 1, visibleSongs[currentPlayIndex + 1]);
  } else {
    audio.currentTime = 0;
    syncPlayingCards(false);
  }
});
audio.addEventListener('pause', () => {
  document.getElementById('miniPlay').textContent = '\u25B6';
  syncPlayingCards(false);
});
audio.addEventListener('play', () => {
  document.getElementById('miniPlay').textContent = '\u23F8';
  syncPlayingCards(true);
});

audio.addEventListener('error', () => {
  showToast('Failed to load audio', 'error');
  syncPlayingCards(false);
});

function syncMiniPlayerProgress() {
  if (!audio.duration) return;
  document.getElementById('miniProgressFill').style.width = (audio.currentTime / audio.duration * 100) + '%';
  document.getElementById('miniTime').textContent = fmtTime(audio.currentTime) + ' / ' + fmtTime(audio.duration);
}
audio.addEventListener('timeupdate', syncMiniPlayerProgress);
audio.addEventListener('loadedmetadata', syncMiniPlayerProgress);

function fmtTime(s) {
  if (!s || isNaN(s)) return '0:00';
  const hours = Math.floor(s / 3600);
  const mins = Math.floor((s % 3600) / 60);
  const secs = Math.floor(s % 60);
  if (hours > 0) {
    return hours + ':' + (mins < 10 ? '0' : '') + mins + ':' + (secs < 10 ? '0' : '') + secs;
  }
  return mins + ':' + (secs < 10 ? '0' : '') + secs;
}

document.getElementById('miniPlay').addEventListener('click', () => {
  if (!audio.src) return;
  audio.paused ? audio.play() : audio.pause();
});
document.getElementById('miniPrev').addEventListener('click', () => {
  if (currentPlayIndex > 0) playSongFile(currentPlayIndex - 1, visibleSongs[currentPlayIndex - 1]);
});
document.getElementById('miniNext').addEventListener('click', () => {
  if (currentPlayIndex < visibleSongs.length - 1) playSongFile(currentPlayIndex + 1, visibleSongs[currentPlayIndex + 1]);
});
document.getElementById('miniProgressWrap').addEventListener('click', e => {
  if (!audio.duration) return;
  audio.currentTime = ((e.clientX - e.currentTarget.getBoundingClientRect().left) / e.currentTarget.getBoundingClientRect().width) * audio.duration;
});

// Keyboard shortcuts for playback
document.addEventListener('keydown', e => {
  if (!audio.src) return;
  if ((e.code === 'Space' || e.key === ' ') && e.target === document.body) {
    e.preventDefault();
    audio.paused ? audio.play() : audio.pause();
  }
  if (e.code === 'ArrowRight' && e.ctrlKey) {
    e.preventDefault();
    if (currentPlayIndex < visibleSongs.length - 1) playSongFile(currentPlayIndex + 1, visibleSongs[currentPlayIndex + 1]);
  }
  if (e.code === 'ArrowLeft' && e.ctrlKey) {
    e.preventDefault();
    if (currentPlayIndex > 0) playSongFile(currentPlayIndex - 1, visibleSongs[currentPlayIndex - 1]);
  }
});

// ── Init ──────────────────────────────────────
loadSongs({ silent: true });
renderQueue();
