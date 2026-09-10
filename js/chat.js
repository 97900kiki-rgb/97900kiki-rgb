/* ============================================================
   AI CODI - Gemini 채팅
   - 브라우저에서 Google Gemini API로 직접 연결되는 스타일 상담 챗
   - API 키는 localStorage에만 저장 (서버 전송 없음)
   ============================================================ */

(function () {
  'use strict';

  const KEY_STORAGE = 'aicodi_gemini_api_key';
  const MODEL_STORAGE = 'aicodi_gemini_model';

  const SYSTEM_PROMPT =
    '당신은 "AI CODI"라는 서비스의 친절하고 감각적인 AI 패션 스타일리스트입니다. ' +
    '사용자의 날씨, 일정, 기분, 퍼스널 컬러, 체형, 옷장 상황 등을 바탕으로 실용적이고 구체적인 코디를 제안하세요. ' +
    '답변은 한국어로, 친근하지만 전문적인 톤으로, 너무 길지 않게(4~8문장 또는 짧은 목록) 작성하세요. ' +
    '필요하면 아이템 조합, 색상 조합, 스타일링 팁을 구체적으로 제시하세요.';

  let history = []; // { role: 'user' | 'model', parts: [{ text }] }
  let isSending = false;

  // ---------- DOM refs ----------
  const keySetup = document.getElementById('key-setup');
  const chatUi = document.getElementById('chat-ui');
  const apiKeyInput = document.getElementById('api-key-input');
  const toggleKeyBtn = document.getElementById('toggle-key-visibility');
  const saveKeyBtn = document.getElementById('save-key-btn');
  const keyError = document.getElementById('key-error');
  const resetKeyBtn = document.getElementById('reset-key-btn');
  const modelSelect = document.getElementById('model-select');
  const chatLog = document.getElementById('chat-log');
  const chatTextarea = document.getElementById('chat-textarea');
  const chatSendBtn = document.getElementById('chat-send-btn');
  const suggestionChips = document.getElementById('suggestion-chips');

  // ---------- Helpers ----------
  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function formatBotText(text) {
    // 굵게(**text**)만 가볍게 처리하고 나머지는 pre-wrap으로 줄바꿈 유지
    return escapeHtml(text).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  }

  function scrollToBottom() {
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  function getApiKey() {
    return localStorage.getItem(KEY_STORAGE) || '';
  }

  function getModel() {
    return localStorage.getItem(MODEL_STORAGE) || 'gemini-2.5-flash';
  }

  // ---------- Message rendering ----------
  function appendUserMessage(text) {
    const row = document.createElement('div');
    row.className = 'msg-row user';
    row.innerHTML =
      '<div class="msg-bubble">' + escapeHtml(text) + '</div>' +
      '<div class="msg-avatar user"><i class="fa-solid fa-user"></i></div>';
    chatLog.appendChild(row);
    scrollToBottom();
  }

  function appendTypingIndicator() {
    const row = document.createElement('div');
    row.className = 'msg-row bot';
    row.dataset.typing = 'true';
    row.innerHTML =
      '<div class="msg-avatar bot"><i class="fa-solid fa-wand-magic-sparkles"></i></div>' +
      '<div class="msg-bubble"><span class="typing-dots"><span></span><span></span><span></span></span></div>';
    chatLog.appendChild(row);
    scrollToBottom();
    return row;
  }

  function replaceWithBotMessage(row, text, isError) {
    row.innerHTML =
      '<div class="msg-avatar bot"><i class="fa-solid fa-wand-magic-sparkles"></i></div>' +
      '<div class="msg-bubble' + (isError ? ' error' : '') + '">' + (isError ? escapeHtml(text) : formatBotText(text)) + '</div>';
    scrollToBottom();
  }

  function appendWelcomeMessage() {
    const row = document.createElement('div');
    row.className = 'msg-row bot';
    row.innerHTML =
      '<div class="msg-avatar bot"><i class="fa-solid fa-wand-magic-sparkles"></i></div>' +
      '<div class="msg-bubble">안녕하세요! 저는 AI CODI의 스타일리스트예요 ✨<br>오늘 날씨나 일정, 어떤 옷이 있는지 알려주시면 바로 코디를 제안해드릴게요.</div>';
    chatLog.appendChild(row);
  }

  // ---------- Gemini API ----------
  async function callGemini(userText) {
    const apiKey = getApiKey();
    const model = getModel();
    const url = 'https://generativelanguage.googleapis.com/v1beta/models/' + encodeURIComponent(model) + ':generateContent?key=' + encodeURIComponent(apiKey);

    history.push({ role: 'user', parts: [{ text: userText }] });

    const body = {
      contents: history,
      systemInstruction: { parts: [{ text: SYSTEM_PROMPT }] },
      generationConfig: { temperature: 0.9, maxOutputTokens: 800 }
    };

    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });

    if (!res.ok) {
      let message = 'Gemini 요청이 실패했습니다 (HTTP ' + res.status + ').';
      try {
        const errJson = await res.json();
        if (errJson && errJson.error && errJson.error.message) {
          message = errJson.error.message;
        }
      } catch (e) { /* ignore parse failure */ }
      history.pop();
      throw new Error(message);
    }

    const data = await res.json();
    const candidate = data.candidates && data.candidates[0];
    const text = candidate && candidate.content && candidate.content.parts
      ? candidate.content.parts.map(function (p) { return p.text || ''; }).join('')
      : '';

    if (!text) {
      history.pop();
      const finishReason = candidate && candidate.finishReason;
      throw new Error(finishReason ? '응답이 차단되었습니다 (' + finishReason + ').' : '빈 응답을 받았습니다.');
    }

    history.push({ role: 'model', parts: [{ text: text }] });
    return text;
  }

  async function sendMessage(text) {
    const trimmed = (text || '').trim();
    if (!trimmed || isSending) return;

    isSending = true;
    chatSendBtn.disabled = true;
    appendUserMessage(trimmed);
    chatTextarea.value = '';
    chatTextarea.style.height = 'auto';

    const typingRow = appendTypingIndicator();

    try {
      const reply = await callGemini(trimmed);
      replaceWithBotMessage(typingRow, reply, false);
    } catch (err) {
      console.error('Gemini 호출 실패:', err);
      replaceWithBotMessage(typingRow, '⚠️ ' + (err.message || '알 수 없는 오류가 발생했습니다.') + ' API 키와 모델을 확인해주세요.', true);
    } finally {
      isSending = false;
      chatSendBtn.disabled = false;
      chatTextarea.focus();
    }
  }

  // ---------- API key setup ----------
  function showChatUi() {
    keySetup.classList.add('hidden');
    chatUi.classList.remove('hidden');
    suggestionChips.classList.remove('hidden');
    if (!chatLog.children.length) appendWelcomeMessage();
  }

  function showKeySetup() {
    chatUi.classList.add('hidden');
    suggestionChips.classList.add('hidden');
    keySetup.classList.remove('hidden');
    apiKeyInput.value = '';
    apiKeyInput.focus();
  }

  if (toggleKeyBtn) {
    toggleKeyBtn.addEventListener('click', function () {
      const isPassword = apiKeyInput.type === 'password';
      apiKeyInput.type = isPassword ? 'text' : 'password';
      toggleKeyBtn.innerHTML = isPassword ? '<i class="fa-solid fa-eye-slash"></i>' : '<i class="fa-solid fa-eye"></i>';
    });
  }

  if (saveKeyBtn) {
    saveKeyBtn.addEventListener('click', function () {
      const key = apiKeyInput.value.trim();
      if (!key) {
        keyError.classList.remove('hidden');
        apiKeyInput.focus();
        return;
      }
      keyError.classList.add('hidden');
      localStorage.setItem(KEY_STORAGE, key);
      history = [];
      chatLog.innerHTML = '';
      showChatUi();
    });
  }

  if (apiKeyInput) {
    apiKeyInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') saveKeyBtn.click();
    });
  }

  if (resetKeyBtn) {
    resetKeyBtn.addEventListener('click', function () {
      if (!confirm('저장된 API 키를 삭제하고 대화를 초기화할까요?')) return;
      localStorage.removeItem(KEY_STORAGE);
      history = [];
      chatLog.innerHTML = '';
      showKeySetup();
    });
  }

  // ---------- Model select ----------
  if (modelSelect) {
    modelSelect.value = getModel();
    modelSelect.addEventListener('change', function () {
      localStorage.setItem(MODEL_STORAGE, modelSelect.value);
    });
  }

  // ---------- Chat input ----------
  if (chatTextarea) {
    chatTextarea.addEventListener('input', function () {
      chatTextarea.style.height = 'auto';
      chatTextarea.style.height = Math.min(chatTextarea.scrollHeight, 128) + 'px';
    });
    chatTextarea.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage(chatTextarea.value);
      }
    });
  }

  if (chatSendBtn) {
    chatSendBtn.addEventListener('click', function () {
      sendMessage(chatTextarea.value);
    });
  }

  if (suggestionChips) {
    suggestionChips.addEventListener('click', function (e) {
      const chip = e.target.closest('.suggestion-chip');
      if (!chip) return;
      sendMessage(chip.dataset.q);
    });
  }

  // ---------- Init ----------
  if (getApiKey()) {
    showChatUi();
  } else {
    showKeySetup();
  }
})();
