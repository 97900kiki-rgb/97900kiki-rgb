FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Asia/Seoul

# mediapipe 1.x 의 네이티브 라이브러리는 libEGL/libGLES 를 dlopen 한다. 없으면
# FaceLandmarker 를 만드는 순간 OSError 로 죽는다(화면이 없어도 필요하다).
# opencv-contrib 는 headless 판이 아니라 libGL 도 찾는다.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libgl1 libglib2.0-0 libegl1 libgles2 libopengl0 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app/ /app/
COPY entrypoint.sh /entrypoint.sh

# 얼굴 랜드마크 모델(3.8MB)을 구울 때 받아 둔다. 실행 중에 내려받으면
# 첫 손님이 그 시간을 고스란히 기다리고, 바깥이 막히면 아예 못 쓴다.
RUN mkdir -p /app/models \
 && python -c "import urllib.request; urllib.request.urlretrieve('https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task', '/app/models/face_landmarker.task')" \
 && python -c "import urllib.request; urllib.request.urlretrieve('https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx', '/app/models/sface.onnx')" \
 && ls -l /app/models

RUN chmod +x /entrypoint.sh \
 && chown -R 1000:1000 /app

# mediapipe·matplotlib 이 홈에 캐시를 쓰려 한다. 1000 번 사용자에게는 집이 없어
# /.local 에 쓰려다 막히므로, 쓸 수 있는 자리를 정해 준다.
ENV HOME=/app XDG_CACHE_HOME=/app/.cache MPLCONFIGDIR=/app/.cache/mpl \
    FACE_MODEL=/app/models/face_landmarker.task \
    SFACE_MODEL=/app/models/sface.onnx
RUN mkdir -p /app/.cache/mpl && chown -R 1000:1000 /app/.cache

USER 1000:1000
EXPOSE 8501
ENTRYPOINT ["/entrypoint.sh"]
