#!/bin/sh
set -e

# 키는 이미지에 굽지 않는다. app.env 로 받아 서버에 넘긴다.
if [ -z "$LLM_BASE_URL" ] || [ -z "$LLM_API_KEY" ]; then
  echo "LLM_BASE_URL / LLM_API_KEY 가 비어 있습니다. app.env 를 확인하세요." >&2
  exit 1
fi

# 감정서는 흘려보내므로(SSE) 프록시가 모아 두지 않게 해야 한다.
exec uvicorn server:app \
  --host 0.0.0.0 \
  --port 8501 \
  --workers 1 \
  --timeout-keep-alive 75 \
  --proxy-headers \
  --no-access-log
