# -*- coding: utf-8 -*-
"""웰니스 관상 '아솔' — 웹 서버.

왜 Streamlit 을 걷어냈나 —
  · 버튼 크기와 자리를 우리가 정할 수 없었다. 붙박이 액션바 하나를 두려고
    남의 클래스 이름을 뒤져 CSS 로 비트는 짓을 해야 했다.
  · 화면을 다시 그릴 때마다 스크립트가 통째로 다시 돌아, 무엇이 언제 실행되는지
    붙잡기 어려웠다. 위젯이 화면에서 사라지면 상태까지 버렸다.
  · 무엇보다 **연결이 끊기면 모든 것이 날아갔다.** 오래 걸리는 감정서를 쓰는 동안
    앞단(Cloudflare)이 조용한 연결을 끊었고, 그때마다 사진도 감정서도 사라졌다.

지금 구조 —
  · 화면은 static/ 의 한 페이지. 우리가 처음부터 끝까지 쥔다.
  · 서버는 몇 개의 요청만 받는다. 상태를 서버에 두지 않으므로 연결이 끊겨도
    브라우저가 들고 있던 것으로 이어 갈 수 있다.
  · 감정서는 SSE 로 흘려보낸다. 한 글자도 안 나오는 동안에도 1초마다 신호를
    보내므로 앞단이 조용하다고 오해하지 않는다.

얼굴 다루기(faceutil)·보관(leads)·메일(mailer)·감정서 짓기(reading) 는 그대로 쓴다.
그 넷은 이미 시험을 거쳤고 화면과 상관이 없다.
"""
import base64
import io
import json
import os
import queue
import re
import threading
import time
import traceback

from fastapi import FastAPI, Request
from fastapi.responses import (FileResponse, JSONResponse, StreamingResponse)
from fastapi.staticfiles import StaticFiles
from PIL import Image

# 판번호는 여기 하나뿐이다. 화면(static/index.html)과 readme 가 이것을 따른다.
__version__ = "4.0.0"

import faceutil
import leads
import llm_client
import mailer
import reading

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")

app = FastAPI(title="웰니스 관상 아솔")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.on_event("startup")
def _boot():
    # 키는 이미지에 굽지 않는다. 띄울 때 환경변수로 받는다.
    llm_client.configure(base_url=os.environ.get("LLM_BASE_URL", ""),
                         api_key=os.environ.get("LLM_API_KEY", ""))
    n = leads.init()
    print("[boot] 준비 완료. 지난 기록 %s 줄 정리." % n, flush=True)


# ── 도우미 ────────────────────────────────────────────────────────────

def _img_from(data_uri):
    """data:image/...;base64,... 를 PIL 이미지로."""
    raw = base64.b64decode((data_uri or "").split(",", 1)[-1])
    return Image.open(io.BytesIO(raw)).convert("RGB"), raw


def _b64png(blob):
    return "data:image/png;base64," + base64.b64encode(blob).decode()


def _parse_basic(text):
    """장군신이 돌려준 기본 정보를 뜯는다.

    받는 모양 —
        성별: 남성
        나이대: 50대 후반
        현재 직업: 경영인, 관리자
        어울리는 직업: 교육, 상담
    줄 하나라도 빠질 수 있으니 없으면 빈 값으로 둔다. 여기서 터지면
    감정서까지 못 보게 되므로, 못 읽은 것은 그냥 비워 둔다.
    """
    out = {"gender": "", "age_range": "", "current_jobs": [], "suitable_jobs": []}
    for line in (text or "").splitlines():
        line = line.strip().lstrip("-•* ").strip()
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip()
        if not v:
            continue
        if "성별" in k:
            out["gender"] = ("남자 사람" if "남" in v else
                             "여자 사람" if "여" in v else v)
        elif "나이" in k:
            m = re.search(r"(\d+\s*대\s*(?:초반|중반|후반)?)", v)
            out["age_range"] = (m.group(1).replace(" ", "") if m else v)
        elif "현재" in k and "직업" in k:
            out["current_jobs"] = [s.strip() for s in v.split(",") if s.strip()][:4]
        elif "어울리" in k or "추천" in k:
            out["suitable_jobs"] = [s.strip() for s in v.split(",") if s.strip()][:4]
    return out


def _sse(event, data):
    return "event: %s\ndata: %s\n\n" % (event, json.dumps(data, ensure_ascii=False))


# ── 얼마나 걸리는지 스스로 익힌다 ────────────────────────────────────
#
# 진행 막대를 글자 수로만 채웠더니 순식간에 끝까지 차고는 한참을 멈춰 있었다.
# 글자는 뒤늦게 몰아서 오는데 시간은 고르게 흐르기 때문이다.
# 그래서 **실제로 걸린 시간을 적어 두고 평균을 낸다.** 쓸수록 정확해진다.
PACE_PATH = os.path.join(os.path.dirname(leads.DB_PATH) or ".", "pace.json")
# 아직 배운 것이 없을 때 쓸 값(초). 27B 짜리 눈 달린 모델의 어림값이다.
PACE_SEED = {"short": 40.0, "full": 95.0}
_pace_lock = threading.Lock()


def _pace_get(kind):
    try:
        with io.open(PACE_PATH, encoding="utf-8") as f:
            d = json.load(f)
        v = d.get(kind) or {}
        if v.get("n"):
            return float(v["secs"]), int(v["n"])
    except Exception:
        pass
    return PACE_SEED.get(kind, 60.0), 0


def _pace_put(kind, secs):
    """새로 걸린 시간을 평균에 섞는다. 최근 것에 조금 더 무게를 준다."""
    if not (2 < secs < 900):          # 터무니없는 값은 배우지 않는다
        return
    with _pace_lock:
        try:
            d = {}
            if os.path.exists(PACE_PATH):
                with io.open(PACE_PATH, encoding="utf-8") as f:
                    d = json.load(f)
            v = d.get(kind) or {"secs": PACE_SEED.get(kind, 60.0), "n": 0}
            n = min(int(v.get("n", 0)) + 1, 30)     # 30번까지만 쌓는다
            w = 1.0 / n                              # 처음엔 크게, 나중엔 조금씩
            v["secs"] = float(v["secs"]) * (1 - w) + float(secs) * w
            v["n"] = n
            d[kind] = v
            os.makedirs(os.path.dirname(PACE_PATH) or ".", exist_ok=True)
            with io.open(PACE_PATH, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False)
            print("[pace] %s 평균 %.1f초 (%d회)" % (kind, v["secs"], n), flush=True)
        except Exception as e:
            print("[pace] 못 적었소:", e, flush=True)


def _pct(elapsed, expect):
    """진행률. **시간만 본다.**

    글자 수도 섞어 봤는데 못 쓸 것이었다. 감정서를 1,200자쯤으로 시켰는데
    장군신이 2,655자를 써 버리면 그것만으로 200% 가 되어 막대가 꽉 차고,
    화면에는 "다 찼는데 남은 시간 53초" 라는 말이 안 되는 짝이 나왔다.
    글자는 몰아서 오지만 시간은 고르게 흐른다. 고르게 흐르는 쪽을 쓴다.

    1 - exp(-t/τ) 꼴이라 끝에 다가갈수록 느려지고 100 에 닿지 않는다.
    예상 시간에서 83% 를 지나므로, 예상보다 늦어져도 막대는 계속 조금씩 움직인다.
    """
    import math
    tau = max(expect, 5.0) * 0.56
    return int(min(97.0, 100.0 * (1.0 - math.exp(-max(elapsed, 0.0) / tau))))


# ── ① 사진을 받아 살펴본다 ───────────────────────────────────────────

@app.post("/api/prepare")
async def prepare(req: Request):
    """사진 한 장을 받아 (1) 잘라 보여 줄 두 장 (2) 자세 안내
    (3) 원하시면 '전에 오신 분인지' 까지 살핀다.

    ⚠️ 얼굴 특징값은 **알아보게 해 달라 하신 때에만** 만든다. 만들어 두고
    쓰지 않는 것과, 아예 만들지 않는 것은 다르다. 만든 값은 저장하지 않는다.
    """
    body = await req.json()
    try:
        im, _raw = _img_from(body.get("image"))
    except Exception as e:
        return JSONResponse({"error": "사진을 읽지 못했소: %s" % e}, status_code=400)

    pts = faceutil.landmarks(im)
    ok_face, note = faceutil.facing_note(pts)
    res = {
        "oval": _b64png(faceutil.oval_png(im)),
        "mesh": _b64png(faceutil.mesh_png(im)),
        "found": pts is not None,
        "facing_ok": bool(ok_face),
        "note": note,
        "person": None,
    }
    try:
        res["quality"] = faceutil.quality(im)[0]
    except Exception:
        res["quality"] = 0.0

    if body.get("recognize"):
        try:
            vec = faceutil.embed(im)
            if vec is not None:
                pid, score, person = leads.find_person(vec)
                if not pid and score >= CANDIDATE_MIN:
                    # 문턱은 못 넘었으나 **그럴듯하게 닮은 분**이 있다.
                    # 누구인지는 알려 주지 않고, 이야기로 여쭤 볼 길만 연다.
                    cpid, cscore, _c = leads.find_person(vec, threshold=CANDIDATE_MIN)
                    if cpid and leads.secret_note(cpid):
                        b = leads.person_brief(cpid) or {}
                        res["candidate"] = {
                            "id": cpid, "score": round(cscore, 3),
                            "masked": _mask(b.get("name", "")),
                            "asked_out": _VFAIL.get(cpid, 0) >= VERIFY_MAX_FAIL}
                        print("[rec] 후보 pid=%s score=%.3f" % (cpid, cscore),
                              flush=True)
                if pid:
                    brief = leads.person_brief(pid) or {}
                    # 문턱을 아슬아슬하게 넘겼으면 확신하지 않는다.
                    # 남을 나로 착각해 **남의 이력을 여는 것**이 가장 나쁜 실패다.
                    sure = score >= leads.FACE_THRESHOLD + 0.09
                    p = {"id": pid, "score": round(score, 3), "sure": sure,
                         "face_consent": bool(brief.get("face_consent")),
                         "has_secret": bool(brief.get("has_secret")),
                         "asked_out": _VFAIL.get(pid, 0) >= VERIFY_MAX_FAIL}
                    if sure:
                        hist = leads.history(pid, limit=3)
                        p.update({
                            "name": brief.get("name", ""),
                            "visits": brief.get("visits") or 0,
                            "days": brief.get("days_since_last"),
                            "email": (person or {}).get("email", ""),
                            "phone": (person or {}).get("phone", ""),
                            "history": [
                                {"ts": (h.get("ts") or "")[:10],
                                 "age": h.get("age"), "gender": h.get("gender"),
                                 "mood": h.get("mood"), "condition": h.get("condition")}
                                for h in hist]})
                    else:
                        # ★ 확신이 없으면 **아무것도 알려 주지 않는다.**
                        #   전에는 "혹시 ○○님 아니시오?" 하고 이름을 그대로
                        #   보여 준 뒤 "네" 한마디로 이력을 열어 주었다.
                        #   그건 아무나 "네" 하면 남의 기록이 열린다는 뜻이다.
                        #   이름은 가리고, **둘만 아는 이야기로 맞혀야** 연다.
                        p.update({"masked": _mask(brief.get("name", "")),
                                  "name": "", "visits": 0, "history": []})
                    res["person"] = p
                    print("[rec] pid=%s score=%.3f %s"
                          % (pid, score, "확신" if sure else "아리송"), flush=True)
        except Exception as e:
            print("[rec] 실패:", e, flush=True)
    return res


# ── ② 감정서를 쓴다 (흘려보내기) ─────────────────────────────────────

def _stream_reading(im, told_age, told_gender, detailed, pid):
    """장군신을 딴 갈래에서 부르고, 이쪽은 쉬지 않고 신호를 내보낸다.

    ★ 한 글자도 안 나오는 동안에도 1초마다 보낸다. 비전 모델은 첫 글자까지
      한참 말이 없을 때가 있는데, 그동안 조용하면 앞단(Cloudflare)이 죽은
      연결로 보고 끊는다. 그러면 쓰던 감정서가 통째로 사라진다.
    """
    q = queue.Queue()
    bag = {"basic": None, "text": "", "chars": 0, "resp": None, "err": None}

    def work():
        try:
            models = reading.get_all_available_models()
            if not models:
                bag["err"] = "당직 서는 장군신이 없소."
                return
            # 1) 기본 정보(성별·나이·직업)
            q.put(("stage", {"msg": "장군신이 얼굴을 살피는 중이오…"}))
            raw, err = reading.analyze_face_info(models[0], im)
            basic = _parse_basic(raw) if raw else {}
            if told_age:
                basic["ai_age"] = basic.get("age_range", "")
                basic["age_range"] = told_age
                basic["told_age"] = True
            if told_gender:
                basic["gender"] = told_gender
            bag["basic"] = basic
            q.put(("basic", basic))

            # 2) 감정서
            info = ""
            if basic.get("gender") or basic.get("age_range"):
                info = "\n\n[이 사람에 대해 알려진 것]\n- 성별: %s\n- 나이: %s" % (
                    basic.get("gender", "모름"), basic.get("age_range", "모름"))
            if pid:
                info += reading.past_note(leads.person_brief(pid),
                                          leads.history(pid, limit=3))
            prompt = reading.build_prompt(info, detailed=bool(detailed))

            def grab(text_so_far, chars, elapsed):
                bag["text"], bag["chars"] = text_so_far, chars

            for m in models:
                q.put(("stage", {"msg": "%s 장군신이 붓을 고쳐 잡는 중…"
                                 % m.split(":")[0].upper()}))
                resp, err = reading.try_model_with_image(m, prompt, im,
                                                         on_progress=grab)
                if resp is not None:
                    bag["resp"], bag["model"] = resp, m.split(":")[0].upper()
                    return
                bag["err"] = err
        except Exception as e:
            traceback.print_exc()
            bag["err"] = str(e)
        finally:
            q.put(("__done__", None))

    th = threading.Thread(target=work, daemon=True)
    t0 = time.time()
    th.start()

    kind = "full" if detailed else "short"
    expect, seen = _pace_get(kind)
    goal = 1200 if detailed else 600
    yield _sse("pace", {"expect": round(expect, 1), "learned": seen})
    done = False
    while not done:
        # 큐에 온 것을 먼저 흘려보낸다.
        try:
            while True:
                ev, data = q.get_nowait()
                if ev == "__done__":
                    done = True
                    break
                yield _sse(ev, data)
        except queue.Empty:
            pass
        if done:
            break
        # 아무것도 없어도 1초마다 신호를 낸다 — 이것이 연결을 지킨다.
        _el = time.time() - t0
        yield _sse("tick", {"chars": bag["chars"],
                            "elapsed": round(_el, 1),
                            "expect": round(expect, 1),
                            "pct": _pct(_el, expect),
                            "tail": bag["text"][-160:].replace("\n", " ")})
        time.sleep(1.0)

    th.join(timeout=5)
    took = time.time() - t0
    if bag["resp"] is None:
        yield _sse("error", {"msg": bag["err"] or "감정서를 짓지 못했소."})
    else:
        # 이번에 걸린 시간을 익혀 둔다. 다음 손님의 막대가 더 정확해진다.
        _pace_put(kind, took)
        yield _sse("done", {"text": bag["resp"].text,
                            "model": bag.get("model", ""),
                            "basic": bag["basic"] or {},
                            "elapsed": round(took, 1)})


@app.post("/api/read")
async def read(req: Request):
    body = await req.json()
    try:
        im, _ = _img_from(body.get("image"))
    except Exception as e:
        return JSONResponse({"error": "사진을 읽지 못했소: %s" % e}, status_code=400)
    gen = _stream_reading(im, (body.get("told_age") or "").strip() or None,
                          (body.get("told_gender") or "").strip() or None,
                          bool(body.get("detailed")),
                          body.get("person_id"))
    return StreamingResponse(gen, media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


# ── ③ 메일로 보내고 담는다 ───────────────────────────────────────────

@app.post("/api/finish")
async def finish(req: Request):
    body = await req.json()
    name = (body.get("name") or "").strip()
    email = (body.get("email") or "").strip()
    phone = (body.get("phone") or "").strip()
    keep = bool(body.get("keep"))           # 기록으로 남기기(선택 동의)
    report = body.get("report") or ""
    basic = body.get("basic") or {}

    if not leads.valid_name(name):
        return {"ok": False, "msg": "이름을 두 글자 이상 적어 주시오."}
    if not mailer.valid(email):
        return {"ok": False, "msg": "메일 주소를 다시 확인해 주시오."}
    # 번호는 **선택**이다. 메일 보내는 데 쓰이지 않으므로 필수로 둘 수 없다.
    if phone and not leads.valid_phone(phone):
        return {"ok": False, "msg": "휴대전화번호를 다시 확인해 주시오."}

    try:
        im, _ = _img_from(body.get("image"))
    except Exception:
        return {"ok": False, "msg": "사진이 사라졌소. 다시 담아 주시오."}

    age = basic.get("age_range", "")
    if age and basic.get("told_age"):
        age += "  (일러 주신 나이)"
    info = [("성별", basic.get("gender", "")), ("나이", age),
            ("현재 직업 추정", ", ".join(basic.get("current_jobs") or [])),
            ("어울리는 직업", ", ".join(basic.get("suitable_jobs") or []))]

    ok, note = mailer.send(email, "📜 관상가 아솔의 감정서가 도착하였소",
                           report, subtitle=("%s · %s" % (
                               basic.get("gender", ""), basic.get("age_range", ""))
                           ).strip(" ·"), photo=im, info=info)

    # 얼굴 특징값과 사진은 **남기겠다 하신 때에만** 만들어 넘긴다.
    vec = faceutil.embed(im) if keep else None
    face = None
    if keep:
        try:
            face = faceutil.face_jpeg(im)
        except Exception as e:
            print("[face] 크롭 실패:", e, flush=True)
    try:
        q = faceutil.quality(im)[0]
    except Exception:
        q = 0.0

    sv_ok, sv_msg, pid = leads.remember(
        body.get("person_id"), name, email, phone, True,
        face_consent=keep, embedding=vec, photo_png=face,
        meta={"gender": basic.get("gender"), "age": basic.get("age_range"),
              "model": body.get("model"), "mail_ok": ok, "mail_msg": note,
              "quality": q, "summary": report,
              "mood": (body.get("mood") or "")[:leads.MOOD_MAX],
              "condition": (body.get("condition") or "")[:leads.MOOD_MAX],
              "secret_note": (body.get("secret") or "") if keep else None})
    if not sv_ok:
        print("[leads] 저장 실패:", sv_msg, flush=True)
    else:
        print("[leads] 담음 pid=%s 기록동의=%s" % (pid, keep), flush=True)
    return {"ok": ok, "msg": note, "person_id": pid}


# ── ④ 둘만 아는 이야기로 본인 확인 ───────────────────────────────────
#
# 얼굴이 아리송할 때 쓰는 마지막 문이다.
#
# ⚠️ **아무에게나 열어 주면 안 된다.** 처음 보는 분이 "나를 알아봐 달라"고 할 때
#    담아 둔 이야기들로 아무 질문이나 만들면, 그것만으로 **남의 사정이 새어
#    나간다.** 그래서 얼굴이 어느 정도 닮은 **후보가 있을 때만** 여쭙는다.
#    이름도 가려서 내보낸다 — 맞히기 전에는 누구인지 알려 주지 않는다.
#
# ⚠️ 이야기 원문은 **사내 LLM 밖으로 내보내지 않는다.** llm_client 는 사내
#    게이트웨이만 바라보므로 그 안에서 끝난다.
#
# ⚠️ 되묻는 질문 자체가 이야기의 주제를 흘린다("따님이…"라고 물으면 자녀
#    이야기임을 알려 준 셈이다). 그래서 **두 번 틀리면 더 묻지 않는다.**

_VERIFY = {}          # 표 = {토큰: {pid, answers, exp}}
_VFAIL = {}           # 사람마다 틀린 횟수
VERIFY_TTL = 300      # 5분이면 넉넉하다
VERIFY_MAX_FAIL = 2
# 얼굴이 이 아래면 후보로도 보지 않는다. 문턱(0.363)보다는 낮되, 아무나
# 걸리지 않을 만큼은 되어야 한다.
CANDIDATE_MIN = 0.22


def _mask(name):
    """홍길동 → **동. 성을 가리고 끝 글자만 남긴다.

    성이 가장 잘 드러나는 대목이라 그쪽을 가린다. 본인은 제 이름 끝 글자를
    보면 알아보지만, 곁에서 보던 사람에게는 짚이는 바가 적다.
    """
    n = (name or "").strip()
    if len(n) <= 1:
        return "○"
    return "*" * (len(n) - 1) + n[-1]


def _visit_facts(pid):
    """지난 걸음에서 **본인만 아는 사실**을 뽑는다. 질문거리를 넓히려는 것이다.

    남긴 이야기 하나만으로 물으면 늘 같은 주제가 되고, 되물을수록 그 이야기가
    닳는다. 언제 처음 왔는지, 몇 번째인지, 지난번에 뭐라 적었는지도 본인만
    아는 것이라 함께 쓴다.
    """
    b = leads.person_brief(pid) or {}
    out = []
    if b.get("first_ts"):
        out.append("처음 오신 날: %s" % b["first_ts"][:10])
    if b.get("last_ts"):
        out.append("가장 최근 걸음: %s" % b["last_ts"][:10])
    if b.get("days_since_last") is not None:
        out.append("그로부터 지난 날수: 약 %s일" % b["days_since_last"])
    if b.get("visits"):
        out.append("지금까지 감정서를 받으신 횟수: %s번" % b["visits"])
    for h in leads.history(pid, limit=3):
        bits = []
        if h.get("age"):
            bits.append("나이를 '%s' 라 일러 주심" % h["age"])
        if h.get("gender"):
            bits.append("성별 '%s'" % h["gender"])
        if h.get("mood"):
            bits.append("그날 남긴 말 '%s'" % h["mood"])
        if h.get("condition"):
            bits.append("그날 기운 %s" % h["condition"])
        if bits:
            out.append("%s 걸음: %s" % ((h.get("ts") or "")[:10], ", ".join(bits)))
    return "\n".join("- " + x for x in out)


def _make_questions(note, image, pid=None):
    """예/아니오 질문 셋을 짓는다. [(질문, 정답bool)] 또는 None.

    맞는 질문과 **일부러 틀린 질문**을 섞는다. 사칭하는 사람은 아무 말에나
    "예" 하기 마련이라, 틀린 질문 하나면 걸러진다. 어느 쪽으로 물을지는
    장군신이 그때그때 정한다.

    남긴 이야기뿐 아니라 **지난 걸음의 기록**으로도 묻는다. 한 가지 이야기만
    파고들면 되물을 때마다 그 이야기가 닳고, 곁에서 듣는 이에게도 훤히 드러난다.
    """
    facts = _visit_facts(pid) if pid else ""
    prompt = (
        "아래는 어떤 손님에 관해 우리가 아는 것이오.\n"
        "이 손님 본인만 맞힐 수 있는 **예/아니오 질문 3개**를 지으시오.\n\n"
        "[본인이 남긴 이야기]\n%s\n\n"
        "[지난 걸음의 기록]\n%s\n\n"
        "규칙:\n"
        "1. 3개 중 **1~2개는 사실과 다르게** 비틀어 물으시오(정답이 '아니오'가 되게).\n"
        "   나머지는 사실대로 물어 정답이 '예'가 되게 하시오.\n"
        "2. **세 질문의 밑천을 서로 다르게** 하시오 — 하나는 남긴 이야기에서,\n"
        "   하나는 언제·몇 번 오셨는지에서, 하나는 그때 적어 두신 말이나 나이에서.\n"
        "   («우리가 처음 만난 것이 한 해 전이오?» 같은 물음도 좋소.)\n"
        "3. 모르는 사람이 찍어 맞히기 어렵게 하되, **본인은 바로 알아볼** 구체적인\n"
        "   것(사람·때·곳·수)을 물으시오.\n"
        "4. 사극 말투로 짧게 한 문장씩. 정답을 질문 안에 흘리지 마시오.\n"
        "5. 다른 말 없이 아래 형식 그대로만 답하시오.\n\n"
        "Q1|예 또는 아니오|질문\n"
        "Q2|예 또는 아니오|질문\n"
        "Q3|예 또는 아니오|질문\n" % (note or "(없소)", facts or "(없소)"))
    for m in reading.get_all_available_models():
        resp, err = llm_client.generate_with_image(m, prompt, image,
                                                   temperature=0.9, max_tokens=512)
        if resp is None:
            continue
        out = []
        for line in (resp.text or "").splitlines():
            parts = [p.strip() for p in line.strip().split("|")]
            if len(parts) >= 3 and parts[0].upper().startswith("Q"):
                ans = parts[1].replace(" ", "")
                out.append((parts[2], ans.startswith("예")))
        if len(out) >= 3:
            return out[:3]
    return None


@app.post("/api/verify/start")
async def verify_start(req: Request):
    body = await req.json()
    pid = body.get("person_id")
    if not pid:
        return {"ok": False, "msg": "누구인지 짚이는 바가 없소."}
    if _VFAIL.get(pid, 0) >= VERIFY_MAX_FAIL:
        # 되묻기를 거듭하면 이야기가 다 새어 나간다. 여기서 그친다.
        return {"ok": False, "msg": "오늘은 더 여쭙지 않겠소. 처음 뵙는 걸로 하리다."}
    note = leads.secret_note(pid)
    facts = _visit_facts(pid)
    if not note and not facts:
        return {"ok": False, "msg": "그분에 대해 여쭐 것이 없소."}
    try:
        im, _ = _img_from(body.get("image"))
    except Exception:
        return {"ok": False, "msg": "사진이 사라졌소."}

    qs = _make_questions(note, im, pid)
    if not qs:
        return {"ok": False, "msg": "장군신이 질문을 짓지 못했소. 잠시 뒤에 다시 청하시오."}

    tok = base64.urlsafe_b64encode(os.urandom(15)).decode()
    _VERIFY[tok] = {"pid": pid, "answers": [a for _q, a in qs],
                    "exp": time.time() + VERIFY_TTL}
    # 정답은 서버만 안다. 화면에는 질문만 보낸다.
    return {"ok": True, "token": tok, "questions": [q for q, _a in qs]}


@app.post("/api/verify/answer")
async def verify_answer(req: Request):
    body = await req.json()
    rec = _VERIFY.pop(body.get("token") or "", None)
    if not rec or rec["exp"] < time.time():
        return {"ok": False, "msg": "시간이 지났소. 다시 청하시오."}
    given = body.get("answers") or []
    if len(given) != len(rec["answers"]):
        return {"ok": False, "msg": "답이 모자라오."}
    # 하나라도 틀리면 통과시키지 않는다. **남의 이력을 여는 쪽이 훨씬 나쁜
    # 실패**이므로, 애매하면 못 알아본 것으로 둔다.
    if all(bool(g) == bool(a) for g, a in zip(given, rec["answers"])):
        _VFAIL.pop(rec["pid"], None)
        pid = rec["pid"]
        brief = leads.person_brief(pid) or {}
        hist = leads.history(pid, limit=3)
        row = None
        try:
            with leads._db() as c:      # noqa: SLF001 — 연락처를 채워 드리려고
                r = c.execute("SELECT email, phone FROM people WHERE id=?",
                              (pid,)).fetchone()
                row = dict(r) if r else None
        except Exception:
            row = None
        print("[verify] 통과 pid=%s" % pid, flush=True)
        return {"ok": True, "person": {
            "id": pid, "score": None, "sure": True, "confirmed": True,
            "name": brief.get("name", ""), "visits": brief.get("visits") or 0,
            "days": brief.get("days_since_last"),
            "face_consent": bool(brief.get("face_consent")),
            "has_secret": bool(brief.get("has_secret")),
            "email": (row or {}).get("email", ""),
            "phone": (row or {}).get("phone", ""),
            "history": [{"ts": (h.get("ts") or "")[:10], "age": h.get("age"),
                         "gender": h.get("gender"), "mood": h.get("mood"),
                         "condition": h.get("condition")} for h in hist]}}
    n = _VFAIL.get(rec["pid"], 0) + 1
    _VFAIL[rec["pid"]] = n
    print("[verify] 실패 pid=%s (%d회)" % (rec["pid"], n), flush=True)
    # 다시 청할 자리를 두지 않는다. 되물을수록 이야기의 주제가 새어 나가고,
    # 화면에 없는 길을 말로만 열어 두면 "그럼 어디서 다시 청하오?" 가 된다.
    return {"ok": False,
            "msg": "어긋나는 대목이 있구려. 새로 오신 손님으로 뵙겠소."}


@app.get("/api/notice")
async def notice():
    """동의 안내문. 화면에 박아 두지 않고 여기서 받아 간다 — 문구가 바뀌면
    한 곳만 고치면 되고, leads 가 실제로 지키는 규칙과 어긋날 일이 없다."""
    return {"notice": leads.NOTICE, "face": leads.FACE_NOTICE,
            "no_medical": getattr(leads, "NO_MEDICAL", "")}


@app.get("/healthz")
async def healthz():
    """compose.yml 의 healthcheck 가 찌르는 자리. **주소를 바꾸면 거기도 고칠 것.**
    v4.0.0 전까지 그쪽이 Streamlit 의 /_stcore/health 를 가리켜 계속 unhealthy 였다."""
    return {"ok": True, "version": __version__}


@app.get("/")
async def index():
    """첫 페이지. **화면 파일에 판번호를 붙여 내보낸다.**

    붙이지 않았더니 고쳐 올려도 브라우저가 예전 app.js 를 그대로 썼다.
    서버는 새 코드인데 화면만 옛것이라, 고친 것이 반영되지 않은 줄 알고
    같은 곳을 몇 번이나 다시 고쳤다. 판번호는 파일이 바뀐 시각이라
    올릴 때마다 저절로 달라진다.
    """
    p = os.path.join(STATIC, "index.html")
    html = io.open(p, encoding="utf-8").read()
    ver = str(int(max(os.path.getmtime(os.path.join(STATIC, f))
                      for f in ("app.js", "app.css"))))
    html = (html.replace('href="/static/app.css"', 'href="/static/app.css?v=%s"' % ver)
                .replace('src="/static/app.js"', 'src="/static/app.js?v=%s"' % ver))
    from fastapi.responses import HTMLResponse
    return HTMLResponse(html, headers={
        "Cache-Control": "no-store, must-revalidate", "Pragma": "no-cache"})
