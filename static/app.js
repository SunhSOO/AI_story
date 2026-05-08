'use strict';

const API = window.location.origin;
const SCENE_COUNT = 4;
const PANEL_COUNT = 3;
const STORY_UNITS = 5;
const IMAGE_UNITS = 13;
const AUDIO_UNITS = 5;
const TOTAL_UNITS = STORY_UNITS + IMAGE_UNITS + AUDIO_UNITS;

const FIELD_IDS = ['era', 'place', 'characters', 'topic'];
const STAGE_LABELS = {
  LLM: '이야기 생성',
  TTS: '음성 생성',
  IMAGE: '이미지 생성',
  PARALLEL: '음성/이미지 병렬 생성',
};
const EMOTION_LABELS = {
  행복: '행복',
  슬픔: '슬픔',
  화남: '화남',
  밝음: '밝음',
  긴장: '긴장',
  무서움: '무서움',
};

const state = {
  runId: '',
  eventSource: null,
  pollTimer: null,
  pollInFlight: false,
  pollFailures: 0,
  mediaRecorder: null,
  audioChunks: [],
  activeStream: null,
  activeVoiceButton: null,
};

document.addEventListener('DOMContentLoaded', () => {
  buildSceneShells();
  bindUI();
  resetRunUI();
});

function bindUI() {
  document.getElementById('story-form').addEventListener('submit', startGeneration);
  document.getElementById('reset-button').addEventListener('click', resetAll);
  document.querySelectorAll('.voice-button').forEach((button) => {
    button.addEventListener('click', () => toggleRecording(button));
  });
}

function buildSceneShells() {
  const grid = document.getElementById('scenes-grid');
  grid.textContent = '';

  for (let sceneNo = 1; sceneNo <= SCENE_COUNT; sceneNo += 1) {
    const article = document.createElement('article');
    article.className = 'scene-card';
    article.id = `scene-card-${sceneNo}`;
    article.innerHTML = `
      <header class="scene-header">
        <div>
          <p class="scene-index">장면 ${sceneNo}</p>
          <h3 id="scene-title-${sceneNo}" class="placeholder-line">이야기 생성 대기</h3>
        </div>
        <span class="resource-pill" id="scene-pill-${sceneNo}">대기</span>
      </header>
      <div class="scene-copy">
        <p id="scene-narration-${sceneNo}" class="placeholder-line">나레이션이 도착하면 표시됩니다.</p>
        <blockquote id="scene-dialogue-${sceneNo}" class="placeholder-line">대사가 도착하면 표시됩니다.</blockquote>
        <div class="emotion-row">
          <span class="emotion-badge" id="scene-narration-emotion-${sceneNo}">나레이션 감정 대기</span>
          <span class="emotion-badge" id="scene-dialogue-emotion-${sceneNo}">대사 감정 대기</span>
        </div>
      </div>
      <div class="panel-grid" id="panel-grid-${sceneNo}">
        ${Array.from({ length: PANEL_COUNT }, (_, index) => `
          <div class="media-slot panel-slot" id="panel-slot-${sceneNo}-${index + 1}">
            <div class="slot-placeholder">
              <span class="loader"></span>
              <p>패널 ${index + 1} 대기</p>
            </div>
            <img id="panel-image-${sceneNo}-${index + 1}" alt="장면 ${sceneNo} 패널 ${index + 1}" hidden>
          </div>
        `).join('')}
      </div>
      <div class="audio-shell" id="scene-audio-shell-${sceneNo}">
        <span>장면 ${sceneNo} 음성</span>
        <audio id="scene-audio-${sceneNo}" controls hidden></audio>
        <small id="scene-audio-status-${sceneNo}">생성 대기</small>
      </div>
    `;
    grid.appendChild(article);
  }
}

async function startGeneration(event) {
  event.preventDefault();

  const payload = collectPayload();
  if (!payload) return;

  closeMonitoring();
  resetRunUI();
  setFormBusy(true);
  showMessage('');
  setConnection('요청 중', 'live');
  document.getElementById('run-panel').hidden = false;
  document.getElementById('run-title').textContent = '작업 요청 중';
  document.getElementById('run-subtitle').textContent = '서버에 새 작업을 등록하고 있습니다.';

  try {
    const response = await fetch(`${API}/api/runs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    const data = await response.json();
    state.runId = data.run_id;
    addEventLog('작업 등록');
    setConnection('연결됨', 'live');
    startMonitoring();
  } catch (error) {
    setConnection('요청 실패', 'error');
    showMessage(`생성 요청 실패: ${error.message}`);
    setFormBusy(false);
    document.getElementById('run-panel').hidden = true;
  }
}

function collectPayload() {
  const values = {};
  for (const id of FIELD_IDS) {
    const input = document.getElementById(id);
    const value = input.value.trim();
    input.toggleAttribute('aria-invalid', !value);
    if (!value) {
      showMessage('모든 기본 작업 내용을 입력해 주세요.');
      input.focus();
      return null;
    }
    values[`${id}_ko`] = value;
  }
  return values;
}

function startMonitoring() {
  if (!state.runId) return;

  if ('EventSource' in window) {
    state.eventSource = new EventSource(`${API}/api/runs/${state.runId}/events`);
    state.eventSource.addEventListener('update', (event) => {
      const message = parseJSON(event.data);
      if (message) addEventLog(eventLabel(message));
      applyEventHint(message);
      refreshRun();

      if (message?.status === 'DONE' || message?.status === 'FAILED') {
        closeMonitoring();
        setFormBusy(false);
      }
    });
    state.eventSource.addEventListener('keepalive', () => {
      setConnection('연결됨', 'live');
    });
    state.eventSource.onerror = () => {
      setConnection('재연결 중', 'error');
    };
  }

  state.pollTimer = window.setInterval(refreshRun, 1500);
  refreshRun();
}

function closeMonitoring() {
  if (state.eventSource) {
    state.eventSource.close();
    state.eventSource = null;
  }
  if (state.pollTimer) {
    window.clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
}

async function refreshRun() {
  if (!state.runId || state.pollInFlight) return;
  state.pollInFlight = true;

  try {
    const response = await fetch(`${API}/api/runs/${state.runId}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    const data = await response.json();
    state.pollFailures = 0;
    renderRun(data);

    if (data.status === 'DONE' || data.status === 'FAILED') {
      closeMonitoring();
      setFormBusy(false);
    }
  } catch (error) {
    state.pollFailures += 1;
    setConnection(state.pollFailures >= 3 ? '상태 확인 실패' : '상태 재시도', state.pollFailures >= 3 ? 'error' : 'live');
  } finally {
    state.pollInFlight = false;
  }
}

function renderRun(data) {
  const counts = getCounts(data);
  const percent = Math.round((counts.done / TOTAL_UNITS) * 100);
  const stageText = data.status === 'DONE'
    ? '완료'
    : data.status === 'FAILED'
      ? '실패'
      : STAGE_LABELS[data.stage] || '진행 중';

  document.getElementById('run-title').textContent = data.story_title || stageText;
  document.getElementById('run-subtitle').textContent = data.error || subtitleFor(data, counts);
  document.getElementById('progress-percent').textContent = `${percent}%`;
  document.getElementById('progress-label').textContent = stageText;
  document.getElementById('progress-fill').style.width = `${percent}%`;
  document.getElementById('story-count').textContent = `${counts.story}/${STORY_UNITS}`;
  document.getElementById('audio-count').textContent = `${counts.audio}/${AUDIO_UNITS}`;
  document.getElementById('image-count').textContent = `${counts.image}/${IMAGE_UNITS}`;
  document.getElementById('done-count').textContent = data.status === 'DONE' ? '완료' : '대기';

  setConnection(data.status === 'FAILED' ? '실패' : '연결됨', data.status === 'FAILED' ? 'error' : 'live');
  updatePipeline(data, counts);
  renderCover(data);
  renderScenes(data.scenes || []);
}

function subtitleFor(data, counts) {
  if (counts.story < STORY_UNITS) return '워커에서 이야기 구조와 장면 정보를 생성하고 있습니다.';
  if (counts.image < IMAGE_UNITS && counts.audio < AUDIO_UNITS) return '음성과 이미지가 병렬로 생성되는 중입니다.';
  if (counts.image < IMAGE_UNITS) return '남은 이미지가 도착하는 순서대로 채워집니다.';
  if (counts.audio < AUDIO_UNITS) return '남은 음성이 도착하는 순서대로 연결됩니다.';
  return '모든 결과가 준비되었습니다.';
}

function getCounts(data) {
  const scenes = data.scenes || [];
  const story = (data.story_title ? 1 : 0) + scenes.filter((scene) => scene?.title).length;
  const image = (data.cover_image_url ? 1 : 0) + scenes.reduce((sum, scene) => {
    return sum + getSceneSlots(scene).filter(Boolean).length;
  }, 0);
  const audio = (data.cover_audio_url ? 1 : 0) + scenes.filter((scene) => scene?.audio_url).length;
  return {
    story,
    image,
    audio,
    done: story + image + audio,
  };
}

function updatePipeline(data, counts) {
  setStepState('story', counts.story >= STORY_UNITS, data.status !== 'DONE' && counts.story < STORY_UNITS);
  setStepState('audio', counts.audio >= AUDIO_UNITS, data.status !== 'DONE' && counts.story >= STORY_UNITS && counts.audio < AUDIO_UNITS);
  setStepState('image', counts.image >= IMAGE_UNITS, data.status !== 'DONE' && counts.story >= STORY_UNITS && counts.image < IMAGE_UNITS);
  setStepState('done', data.status === 'DONE', data.status !== 'DONE' && counts.done >= TOTAL_UNITS);
}

function setStepState(step, done, active) {
  const item = document.querySelector(`[data-step="${step}"]`);
  if (!item) return;
  item.classList.toggle('is-done', done);
  item.classList.toggle('is-active', !done && active);
}

function renderCover(data) {
  const heading = document.getElementById('cover-heading');
  const title = document.getElementById('cover-title');
  heading.textContent = data.cover_image_url ? '표지 준비 완료' : '표지 생성 중';
  title.textContent = data.story_title || '이야기 제목 대기';
  title.classList.toggle('placeholder-line', !data.story_title);

  updateImageSlot('cover-image-slot', 'cover-image', data.cover_image_url, '표지 이미지 대기');
  updateAudio('cover-audio-shell', 'cover-audio', 'cover-audio-status', data.cover_audio_url);
}

function renderScenes(scenes) {
  for (let sceneNo = 1; sceneNo <= SCENE_COUNT; sceneNo += 1) {
    const scene = scenes.find((item) => item.scene_no === sceneNo) || {};
    const hasMeta = Boolean(scene.title);
    const imageSlots = getSceneSlots(scene);
    const imageCount = imageSlots.filter(Boolean).length;
    const hasAudio = Boolean(scene.audio_url);

    setText(`scene-title-${sceneNo}`, scene.title || '이야기 생성 대기', !hasMeta);
    setText(`scene-narration-${sceneNo}`, scene.narration || '나레이션이 도착하면 표시됩니다.', !scene.narration);
    setText(`scene-dialogue-${sceneNo}`, scene.dialogue || '대사가 도착하면 표시됩니다.', !scene.dialogue);
    updateEmotion(`scene-narration-emotion-${sceneNo}`, '나레이션', scene.narration_emotion);
    updateEmotion(`scene-dialogue-emotion-${sceneNo}`, '대사', scene.dialogue_emotion);

    const pill = document.getElementById(`scene-pill-${sceneNo}`);
    const readyUnits = (hasMeta ? 1 : 0) + imageCount + (hasAudio ? 1 : 0);
    pill.textContent = readyUnits >= 5 ? '완료' : `${readyUnits}/5`;
    pill.classList.toggle('is-live', readyUnits > 0 && readyUnits < 5);

    for (let panel = 1; panel <= PANEL_COUNT; panel += 1) {
      updateImageSlot(
        `panel-slot-${sceneNo}-${panel}`,
        `panel-image-${sceneNo}-${panel}`,
        imageSlots[panel - 1],
        `패널 ${panel} 대기`,
      );
    }

    updateAudio(`scene-audio-shell-${sceneNo}`, `scene-audio-${sceneNo}`, `scene-audio-status-${sceneNo}`, scene.audio_url);
  }
}

function getSceneSlots(scene) {
  const slots = Array(PANEL_COUNT).fill('');
  const overflow = [];

  for (const url of scene?.image_urls || []) {
    const slot = parsePanelIndex(url);
    if (slot >= 1 && slot <= PANEL_COUNT) {
      slots[slot - 1] = url;
    } else {
      overflow.push(url);
    }
  }

  for (const url of overflow) {
    const emptyIndex = slots.findIndex((value) => !value);
    if (emptyIndex === -1) break;
    slots[emptyIndex] = url;
  }

  return slots;
}

function parsePanelIndex(url) {
  const match = /scene_\d+_img_(\d+)\.png/i.exec(url || '');
  return match ? Number(match[1]) : 0;
}

function updateImageSlot(slotId, imageId, rawUrl, placeholderText) {
  const slot = document.getElementById(slotId);
  const image = document.getElementById(imageId);
  const placeholder = slot?.querySelector('.slot-placeholder p');
  if (!slot || !image) return;

  if (placeholder) placeholder.textContent = placeholderText;

  if (!rawUrl) {
    slot.classList.remove('is-ready');
    image.hidden = true;
    image.removeAttribute('src');
    image.dataset.rawUrl = '';
    return;
  }

  if (image.dataset.rawUrl === rawUrl) return;

  slot.classList.remove('is-ready');
  image.hidden = true;
  image.dataset.rawUrl = rawUrl;
  image.onload = () => {
    slot.classList.add('is-ready');
    image.hidden = false;
  };
  image.onerror = () => {
    slot.classList.remove('is-ready');
    image.hidden = true;
  };
  image.src = withCache(rawUrl);
}

function updateAudio(shellId, audioId, statusId, rawUrl) {
  const shell = document.getElementById(shellId);
  const audio = document.getElementById(audioId);
  const status = document.getElementById(statusId);
  if (!shell || !audio || !status) return;

  if (!rawUrl) {
    shell.classList.remove('is-ready');
    audio.hidden = true;
    audio.removeAttribute('src');
    audio.dataset.rawUrl = '';
    status.textContent = '생성 대기';
    return;
  }

  shell.classList.add('is-ready');
  status.textContent = '재생 가능';
  if (audio.dataset.rawUrl === rawUrl) return;

  audio.dataset.rawUrl = rawUrl;
  audio.src = withCache(rawUrl);
  audio.hidden = false;
  audio.load();
}

function updateEmotion(id, prefix, emotion) {
  const badge = document.getElementById(id);
  if (!badge) return;
  badge.textContent = emotion ? `${prefix}: ${EMOTION_LABELS[emotion] || emotion}` : `${prefix} 감정 대기`;
  badge.dataset.emotion = emotion || '';
}

function setText(id, text, placeholder = false) {
  const element = document.getElementById(id);
  if (!element) return;
  element.textContent = text;
  element.classList.toggle('placeholder-line', placeholder);
}

function withCache(path) {
  const absolute = path.startsWith('http') ? path : `${API}${path}`;
  const separator = absolute.includes('?') ? '&' : '?';
  return `${absolute}${separator}t=${Date.now()}`;
}

async function toggleRecording(button) {
  const field = button.dataset.field;

  if (state.mediaRecorder?.state === 'recording') {
    state.mediaRecorder.stop();
    return;
  }

  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
    setFieldStatus(field, '이 브라우저에서는 녹음을 사용할 수 없습니다.');
    return;
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mimeType = getSupportedMimeType();
    state.audioChunks = [];
    state.activeStream = stream;
    state.activeVoiceButton = button;
    state.mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);

    state.mediaRecorder.addEventListener('dataavailable', (event) => {
      if (event.data.size) state.audioChunks.push(event.data);
    });
    state.mediaRecorder.addEventListener('stop', () => finishRecording(field, mimeType));
    state.mediaRecorder.start();

    button.classList.add('is-recording');
    button.textContent = '정지';
    setFieldStatus(field, '녹음 중');
  } catch (error) {
    setFieldStatus(field, `녹음 실패: ${error.message}`);
  }
}

async function finishRecording(field, mimeType) {
  const button = state.activeVoiceButton;
  if (button) {
    button.classList.remove('is-recording');
    button.textContent = '녹음';
  }
  if (state.activeStream) {
    state.activeStream.getTracks().forEach((track) => track.stop());
  }

  const blob = new Blob(state.audioChunks, { type: mimeType || 'audio/webm' });
  state.mediaRecorder = null;
  state.audioChunks = [];
  state.activeStream = null;
  state.activeVoiceButton = null;

  if (!blob.size) {
    setFieldStatus(field, '녹음된 음성이 없습니다.');
    return;
  }

  setFieldStatus(field, '음성 인식 중');
  const extension = mimeType.includes('mp4') ? 'mp4' : mimeType.includes('wav') ? 'wav' : 'webm';
  const form = new FormData();
  form.append('audio_file', blob, `recording.${extension}`);
  form.append('field_type', field);

  try {
    const response = await fetch(`${API}/api/stt/field`, { method: 'POST', body: form });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    const text = data.parsed_value || data.stt_text || '';
    document.getElementById(field).value = text;
    setFieldStatus(field, text ? `인식 완료 ${Math.round((data.confidence || 0) * 100)}%` : '인식 결과 없음');
  } catch (error) {
    setFieldStatus(field, `인식 실패: ${error.message}`);
  }
}

function getSupportedMimeType() {
  return ['audio/webm', 'audio/mp4', 'audio/wav'].find((type) => MediaRecorder.isTypeSupported(type)) || '';
}

function setFieldStatus(field, message) {
  const element = document.getElementById(`${field}-status`);
  if (element) element.textContent = message;
}

function setFormBusy(isBusy) {
  document.getElementById('start-button').disabled = isBusy;
  document.querySelectorAll('.voice-button').forEach((button) => {
    button.disabled = isBusy;
  });
}

function setConnection(text, mode = '') {
  const pill = document.getElementById('connection-status');
  pill.textContent = text;
  pill.classList.toggle('is-live', mode === 'live');
  pill.classList.toggle('is-error', mode === 'error');
}

function showMessage(message) {
  document.getElementById('form-message').textContent = message;
}

function addEventLog(label) {
  if (!label) return;
  const log = document.getElementById('event-log');
  const item = document.createElement('li');
  item.textContent = label;
  log.prepend(item);
  while (log.children.length > 8) {
    log.lastElementChild.remove();
  }
}

function eventLabel(message) {
  if (message.status === 'FAILED') return '작업 실패';
  if (message.status === 'DONE') return '작업 완료';
  if (message.cover_image) return '표지 이미지 도착';
  if (message.cover_audio) return '표지 음성 도착';
  if (message.image && message.scene_no) return `장면 ${message.scene_no} 이미지 도착`;
  if (message.audio && message.scene_no) return `장면 ${message.scene_no} 음성 도착`;
  if (message.scene_no) return `장면 ${message.scene_no} 갱신`;
  return STAGE_LABELS[message.stage] || '상태 갱신';
}

function applyEventHint(message) {
  if (!message || !state.runId) return;

  const coverImageUrl = message.cover_image_url || imageUrlFromMessage(message.cover_image);
  if (coverImageUrl) {
    document.getElementById('cover-heading').textContent = '표지 준비 완료';
    updateImageSlot('cover-image-slot', 'cover-image', coverImageUrl, '표지 이미지 대기');
  }

  const coverAudioUrl = message.cover_audio_url || audioUrlFromMessage(message.cover_audio);
  if (coverAudioUrl) {
    updateAudio('cover-audio-shell', 'cover-audio', 'cover-audio-status', coverAudioUrl);
  }

  if (!message.scene_no) return;

  const sceneNo = Number(message.scene_no);
  const sceneImageUrl = message.image_url || imageUrlFromMessage(message.image);
  if (sceneImageUrl) {
    const panel = parsePanelIndex(sceneImageUrl) || 1;
    updateImageSlot(
      `panel-slot-${sceneNo}-${panel}`,
      `panel-image-${sceneNo}-${panel}`,
      sceneImageUrl,
      `패널 ${panel} 대기`,
    );
  }

  const sceneAudioUrl = message.audio_url || audioUrlFromMessage(message.audio);
  if (sceneAudioUrl) {
    updateAudio(`scene-audio-shell-${sceneNo}`, `scene-audio-${sceneNo}`, `scene-audio-status-${sceneNo}`, sceneAudioUrl);
  }
}

function imageUrlFromMessage(filename) {
  if (!filename) return '';
  if (filename.startsWith('http') || filename.startsWith('/api/')) return filename;
  return `/api/runs/${state.runId}/images/${filename}`;
}

function audioUrlFromMessage(filename) {
  if (!filename) return '';
  if (filename.startsWith('http') || filename.startsWith('/api/')) return filename;
  return `/api/runs/${state.runId}/audio/${filename}`;
}

function resetAll() {
  closeMonitoring();
  state.runId = '';
  FIELD_IDS.forEach((id) => {
    document.getElementById(id).value = '';
    setFieldStatus(id, '');
  });
  resetRunUI();
  document.getElementById('run-panel').hidden = true;
  setFormBusy(false);
  showMessage('');
  setConnection('대기');
}

function resetRunUI() {
  document.getElementById('run-title').textContent = '작업 준비 중';
  document.getElementById('run-subtitle').textContent = '요청을 보내면 생성된 결과가 도착하는 순서대로 표시됩니다.';
  document.getElementById('progress-percent').textContent = '0%';
  document.getElementById('progress-label').textContent = '대기';
  document.getElementById('progress-fill').style.width = '0%';
  document.getElementById('story-count').textContent = `0/${STORY_UNITS}`;
  document.getElementById('audio-count').textContent = `0/${AUDIO_UNITS}`;
  document.getElementById('image-count').textContent = `0/${IMAGE_UNITS}`;
  document.getElementById('done-count').textContent = '대기';
  document.getElementById('event-log').textContent = '';
  document.getElementById('cover-heading').textContent = '표지 생성 중';
  document.getElementById('cover-title').textContent = '이야기 제목 대기';
  document.getElementById('cover-title').classList.add('placeholder-line');
  updateImageSlot('cover-image-slot', 'cover-image', '', '표지 이미지 대기');
  updateAudio('cover-audio-shell', 'cover-audio', 'cover-audio-status', '');

  for (let sceneNo = 1; sceneNo <= SCENE_COUNT; sceneNo += 1) {
    setText(`scene-title-${sceneNo}`, '이야기 생성 대기', true);
    setText(`scene-narration-${sceneNo}`, '나레이션이 도착하면 표시됩니다.', true);
    setText(`scene-dialogue-${sceneNo}`, '대사가 도착하면 표시됩니다.', true);
    updateEmotion(`scene-narration-emotion-${sceneNo}`, '나레이션', '');
    updateEmotion(`scene-dialogue-emotion-${sceneNo}`, '대사', '');
    document.getElementById(`scene-pill-${sceneNo}`).textContent = '대기';
    for (let panel = 1; panel <= PANEL_COUNT; panel += 1) {
      updateImageSlot(`panel-slot-${sceneNo}-${panel}`, `panel-image-${sceneNo}-${panel}`, '', `패널 ${panel} 대기`);
    }
    updateAudio(`scene-audio-shell-${sceneNo}`, `scene-audio-${sceneNo}`, `scene-audio-status-${sceneNo}`, '');
  }

  document.querySelectorAll('.pipeline li').forEach((item) => {
    item.classList.remove('is-active', 'is-done');
  });
}

function parseJSON(value) {
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}
