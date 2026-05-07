'use strict';

const API = window.location.origin;

// ── 입력 화면 상태 ────────────────────────────────────────────────────
const INPUT_FIELDS   = ['era', 'place', 'characters', 'topic'];
const INPUT_SCREENS  = INPUT_FIELDS.map(f => `screen-${f}`);
let inputIdx = 0;

// ── 생성 상태 ──────────────────────────────────────────────────────────
let runId       = null;
let eventSource = null;
let pollTimer   = null;

// ── STT 상태 ───────────────────────────────────────────────────────────
let mediaRecorder = null;
let audioChunks   = [];

// ── 미디어 상태 ────────────────────────────────────────────────────────
let coverState = { url: '', loaded: false };

// sceneStates[0..3] → scene_no 1..4
let sceneStates = Array.from({ length: 4 }, () => ({
  imageUrls:   [],
  imgIdx:      0,
  imageLoaded: false,
  audioUrl:    '',
  audioLoaded: false,
}));

// 현재 보고 있는 화면
let currentView = null; // 'cover' | 1..4

// ── 화면 전환 ────────────────────────────────────────────────────────
function showScreen(id) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.getElementById(id).classList.add('active');
}

function goToCover()    { currentView = 'cover'; showScreen('screen-cover'); }
function goToScene(n)   { currentView = n;       showScreen(`screen-scene-${n}`); }

// ── 입력 화면 이동 ────────────────────────────────────────────────────
function nextInput() {
  const field = INPUT_FIELDS[inputIdx];
  if (!document.getElementById(field).value.trim()) {
    alert('내용을 입력해주세요!');
    return;
  }
  if (inputIdx < INPUT_FIELDS.length - 1) {
    inputIdx++;
    showScreen(INPUT_SCREENS[inputIdx]);
  }
}

function prevInput() {
  if (inputIdx > 0) {
    inputIdx--;
    showScreen(INPUT_SCREENS[inputIdx]);
  }
}

// ── STT ──────────────────────────────────────────────────────────────
async function startSTT(fieldType) {
  const btn       = event.currentTarget;
  const statusEl  = document.getElementById(`${fieldType}-status`);

  if (!navigator.mediaDevices?.getUserMedia) {
    alert('이 브라우저는 마이크를 지원하지 않습니다.');
    return;
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioChunks  = [];

    const mime = ['audio/webm','audio/mp4','audio/mpeg','audio/wav']
      .find(t => MediaRecorder.isTypeSupported(t)) || '';
    mediaRecorder = new MediaRecorder(stream, mime ? { mimeType: mime } : {});

    mediaRecorder.ondataavailable = e => { if (e.data.size) audioChunks.push(e.data); };
    mediaRecorder.onstop = async () => {
      const blob = new Blob(audioChunks, { type: mime || 'audio/webm' });
      stream.getTracks().forEach(t => t.stop());
      await sendSTT(blob, fieldType, mime);
    };

    btn.classList.add('recording');
    statusEl.textContent = '녹음 중... (다시 클릭하면 종료)';
    mediaRecorder.start();

    btn.onclick = () => {
      if (mediaRecorder.state === 'recording') {
        mediaRecorder.stop();
        btn.classList.remove('recording');
        statusEl.textContent = '처리 중...';
        btn.onclick = () => startSTT(fieldType);
      }
    };
  } catch (err) {
    alert('마이크 권한이 필요합니다: ' + err.message);
  }
}

async function sendSTT(blob, fieldType, mime) {
  const statusEl = document.getElementById(`${fieldType}-status`);
  const ext = mime.includes('mp4') ? 'mp4'
            : mime.includes('mpeg') ? 'mp3'
            : mime.includes('wav')  ? 'wav' : 'webm';

  const form = new FormData();
  form.append('audio_file', blob, `rec.${ext}`);
  form.append('field_type', fieldType);

  try {
    const res  = await fetch(`${API}/api/stt/field`, { method: 'POST', body: form });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const text = data.parsed_value || data.stt_text || '';
    document.getElementById(fieldType).value = text;
    statusEl.textContent = text
      ? `인식됨 (${Math.round(data.confidence * 100)}%)`
      : '음성을 인식하지 못했습니다';
  } catch (err) {
    statusEl.textContent = '인식 실패: ' + err.message;
  }
  setTimeout(() => { statusEl.textContent = ''; }, 3000);
}

// ── 생성 시작 ─────────────────────────────────────────────────────────
async function startGeneration() {
  const era        = document.getElementById('era').value.trim();
  const place      = document.getElementById('place').value.trim();
  const characters = document.getElementById('characters').value.trim();
  const topic      = document.getElementById('topic').value.trim();

  if (!era || !place || !characters || !topic) {
    alert('모든 항목을 입력해주세요!');
    return;
  }

  _resetStoryState();

  try {
    const res = await fetch(`${API}/api/runs`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ era_ko: era, place_ko: place, characters_ko: characters, topic_ko: topic }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    runId = data.run_id;
  } catch (err) {
    alert('생성 요청 실패: ' + err.message);
    return;
  }

  goToCover();
  _startMonitoring();
}

// ── SSE + polling ─────────────────────────────────────────────────────
function _startMonitoring() {
  eventSource = new EventSource(`${API}/api/runs/${runId}/events`);
  pollTimer   = setInterval(refresh, 2500);

  eventSource.addEventListener('update', async e => {
    const data = JSON.parse(e.data);
    await refresh();
    if (data.status === 'DONE' || data.status === 'FAILED') {
      _stopMonitoring();
      if (data.status === 'FAILED') {
        alert('생성 실패: ' + (data.error || '알 수 없는 오류'));
        reset();
      }
    }
  });

  eventSource.onerror = () => {}; // keep alive, suppress console noise
}

function _stopMonitoring() {
  if (eventSource) { eventSource.close(); eventSource = null; }
  if (pollTimer)   { clearInterval(pollTimer); pollTimer = null; }
}

// ── 상태 갱신 ─────────────────────────────────────────────────────────
async function refresh() {
  if (!runId) return;
  let data;
  try {
    const res = await fetch(`${API}/api/runs/${runId}`, { cache: 'no-store' });
    if (!res.ok) return;
    data = await res.json();
  } catch { return; }

  _renderCover(data);
  for (let i = 0; i < 4; i++) _renderScene(i, data.scenes[i]);
  _updateNavButtons();
}

// ── 표지 렌더링 ───────────────────────────────────────────────────────
function _renderCover(data) {
  // 로딩 메시지
  const STAGE_MSG = {
    LLM:      '동화 스토리를 생성하는 중...',
    IMAGE:    '이미지를 그리는 중...',
    TTS:      '음성을 생성하는 중...',
    PARALLEL: '이미지와 음성을 동시에 생성하는 중...',
  };
  const msgEl = document.getElementById('cover-loading-msg');
  if (msgEl && data.stage) msgEl.textContent = STAGE_MSG[data.stage] || '';

  // 제목
  if (data.story_title) {
    document.getElementById('cover-title').textContent = data.story_title;
  }

  // 표지 이미지
  if (data.cover_image_url && data.cover_image_url !== coverState.url) {
    coverState.url    = data.cover_image_url;
    coverState.loaded = false;
    const img = document.getElementById('cover-img');
    img.onload  = () => { coverState.loaded = true; _syncCoverVisibility(); _updateNavButtons(); };
    img.onerror = () => { coverState.url = ''; };
    img.src = API + data.cover_image_url + '?t=' + Date.now();
  }

  _syncCoverVisibility();
}

function _syncCoverVisibility() {
  const ready = !!(coverState.url && coverState.loaded);
  document.getElementById('cover-loading').style.display  = ready ? 'none' : '';
  const content = document.getElementById('cover-content');
  content.style.display = ready ? 'flex' : 'none';
  content.classList.toggle('visible', ready);
}

// ── 장면 렌더링 ───────────────────────────────────────────────────────
function _renderScene(i, scene) {
  if (!scene) return;
  const n  = i + 1;
  const st = sceneStates[i];

  // 텍스트
  _setText(`scene-title-${n}`,    scene.title    || '');
  _setText(`scene-narration-${n}`, scene.narration || '');
  _setText(`scene-dialogue-${n}`, scene.dialogue  || '');

  // 감정 배지
  const badge = document.getElementById(`scene-emotion-${n}`);
  const emotion = scene.dialogue_emotion || scene.narration_emotion || '';
  if (badge && emotion) {
    badge.textContent = _emotionLabel(emotion);
    badge.dataset.emotion = emotion;
  }

  // 이미지 URL 목록 갱신
  const urls = scene.image_urls || [];
  if (urls.length && JSON.stringify(urls) !== JSON.stringify(st.imageUrls)) {
    st.imageUrls   = urls;
    st.imgIdx      = 0;
    st.imageLoaded = false;
    _loadSceneImage(n, i);
  }

  // 오디오
  if (scene.audio_url && scene.audio_url !== st.audioUrl) {
    st.audioUrl    = scene.audio_url;
    st.audioLoaded = false;
    const audio = document.getElementById(`scene-audio-${n}`);
    if (audio) {
      audio.oncanplay = () => { st.audioLoaded = true; };
      audio.src = API + scene.audio_url + '?t=' + Date.now();
      audio.load();
    }
  }

  _syncSceneVisibility(n, i);
}

function _loadSceneImage(n, i) {
  const st  = sceneStates[i];
  const img = document.getElementById(`scene-img-${n}`);
  if (!img) return;
  img.onload  = () => { st.imageLoaded = true; _syncSceneVisibility(n, i); _updateNavButtons(); };
  img.onerror = () => { st.imageLoaded = false; st.imageUrls = []; };
  img.src = API + st.imageUrls[st.imgIdx] + '?t=' + Date.now();
  _updateCarouselControls(n, i);
}

function _syncSceneVisibility(n, i) {
  const st    = sceneStates[i];
  const ready = st.imageUrls.length > 0 && st.imageLoaded;
  document.getElementById(`scene-loading-${n}`).style.display  = ready ? 'none' : '';
  const content = document.getElementById(`scene-content-${n}`);
  content.style.display = ready ? 'flex' : 'none';
  content.classList.toggle('visible', ready);
}

// ── 이미지 캐러셀 ─────────────────────────────────────────────────────
function prevImage(n) {
  const i  = n - 1;
  const st = sceneStates[i];
  if (st.imgIdx > 0) { st.imgIdx--; st.imageLoaded = false; _loadSceneImage(n, i); }
}

function nextImage(n) {
  const i  = n - 1;
  const st = sceneStates[i];
  if (st.imgIdx < st.imageUrls.length - 1) { st.imgIdx++; st.imageLoaded = false; _loadSceneImage(n, i); }
}

function _updateCarouselControls(n, i) {
  const st    = sceneStates[i];
  const total = st.imageUrls.length;
  const prev  = document.getElementById(`img-prev-${n}`);
  const next  = document.getElementById(`img-next-${n}`);
  const ind   = document.getElementById(`img-indicator-${n}`);
  if (prev) prev.disabled = st.imgIdx === 0;
  if (next) next.disabled = st.imgIdx >= total - 1;
  if (ind)  ind.textContent = total ? `${st.imgIdx + 1} / ${total}` : '';
}

// ── 내비게이션 버튼 상태 갱신 ────────────────────────────────────────
function _updateNavButtons() {
  // 표지 → 장면 1
  const coverNext = document.getElementById('cover-next');
  if (coverNext) coverNext.disabled = !_isSceneReady(0);

  // 장면 N → 장면 N+1
  for (let i = 0; i < 3; i++) {
    const btn = document.getElementById(`scene-next-${i + 1}`);
    if (btn) btn.disabled = !_isSceneReady(i) || !_isSceneReady(i + 1);
  }
}

function _isSceneReady(i) {
  const st = sceneStates[i];
  return st.imageUrls.length > 0 && st.imageLoaded;
}

// ── 리셋 ─────────────────────────────────────────────────────────────
function reset() {
  _stopMonitoring();
  _resetStoryState();
  inputIdx = 0;
  INPUT_FIELDS.forEach(f => { document.getElementById(f).value = ''; });
  showScreen('screen-era');
}

function _resetStoryState() {
  runId      = null;
  coverState = { url: '', loaded: false };
  sceneStates = Array.from({ length: 4 }, () => ({
    imageUrls: [], imgIdx: 0, imageLoaded: false, audioUrl: '', audioLoaded: false,
  }));

  // 표지 화면 초기화
  _syncCoverVisibility();
  document.getElementById('cover-title').textContent = '';
  const coverImg = document.getElementById('cover-img');
  coverImg.src = '';
  document.getElementById('cover-loading-msg').textContent = '동화 스토리를 생성하는 중...';
  document.getElementById('cover-loading').style.display = '';
  document.getElementById('cover-next').disabled = true;

  // 장면 화면 초기화
  for (let n = 1; n <= 4; n++) {
    const i = n - 1;
    _setText(`scene-title-${n}`,    '');
    _setText(`scene-narration-${n}`,'');
    _setText(`scene-dialogue-${n}`, '');
    const badge = document.getElementById(`scene-emotion-${n}`);
    if (badge) { badge.textContent = ''; badge.dataset.emotion = ''; }
    const img = document.getElementById(`scene-img-${n}`);
    if (img)  img.src = '';
    const audio = document.getElementById(`scene-audio-${n}`);
    if (audio) { audio.src = ''; audio.load(); }
    _updateCarouselControls(n, i);
    document.getElementById(`scene-loading-${n}`).style.display = '';
    const content = document.getElementById(`scene-content-${n}`);
    content.style.display = 'none';
    content.classList.remove('visible');
    const nextBtn = document.getElementById(`scene-next-${n}`);
    if (nextBtn) nextBtn.disabled = true;
  }
}

// ── 유틸 ─────────────────────────────────────────────────────────────
function _setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

const EMOTION_LABELS = {
  happy:    '기쁨',
  sad:      '슬픔',
  curious:  '호기심',
  surprised:'놀람',
  tense:    '긴장',
  calm:     '차분',
  warm:     '따뜻함',
  magical:  '신비',
};

function _emotionLabel(emotion) {
  return EMOTION_LABELS[emotion] || emotion;
}
