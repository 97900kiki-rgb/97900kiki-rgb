# -*- coding: utf-8 -*-
# ================================================================
# llm_client.py - 사내 LLM 서버(OpenAI 호환) 클라이언트
#
# 기존 google.generativeai 를 대체한다.
# 앱 쪽 UI 코드를 건드리지 않으려고, 응답 객체가 `.text` 속성을
# 그대로 갖도록 맞춰 두었다. (streamlit_app.py 의 response.text 유지)
# ================================================================

import base64
import io
import json
import time

import requests

# 비전(이미지 인식) 가능한 모델만. 앞쪽이 우선순위.
# 관상 분석은 사진을 봐야 하므로 텍스트 전용 모델은 쓸 수 없다.
#
# 순서 근거(실측): 같은 관상 프롬프트로
#   gemma3:27b    -> 24초에 정상 응답, 요구 형식도 정확
#   qwen3-vl:32b  -> 126초를 끌다가 HTTP 524 (앞단 Cloudflare 가 끊음)
#
# qwen3-vl 이 느린 이유는 thinking 모드로 사고과정(reasoning)을 길게
# 뱉기 때문이다. 지금은 gemma3 만 쓴다. qwen3-vl 을 되살리려면 thinking 을
# 끄는 옵션을 먼저 확인할 것.
VISION_MODELS = ["gemma3:27b"]

# 이미지가 크면 토큰·시간이 크게 늘어난다. 긴 변 기준으로 줄여서 보낸다.
MAX_IMAGE_EDGE = 1024
JPEG_QUALITY = 85

# 서버 앞단 Cloudflare 가 약 100초에서 응답을 끊고 524 를 준다(실측 126초 524).
# 그보다 먼저 우리가 포기해야 다음 모델로 빨리 넘어갈 수 있다.
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 90

# 스트리밍이면 조각이 계속 오므로 총 시간은 더 줘도 안전하다.
STREAM_TOTAL_TIMEOUT = 240

_config = {"base_url": None, "api_key": None}


class LLMError(Exception):
    pass


class LLMResponse:
    """genai 응답 객체 흉내 - .text 만 있으면 앱 코드가 그대로 돈다."""

    def __init__(self, text, model=None, usage=None):
        self.text = text
        self.model = model
        self.usage = usage or {}

    def __repr__(self):
        return "<LLMResponse model=%r len=%d>" % (self.model, len(self.text or ""))


def configure(base_url, api_key):
    """앱 시작 시 1회 호출. base_url 은 .../v1 까지."""
    if not base_url or not api_key:
        raise LLMError("LLM_BASE_URL 과 LLM_API_KEY 가 모두 필요합니다.")
    _config["base_url"] = base_url.rstrip("/")
    _config["api_key"] = api_key


def _headers():
    if not _config["api_key"]:
        raise LLMError("configure() 가 먼저 호출되어야 합니다.")
    return {
        "Authorization": "Bearer %s" % _config["api_key"],
        "Content-Type": "application/json",
    }


def image_to_data_uri(image):
    """PIL 이미지 -> data:image/jpeg;base64,... (긴 변 기준 축소)"""
    im = image
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    elif im.mode == "L":
        im = im.convert("RGB")

    longest = max(im.size)
    if longest > MAX_IMAGE_EDGE:
        ratio = MAX_IMAGE_EDGE / float(longest)
        new_size = (max(1, int(im.size[0] * ratio)), max(1, int(im.size[1] * ratio)))
        im = im.resize(new_size)

    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=JPEG_QUALITY)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return "data:image/jpeg;base64,%s" % b64


def list_vision_models():
    """서버에 실제로 살아 있는 비전 모델만 우선순위 순으로 반환."""
    try:
        r = requests.get(
            "%s/models" % _config["base_url"], headers=_headers(), timeout=20
        )
        r.raise_for_status()
        available = {m.get("id") for m in r.json().get("data", [])}
        found = [m for m in VISION_MODELS if m in available]
        if found:
            return found
        print("[LLM] 경고: 서버에 알려진 비전 모델이 없음. 목록=%s" % sorted(available), flush=True)
        return list(VISION_MODELS)
    except Exception as e:
        # 목록 조회가 실패해도 분석 자체는 시도해 볼 수 있게 기본값을 준다.
        print("[LLM] 모델 목록 조회 실패(%s) - 기본 목록 사용" % e, flush=True)
        return list(VISION_MODELS)


def _post(body, stream):
    return requests.post(
        "%s/chat/completions" % _config["base_url"],
        headers=_headers(),
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
        stream=stream,
    )


def _classify(status, text):
    if status == 429:
        return "quota_exceeded"
    if status == 404:
        return "model_not_found"
    if status == 524:
        # Cloudflare 가 원본 응답을 기다리다 끊은 것. 모델이 너무 느린 경우다.
        return "upstream_timeout"
    return "HTTP %d: %s" % (status, (text or "")[:200])


def generate_with_image(model_name, prompt, image, temperature=0.8, max_tokens=4096,
                        on_progress=None):
    """이미지 + 프롬프트로 생성. (LLMResponse, None) 또는 (None, 오류문자열)

    스트리밍으로 받는다. 첫 조각이 곧바로 흘러나오므로 앞단 Cloudflare 가
    응답을 기다리다 524 로 끊는 일을 피할 수 있다.

    on_progress(text_so_far, chars, elapsed) 를 주면 조각이 올 때마다 불러 준다.
    긴 본문은 30~70초가 걸려서, 아무 표시가 없으면 화면이 멈춘 줄 안다.
    화면 갱신이 잦으면 오히려 느려지므로 0.35초에 한 번으로 제한한다.
    """
    try:
        data_uri = image_to_data_uri(image)
        body = {
            "model": model_name,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                }
            ],
        }

        started = time.time()
        r = _post(body, stream=True)
        if r.status_code >= 400:
            return None, _classify(r.status_code, r.text)

        chunks = []
        last_cb = 0.0
        for raw in r.iter_lines():
            if time.time() - started > STREAM_TOTAL_TIMEOUT:
                r.close()
                return None, "stream_timeout (%d초 초과)" % STREAM_TOTAL_TIMEOUT
            if not raw:
                continue
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                obj = json.loads(payload)
            except ValueError:
                continue
            choices = obj.get("choices") or [{}]
            delta = choices[0].get("delta") or {}
            # qwen3 계열은 사고과정을 reasoning 으로 따로 흘린다. 본문만 모은다.
            piece = delta.get("content")
            if piece:
                chunks.append(piece)
                now = time.time()
                if on_progress and now - last_cb >= 0.35:
                    last_cb = now
                    try:
                        on_progress("".join(chunks), sum(len(c) for c in chunks),
                                    now - started)
                    except Exception:
                        pass          # 화면 갱신 실패로 생성이 끊기면 안 된다

        text = "".join(chunks).strip()
        if on_progress and text:
            try:
                on_progress(text, len(text), time.time() - started)
            except Exception:
                pass

        if not text:
            # 서버가 스트리밍(SSE)을 지원하지 않으면 조각이 하나도 안 모인다.
            # 그럴 때는 일반(비스트리밍) 방식으로 한 번 더 시도한다.
            print("[LLM] %s 스트리밍 결과가 비어 있음 -> 일반 방식으로 재시도" % model_name, flush=True)
            body["stream"] = False
            r2 = _post(body, stream=False)
            if r2.status_code >= 400:
                return None, _classify(r2.status_code, r2.text)
            choices = (r2.json().get("choices") or [{}])
            msg = choices[0].get("message") or {}
            text = (msg.get("content") or "").strip()

        if not text:
            return None, "본문(content)이 비어 있음 (reasoning만 반환된 듯)"

        elapsed = time.time() - started
        print("[LLM] %s 응답 %.1f초, %d자" % (model_name, elapsed, len(text)), flush=True)
        return LLMResponse(text, model=model_name), None

    except requests.Timeout:
        return None, "timeout (%d초 초과)" % READ_TIMEOUT
    except Exception as e:
        return None, str(e)
