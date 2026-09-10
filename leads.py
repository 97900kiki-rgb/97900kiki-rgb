# -*- coding: utf-8 -*-
"""남긴 사람을 담고, 다시 오셨을 때 알아본다.

개인정보라 다루는 규칙을 코드에 박아 둔다 — 화면에 적어 둔 약속과
실제 동작이 어긋나면 그게 제일 나쁘다.

  · 수집 항목 : 이름, 이메일, 휴대전화번호, 얼굴 사진, 감정서 내용
                그리고 **선택 동의**를 받은 경우에만
                얼굴 특징값 · 그날의 기분과 컨디션
  · 수집 목적 : 감정서 발송 · 재방문 확인 · 얼굴과 기록의 변화 살펴보기
  · 보유 기간 : RETAIN_DAYS 일. **열 때마다 지난 것을 실제로 지운다.**
  · 동의 없이는 저장하지 않는다(save/remember 가 거부한다).
  · 얼굴 특징값은 개인정보 보호법상 **민감정보**다. 사람이 적는 기분·컨디션도
    건강에 관한 내용이 담길 수 있어 같은 무게로 다룬다. 그래서 **별도 동의**를
    받고, 동의가 없거나 무르면 **저장하지 않고 이미 있던 것도 지운다.**
  · 이 서비스는 건강을 진단하지 않는다. 문구(NO_MEDICAL)에 적어 두었고,
    적어 둔 대로 코드도 그렇게 둔다.

표 넷
  leads   기존 그대로. 한 번 남길 때마다 한 줄. 되돌릴 자리로 남겨 둔다.
  people  사람 하나. 이름·연락처·방문 횟수·생체정보 동의 여부.
  faces   얼굴 특징값. 사람 하나에 여러 장(시간에 따른 변화를 쌓는다).
  visits  방문 하나. 그때의 나이·성별·감정서 요약·기분·컨디션.

파일은 컨테이너 볼륨(`data/`)에 있어 이미지를 다시 구워도 남고,
`.gitignore` 로 저장소에는 들어가지 않는다.
"""
import os
import re
import math
import array
import sqlite3
import datetime
import contextlib

DB_PATH = os.getenv("LEADS_DB", "data/leads.db")
RETAIN_DAYS = int(os.getenv("LEADS_RETAIN_DAYS", "365"))

# 같은 사람으로 볼 코사인 문턱값. OpenCV SFace 권장치.
FACE_THRESHOLD = float(os.getenv("LEADS_FACE_THRESHOLD", "0.363"))
# 감정서를 통째로 담지 않는다. 다음 방문 때 참고할 만큼만.
SUMMARY_MAX = 800
# 기분·컨디션은 "한 줄"이다. 길게 적을 칸이 아니다.
MOOD_MAX = 200
# 본인 확인용 이야기. 한두 문장이면 된다.
SECRET_MAX = 500


def _trim(s, n):
    """앞 n 글자만. 비었으면 None — 빈 문자열을 넣어 두면 '적었는데 비었다'와
    '아예 안 적었다'를 구분할 수 없다."""
    s = (s or "").strip()
    return s[:n] or None

# 국내 휴대전화. 하이픈이 있든 없든 받고, 숫자만 남겨 비교한다.
PHONE_RE = re.compile(r"^0\d{1,2}\d{7,8}$")


def normalize_phone(raw):
    """숫자만 남긴다. 사람마다 010-1234-5678 / 01012345678 / 010 1234 5678 로 쓴다."""
    return re.sub(r"\D", "", raw or "")


def valid_phone(raw):
    """제대로 된 번호인가. **화면에서 '적으셨을 때'만** 물어야 한다 — 아래 참조."""
    return bool(PHONE_RE.match(normalize_phone(raw)))


def _phone_ok(raw):
    """비워 두셔도 되고, 적으셨으면 제대로여야 한다.

    개인정보 보호법 제16조 3항은 **필수가 아닌 항목에 동의하지 않았다는 이유로
    서비스를 거부하지 못하게** 한다. 감정서를 메일로 보내는 데 전화번호는
    필요하지 않다(메일 주소면 된다). 그래서 저장 쪽에서는 빈 값을 받는다.
    화면에서 계속 받으실 거면 **선택 항목으로** 두시면 된다.
    """
    ph = normalize_phone(raw)
    return (True, "") if (not ph or PHONE_RE.match(ph)) \
        else (False, "휴대전화번호를 확인해 주세요.")


def valid_name(raw):
    n = (raw or "").strip()
    return 2 <= len(n) <= 30


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _conn():
    d = os.path.dirname(DB_PATH)
    if d:
        os.makedirs(d, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


@contextlib.contextmanager
def _db():
    """열고 · 성공하면 커밋 · 반드시 닫는다.

    `with sqlite3.connect(...)` 만 쓰면 **커밋은 되지만 닫히지 않는다.**
    Streamlit 은 조작 한 번에 스크립트를 통째로 다시 돌리므로, 닫지 않으면
    연결이 계속 쌓인다. 그래서 닫는 것까지 여기서 책임진다.
    """
    c = _conn()
    try:
        with c:
            yield c
    finally:
        c.close()


# ── 얼굴 특징값 담기 ──────────────────────────────────────────────────────
# 길이가 1이 되도록 미리 맞춰(L2 정규화) 담는다. 그러면 코사인 유사도가
# 그냥 내적이 되어, 비교할 때 numpy 없이도 빠르고 값은 완전히 같다.
# (정규화는 코사인 값을 바꾸지 않는다 — faceutil.cosine 과 같은 수를 낸다.)

def pack_embedding(vec):
    """실수 목록 → BLOB. 담을 것이 없거나 길이가 0 이면 None.

    `vec or []` 로 쓰면 안 된다 — numpy 배열이 오면 참·거짓을 물을 수 없어
    ValueError 가 난다. 실제로 faceutil.embed 가 배열을 넘겨 터졌던 자리다.
    """
    if vec is None:
        return None
    v = [float(x) for x in vec]
    n = math.sqrt(sum(x * x for x in v))
    if not v or not n or not math.isfinite(n):
        return None
    return sqlite3.Binary(array.array("f", [x / n for x in v]).tobytes())


def unpack_embedding(blob):
    a = array.array("f")
    a.frombytes(bytes(blob))
    return list(a)


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b)) if len(a) == len(b) else -1.0


def cosine(a, b):
    """코사인 유사도. faceutil.cosine 과 같은 값을 낸다(여기선 numpy 없이)."""
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if not na or not nb or len(a) != len(b):
        return -1.0
    return _dot(a, b) / (na * nb)


# ── 표 만들기 · 오래된 것 지우기 ─────────────────────────────────────────

def init():
    """표를 만들고(없으면), 보유 기간이 지난 것을 지운다. 지운 줄 수를 돌려준다."""
    with _db() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                ts       TEXT    NOT NULL,
                name     TEXT    NOT NULL,
                email    TEXT    NOT NULL,
                phone    TEXT    NOT NULL,
                gender   TEXT,
                age      TEXT,
                model    TEXT,
                mail_ok  INTEGER,
                mail_msg TEXT
            )""")
        c.execute("CREATE INDEX IF NOT EXISTS leads_ts ON leads(ts)")

        c.execute("""
            CREATE TABLE IF NOT EXISTS people (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                name         TEXT    NOT NULL,
                email        TEXT,
                phone        TEXT,
                created_ts   TEXT    NOT NULL,
                last_seen_ts TEXT    NOT NULL,
                visits       INTEGER NOT NULL DEFAULT 0,
                face_consent INTEGER NOT NULL DEFAULT 0,
                secret_note  TEXT
            )""")
        c.execute("CREATE INDEX IF NOT EXISTS people_phone ON people(phone)")
        c.execute("CREATE INDEX IF NOT EXISTS people_seen  ON people(last_seen_ts)")
        pcols = [r[1] for r in c.execute("PRAGMA table_info(people)")]
        if "secret_note" not in pcols:                 # v3.4.0
            c.execute("ALTER TABLE people ADD COLUMN secret_note TEXT")

        c.execute("""
            CREATE TABLE IF NOT EXISTS faces (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id INTEGER NOT NULL,
                ts        TEXT    NOT NULL,
                embedding BLOB    NOT NULL,
                photo     BLOB,
                quality   REAL
            )""")
        c.execute("CREATE INDEX IF NOT EXISTS faces_person ON faces(person_id)")

        c.execute("""
            CREATE TABLE IF NOT EXISTS visits (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id INTEGER NOT NULL,
                ts        TEXT    NOT NULL,
                gender    TEXT,
                age       TEXT,
                model     TEXT,
                summary   TEXT,
                mail_ok   INTEGER,
                mood      TEXT,
                condition TEXT
            )""")
        c.execute("CREATE INDEX IF NOT EXISTS visits_person ON visits(person_id, ts)")

        # 이미 만들어진 DB 에도 칸을 붙인다.
        vcols = [r[1] for r in c.execute("PRAGMA table_info(visits)")]
        for col in ("mood", "condition"):              # v3.4.0
            if col not in vcols:
                c.execute("ALTER TABLE visits ADD COLUMN %s TEXT" % col)

        cols = [r[1] for r in c.execute("PRAGMA table_info(leads)")]
        if "photo" not in cols:                       # v2.9.2
            c.execute("ALTER TABLE leads ADD COLUMN photo BLOB")
        if "person_id" not in cols:                   # v3.4.0
            # 옛 줄에는 값이 없다(NULL). 그래도 사람을 지울 때 그 사람의
            # leads 줄까지 함께 지우려면 이 연결이 있어야 한다.
            c.execute("ALTER TABLE leads ADD COLUMN person_id INTEGER")

        return _purge(c)


def _purge(c):
    """보유 기간이 지난 것을 실제로 지운다. people 을 지우면 딸린 것도 함께.

    기준이 표마다 다르다 — 일부러 그렇다.
      · leads  : 그 줄이 쓰인 날로부터. 예전 약속 그대로 둔다.
      · people : **마지막 방문일**로부터. 그래야 다시 찾아 주시는 분을
                 한창 쓰시는 중에 지워 버리지 않는다. 동의 문구도 이렇게 적었다.
    사람이 지워지면 얼굴 특징값이 남아서는 안 되므로 faces·visits·leads 를
    함께 지운다. 외래키에 기대지 않고 눈에 보이게 지운다.
    """
    cut = (datetime.datetime.now()
           - datetime.timedelta(days=RETAIN_DAYS)).isoformat(timespec="seconds")
    gone = [r["id"] for r in c.execute(
        "SELECT id FROM people WHERE last_seen_ts < ?", (cut,))]
    n = 0
    for pid in gone:
        n += _erase(c, pid)
    n += c.execute("DELETE FROM leads WHERE ts < ?", (cut,)).rowcount
    # 사람이 사라졌는데 남아 있는 것(옛 사고의 흔적)도 함께 치운다.
    n += c.execute("DELETE FROM faces  WHERE person_id NOT IN"
                   " (SELECT id FROM people)").rowcount
    n += c.execute("DELETE FROM visits WHERE person_id NOT IN"
                   " (SELECT id FROM people)").rowcount
    return n


def _erase(c, person_id):
    """한 사람에 딸린 모든 것을 지운다. 지운 줄 수."""
    n = 0
    for sql in ("DELETE FROM faces  WHERE person_id=?",
                "DELETE FROM visits WHERE person_id=?",
                "DELETE FROM leads  WHERE person_id=?",
                "DELETE FROM people WHERE id=?"):
        n += c.execute(sql, (person_id,)).rowcount
    return n


# ── 알아보기 ──────────────────────────────────────────────────────────────

def find_person(embedding, threshold=None):
    """얼굴 특징값으로 사람을 찾는다.

    돌려주는 값은 (person_id, score, person) — 못 찾으면 (None, 최고점, None).
    최고점을 함께 주는 까닭은, 문턱을 아슬아슬하게 못 넘은 경우를 로그로
    남겨 문턱값을 손볼 수 있게 하기 위해서다.

    한 사람의 여러 장 중 **가장 높은 점수**를 그 사람의 점수로 본다.
    얼굴은 날마다 조금씩 다르므로, 가장 닮은 한 장이 맞으면 맞는 것이다.
    """
    thr = FACE_THRESHOLD if threshold is None else threshold
    if embedding is None or len(embedding) == 0:
        return None, -1.0, None

    q = [float(x) for x in embedding]
    n = math.sqrt(sum(x * x for x in q))
    if not n or not math.isfinite(n):
        return None, -1.0, None
    q = [x / n for x in q]

    best_pid, best = None, -1.0
    try:
        with _db() as c:
            for r in c.execute("SELECT person_id, embedding FROM faces"):
                v = unpack_embedding(r["embedding"])
                if len(v) != len(q):     # 모델이 바뀌면 길이가 달라진다 — 건너뛴다
                    continue
                s = _dot(q, v)           # 둘 다 길이 1 이라 내적 = 코사인
                if s > best:
                    best_pid, best = r["person_id"], s
            if best_pid is None or best < thr:
                return None, best, None
            row = c.execute("SELECT * FROM people WHERE id=?",
                            (best_pid,)).fetchone()
            if row is None:              # 사람이 지워졌는데 얼굴만 남은 경우
                return None, best, None
            return best_pid, best, dict(row)
    except sqlite3.Error:
        return None, -1.0, None


def _find_by_contact(c, email, phone):
    """연락처가 같은 사람. **오직 중복 등록을 막기 위해서만** 쓴다.

    이력을 열어 주는 열쇠로 써서는 안 된다 — 남의 전화번호를 적어 넣으면
    그 사람의 지난 감정서가 보이게 된다. 이력을 여는 것은 얼굴(find_person)
    뿐이다. 여기서는 이미 있는 사람에게 이번 방문을 이어 붙이는 데만 쓴다.
    """
    ph = normalize_phone(phone)
    if ph:
        r = c.execute("SELECT * FROM people WHERE phone=?"
                      " ORDER BY last_seen_ts DESC LIMIT 1", (ph,)).fetchone()
        if r:
            return r
    em = (email or "").strip().lower()
    if em:
        r = c.execute("SELECT * FROM people WHERE lower(email)=?"
                      " ORDER BY last_seen_ts DESC LIMIT 1", (em,)).fetchone()
        if r:
            return r
    return None


# ── 담기 ──────────────────────────────────────────────────────────────────

def remember(person_id, name, email, phone, consent, face_consent=False,
             embedding=None, photo_png=None, meta=None, wellness_consent=None):
    """이번 방문을 담는다. 돌려주는 값은 (성공여부, 설명, person_id).

    **동의가 없으면 아무것도 저장하지 않는다.** 화면에서 막더라도 여기서 한 번
    더 막는다 — 화면 코드가 바뀌어도 이 규칙은 남아야 한다.

    **face_consent 가 거짓이면 얼굴 특징값을 저장하지 않는다.** 나아가 전에
    동의하셨다가 무르신 것이므로 **이미 담아 둔 특징값도 지운다.** 동의 철회는
    "앞으로 안 모음"이 아니라 "모아 둔 것도 없앰"이어야 한다.

    기분·컨디션(meta 의 mood·condition)도 같은 동의를 따른다. wellness_consent 를
    따로 주지 않으면 **face_consent 를 그대로 쓴다** — 둘 다 "다시 오셨을 때
    변화를 살펴 드리기" 하나를 위한 것이라 동의를 쪼갤 이유가 없고, 체크박스를
    셋으로 늘리면 오히려 아무도 읽지 않는다. 무르시면 **지난 방문에 적어 두신
    기분·컨디션까지 지운다**(얼굴 특징값과 같은 규칙).

    secret_note(본인 확인용 이야기)는 meta 로 받되 **이미 있으면 덮지 않는다.**
    처음 남기신 이야기가 기준이어야 하기 때문이다. 바꾸시려면 update_secret().
    """
    if not consent:
        return False, "동의 없이는 저장하지 않습니다.", None
    if not valid_name(name):
        return False, "이름을 확인해 주세요.", None
    pok, perr = _phone_ok(phone)
    if not pok:
        return False, perr, None

    m = meta or {}
    nm, em = name.strip(), (email or "").strip()
    ph = normalize_phone(phone)
    well = face_consent if wellness_consent is None else wellness_consent
    mood = _trim(m.get("mood"), MOOD_MAX) if well else None
    cond = _trim(m.get("condition"), MOOD_MAX) if well else None
    secret = _trim(m.get("secret_note"), SECRET_MAX) if well else None
    # 감정서와 사진을 **남겨 두는** 것은 보내는 데 필요한 일이 아니라
    # "다음에 견주어 보기" 위한 일이다. 그래서 기록 동의를 받았을 때만 담는다.
    # (보내는 동안 쓰는 것은 여기 오기 전에 이미 끝났다.)
    summ = _trim(m.get("summary"), SUMMARY_MAX) if well else None
    keep_photo = photo_png if well else None

    # 기존 경로를 그대로 태운다. 새 표가 잘못되어도 여기까지는 남는다.
    ok, msg = save(nm, em, ph, consent, m, keep_photo)

    try:
        init()
        with _db() as c:
            ts = _now()
            row = None
            if person_id:
                row = c.execute("SELECT * FROM people WHERE id=?",
                                (person_id,)).fetchone()
            if row is None:
                row = _find_by_contact(c, em, ph)

            if row is None:
                pid = c.execute(
                    "INSERT INTO people"
                    " (name,email,phone,created_ts,last_seen_ts,visits,"
                    "  face_consent,secret_note)"
                    " VALUES (?,?,?,?,?,1,?,?)",
                    (nm, em, ph, ts, ts,
                     1 if face_consent else 0, secret)).lastrowid
            else:
                pid = row["id"]
                c.execute(
                    "UPDATE people SET name=?, email=?, phone=?, last_seen_ts=?,"
                    " visits=visits+1, face_consent=? WHERE id=?",
                    (nm, em or row["email"], ph or row["phone"], ts,
                     1 if face_consent else 0, pid))
                # 처음 남기신 이야기가 기준이다. 비어 있을 때만 채운다.
                if secret and not (row["secret_note"] or "").strip():
                    c.execute("UPDATE people SET secret_note=? WHERE id=?",
                              (secret, pid))

            # 방금 save() 가 넣은 leads 줄을 사람과 이어 둔다(함께 지우려고).
            # ⚠️ 전화번호가 비어 있을 수 있다. 그대로 맞추면 번호를 안 적으신
            #    **다른 분들의 줄까지 한 사람에게 몰아 붙는다.** 빈 값이면 메일로.
            if ph:
                c.execute("UPDATE leads SET person_id=? WHERE person_id IS NULL"
                          " AND phone=?", (pid, ph))
            elif em:
                c.execute("UPDATE leads SET person_id=? WHERE person_id IS NULL"
                          " AND phone='' AND lower(email)=?", (pid, em.lower()))

            c.execute(
                "INSERT INTO visits (person_id,ts,gender,age,model,summary,"
                " mail_ok,mood,condition) VALUES (?,?,?,?,?,?,?,?,?)",
                (pid, ts, m.get("gender"), m.get("age"), m.get("model"), summ,
                 1 if m.get("mail_ok") else 0, mood, cond))

            if face_consent:
                _store_face(c, pid, ts, embedding, photo_png, m.get("quality"))
            else:
                # 동의가 없다 = 모아 둔 것도 없앤다.
                c.execute("DELETE FROM faces WHERE person_id=?", (pid,))
            if not well:
                # 기록 동의를 안 하셨거나 무르셨다 = **모아 둔 것도 없앤다.**
                # 얼굴 특징값(위)과 같은 규칙을 기분·컨디션·지난 감정서·보관
                # 사진·본인확인 이야기에도 똑같이 적용한다. 모두 "다음에 견주어
                # 보기" 하나를 위해 두던 것이라, 그 뜻을 거두시면 남을 이유가 없다.
                c.execute("UPDATE visits SET mood=NULL, condition=NULL,"
                          " summary=NULL WHERE person_id=?", (pid,))
                c.execute("UPDATE leads SET photo=NULL WHERE person_id=?", (pid,))
                c.execute("UPDATE people SET secret_note=NULL WHERE id=?", (pid,))

        return True, ("저장했습니다." if ok else msg), pid
    except sqlite3.Error as e:
        # 저장 실패로 감정서까지 막지는 않는다. 다만 성공한 척도 하지 않는다.
        return False, "저장하지 못했습니다: %s" % e, None


def _store_face(c, pid, ts, embedding, photo_png, quality):
    """얼굴 특징값 한 장. 같은 날 것이 이미 있으면 좋은 쪽만 남긴다.

    한 번 방문에 사진을 여러 번 찍는 일이 흔한데, 그것을 다 담으면 거의 같은
    장이 잔뜩 쌓여 비교가 느려질 뿐 얻는 것이 없다. 우리가 보고 싶은 것은
    **날짜를 사이에 둔 변화**다. 그래서 하루 한 장으로 한다.
    """
    blob = pack_embedding(embedding)
    if blob is None:
        return
    day = ts[:10]
    q = float(quality) if quality is not None else 0.0
    old = c.execute("SELECT id, quality FROM faces"
                    " WHERE person_id=? AND substr(ts,1,10)=?"
                    " ORDER BY id DESC LIMIT 1", (pid, day)).fetchone()
    if old is not None:
        if (old["quality"] or 0.0) >= q:
            return                                    # 이미 더 좋은 것이 있다
        c.execute("DELETE FROM faces WHERE id=?", (old["id"],))
    c.execute("INSERT INTO faces (person_id,ts,embedding,photo,quality)"
              " VALUES (?,?,?,?,?)",
              (pid, ts, blob,
               sqlite3.Binary(photo_png) if photo_png else None, q))


# ── 되돌아보기 ────────────────────────────────────────────────────────────

def history(person_id, limit=5):
    """지난 방문을 최신순으로.

    [{ts, age, gender, model, summary, mood, condition}, ...]
    mood·condition 은 적지 않으셨거나 동의를 무르신 경우 None 이다.
    """
    if not person_id:
        return []
    try:
        with _db() as c:
            return [dict(r) for r in c.execute(
                "SELECT ts, age, gender, model, summary, mood, condition"
                " FROM visits WHERE person_id=? ORDER BY ts DESC LIMIT ?",
                (person_id, int(limit)))]
    except sqlite3.Error:
        return []


def secret_note(person_id):
    """본인 확인용으로 남기신 이야기. 없으면 None.

    ⚠️ **이 값을 화면에 그대로 띄우지 말 것.** 곁에서 보던 사람이 그대로
    외워 버리면 확인 장치가 아무 소용이 없어진다. 되물을 질문을 만드는 데만
    쓰고, 원문은 화면·로그 어디에도 남기지 않는다.

    ⚠️ 이 값은 그대로(평문) 담긴다. 되물을 질문을 지어내려면 원문이 있어야 해서
    해시로 바꿔 둘 수가 없다. 비밀번호가 아니라 **기억을 확인하는 실마리**로만
    다루고, 보유기간·삭제 규칙은 다른 개인정보와 똑같이 적용한다.
    """
    if not person_id:
        return None
    try:
        with _db() as c:
            r = c.execute("SELECT secret_note FROM people WHERE id=?",
                          (person_id,)).fetchone()
            return (r["secret_note"] or None) if r else None
    except sqlite3.Error:
        return None


def update_secret(person_id, note):
    """이야기를 새로 바꾼다. (성공여부, 설명)

    remember() 는 **비어 있을 때만** 채운다 — 처음 남기신 이야기가 기준이어야
    하기 때문이다. 일부러 바꾸실 때만 이 함수를 쓴다.
    """
    if not person_id:
        return False, "누구의 것인지 알 수 없습니다."
    try:
        with _db() as c:
            n = c.execute("UPDATE people SET secret_note=? WHERE id=?",
                          (_trim(note, SECRET_MAX), person_id)).rowcount
        return (n > 0), "바꿨습니다." if n else "그런 분이 없습니다."
    except sqlite3.Error as e:
        return False, "바꾸지 못했습니다: %s" % e


def person_brief(person_id):
    """{name, visits, first_ts, last_ts, days_since_last, face_consent, faces} 또는 None.

    days_since_last 는 **이번 방문을 담기 전에** 불러야 뜻이 있다.
    remember() 가 last_seen_ts 를 지금으로 바꾸므로, 담은 뒤에 부르면 늘 0 이다.
    """
    if not person_id:
        return None
    try:
        with _db() as c:
            r = c.execute("SELECT * FROM people WHERE id=?",
                          (person_id,)).fetchone()
            if r is None:
                return None
            days = None
            try:
                last = datetime.datetime.fromisoformat(r["last_seen_ts"])
                days = (datetime.datetime.now() - last).days
            except (TypeError, ValueError):
                pass
            n = c.execute("SELECT COUNT(*) FROM faces WHERE person_id=?",
                          (person_id,)).fetchone()[0]
            return {"name": r["name"], "visits": r["visits"],
                    "first_ts": r["created_ts"], "last_ts": r["last_seen_ts"],
                    "days_since_last": days,
                    "face_consent": bool(r["face_consent"]), "faces": n,
                    # 이야기를 남기셨는지만 알린다. 내용은 주지 않는다 —
                    # 화면에 뿌려질 자리에 원문이 실려 가면 안 된다.
                    "has_secret": bool((r["secret_note"] or "").strip())}
    except sqlite3.Error:
        return None


def forget_person(person_id):
    """그 사람에 딸린 모든 것을 지운다. (성공여부, 설명)

    법으로 보장된 삭제 요구에 응할 길이 코드에 있어야 한다. 동의 문구에
    "무르시면 곧바로 지웁니다" 라고 적어 놓고 방법이 없으면 거짓말이 된다.
    """
    if not person_id:
        return False, "누구를 지울지 알 수 없습니다."
    try:
        with _db() as c:
            n = _erase(c, person_id)
        return (n > 0), ("%d 건을 지웠습니다." % n) if n else "지울 것이 없습니다."
    except sqlite3.Error as e:
        return False, "지우지 못했습니다: %s" % e


# ── 기존 경로 (그대로 둔다) ───────────────────────────────────────────────

def save(name, email, phone, consent, meta=None, photo_png=None):
    """한 사람을 leads 표에 한 줄 담는다. 돌려주는 값은 (성공여부, 설명).

    **동의가 없으면 저장하지 않는다.** remember() 가 이 함수를 그대로 쓴다 —
    새 표가 잘못되어도 여기까지는 남도록, 되돌릴 자리로 남겨 둔 길이다.
    """
    if not consent:
        return False, "동의 없이는 저장하지 않습니다."
    if not valid_name(name):
        return False, "이름을 확인해 주세요."
    pok, perr = _phone_ok(phone)
    if not pok:
        return False, perr

    m = meta or {}
    try:
        init()
        with _db() as c:
            c.execute(
                "INSERT INTO leads"
                " (ts,name,email,phone,gender,age,model,mail_ok,mail_msg,photo)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (_now(), name.strip(), email.strip(), normalize_phone(phone),
                 m.get("gender"), m.get("age"), m.get("model"),
                 1 if m.get("mail_ok") else 0, m.get("mail_msg"),
                 sqlite3.Binary(photo_png) if photo_png else None))
        return True, "저장했습니다."
    except sqlite3.Error as e:
        # 저장 실패로 감정서까지 막지는 않는다. 다만 성공한 척도 하지 않는다.
        return False, "저장하지 못했습니다: %s" % e


def count():
    """지금 담겨 있는 사람 수(leads 줄 수)."""
    try:
        with _db() as c:
            return c.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    except sqlite3.Error:
        return 0


def stats():
    """{people, faces, visits, leads} — 관리 화면에 쓸 셈."""
    out = {}
    try:
        with _db() as c:
            for t in ("people", "faces", "visits", "leads"):
                out[t] = c.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
    except sqlite3.Error:
        pass
    return out


# ── 동의 문구 ─────────────────────────────────────────────────────────────
# 두 개로 나눈 까닭: 얼굴 특징값은 개인정보 보호법상 **민감정보**라
# 다른 항목과 묶어 한 번에 받을 수 없다. 별도 항목·별도 체크박스여야 한다.
# 그리고 거부해도 본래 서비스(감정서)는 그대로 받으실 수 있어야 한다.

NO_MEDICAL = """> 이 서비스는 **재미로 보는 관상**이고, 스스로 남겨 두는 기록입니다.
> 건강 상태를 진단하거나 병을 찾아 드리지 않으며, 여기 적힌 어떤 말도
> 의학적 판단의 근거가 되지 않습니다. 몸이 편찮으시면 의료기관을 찾으십시오."""

NOTICE = """**개인정보 수집·이용 안내**

- **수집 항목** — **이름**과 **이메일 주소**. 감정서를 지어 보내 드리는 데
  꼭 필요한 것만 받습니다.
  · 휴대전화번호는 **적지 않으셔도 됩니다.** 연락드릴 일이 있을 때만 씁니다.
- **수집 목적** — 관상 감정서 작성과 발송, 그에 딸린 문의 응대
- **보유 기간** — 마지막 방문일로부터 **%d일**, 지나면 자동으로 지워집니다
- **아래 버튼을 누르시면 이 안내에 동의하신 것으로 봅니다.** 원하지 않으시면
  적지 않고 그냥 나가셔도 됩니다. 다만 그 경우 전체 감정서와 메일 발송은
  드리지 못합니다.
""" % RETAIN_DAYS

FACE_NOTICE = """**기록으로 남기기 — 얼굴 특징값과 그날의 기록** (선택 · 체크)

얼굴 특징값은 개인정보 보호법에서 **민감정보**로 봅니다. 적어 주시는
기분·컨디션에도 몸에 관한 이야기가 담길 수 있어 같은 무게로 다룹니다.
그래서 위 안내와 **따로**, 체크로 여쭙습니다.

- **수집 항목**
  · 얼굴 사진에서 뽑아낸 **얼굴 특징값**(숫자 128개) — 사진을 그대로 담고
    있지 않은 숫자 묶음이며, 이 서비스 밖으로 내보내지 않습니다
  · 그날의 **얼굴 사진**과 **감정서 내용**
  · 그날 적어 두신 **기분·컨디션 한 줄**
  · 다음에 본인이신지 알아보려고 남기신 **이야기**
- **수집 목적** — 다시 찾아 주셨을 때 **알아보고 인사드리기**, 그리고 지난
  기록과 견주어 **얼굴과 그날그날의 기분이 어떻게 달라지셨는지 함께
  들여다보기**. 셀카를 남기듯 스스로 돌아보시라는 뜻입니다.
- 남기시는 이야기에는 **다른 분의 사정을 적지 말아 주십시오.** 본인을
  떠올리실 만한 것이면 충분합니다.
- **보유 기간** — 마지막 방문일로부터 **%d일**, 지나면 자동으로 지워집니다.
  **체크를 거두시면 그때까지 쌓인 얼굴 특징값·사진·지난 감정서·기분·이야기를
  곧바로 지웁니다.**
- 체크하지 않으셔도 됩니다. **감정서는 그대로 지어 드리고 메일로도 보내
  드립니다.** 다만 다음에 오셨을 때 알아보지 못합니다.

%s
""" % (RETAIN_DAYS, NO_MEDICAL)
