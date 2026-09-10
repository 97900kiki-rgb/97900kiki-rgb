/* 웰니스 관상 '아솔' — 화면 동작
 *
 * 흐름 하나로 이어진다.
 *   카메라 → (4초 머무르면 저절로) 찍기 → 살펴보기 → 관상 → 자세히·메일
 *
 * 상태는 이 파일이 쥔다. 서버에는 사진 한 장씩 보내고 결과만 받아 오므로,
 * 연결이 잠깐 끊겨도 브라우저가 들고 있던 것으로 이어 갈 수 있다.
 */
'use strict';

const $ = (id) => document.getElementById(id);
const S = {
  image: null,        // 지금 다루는 사진 (data URI)
  person: null,       // 알아본 분
  basic: null,        // 성별·나이·직업
  report: '',         // 감정서 본문
  detailed: false,    // 전체판인가
  model: '',
  stars: 0,
  busy: false,
};

/* ── 켜 둔 뜻은 주소줄에 적어 둔다 ────────────────────────────────
   새로고침해도, 서버를 다시 올려도 살아남는다. 링크로 건네줄 수도 있다. */
const qp = new URLSearchParams(location.search);
const want = {
  auto: qp.get('auto') === '1',
  rec: qp.get('rec') === '1',
};
function saveWant() {
  const u = new URL(location.href);
  u.searchParams.set('auto', want.auto ? '1' : '0');
  u.searchParams.set('rec', want.rec ? '1' : '0');
  history.replaceState(null, '', u);
}
$('swAuto').checked = want.auto;
$('swRec').checked = want.rec;
$('swAuto').onchange = (e) => { want.auto = e.target.checked; saveWant(); if (want.auto) startCam(); };
$('swRec').onchange = (e) => { want.rec = e.target.checked; saveWant(); if (S.image) prepare(); };

/* ── 모달 ──────────────────────────────────────────────────── */
function modal(title, html) {
  $('dlgTitle').textContent = title;
  $('dlgBody').innerHTML = html;
  $('dlg').showModal();
}
$('dlgClose').onclick = () => $('dlg').close();

$('btnAbout').onclick = () => modal('🧙‍♂️ 웰니스 관상 ‘아솔’', `
<p><b>조선 팔도를 떠돌며 수많은 관상을 봐온 아솔이, 얼굴을 기억하고 안부를 묻소.</b></p>
<h4>🌱 즐기면서 남기는 기록</h4>
<p>재미로 보는 관상이면서, 스스로 남겨 두는 얼굴 기록입니다.
<b>틈틈이 셀카 찍듯 남겨 보세요.</b> 다시 오시면 아솔이 알아보고 그동안의 변화를 함께 살펴 드립니다.</p>
<h4>🩺 진단하지 않습니다</h4>
<p>건강 상태를 진단하거나 병을 찾아 드리지 않으며, 의학적 판단을 대신하지 않습니다.
몸이 편찮으시면 의료기관을 찾으십시오.</p>
<h4>⏱️ 자동으로 찍기</h4>
<p>카메라를 보고 있다가 얼굴이 4초간 머무르면 스스로 담고 이어서 관상까지 봅니다.
<b>영상은 이 기기 안에서만 봅니다.</b> 담긴 사진 한 장만 아솔에게 전해집니다.</p>
<h4>🔁 다시 온 사람 알아보기</h4>
<p>얼굴로 전에 오신 분인지 살펴봅니다. 켜 두신 뜻은 주소줄에 적히므로 새로고침해도 남습니다.</p>
<hr><p style="color:#8f807c;font-size:13px">🧙‍♂️ 웰니스 관상 아솔 © 2026 · Powered by 사내 LLM 서버</p>`);

let NOTICE = null;
fetch('/api/notice').then(r => r.json()).then(j => { NOTICE = j; }).catch(() => {});
const md = (t) => (t || '').replace(/&/g, '&amp;').replace(/</g, '&lt;')
  .replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
  .replace(/^\s*[-·]\s?/gm, '• ').replace(/\n/g, '<br>');
$('lnkNotice').onclick = (e) => { e.preventDefault(); modal('개인정보 수집·이용 안내', md(NOTICE && NOTICE.notice)); };
$('lnkFaceNotice').onclick = (e) => { e.preventDefault(); modal('기록으로 남기기 (선택)', md(NOTICE && NOTICE.face)); };

$('btnCopyUrl').onclick = () => {
  const el = $('camUrl'); el.select();
  navigator.clipboard.writeText(el.value).then(
    () => { $('btnCopyUrl').textContent = '복사됨'; setTimeout(() => $('btnCopyUrl').textContent = '복사', 1500); },
    () => document.execCommand('copy'));
};

/* ── 나이 고르개 ───────────────────────────────────────────── */
(function fillDec() {
  const sel = $('dec');
  sel.innerHTML = '<option value="">🤖 아솔이 알아서 보겠소</option>' +
    [10, 20, 30, 40, 50, 60, 70, 80].map(d => `<option>${d}대</option>`).join('') +
    '<option>90대 이상</option>';
  sel.onchange = () => { $('part').disabled = !sel.value || sel.value === '90대 이상'; };
  sel.onchange();
})();
function toldAge() {
  const d = $('dec').value;
  if (!d) return '';
  if (d === '90대 이상') return d;
  return d + ' ' + $('part').value;
}

/* ── 카메라 ────────────────────────────────────────────────
   영상과 얼굴 찾기는 **브라우저 안에서만** 돈다. 담긴 사진 한 장만 서버로 간다.
   거울로 뒤집지 않는다 — 관상은 좌우를 달리 보므로 실제 방향이어야 하고,
   보여 준 것과 찍힌 것이 달라 "좌우가 바뀌었다"는 일도 없어야 한다. */
const v = $('v'), ov = $('ov'), g = ov.getContext('2d');
let stream = null, detector = null, holdFrom = 0, last = null, shooting = false;
// 2초는 자세를 잡기 전에 찍혀 버렸다. 4초면 안경을 고쳐 쓰고 턱을 당길 참이 된다.
const HOLD_MS = 4000;
const say = (m, s) => { $('camMsg').textContent = m; $('camSub').textContent = s || ''; };

(async function loadDetector() {
  try {
    const vision = await import('https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14');
    const files = await vision.FilesetResolver.forVisionTasks(
      'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm');
    detector = await vision.FaceDetector.createFromOptions(files, {
      baseOptions: {
        modelAssetPath: 'https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite',
        delegate: 'GPU',
      },
      runningMode: 'VIDEO', minDetectionConfidence: 0.5,
    });
  } catch (e) {
    console.warn('[cam] 자동 인식 준비 실패', e);
  }
  if (want.auto) startCam();
})();

async function startCam() {
  if (stream) return;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 960 } },
      audio: false,
    });
    v.srcObject = stream; await v.play();
    ov.width = v.videoWidth; ov.height = v.videoHeight;
    say(detector ? '얼굴을 찾는 중이오…' : '카메라가 켜졌소.',
        detector ? '' : '아래 [지금 찍기] 로 담으시오.');
    loop();
  } catch (e) {
    say('카메라를 열지 못했소.', String(e.name || e));
  }
}
function stopCam() {
  if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; }
}

function steady(b) {
  if (!last) return false;
  return Math.abs(b.cx - last.cx) < b.w * .16 &&
         Math.abs(b.cy - last.cy) < b.w * .16 &&
         Math.abs(b.w - last.w) < b.w * .22;
}

function loop() {
  if (!stream) return;
  requestAnimationFrame(loop);
  if (v.readyState < 2) return;
  let b = null;
  if (detector) {
    try {
      const r = detector.detectForVideo(v, performance.now());
      const d = r && r.detections && r.detections[0];
      if (d) {
        const x = d.boundingBox;
        b = { cx: x.originX + x.width / 2, cy: x.originY + x.height / 2, w: x.width, h: x.height };
      }
    } catch (e) { /* 한 프레임쯤 놓쳐도 그만 */ }
  }
  g.clearRect(0, 0, ov.width, ov.height);
  if (!want.auto || !detector) { $('hold').style.width = '0%'; return; }

  if (!b) { holdFrom = 0; last = null; $('hold').style.width = '0%'; say('얼굴이 보이지 않소.', '화면 안으로 들어오시오.'); return; }
  const small = b.w < ov.width * .20;
  g.lineWidth = Math.max(2, ov.width * .004);
  g.strokeStyle = small ? 'rgba(200,120,60,.9)' : 'rgba(120,220,160,.95)';
  g.strokeRect(b.cx - b.w / 2, b.cy - b.h / 2, b.w, b.h);
  if (small) { holdFrom = 0; last = b; $('hold').style.width = '0%'; say('조금 더 가까이 오시오.', '얼굴이 화면을 넉넉히 채워야 하오.'); return; }

  if (steady(b)) {
    if (!holdFrom) holdFrom = performance.now();
    const held = performance.now() - holdFrom;
    $('hold').style.width = Math.min(100, held / HOLD_MS * 100) + '%';
    const left = Math.max(0, (HOLD_MS - held) / 1000);
    say('가만히 계시오…', left > .1 ? left.toFixed(1) + '초' : '찰칵!');
    if (held >= HOLD_MS) shoot();
  } else {
    holdFrom = 0; $('hold').style.width = '0%';
    say('자세를 잡으시오.', '정면을 바라보고 잠시 멈추면 저절로 찍히오.');
  }
  last = b;
}

function shoot() {
  if (shooting || !stream) return;
  shooting = true;
  const c = document.createElement('canvas');
  c.width = v.videoWidth; c.height = v.videoHeight;
  c.getContext('2d').drawImage(v, 0, 0, c.width, c.height);
  S.image = c.toDataURL('image/jpeg', .92);
  stopCam(); shooting = false;
  $('camCard').classList.add('hidden');
  prepare();
}
$('btnShoot').onclick = shoot;

/* 앨범에서 고르기 */
$('btnPick').onclick = () => $('file').click();
$('file').onchange = (e) => {
  const f = e.target.files && e.target.files[0];
  if (!f) return;
  const rd = new FileReader();
  rd.onload = () => { S.image = rd.result; stopCam(); $('camCard').classList.add('hidden'); prepare(); };
  rd.readAsDataURL(f);
};

/* ── 사진을 서버에 보내 살펴본다 ───────────────────────────── */
async function prepare() {
  if (!S.image) return;
  $('shotCard').classList.remove('hidden');
  $('faceNote').innerHTML = '<div class="hint">아솔이 살펴보는 중이오…</div>';
  paint();
  try {
    const r = await fetch('/api/prepare', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image: S.image, recognize: want.rec }),
    });
    const j = await r.json();
    if (j.error) { $('faceNote').innerHTML = `<div class="note">${j.error}</div>`; return; }
    $('imgOval').src = j.oval; $('imgMesh').src = j.mesh;
    let n = '';
    if (!j.found) n = `<div class="note">얼굴을 찾지 못해 가운데를 잘랐소. 정면으로, 밝은 곳에서,
      얼굴이 화면에 크게 들어오도록 다시 담아 주시오.</div>`;
    else if (!j.facing_ok) n = `<div class="note">🙂 ${md(j.note)}<br>관상은 좌우 균형을 보는 것이라
      정면일수록 잘 맞소. 그대로 보셔도 되오.</div>`;
    else if (j.note) n = `<div class="hint">🙂 ${md(j.note)}</div>`;
    $('faceNote').innerHTML = n;
    S.person = j.person || null;
    S.candidate = j.candidate || null;
    $('ageCard').classList.remove('hidden');

    // ★ 낯이 아리송하면 **관상을 보기 전에** 결판을 낸다.
    //   누구인지에 따라 지난 이력을 감정서에 넣을지가 갈리므로, 먼저 정해야 한다.
    //   흐름을 멈추는 결정이라 화면 가운데 모달로 여쭙는다.
    const amb = (S.person && !S.person.sure && S.person.has_secret && !S.person.asked_out)
      ? S.person
      : (S.candidate && !S.candidate.asked_out ? S.candidate : null);
    if (amb && !amb.masked && S.person) amb.masked = S.person.masked;
    if (amb) { askWhoAreYou(amb); return; }

    showGreet();
    prefill();
    paint();
    read(false);           // 맛보기를 곧바로 시작한다 — 누를 일을 하나 줄인다
  } catch (e) {
    $('faceNote').innerHTML = `<div class="note">살펴보다 탈이 났소: ${e}</div>`;
    paint();
  }
}

function showGreet() {
  const p = S.person, box = $('greet');
  if (!p) {
    // 얼굴로는 못 알아봤으나 닮은 분이 있으면, **둘만 아는 이야기**로
    // 여쭤 볼 길을 연다. 누구인지는 아직 알려 주지 않는다(이름을 가린다).
    const c = S.candidate;
    if (c && !c.asked_out) {
      box.innerHTML = `<div class="note">🤔 얼굴만으로는 알아보지 못하였소.
        <b>${c.masked}</b>님과 닮으셨는데, 맞다면 우리 둘만 아는 이야기로 알아보겠소.
        <div style="margin-top:8px"><button class="sm" id="askme">🙋 나를 알아봐 주오</button></div></div>`;
      box.querySelector('#askme').onclick = startVerify;
    } else if (c) {
      box.innerHTML = `<div class="hint">얼굴만으로는 알아보지 못하였소.
        오늘은 처음 뵙는 걸로 하겠소.</div>`;
    } else {
      box.classList.add('hidden'); box.innerHTML = ''; return;
    }
    box.classList.remove('hidden');
    return;
  }
  const when = !p.days ? '오늘도 오셨구려' : p.days === 1 ? '어제 뵙고 또 오셨구려' : `${p.days}일 만이오`;
  if (!(p.sure || p.confirmed)) {
    box.innerHTML = `<div class="hint">얼굴만으로는 알아보지 못하였소.
      오늘은 처음 뵙는 걸로 하겠소.</div>`;
    box.classList.remove('hidden');
    return;
  }
  {
    let h = `<div class="good">🙌 <b>${p.name}님</b>, ${when}. 이번이 <b>${(p.visits || 0) + 1}번째</b> 걸음이오.`;
    if (p.history && p.history.length) {
      h += '<div style="margin-top:6px;font-size:13.5px;color:#5d4f4f">';
      p.history.forEach(x => {
        let l = '· ' + x.ts;
        if (x.mood) l += ' — ' + x.mood;
        if (x.condition) l += ' (기운 ' + x.condition + ')';
        h += l + '<br>';
      });
      h += '</div>';
    }
    box.innerHTML = h + '</div>';
  }
  box.classList.remove('hidden');
}

/* ── 둘만 아는 이야기로 본인 확인 ────────────────────────────────
   장군신이 이야기를 보고 예/아니오 질문 셋을 짓는다. 맞는 질문과 일부러
   틀린 질문이 섞여 있어, 아무 말에나 "예" 하면 걸러진다.
   정답은 서버만 알고, 화면에는 질문만 온다. */
/* 낯이 아리송할 때의 문 —
 *
 * ★ **누구와 닮았는지 이름을 내보이지 않는다.** 조금이라도 비추면(황*하, **하)
 *   곁에 선 낯선 사람에게 후보를 좁혀 주는 셈이다. 그리고 알려 줄 까닭도 없다 —
 *   진짜 본인은 제 이름을 들어야 답할 수 있는 것이 아니다. **질문 자체가 시험**이다.
 * ★ 여기서 정해야 지난 이력을 감정서에 넣을지가 갈리므로, 관상보다 먼저 묻는다.
 */
function askWhoAreYou(cand) {
  S.candidate = { id: cand.id };
  const who = cand.masked ? `<b>${cand.masked}</b>님` : '전에 뵌 분';
  modal('🤔 낯이 익소만', `
    <p>얼굴만으로는 확신이 서지 않소. <b>내가 알고 있는 ${who}과 닮으셨는데…</b></p>
    <p>맞으시다면 <b>우리 둘만 아는 이야기</b>로 알아보겠소.
       처음이시라면 그대로 보아 드리리다.</p>
    <div style="display:flex;gap:8px;margin-top:16px">
      <button class="pri" style="flex:1.4" id="askme">🙋 나를 알아봐 주오</button>
      <button style="flex:1" id="skipme">처음이오</button>
    </div>`);
  $('dlgBody').querySelector('#askme').onclick = startVerify;
  $('dlgBody').querySelector('#skipme').onclick = () => {
    S.person = null; S.candidate = null;
    $('dlg').close(); showGreet(); prefill(); paint(); read(false);
  };
}

async function startVerify() {
  const c = S.candidate; if (!c) return;
  modal('🤫 둘만 아는 이야기', '<p>장군신이 물을 말을 고르는 중이오…</p>');
  try {
    const r = await fetch('/api/verify/start', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ person_id: c.id, image: S.image }),
    });
    const j = await r.json();
    if (!j.ok) { modal('🤫 둘만 아는 이야기', `<p>${j.msg}</p>`); return; }
    askQuestions(j.token, j.questions);
  } catch (e) {
    modal('🤫 둘만 아는 이야기', `<p>여쭙지 못했소: ${e}</p>`);
  }
}

function askQuestions(token, qs) {
  const answers = [];
  const step = () => {
    const i = answers.length;
    if (i >= qs.length) return sendAnswers(token, answers);
    $('dlgTitle').textContent = `🤫 둘만 아는 이야기 (${i + 1}/${qs.length})`;
    $('dlgBody').innerHTML =
      `<p style="font-size:16px;line-height:1.9"><b>${qs[i]}</b></p>
       <div style="display:flex;gap:8px;margin-top:14px">
         <button class="pri" style="flex:1" id="yy">예</button>
         <button style="flex:1" id="nn">아니오</button></div>
       <div class="hint" style="margin-top:10px">셋 다 맞히셔야 하오.</div>`;
    $('dlgBody').querySelector('#yy').onclick = () => { answers.push(true); step(); };
    $('dlgBody').querySelector('#nn').onclick = () => { answers.push(false); step(); };
  };
  if (!$('dlg').open) $('dlg').showModal();
  step();
}

async function sendAnswers(token, answers) {
  $('dlgBody').innerHTML = '<p>맞춰 보는 중이오…</p>';
  try {
    const r = await fetch('/api/verify/answer', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, answers }),
    });
    const j = await r.json();
    if (j.ok) {
      S.person = j.person; S.candidate = null;
      $('dlgTitle').textContent = '🙌 알아뵈었소';
      $('dlgBody').innerHTML = `<p><b>${j.person.name}님</b>이 맞구려. 반갑소.</p>`;
      showGreet(); prefill(); paint();
      setTimeout(() => { $('dlg').close(); read(false); }, 1500);
    } else {
      $('dlgTitle').textContent = '🤫 둘만 아는 이야기';
      $('dlgBody').innerHTML = `<p>${j.msg}</p>
        <div style="margin-top:14px"><button class="pri wide" id="goon">그대로 보아 주오</button></div>`;
      S.person = null; S.candidate = null;
      $('dlgBody').querySelector('#goon').onclick = () => {
        $('dlg').close(); showGreet(); prefill(); paint(); read(false);
      };
    }
  } catch (e) {
    $('dlgBody').innerHTML = `<p>맞춰 보지 못했소: ${e}</p>`;
  }
}

function prefill() {
  const p = S.person;
  const on = p && (p.sure || p.confirmed);
  $('fillHint').classList.toggle('hidden', !on);
  $('ageKnown').classList.add('hidden');
  $('keptBox').classList.toggle('hidden', !(on && p.face_consent));
  if (!on) return;
  if (p.name) $('nm').value = p.name;
  if (p.email) $('em').value = p.email;
  if (p.phone) $('ph').value = p.phone.length === 11
    ? p.phone.replace(/(\d{3})(\d{4})(\d{4})/, '$1-$2-$3') : p.phone;
  if (p.face_consent) { $('keep').checked = true; $('keepBox').classList.toggle('hidden', !!p.has_secret); }
  // 지난번에 일러 주신 나이·성별을 골라 둔다
  const h = (p.history || []).find(x => x.age || x.gender);
  if (h) {
    if (h.age) {
      const m = h.age.match(/(\d+대|90대 이상)/);
      if (m) { $('dec').value = m[1]; $('dec').onchange(); }
      const q = h.age.match(/(초반|중반|후반)/);
      if (q) $('part').value = q[1];
    }
    if (h.gender) $('gender').value = h.gender.indexOf('남') >= 0 ? '남자 사람' : '여자 사람';
    $('ageKnown').classList.remove('hidden');
  }
}

/* ── 감정서 (흘려 받기) ────────────────────────────────────── */
async function read(detailed) {
  if (S.busy || !S.image) return;
  S.busy = true; S.detailed = detailed;
  // 기다리는 동안은 가운데 모달로 크게 보여 준다. 구석의 작은 글씨는
  // 멈춘 것으로 읽힌다.
  // 첫 감정서는 **초벌**이다 — "맛보기"보다 붓을 든 이의 말에 가깝다.
  $('workMsg').textContent = detailed
    ? '장군신을 부르는 중이오…' : '장군신을 불러 감정서 초벌을 뜨는 중이오…';
  $('workBar').style.width = '0%';
  $('workChars').textContent = '0자';
  $('workTime').textContent = '0초';
  $('tail').textContent = '';
  if (!$('workDlg').open) $('workDlg').showModal();
  paint();

  try {
    const r = await fetch('/api/read', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        image: S.image, detailed,
        told_age: toldAge(), told_gender: $('gender').value,
        person_id: (S.person && (S.person.sure || S.person.confirmed)) ? S.person.id : null,
      }),
    });
    const rd = r.body.getReader(), dec = new TextDecoder();
    let buf = '';
    for (;;) {
      const { value, done } = await rd.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf('\n\n')) >= 0) {
        handleSSE(buf.slice(0, i)); buf = buf.slice(i + 2);
      }
    }
  } catch (e) {
    $('workMsg').textContent = '감정서를 받다 끊겼소: ' + e;
    setTimeout(() => { if ($('workDlg').open) $('workDlg').close(); }, 2500);
  }
  S.busy = false;
  if ($('workDlg').open) $('workDlg').close();
  paint();
}

function handleSSE(chunk) {
  const ev = (chunk.match(/^event:\s*(.+)$/m) || [])[1];
  const dl = (chunk.match(/^data:\s*([\s\S]*)$/m) || [])[1];
  if (!ev) return;
  let d = {}; try { d = JSON.parse(dl); } catch (e) { }
  if (ev === 'stage') { $('workMsg').textContent = d.msg; }
  else if (ev === 'basic') { S.basic = d; showBasic(); }
  else if (ev === 'pace') {
    // 서버가 지난 기록으로 익힌 예상 시간. 몇 번 겪을수록 정확해진다.
    S.expect = d.expect;
    $('workTime').textContent = '0초';
    $('workChars').textContent = d.learned
      ? `보통 ${Math.round(d.expect)}초쯤 걸리오`
      : '처음이라 얼마나 걸릴지 지켜보는 중이오';
  }
  else if (ev === 'tick') {
    $('workBar').style.width = (d.pct || 0) + '%';
    // 남은 시간과 막대는 **같은 셈에서 나와야** 한다. 따로 놀면
    // "막대는 꽉 찼는데 53초 남았다" 는 말이 안 되는 짝이 나온다.
    const left = Math.max(0, (d.expect || 0) - (d.elapsed || 0));
    $('workChars').textContent = (d.chars || 0).toLocaleString() + '자';
    $('workTime').textContent = d.elapsed + '초'
      + (left > 3 ? ` · ${Math.round(left)}초쯤 남았소`
                  : (d.pct >= 90 ? ' · 곧 끝나오' : ' · 조금만 더'));
    if (d.chars) $('workMsg').textContent = S.detailed
      ? '🖌️ 아솔이 감정서를 쓰는 중이오' : '🖌️ 아솔이 감정서 초벌을 뜨는 중이오';
    if (d.tail) $('tail').textContent = '…' + d.tail;
  } else if (ev === 'done') {
    S.report = d.text; S.model = d.model; if (d.basic) { S.basic = d.basic; showBasic(); }
    if ($('workDlg').open) $('workDlg').close();
    showReport(); paint();
    // 초벌이 나오면 **[아솔이 본 것]** 자리에 세운다. 성별·나이·직업을 먼저
    // 보고 나이를 고쳐 일러 줄 참이기 때문이다. 감정서로 확 내려가 버리면
    // 다시 거슬러 올라와야 한다.
    // 전체 감정서는 그 자체가 볼 것이니 그때만 글로 내려간다.
    scrollTo2(S.detailed ? $('reportCard')
                         : ($('basicCard').classList.contains('hidden')
                            ? $('shotCard') : $('basicCard')));
  } else if (ev === 'error') {
    if ($('workDlg').open) $('workDlg').close();
    $('faceNote').innerHTML = `<div class="note">${d.msg}</div>`;
  }
}

function showBasic() {
  const b = S.basic; if (!b) return;
  const bits = [];
  // 알아본 분이면 **누구인지부터** 적는다. 아솔이 본 것 가운데 가장 큰 것이
  // 이름인데, 성별·나이만 늘어놓으면 알아본 티가 나지 않는다.
  const p = S.person;
  if (p && (p.sure || p.confirmed)) {
    const n = (p.visits || 0) + 1;
    bits.push(`<b>누구</b> ${p.name}님 <span style="color:#8f807c">` +
              `(${n}번째 걸음${p.days ? ` · ${p.days}일 만`: ''})</span>`);
  }
  if (b.gender) bits.push(`<b>성별</b> ${b.gender}`);
  if (b.age_range) {
    // 일러 주신 나이로 감정하되, **아솔이 본 나이도 함께** 적는다.
    // 감춰 두면 왜 나이를 물었는지 알 수 없고, 아솔이 얼마나 맞히는지도 모른다.
    let s = `<b>나이</b> ${b.age_range}`;
    if (b.told_age) {
      s += ' <span style="color:#8f807c">(일러 주신 나이)</span>';
      if (b.ai_age && b.ai_age !== b.age_range)
        s += `<br><span style="color:#8f807c">↳ 아솔은 <b>${b.ai_age}</b>로 보았소만,` +
             ' 일러 주신 나이로 감정하였소.</span>';
      else if (b.ai_age)
        s += '<br><span style="color:#3f8c68">↳ 아솔도 같이 보았소. 눈이 맞았구려.</span>';
    }
    bits.push(s);
  }
  if (b.current_jobs && b.current_jobs.length) bits.push(`<b>현재 직업 추정</b> ${b.current_jobs.join(', ')}`);
  if (b.suitable_jobs && b.suitable_jobs.length) bits.push(`<b>어울리는 직업</b> ${b.suitable_jobs.join(', ')}`);
  if (!bits.length) return;
  $('basicCard').innerHTML = '<h2 class="sec">🔎 아솔이 본 것</h2>' + bits.join('<br>');
  $('basicCard').classList.remove('hidden');
}

function showReport() {
  $('reportTitle').textContent = '📜 아솔의 관상 풀이' + (S.detailed ? '' : '  (초벌)');
  $('report').innerHTML = md(S.report) +
    `<div class="hint" style="margin-top:10px">by ${S.model} 장군신</div>`;
  $('reportCard').classList.remove('hidden');
  // 초벌 자리에서는 기운·기록·연락처를 함께 펼쳐 둔다. 어차피 이어서 적을
  // 것들이라, 눌러야 나타나게 하면 한 걸음이 더 든다.
  $('formCard').classList.toggle('hidden', S.detailed);
  // 전체 감정서가 나온 뒤에는 나이 고르개도 할 일이 끝났다. 그 값으로 이미
  // 다 보았으니 남겨 두면 "고치면 다시 보아 주나" 하고 손이 간다.
  $('ageCard').classList.toggle('hidden', S.detailed);
}

$('btnCopy').onclick = () => {
  navigator.clipboard.writeText(S.report).then(() => {
    $('btnCopy').textContent = '✅ 복사되었소'; setTimeout(() => $('btnCopy').textContent = '📋 감정서 복사하기', 1800);
  });
};

/* ── 별점·기록 체크 ────────────────────────────────────────── */
const STAR_WORD = ['말하지 않으셔도 되오', '몹시 고단하오', '기운이 없소',
                   '그럭저럭하오', '괜찮소', '더할 나위 없소'];
function paintStars() {
  [...$('stars').children].forEach((x, i) => x.classList.toggle('on', i < S.stars));
  $('starLab').textContent = STAR_WORD[S.stars] || '';
  $('starClear').classList.toggle('hidden', !S.stars);
}
$('stars').onclick = (e) => {
  const b = e.target.closest('button'); if (!b) return;
  // 같은 별을 다시 누르면 지운다 — 고르고 나서 무를 길이 있어야 한다.
  S.stars = (S.stars === +b.dataset.v) ? 0 : +b.dataset.v;
  paintStars();
};
$('starClear').onclick = () => { S.stars = 0; paintStars(); };
$('keep').onchange = (e) => {
  const p = S.person;
  $('keepBox').classList.toggle('hidden', !e.target.checked || !!(p && p.has_secret));
};

/* ── 자세히 보고 메일로 받기 ───────────────────────────────── */
async function finish() {
  if (S.busy) return;
  $('formMsg').innerHTML = '';
  const body = {
    image: S.image, report: S.report, basic: S.basic, model: S.model,
    name: $('nm').value, email: $('em').value, phone: $('ph').value,
    mood: $('mood').value, condition: S.stars ? S.stars + '/5' : '',
    secret: $('secret').value, keep: $('keep').checked,
    person_id: (S.person && (S.person.sure || S.person.confirmed)) ? S.person.id : null,
  };
  // 처음 오신 분은 이 칸들이 비어 있다. 그런데 그 칸은 화면 한참 아래에 있어
  // 버튼만 다시 누르며 "왜 안 되지" 하게 된다. 그래서 **모달로 알리고,
  // 그 자리를 붉게 감싸고, 거기로 데려간다.**
  const bad = [];
  if (!body.name || body.name.trim().length < 2) bad.push(['nm', '이름을 두 글자 이상 적어 주시오.']);
  if (!/^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$/.test(body.email)) bad.push(['em', '메일 주소를 적어 주시오.']);
  if (body.phone && !/^0\d{1,2}-?\d{3,4}-?\d{4}$/.test(body.phone.replace(/\s/g, '')))
    bad.push(['ph', '휴대전화번호를 다시 확인해 주시오. (적지 않으셔도 되오)']);
  ['nm', 'em', 'ph'].forEach(i => $(i).classList.remove('need'));
  if (bad.length) {
    $('formCard').classList.remove('hidden', 'need');
    void $('formCard').offsetWidth;              // 흔들림을 다시 태우려고
    $('formCard').classList.add('need');
    bad.forEach(([i]) => $(i).classList.add('need'));
    modal('✍️ 적어 주셔야 하오', `
      <p>감정서를 보내 드리려면 아래를 적어 주셔야 하오.</p>
      <ul style="margin:8px 0 0 -8px">${bad.map(([, m]) => `<li>${m}</li>`).join('')}</ul>
      <div style="margin-top:16px"><button class="pri wide" id="goform">적으러 가기</button></div>`);
    $('dlgBody').querySelector('#goform').onclick = () => {
      $('dlg').close();
      scrollTo2($('formCard'));
      setTimeout(() => $(bad[0][0]).focus(), 500);
    };
    return;
  }
  $('formCard').classList.remove('need');

  // 먼저 전체 감정서를 받고, 그 글로 메일을 보낸다.
  await read(true);
  body.report = S.report; body.basic = S.basic; body.model = S.model;
  if (!S.report) return;

  // 결과는 **폼 밖**에 띄운다. 전체 감정서가 나오면 폼이 접히는데, 그 안에
  // 두었더니 "보냈다"는 말이 함께 사라져 아무 일도 안 일어난 것처럼 보였다.
  $('mailMsg').innerHTML = '<div class="card"><b>📮 메일을 보내는 중이오…</b></div>';
  try {
    const r = await fetch('/api/finish', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    $('mailMsg').innerHTML = j.ok
      ? `<div class="good">📬 <b>${$('em').value}</b> 로 감정서를 보냈소.<br>
         <span style="font-size:13px;color:#5d4f4f">받은편지함에 없거든 스팸함도 살펴보시오.</span></div>`
      : `<div class="note">📪 보내지 못했소 — ${j.msg}</div>`;
    if (j.ok) {
      // 보내고 나면 그 폼은 할 일이 끝났다. 기운·기록·연락처를 그대로 두면
      // 다시 적어야 하는 줄 알거나, 한 번 더 보내야 하나 망설이게 된다.
      $('formCard').classList.add('hidden');
      modal('📬 감정서를 보냈소', `<p><b>${$('em').value}</b> 로 보냈소.</p>
        <p>받은편지함에 없거든 스팸함도 살펴보시오.</p>
        ${$('keep').checked ? '<p>🔐 얼굴을 기억해 두었소. 다음에 오시면 알아보고 안부를 묻겠소.</p>' : ''}`);
    }
    if (j.person_id && S.person) S.person.id = j.person_id;
    scrollTo2($('mailMsg'));
  } catch (e) {
    $('mailMsg').innerHTML = `<div class="note">📪 보내지 못했소: ${e}</div>`;
  }
  paint();
}

/* ── 붙박이 액션바 — 지금 할 수 있는 일만 보여 준다 ─────────── */
function paint() {
  const bar = $('actions');
  const B = [];
  if (!S.image) {
    B.push(['📸 지금 찍기', 'pri', () => (stream ? shoot() : startCam()), !detector && !stream ? false : false]);
    B.push(['📂 앨범에서', '', () => $('file').click(), false]);
  } else if (!S.report) {
    // "다시 찍기" 가 아니라 **처음부터** 다. 사진만 새로 담는 것이 아니라
    // 적어 두신 것과 본 것을 모두 비우고 첫 자리로 돌아간다. 반쯤 지워진
    // 상태가 남아 있으면 무엇이 지워졌는지 알 수 없다.
    B.push(['↩️ 처음부터', '', reset, S.busy]);
    B.push(['🔮 관상 보기', 'pri', () => read(false), S.busy]);
  } else if (!$('formCard').classList.contains('hidden')) {
    // ★ 깃발(S.detailed)이 아니라 **폼이 실제로 떠 있는지**를 본다.
    //   깃발로 갈랐더니 어긋나는 때가 있어 폼은 보이는데 그 폼을 보내는
    //   버튼만 사라졌다. 적으라고 해 놓고 보낼 길이 없는 화면이 된 셈이다.
    //   같은 것을 보고 정하면 둘이 어긋날 수가 없다.
    B.push(['↩️ 처음부터', '', reset, S.busy]);
    B.push(['🔍 자세히 보고 메일로 받기', 'pri', finish, S.busy]);
  } else {
    // 복사는 감정서 바로 밑에 이미 있다. 액션바에 또 두면 같은 버튼이
    // 화면에 둘이 되어 어느 쪽을 눌러야 하나 망설이게 된다.
    B.push(['↩️ 처음부터', '', reset, S.busy]);
  }
  bar.innerHTML = '';
  B.forEach(([label, cls, fn, dis]) => {
    const b = document.createElement('button');
    b.textContent = label; if (cls) b.className = cls;
    b.disabled = !!dis; b.onclick = fn;
    bar.appendChild(b);
  });
}

function reset() {
  /* 첫 자리로 되돌린다.
   *
   * 상태를 하나씩 지우다 보면 한 군데만 어긋나도 반쯤 지워진 화면이 남고,
   * 무엇이 지워졌는지 알 수 없다(실제로 그렇게 막혔다). '처음부터' 는 말
   * 그대로 처음이니 **페이지를 다시 여는 것**이 가장 확실하다.
   *
   * 켜 두신 뜻(자동 찍기·알아보기)은 주소줄에 있으므로 그대로 살아남는다.
   * 카메라도 새로 잡히고, 남아 있던 갈래나 스트림도 함께 정리된다.
   */
  try { stopCam(); } catch (e) { }
  const u = new URL(location.href);
  u.searchParams.set('auto', want.auto ? '1' : '0');
  u.searchParams.set('rec', want.rec ? '1' : '0');
  location.replace(u.toString());
}

function scrollTo2(el) {
  setTimeout(() => el.scrollIntoView({ behavior: 'smooth', block: 'start' }), 120);
}

paint();
if (!want.auto) say('아래 [지금 찍기] 를 누르시오.', '자동으로 찍히길 원하시면 위에서 켜시오.');
