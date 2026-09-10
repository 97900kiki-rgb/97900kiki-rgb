# -*- coding: utf-8 -*-
"""얼굴을 찾아 반듯하게 잘라 준다. 메일용 타원·보관용 크롭·화면용 모프를 함께 만든다.

왜 따로 뒀나 — 메일(`mailer`)과 보관(`leads`)이 **같은 기준으로** 자르지 않으면
메일에 나간 얼굴과 DB 에 남은 얼굴이 달라진다. 한 군데서 정한다.

**검출은 MediaPipe FaceMesh 가 맡는다(468점).** 전에는 Haar 만 썼는데,
안경을 썼거나 고개를 조금만 숙여도 얼굴을 통째로 놓쳤다. 그러면 "가운데 자르기"로
물러서면서 배경이 잔뜩 든 그림이 감정서에 실렸다. FaceMesh 는 그런 얼굴도 잡고,
덤으로 눈·코·턱 위치를 알려 주어 **얼굴을 틀 한가운데에 놓을 수 있다.**
GPU 는 쓰지 않는다 — CPU 로 수십 ms 면 끝나고, GPU 를 붙이면 이미지만 몇 GB 불어난다.

Haar 는 폴백으로 남긴다. MediaPipe 가 없거나 터져도 앱은 돌아야 한다.
그마저 실패하면 가운데를 자른다.

배경을 실제로 지우지는 않는다. `rembg` 같은 분리 모델은 400MB 가 넘고 요청마다
수 초가 드는데, **얼굴을 틀에 꽉 채우면** 배경이 거의 남지 않아 눈에 보이는
결과가 거의 같다.
"""
import io
import os
import threading

# 세로 타원 기본 크기. 240x320(3:4)은 너무 갸름해 얼굴이 눌려 보였다.
# 300x330 은 동그라미에 가깝다. 바꾸면 mailer 의 <img width height> 도 함께 고칠 것.
OVAL_W, OVAL_H = 300, 330

# 얼굴 폭의 몇 배를 틀에 담을지. 1.0 이면 얼굴만, 크면 여백이 는다.
WIDTH_RATIO = 1.45
# 눈이 틀의 위에서 몇 쯤에 오게 할지. 초상 사진은 눈이 조금 위에 있어야 편안하다.
EYE_LINE = 0.42
# Haar 폴백에서 쓰는 값(랜드마크가 없어 눈 위치를 모를 때).
HAAR_WIDTH_RATIO = 1.70
HAAR_CENTER_Y = 0.50

# 모델은 이미지를 구울 때 미리 받아 둔다(Dockerfile). 실행 중에 내려받으면
# 첫 손님이 그 시간을 기다리고, 바깥이 막히면 아예 못 쓴다.
MODEL_PATH = os.environ.get("FACE_MODEL", "/app/models/face_landmarker.task")

# FaceLandmarker 는 만들 때 모델을 읽어 한참 걸린다. 요청마다 새로 만들면
# 그 값이 그대로 화면 지연이 되므로 한 번 만들어 두고 계속 쓴다.
# detect() 가 여러 갈래에서 동시에 불릴 수 있어 자물쇠를 채운다.
_LANDMARKER = None
_LOCK = threading.Lock()


def _landmarker():
    """mediapipe 1.x 의 tasks API. 옛 `mp.solutions.face_mesh` 는 없어졌다."""
    global _LANDMARKER
    if _LANDMARKER is None:
        from mediapipe.tasks import python as mpp
        from mediapipe.tasks.python import vision
        _LANDMARKER = vision.FaceLandmarker.create_from_options(
            vision.FaceLandmarkerOptions(
                base_options=mpp.BaseOptions(model_asset_path=MODEL_PATH),
                running_mode=vision.RunningMode.IMAGE,
                num_faces=1,
                # 기본값 0.5 는 멀리 찍힌 작은 얼굴을 놓친다. 여기서는 못 찾는
                # 편이 훨씬 나쁘다 — 못 찾으면 배경만 든 그림이 감정서에 실린다.
                min_face_detection_confidence=0.25,
                min_face_presence_confidence=0.25))
    return _LANDMARKER


def landmarks(im):
    """얼굴 478점을 사진 좌표로. 못 찾거나 mediapipe 가 없으면 None.

    돌려주는 값은 [(x, y), ...] 이다(눈동자 10점 포함).
    """
    try:
        import numpy as np
        import mediapipe as mp
    except Exception:
        return None
    try:
        arr = np.asarray(im.convert("RGB"))
        mpimg = mp.Image(image_format=mp.ImageFormat.SRGB, data=arr)
        with _LOCK:
            res = _landmarker().detect(mpimg)
        if not res.face_landmarks:
            return None
        ih, iw = arr.shape[:2]
        return [(p.x * iw, p.y * ih) for p in res.face_landmarks[0]]
    except Exception as e:
        # 조용히 삼키면 왜 Haar 로 물러섰는지 알 길이 없다. 한 줄은 남긴다.
        print("[faceutil] 랜드마크 실패:", e, flush=True)
        return None


def _haar_face(im):
    """Haar 폴백. 정면 분류기 셋을 차례로 써 보고, 마지막에 옆얼굴까지 본다."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    try:
        gray = cv2.cvtColor(np.asarray(im.convert("RGB")), cv2.COLOR_RGB2GRAY)
        gray = cv2.equalizeHist(gray)
        # 큰 사진은 줄여서 본다 — 느리기도 하고 잔무늬를 얼굴로 오인하기도 한다.
        h, w = gray.shape[:2]
        scale = 1.0
        if max(h, w) > 900:
            scale = 900.0 / max(h, w)
            gray = cv2.resize(gray, (int(w * scale), int(h * scale)))
        for xml in ("haarcascade_frontalface_alt2.xml",
                    "haarcascade_frontalface_default.xml",
                    "haarcascade_frontalface_alt.xml",
                    "haarcascade_profileface.xml"):
            casc = cv2.CascadeClassifier(cv2.data.haarcascades + xml)
            if casc.empty():
                continue
            faces = casc.detectMultiScale(gray, 1.08, 4, minSize=(40, 40))
            if len(faces):
                f = max(faces, key=lambda b: int(b[2]) * int(b[3]))
                return tuple(int(round(v / scale)) for v in f)
    except Exception:
        pass
    return None


def find_face(im):
    """가장 큰 얼굴의 (x, y, w, h). 못 찾으면 None.

    `mailer` · `leads` 가 예전부터 쓰던 이름이라 반환 모양을 바꾸지 않는다.
    """
    pts = landmarks(im)
    if pts:
        return _box_of(pts)
    return _haar_face(im)


def _box_of(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    return (int(x0), int(y0), int(x1 - x0), int(y1 - y0))


def _mean(pts, idx):
    sel = [pts[i] for i in idx if i < len(pts)]
    if not sel:
        return None
    return (sum(p[0] for p in sel) / len(sel), sum(p[1] for p in sel) / len(sel))


def eye_angle(pts):
    """두 눈을 잇는 선이 수평에서 몇 도 기울었는지. 못 재면 None.

    화면 좌표는 y 가 아래로 자라므로, 값이 크면 오른쪽 눈이 더 아래에 있다는 뜻이다.
    """
    import math
    L = _mean(pts, [33, 133])       # 한쪽 눈
    R = _mean(pts, [362, 263])      # 반대쪽 눈
    if not L or not R:
        return None
    return math.degrees(math.atan2(R[1] - L[1], R[0] - L[0]))


def pose(pts):
    """고개가 어디를 보고 있는지. (yaw, pitch) 를 -1~1 로 준다. 못 재면 (0, 0).

    yaw  좌우 돌아감 — 0 이 정면. 양수·음수는 방향이고, 크기가 중요하다.
    pitch 위아래 — 0 이 정면. 양수면 숙인 쪽, 음수면 든 쪽.

    ⚠️ 측면 얼굴을 정면으로 **돌려 세울 수는 없다.** 그러려면 3D 얼굴을 다시
    지어내야 하는데(무겁고 결과도 못 믿는다), 그렇게 지어낸 얼굴로 관상을 보는
    것은 앞뒤가 안 맞는다. 그래서 재기만 하고, 많이 돌아갔으면 **다시 담으시라고
    말한다.** 기울기(roll)만은 `align` 이 실제로 바로 세운다 — 그건 평면 회전이라
    없는 것을 지어내지 않기 때문이다.
    """
    try:
        L, R = pts[234], pts[454]        # 왼쪽·오른쪽 얼굴 가장자리
        N = pts[1]                       # 코끝
        dl, dr = abs(N[0] - L[0]), abs(R[0] - N[0])
        yaw = (dr - dl) / (dr + dl) if (dr + dl) else 0.0

        _ex, ey = _eye_center(pts)
        ny, cy = pts[1][1], pts[152][1]  # 코끝, 턱끝
        upper, lower = ny - ey, cy - ny
        if upper > 0 and lower > 0:
            # 정면이면 눈~코와 코~턱이 엇비슷하다. 숙이면 코~턱이 짧아진다.
            r = upper / lower
            pitch = max(-1.0, min(1.0, (r - 1.0)))
        else:
            pitch = 0.0
        return float(yaw), float(pitch)
    except Exception:
        return 0.0, 0.0


# 이보다 크면 다시 담으시라고 한다. 넉넉히 잡았다 — 조금 돌아간 얼굴까지
# 퇴짜 놓으면 아무도 못 찍는다.
YAW_LIMIT = 0.22
PITCH_LIMIT = 0.42


def facing_note(pts):
    """정면을 보고 있는지. (괜찮은가, 사람에게 할 말). 괜찮으면 (True, "")."""
    if not pts:
        return False, "얼굴을 찾지 못했소."
    yaw, pitch = pose(pts)
    ang = eye_angle(pts) or 0.0
    if abs(yaw) > YAW_LIMIT:
        side = "왼쪽" if yaw > 0 else "오른쪽"
        return False, ("고개가 %s으로 돌아갔소. **정면을 바라보고** 다시 담아 주시오."
                       % side)
    if pitch > PITCH_LIMIT:
        return False, "고개를 숙이셨소. **턱을 조금 드시고** 다시 담아 주시오."
    if pitch < -PITCH_LIMIT:
        return False, "고개를 드셨소. **턱을 조금 당기시고** 다시 담아 주시오."
    if abs(ang) > 25:
        return True, "고개가 기울었으나 아솔이 바로 세워 보았소."
    return True, ""


def align(im, pts, min_deg=1.0, max_deg=89.0):
    """눈이 수평이 되도록 사진을 돌린다. (돌린사진, 새 랜드마크, 돌린각) 을 준다.

    왜 하나 — 고개를 갸웃한 채 찍으면 (1) 잘라 낸 얼굴이 비뚤어 보이고
    (2) **얼굴 특징값이 흔들려 같은 사람을 못 알아본다.** 재방문자 인식을
    붙이려면 정렬이 먼저다. 얼굴 인식에서 정렬은 선택이 아니라 기본이다.

    돌린 **뒤에 랜드마크를 다시 찾는다.** 좌표를 손으로 회전시키면 부호 하나로
    조용히 틀어지는데, 다시 찾으면 그럴 일이 없고 비용도 몇 ms 뿐이다.
    다시 못 찾으면 돌리지 않은 원본을 그대로 쓴다 — 어설프게 돌린 것보다 낫다.

    상한을 89도까지 둔 까닭 — 처음엔 45도로 막았더니 옆으로 누운 사진을 못 세웠고,
    **같은 사람인데 특징값이 0.06 까지 떨어졌다**(문턱값 0.363). 눈 기울기로 도는
    것은 각이 커도 옳은 계산이라 막을 이유가 없다. 돌린 뒤 되레 더 기울면
    아래에서 되돌리므로 안전하다.
    """
    from PIL import Image

    ang = eye_angle(pts)
    if ang is None or abs(ang) < min_deg or abs(ang) > max_deg:
        return im, pts, 0.0

    cx, cy = _eye_center(pts)
    rot = im.rotate(ang, resample=Image.BICUBIC, center=(cx, cy),
                    expand=False, fillcolor=(255, 255, 255))
    pts2 = landmarks(rot)
    if not pts2:
        return im, pts, 0.0
    # 되레 더 기울었으면 방향이 틀린 것이다. 그럴 땐 원본을 쓴다.
    ang2 = eye_angle(pts2)
    if ang2 is not None and abs(ang2) > abs(ang):
        return im, pts, 0.0
    return rot, pts2, ang


def face_span(pts):
    """이마(헤어라인)까지 포함한 얼굴 상자 (x, y, w, h). 못 재면 478점 상자 그대로.

    왜 따로 재나 — MediaPipe 478 점은 **이마 중간에서 끝난다.** 헤어라인까지 가지
    않는다. 그런데 관상은 "이마가 넓다"는 말을 하는 판이라, 이마가 잘리면 볼 것을
    못 보고 잘라 내는 셈이 된다.

    그래서 **삼정(三停)** 으로 메운다. 얼굴을 상정(이마)·중정(눈썹~코밑)·
    하정(코밑~턱)으로 나누면 셋이 엇비슷하다는 것이 관상의 오랜 셈법이다.
    아래 둘은 점으로 잴 수 있으니, 그 평균만큼 눈썹 위로 올리면 상정이 나온다.
    """
    fx, fy, fw, fh = _box_of(pts)
    try:
        # 눈썹 위쪽(양쪽 눈썹 점들 중 가장 높은 곳), 코밑, 턱끝
        brow = min(pts[i][1] for i in
                   (70, 63, 105, 66, 107, 336, 296, 334, 293, 300) if i < len(pts))
        nose = pts[2][1]          # 코밑
        chin = pts[152][1]        # 턱끝
        mid, low = nose - brow, chin - nose
        if mid <= 0 or low <= 0:
            return fx, fy, fw, fh
        top = brow - (mid + low) / 2.0        # 상정 = 중정·하정의 평균만큼
        top = max(top, fy - fh * 1.2)         # 터무니없이 올라가지 않게
        if top >= fy:                         # 이미 478점이 더 위면 그대로 둔다
            return fx, fy, fw, fh
        return fx, int(top), fw, int(chin - top)
    except Exception:
        return fx, fy, fw, fh


def _eye_center(pts):
    """두 눈 사이 한가운데. 얼굴을 어디에 놓을지는 눈이 정한다 — 초상 사진의 기본이다."""
    # 33 오른눈 바깥, 133 오른눈 안쪽, 362 왼눈 안쪽, 263 왼눈 바깥 (FaceMesh 표준 번호)
    idx = [33, 133, 362, 263]
    if len(pts) > max(idx):
        sel = [pts[i] for i in idx]
        return (sum(p[0] for p in sel) / 4.0, sum(p[1] for p in sel) / 4.0)
    x, y, w, h = _box_of(pts)
    return (x + w / 2.0, y + h * 0.42)


def _fit_box(iw, ih, cx, cy, bw, bh):
    """(cx,cy) 를 가운데 두는 bw×bh 상자를 사진 **안으로** 밀어 넣는다.

    이 밀어 넣기가 없으면 얼굴이 가장자리에 있을 때 상자가 사진 밖으로 나가고,
    PIL 은 그 부분을 검게 채운다. 먼저 밀어 보고, 그래도 넘치면 상자를 줄인다.
    """
    if bw > iw:
        bh *= iw / float(bw)
        bw = float(iw)
    if bh > ih:
        bw *= ih / float(bh)
        bh = float(ih)
    left = min(max(cx - bw / 2.0, 0.0), iw - bw)
    top = min(max(cy - bh / 2.0, 0.0), ih - bh)
    return (int(round(left)), int(round(top)),
            int(round(left + bw)), int(round(top + bh)))


def _crop_box(im, w, h, pts=None, face=None):
    """자르기 상자. 상자를 따로 뺀 까닭은 `mesh_png` 가 **같은 상자**를 알아야
    선을 제자리에 그릴 수 있기 때문이다.

    랜드마크가 있으면 눈높이로 맞춘다(얼굴이 한가운데 온다).
    없으면 예전처럼 Haar 상자만 보고 어림잡는다.
    """
    iw, ih = im.size

    if pts:
        # 478점 상자가 아니라 **이마까지 포함한** 상자를 쓴다. 관상은 이마를 보는데
        # 478점은 이마 중간에서 끝나므로, 그대로 쓰면 이마가 잘려 나간다.
        fx, fy, fw, fh = face_span(pts)
        ex, ey = _eye_center(pts)
        bw = fw * WIDTH_RATIO
        bh = bw * (h / float(w))
        if bh < fh * 1.12:              # 이마와 턱이 잘리지 않게
            bh = fh * 1.12
            bw = bh * (w / float(h))
        # 눈이 틀의 EYE_LINE 자리에 오도록 상자 중심을 잡는다
        cx = ex
        cy = ey + bh * (0.5 - EYE_LINE)
    elif face is not None:
        fx, fy, fw, fh = face
        cx = fx + fw / 2.0
        cy = fy + fh * HAAR_CENTER_Y
        bw = fw * HAAR_WIDTH_RATIO
        bh = bw * (h / float(w))
        if bh < fh * 1.45:
            bh = fh * 1.45
            bw = bh * (w / float(h))
    else:
        scale = max(w / float(iw), h / float(ih))
        bw, bh = w / scale, h / scale
        cx, cy = iw / 2.0, ih * 0.42

    return _fit_box(iw, ih, cx, cy, bw, bh)


def _prepare(img, w, h):
    """(잘린 그림, 자르기상자, 랜드마크) 한 벌.

    얼굴 찾기를 한 번만 하려고 묶었고, **여기서 기울기도 바로 세운다.**
    상자와 랜드마크는 둘 다 *돌린 뒤* 좌표계라, 부르는 쪽은 신경 쓸 것이 없다.
    """
    from PIL import Image

    im = img.convert("RGB")
    pts = landmarks(im)
    if pts:
        im, pts, _ = align(im, pts)
    face = None if pts else _haar_face(im)
    box = _crop_box(im, w, h, pts=pts, face=face)
    return im.crop(box).resize((w, h), Image.LANCZOS), box, pts


def face_crop(img, w, h):
    """얼굴을 가운데 둔 w×h 이미지. 얼굴을 못 찾으면 가운데를 자른다."""
    return _prepare(img, w, h)[0]


def oval_png(img, w=OVAL_W, h=OVAL_H, bg=(255, 255, 255)):
    """메일에 넣을 타원 PNG.

    메일에서는 CSS ``border-radius`` 를 믿을 수 없으므로(Outlook 이 무시한다)
    **이미지 자체를** 타원으로 만든다. 투명 PNG 도 클라이언트마다 배경이 달라
    지저분해지므로 흰 바탕에 올려 불투명하게 굽고, 가장자리를 살짝 흐려
    오려 붙인 느낌을 낸다.
    """
    from PIL import Image, ImageDraw, ImageFilter

    im = face_crop(img, w, h)

    S = 4                                   # 4배로 그렸다 줄여 계단을 없앤다
    mask = Image.new("L", (w * S, h * S), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, w * S - 1, h * S - 1), fill=255)
    mask = mask.resize((w, h), Image.LANCZOS).filter(ImageFilter.GaussianBlur(2.0))

    out = Image.new("RGB", (w, h), bg)
    out.paste(im, (0, 0), mask)

    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def mesh_png(img, w=OVAL_W, h=OVAL_H, dim=0.07):
    """얼굴 위에 **가느다란 모프(메시)** 를 얹은 PNG.

    타원은 결과만 보여 줄 뿐 '왜 그렇게 잘렸는지'를 말해 주지 않는다.
    아솔이 얼굴을 어떻게 읽었는지 그물로 그려 주면, 엉뚱한 데를 잡았을 때
    사람이 바로 알아채고 다시 찍는다.

    **얼굴이 묻히면 안 된다.** 처음엔 사진을 많이 어둡게 깔고 선을 굵게 그렸더니
    그물만 보이고 사람이 안 보였다. 그래서 (1) 어둡게 하는 정도를 확 줄이고
    (2) 3배로 그렸다 줄여 선을 1픽셀 두께로 가늘게 뽑는다.

    얼굴로 본 영역은 **타원으로 따로 표시한다 — 이마까지 들어간다.**
    478 점의 위끝이 이마 언저리라, 그 상자에 맞춘 타원이 곧 "여기를 얼굴로 봤소"다.

    얼굴을 못 찾았으면 그물 없이 크롭만 돌려준다 — 못 찾았다는 말은 화면이 한다.
    """
    from PIL import Image, ImageDraw, ImageEnhance

    crop, box, pts = _prepare(img, w, h)
    if not pts:
        buf = io.BytesIO()
        crop.save(buf, format="PNG", optimize=True)
        return buf.getvalue()

    base = ImageEnhance.Brightness(crop).enhance(1.0 - dim).convert("RGBA")
    sx = w / float(box[2] - box[0])
    sy = h / float(box[3] - box[1])

    def at(i):
        x, y = pts[i]
        return ((x - box[0]) * sx, (y - box[1]) * sy)

    # 선을 가늘고 은은하게 얻는 두 가지 수 —
    #  (1) 3배로 크게 그렸다 줄인다. PIL 에는 안티에일리어싱이 없어서, 이것이
    #      1픽셀짜리 매끈한 선을 얻는 유일한 방법이다.
    #  (2) 따로 만든 투명한 장에 그려서 겹친다. 색을 옅게 하는 것과 달리
    #      **얼굴 살결이 선 밑으로 비쳐** 사람이 묻히지 않는다.
    #      처음엔 불투명하게 그렸더니 그물만 보이고 얼굴이 안 보였다.
    # S 를 4 로 크게 잡고 선은 S 보다 **가늘게** 긋는다. 줄이고 나면 1픽셀도 안 되는
    # 실선이 되어, 색이 옅게 퍼지며 자연히 반투명해진다. 굵기를 S 로 두면 딱 1픽셀
    # 실선이라 또렷하게 남는다 — 그게 "여전히 투박하다"는 소리를 들은 까닭이다.
    S = 4
    layer = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    from mediapipe.tasks.python.vision import FaceLandmarksConnections as C

    import math

    def seg(p0, p1, color, width, dash=0, gap=0):
        """한 선분. dash 를 주면 끊어 그린다 — PIL 에는 점선이 없어 직접 나눈다.

        점선으로 하는 까닭 — 실선 그물은 굵히는 순간 얼굴을 덮어 버린다.
        끊어 그리면 같은 굵기라도 살결이 사이사이로 비쳐 **굵으면서도 가볍다.**
        """
        x0, y0 = p0[0] * S, p0[1] * S
        x1, y1 = p1[0] * S, p1[1] * S
        if not dash:
            d.line([x0, y0, x1, y1], fill=color, width=width)
            return
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy)
        if L < 1:
            return
        ux, uy = dx / L, dy / L
        t = 0.0
        while t < L:
            t2 = min(t + dash, L)
            d.line([x0 + ux * t, y0 + uy * t, x0 + ux * t2, y0 + uy * t2],
                   fill=color, width=width)
            t += dash + gap

    def draw(conns, color, width, dash=0, gap=0):
        for c in conns:
            a, b = c.start, c.end
            if a < len(pts) and b < len(pts):
                seg(at(a), at(b), color, width, dash, gap)

    # 선은 어두운 먹빛으로. 밝은 선은 살결 위에서 번져 보이는데, 어두운 선은
    # 또렷하면서도 사진을 덜 가린다. 붓으로 그은 듯해 관상 화면에도 어울린다.
    # 그물은 2556 선이라 실선으로 굵히면 얼굴을 덮는다. 굵히되 **끊어** 그린다.
    draw(C.FACE_LANDMARKS_TESSELATION, (24, 32, 30, 95), 4, dash=9, gap=7)
    # 눈·눈썹·코·입은 실선으로 또렷하게. 여기는 끊으면 모양이 안 읽힌다.
    for conns in (C.FACE_LANDMARKS_LEFT_EYE, C.FACE_LANDMARKS_RIGHT_EYE,
                  C.FACE_LANDMARKS_LEFT_EYEBROW, C.FACE_LANDMARKS_RIGHT_EYEBROW,
                  C.FACE_LANDMARKS_NOSE, C.FACE_LANDMARKS_LIPS):
        draw(conns, (16, 20, 26, 200), 5)
    for conns in (C.FACE_LANDMARKS_LEFT_IRIS, C.FACE_LANDMARKS_RIGHT_IRIS):
        draw(conns, (12, 40, 72, 215), 5)

    # 얼굴로 본 영역 — **이마(헤어라인)까지** 감싸는 타원. 관상은 이마를 보고
    # 말하는 판이라, 이마가 타원 밖에 있으면 안 본 것처럼 읽힌다.
    # 위끝은 삼정으로 추정한 자리라 여유를 더 얹지 않는다. 턱 쪽만 조금 준다.
    fx, fy, fw, fh = face_span(pts)
    pad_x = fw * 0.08
    pad_bot = fh * 0.03
    x0 = (fx - pad_x - box[0]) * sx
    y0 = (fy - box[1]) * sy
    x1 = (fx + fw + pad_x - box[0]) * sx
    y1 = (fy + fh + pad_bot - box[1]) * sy
    # 타원도 끊어 그린다 — 그물과 결을 맞추고, 얼굴 가장자리를 막지 않는다.
    # PIL 의 ellipse 로는 점선을 못 그리니 각도를 돌며 잇는다.
    _cx, _cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    _rx, _ry = (x1 - x0) / 2.0, (y1 - y0) / 2.0
    _N = 180
    _prev = None
    for _i in range(_N + 1):
        _t = 2 * math.pi * _i / _N
        _p = (_cx + _rx * math.cos(_t), _cy + _ry * math.sin(_t))
        if _prev is not None and (_i % 6) < 4:      # 넷 긋고 둘 쉰다
            d.line([_prev[0] * S, _prev[1] * S, _p[0] * S, _p[1] * S],
                   fill=(38, 28, 32, 175), width=5)
        _prev = _p

    layer = layer.resize((w, h), Image.LANCZOS)
    out = Image.alpha_composite(base, layer).convert("RGB")
    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────
# 얼굴 특징값 — 다시 온 사람을 알아보는 데 쓴다.
#
# ⚠️ 이것은 **생체정보**다. 개인정보보호법상 민감정보이므로 별도의 명시적
#    동의 없이 만들어 두거나 저장해서는 안 된다. 저장 여부는 leads 가 정한다.
# ─────────────────────────────────────────────────────────────────────────

SFACE_PATH = os.environ.get("SFACE_MODEL", "/app/models/sface.onnx")
SFACE_INPUT = 112                 # SFace 가 받는 입력 크기
# OpenCV 가 권장하는 동일인 문턱값. 코사인이 이보다 크면 같은 사람으로 본다.
SAME_PERSON = 0.363

_SFACE = None


def _sface():
    global _SFACE
    if _SFACE is None:
        import cv2
        _SFACE = cv2.FaceRecognizerSF.create(SFACE_PATH, "")
    return _SFACE


def embed(img):
    """얼굴 특징값 128개(float32, **평평한 1차원**). 얼굴이 없거나 실패하면 None.

    SFace 는 (1, 128) 모양으로 돌려주는데, 그대로 넘기면 받는 쪽에서 하나씩
    꺼낼 때 숫자가 아니라 배열이 나온다(leads.find_person 이 실제로 여기서 터졌다).
    담는 쪽·비교하는 쪽 모두 "숫자 128개"를 기대하므로 여기서 펴서 넘긴다.

    넣기 전에 `_prepare` 로 **기울기를 세우고 같은 규칙으로 자른다.** 등록할 때와
    맞춰 볼 때가 같은 손질을 거쳐야 점수가 흔들리지 않는다. 정렬을 빼먹으면
    같은 사람인데도 점수가 뚝 떨어져 못 알아본다.
    """
    try:
        import cv2
        import numpy as np

        crop, _box, pts = _prepare(img, SFACE_INPUT, SFACE_INPUT)
        if not pts:                      # 얼굴을 못 찾았으면 특징값도 뜻이 없다
            return None
        bgr = cv2.cvtColor(np.asarray(crop), cv2.COLOR_RGB2BGR)
        vec = np.asarray(_sface().feature(bgr), dtype="float32").reshape(-1)
        # 평범한 숫자 목록으로 넘긴다. numpy 배열을 넘기면 받는 쪽에서 `vec or []`
        # 같은 흔한 표현이 "배열의 참거짓이 모호하다"며 터진다(실제로 그랬다).
        # 담는 쪽·비교하는 쪽 모두 "숫자 128개"만 알면 되므로 이쪽이 낫다.
        return [float(x) for x in vec]
    except Exception as e:
        print("[faceutil] 특징값 실패:", e, flush=True)
        return None


def cosine(a, b):
    """두 특징값이 얼마나 닮았는지(-1~1). 클수록 같은 사람. 실패하면 None."""
    try:
        import cv2
        import numpy as np
        a = np.asarray(a, dtype="float32").reshape(1, -1)
        b = np.asarray(b, dtype="float32").reshape(1, -1)
        return float(_sface().match(a, b, cv2.FaceRecognizerSF_FR_COSINE))
    except Exception as e:
        print("[faceutil] 비교 실패:", e, flush=True)
        return None


def pack(vec):
    """특징값을 DB 에 넣을 바이트로. numpy 를 모르는 쪽에서도 다루게."""
    import numpy as np
    return np.asarray(vec, dtype="float32").reshape(-1).tobytes()


def unpack(blob):
    """`pack` 이 만든 바이트를 다시 특징값으로."""
    import numpy as np
    return np.frombuffer(blob, dtype="float32").reshape(1, -1)


def quality(img):
    """사진이 얼굴 등록에 쓸 만한지 0~1 점수와 까닭. (점수, 설명) 을 준다.

    여러 번 온 사람의 사진 중 **가장 좋은 것**을 골라 두려고 쓴다. 흐리거나
    얼굴이 작은 사진으로 등록해 두면 다음에 와도 못 알아본다.
    """
    try:
        import cv2
        import numpy as np

        im = img.convert("RGB")
        pts = landmarks(im)
        if not pts:
            return 0.0, "얼굴을 찾지 못했소."

        iw, ih = im.size
        _fx, _fy, fw, fh = _box_of(pts)
        size = min(fw / float(iw), 1.0)                 # 얼굴이 사진에서 차지하는 폭
        ang = abs(eye_angle(pts) or 0.0)

        gray = cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2GRAY)
        sharp = cv2.Laplacian(gray, cv2.CV_64F).var()   # 흐릴수록 작다

        s_size = min(size / 0.35, 1.0)                  # 폭의 35% 면 만점
        s_sharp = min(sharp / 120.0, 1.0)               # 경험값
        s_ang = max(0.0, 1.0 - ang / 30.0)              # 30도 넘게 기울면 0점
        score = 0.5 * s_size + 0.3 * s_sharp + 0.2 * s_ang

        why = []
        if s_size < 0.6:
            why.append("얼굴이 작소 — 가까이 오시오")
        if s_sharp < 0.5:
            why.append("흐릿하오 — 밝은 곳에서 다시")
        if s_ang < 0.7:
            why.append("고개가 기울었소")
        return round(score, 3), " · ".join(why) or "좋소."
    except Exception as e:
        print("[faceutil] 품질 판정 실패:", e, flush=True)
        return 0.0, "판정하지 못했소."


def face_jpeg(img, w=480, h=640, jpeg_quality=88):
    """보관용 얼굴 크롭. 타원 마스크를 씌우지 않는다.

    마스크는 보여 주는 방식일 뿐이고, 나중에 다른 데 쓰려면 **가려지지 않은**
    크롭이 훨씬 쓸모 있다. 필요하면 그때 다시 타원을 씌우면 된다.
    """
    buf = io.BytesIO()
    # 이름을 jpeg_quality 로 둔 까닭 — 이 파일에 quality() 함수가 생겨서,
    # 인자 이름을 quality 로 두면 그 함수를 PIL 에 넘겨 버린다(실제로 그랬다).
    face_crop(img, w, h).save(buf, format="JPEG", quality=jpeg_quality, optimize=True)
    return buf.getvalue()
