# -*- coding: utf-8 -*-
"""leads.py 시험. 약속한 것이 실제로 그렇게 되는지 하나씩 확인한다."""
import os, sys, math, random, datetime, sqlite3, tempfile, importlib

DB = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ["LEADS_DB"] = DB
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import leads
importlib.reload(leads)

OK = [0, 0]
def chk(cond, what):
    OK[0 if cond else 1] += 1
    print(("  OK   " if cond else "  실패 ") + what)

def emb(seed, jitter=0.0):
    r = random.Random(seed)
    v = [r.gauss(0, 1) for _ in range(128)]
    if jitter:
        j = random.Random(seed * 7 + 1)
        v = [x + j.gauss(0, jitter) for x in v]
    return v

def rows(t):
    c = sqlite3.connect(DB); n = c.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
    c.close(); return n

A, B = emb(1), emb(2)
A2 = emb(1, 0.25)          # 같은 사람의 다른 날 얼굴

print("── 1. init / 멱등 ──")
leads.init(); leads.init()
chk(rows("people") == 0 and rows("faces") == 0 and rows("visits") == 0, "표 넷이 생기고 비어 있다")

print("── 2. 동의 없으면 아무것도 저장하지 않는다 ──")
ok, msg, pid = leads.remember(None, "홍길동", "a@b.c", "010-1234-5678",
                              consent=False, face_consent=True, embedding=A)
chk(not ok and pid is None, "remember 가 거부한다: " + msg)
chk(rows("leads") == 0 and rows("people") == 0 and rows("faces") == 0, "어느 표에도 안 들어갔다")

print("── 3. 얼굴 동의 없이 저장 ──")
ok, msg, p1 = leads.remember(None, "홍길동", "a@b.c", "010-1234-5678",
                             consent=True, face_consent=False, embedding=A,
                             photo_png=b"PNG-fake",
                             meta={"gender": "남", "age": "40대 중반", "summary": "가"*2000})
chk(ok and p1, "저장됨 person_id=%s" % p1)
chk(rows("faces") == 0, "★ 얼굴 특징값은 저장되지 않았다")
chk(rows("people") == 1 and rows("visits") == 1 and rows("leads") == 1, "people/visits/leads 각 1")
chk(leads.history(p1)[0]["summary"] is None, "★ 기록 동의가 없으면 감정서도 남기지 않는다")
c = sqlite3.connect(DB)
chk(c.execute("SELECT photo FROM leads").fetchone()[0] is None, "★ 사진도 남기지 않는다")
c.close()
chk(leads.find_person(A)[0] is None, "★ 알아보지 못한다(특징값이 없으니 당연)")

print("── 4. 얼굴 동의 받고 다시 방문 ──")
ok, msg, p2 = leads.remember(None, "홍길동", "a@b.c", "010-1234-5678",
                             consent=True, face_consent=True, embedding=A,
                             meta={"quality": 0.5, "summary": "두번째"})
chk(p2 == p1, "★ 연락처가 같아 같은 사람으로 이어졌다 (%s)" % p2)
chk(rows("people") == 1 and rows("visits") == 2 and rows("faces") == 1, "visits 2 · faces 1")
b = leads.person_brief(p1)
chk(b["visits"] == 2 and b["faces"] == 1 and b["face_consent"], "brief: %s회 방문" % b["visits"])
leads.remember(p1, "홍길동", "a@b.c", "010-1234-5678", True, True, A,
               meta={"quality": 0.5, "summary": "가"*2000})
chk(len(leads.history(p1)[0]["summary"]) == leads.SUMMARY_MAX,
    "감정서는 %d자로 잘려 담긴다" % leads.SUMMARY_MAX)

print("── 5. 얼굴로 알아보기 ──")
pid, sc, row = leads.find_person(A)
chk(pid == p1 and sc > 0.99, "똑같은 얼굴 → 알아봄 (코사인 %.3f)" % sc)
pid, sc, _ = leads.find_person(A2)
chk(pid == p1, "★ 조금 다른 날의 같은 얼굴 → 알아봄 (%.3f)" % sc)
pid, sc, _ = leads.find_person(B)
chk(pid is None, "★ 다른 사람 → 못 알아봄 (최고점 %.3f < %.3f)" % (sc, leads.FACE_THRESHOLD))

print("── 6. 같은 날 여러 번 = 한 장만, 좋은 쪽으로 ──")
leads.remember(p1, "홍길동", "a@b.c", "010-1234-5678", True, True, A,
               meta={"quality": 0.2})
chk(rows("faces") == 1, "질 낮은 것은 안 밀어냈다")
c = sqlite3.connect(DB)
chk(abs(c.execute("SELECT quality FROM faces").fetchone()[0] - 0.5) < 1e-6, "quality 0.5 유지")
c.close()
leads.remember(p1, "홍길동", "a@b.c", "010-1234-5678", True, True, A2,
               meta={"quality": 0.9})
c = sqlite3.connect(DB)
q = c.execute("SELECT quality FROM faces").fetchone()[0]; c.close()
chk(rows("faces") == 1 and abs(q - 0.9) < 1e-6, "★ 더 좋은 것으로 갈아탔다 (q=%.1f)" % q)

print("── 7. 코사인이 numpy 와 같은 값인가 ──")
try:
    import numpy as np
    a, b2 = np.array(A), np.array(A2)
    want = float(a.dot(b2) / (np.linalg.norm(a) * np.linalg.norm(b2)))
    got = leads.cosine(A, A2)
    chk(abs(want - got) < 1e-9, "numpy %.9f vs leads %.9f" % (want, got))
    # 저장할 때 정규화한 뒤 내적으로 비교하는 길도 같은 값인가
    _, sc2, _ = leads.find_person(A2)
    chk(abs(sc2 - 1.0) < 1e-5, "★ 정규화 저장 → 내적 비교가 코사인과 일치 (%.6f)" % sc2)
except ImportError:
    print("  건너뜀 (numpy 없음)")

print("── 8. 동의 철회 = 모아 둔 것도 지운다 ──")
leads.remember(p1, "홍길동", "a@b.c", "010-1234-5678", True,
               face_consent=False, embedding=A)
chk(rows("faces") == 0, "★ 얼굴 특징값이 모두 지워졌다")
chk(rows("people") == 1 and rows("visits") == 6, "사람과 방문 기록은 남는다")
chk(not leads.person_brief(p1)["face_consent"], "동의 여부도 꺼졌다")

print("── 9. 남의 전화번호로는 이력이 열리지 않는가 ──")
ok, _, p3 = leads.remember(None, "김철수", "c@d.e", "010-9999-8888", True, True, B,
                           meta={"quality": 0.7, "summary": "철수 감정서"})
chk(p3 != p1, "다른 사람은 다른 id")
pid, sc, _ = leads.find_person(A)
chk(pid is None, "★ 이력을 여는 열쇠는 얼굴뿐 — A 는 이제 등록된 얼굴이 없다")

print("── 10. forget_person: 흔적이 남지 않는가 ──")
ok, msg = leads.forget_person(p3)
chk(ok, msg)
c = sqlite3.connect(DB)
left = {t: c.execute("SELECT COUNT(*) FROM %s WHERE person_id=?" % t,
                     (p3,)).fetchone()[0] for t in ("faces", "visits", "leads")}
left["people"] = c.execute("SELECT COUNT(*) FROM people WHERE id=?", (p3,)).fetchone()[0]
c.close()
chk(all(v == 0 for v in left.values()), "★ 네 표 모두 0 %s" % left)
chk(leads.find_person(B)[0] is None, "얼굴로도 못 찾는다")

print("── 11. 보유기간 지나면 딸린 것까지 함께 지워지는가 ──")
ok, _, p4 = leads.remember(None, "이영희", "e@f.g", "010-1111-2222", True, True, emb(9),
                           meta={"quality": 0.8})
old = (datetime.datetime.now()
       - datetime.timedelta(days=leads.RETAIN_DAYS + 1)).isoformat(timespec="seconds")
c = sqlite3.connect(DB)
c.execute("UPDATE people SET last_seen_ts=? WHERE id=?", (old, p4)); c.commit(); c.close()
leads.init()
c = sqlite3.connect(DB)
left = {t: c.execute("SELECT COUNT(*) FROM %s WHERE person_id=?" % t,
                     (p4,)).fetchone()[0] for t in ("faces", "visits", "leads")}
left["people"] = c.execute("SELECT COUNT(*) FROM people WHERE id=?", (p4,)).fetchone()[0]
c.close()
chk(all(v == 0 for v in left.values()), "★ 기간 지난 사람은 얼굴까지 함께 사라졌다 %s" % left)
chk(leads.person_brief(p1) is not None, "한창 오시는 분(p1)은 그대로 계신다")

print("── 12. 기존 경로가 그대로인가 ──")
n0 = leads.count()
chk(leads.save("박보검", "x@y.z", "010-5555-6666", True)[0], "save() 동작")
chk(leads.count() == n0 + 1, "count() 늘었다")
chk(leads.save("박", "x@y.z", "010-5555-6666", True)[0] is False, "이름 검사 그대로")
chk(leads.save("박보검", "x@y.z", "123", True)[0] is False, "전화 검사 그대로")
chk(leads.save("박보검", "x@y.z", "010-5555-6666", False)[0] is False, "동의 검사 그대로")

print("── 13. 이상한 입력에 안 죽는가 ──")
chk(leads.find_person(None)[0] is None, "None 임베딩")
chk(leads.find_person([])[0] is None, "빈 임베딩")
chk(leads.find_person([0.0] * 128)[0] is None, "길이 0 벡터")
chk(leads.find_person([1.0] * 64)[0] is None, "길이가 다른 벡터(모델 교체) — 건너뛴다")
chk(leads.pack_embedding([]) is None and leads.pack_embedding(None) is None, "pack 빈 값")
chk(leads.history(None) == [] and leads.person_brief(None) is None, "person_id 없음")
chk(leads.forget_person(None)[0] is False, "forget 빈 id")
chk(leads.remember(None, "홍", "a@b.c", "010-1234-5678", True)[0] is False, "짧은 이름 거부")

print("── 14. 동의 문구 ──")
chk("민감정보" in leads.FACE_NOTICE and "선택" in leads.FACE_NOTICE, "생체정보 별도 고지")
chk("체크하지 않으셔도" in leads.FACE_NOTICE and "감정서는 그대로" in leads.FACE_NOTICE,
    "거부해도 서비스 그대로 (제16조 3항)")
chk("버튼을 누르시면" in leads.NOTICE, "★ 버튼 = 동의 방식에 맞는 문구")
chk("화면으로만 보기" not in leads.NOTICE, "★ 없어진 버튼을 더 가리키지 않는다")
chk("그냥 나가셔도" in leads.NOTICE, "안 남기고 나갈 수 있다고 알린다")
chk("적지 않으셔도" in leads.NOTICE, "★ 전화번호는 선택이라고 알린다")
chk("얼굴 사진" not in leads.NOTICE and "얼굴 사진" in leads.FACE_NOTICE,
    "★ 사진 보관은 필수가 아니라 선택 쪽에 있다")
chk("마지막 방문일" in leads.NOTICE and "마지막 방문일" in leads.FACE_NOTICE,
    "★ 보유기간 문구가 코드(_purge)와 같은 기준")
chk("기분" in leads.FACE_NOTICE and "컨디션" in leads.FACE_NOTICE, "기분·컨디션도 선택 동의에 고지")
chk("이야기" in leads.FACE_NOTICE and "다른 분의 사정" in leads.FACE_NOTICE,
    "본인확인 이야기 고지 + 제3자 주의 (선택 쪽)")
chk("진단하거나" in leads.NO_MEDICAL and "의료기관" in leads.NO_MEDICAL, "★ 진단하지 않는다고 못박음")
chk(leads.NO_MEDICAL in leads.FACE_NOTICE, "선택 동의 문구에 실려 있다")
# 의료 표현 금칙 — 다만 "진단하지 않는다"는 부인 문구는 있어야 하므로 그 문단은 빼고 본다
body = (leads.NOTICE + leads.FACE_NOTICE).replace(leads.NO_MEDICAL, "")
med = [w for w in ("치료", "질병", "병증", "진단", "의학", "질환", "증상") if w in body]
chk(not med, "★ 부인 문구 밖에는 의료 표현이 없다 %s" % (med or ""))
chk(leads.stats()["people"] >= 1, "stats() %s" % leads.stats())

print("── 15. 기분·컨디션 ──")
ok, _, w1 = leads.remember(None, "최웰니", "w@x.y", "010-7777-1111", True,
                           face_consent=True, embedding=emb(31),
                           meta={"quality": .8, "mood": "가뿐하다", "condition": "잘 잤다",
                                 "secret_note": "아들이 고1 때 자퇴하고 대안학교에 갔다"})
h = leads.history(w1)[0]
chk(h["mood"] == "가뿐하다" and h["condition"] == "잘 잤다", "history 에 실려 나온다")
chk(leads.remember(w1, "최웰니", "w@x.y", "010-7777-1111", True, True, emb(31),
                   meta={"quality": .8, "mood": "가"*500})[0], "긴 기분도 받는다")
chk(len(leads.history(w1)[0]["mood"]) == leads.MOOD_MAX, "%d자로 잘린다" % leads.MOOD_MAX)
leads.remember(w1, "최웰니", "w@x.y", "010-7777-1111", True, True, emb(31),
               meta={"quality": .8})
chk(leads.history(w1)[0]["mood"] is None, "안 적으면 None (빈 문자열 아님)")

print("── 16. 얼굴 동의를 무르면 기분·컨디션도 지워지는가 ──")
chk(any(v["mood"] for v in leads.history(w1, 9)), "지금은 남아 있다")
leads.remember(w1, "최웰니", "w@x.y", "010-7777-1111", True,
               face_consent=False, meta={"mood": "이건 저장되면 안 된다"})
chk(all(v["mood"] is None and v["condition"] is None for v in leads.history(w1, 9)),
    "★ 지난 방문에 적어 둔 기분·컨디션까지 모두 지워졌다")
c = sqlite3.connect(DB)
nf = c.execute("SELECT COUNT(*) FROM faces WHERE person_id=?", (w1,)).fetchone()[0]
c.close()
chk(nf == 0, "얼굴 특징값도 함께 지워졌다")
chk(all(v["summary"] is None for v in leads.history(w1, 9)), "★ 지난 감정서도 지워졌다")
chk(leads.secret_note(w1) is None, "★ 본인확인 이야기도 지워졌다")
c = sqlite3.connect(DB)
np_ = c.execute("SELECT COUNT(*) FROM leads WHERE person_id=? AND photo IS NOT NULL",
                (w1,)).fetchone()[0]
c.close()
chk(np_ == 0, "★ 보관하던 사진도 지워졌다")

print("── 17. wellness_consent 를 따로 주면 그것을 따르는가 ──")
ok, _, w2 = leads.remember(None, "정따로", "s@x.y", "010-7777-2222", True,
                           face_consent=True, embedding=emb(32), wellness_consent=False,
                           meta={"quality": .8, "mood": "안 담겨야 한다"})
chk(leads.history(w2)[0]["mood"] is None, "★ 얼굴은 되고 기분은 안 됨 (따로 지정)")
c = sqlite3.connect(DB)
nf = c.execute("SELECT COUNT(*) FROM faces WHERE person_id=?", (w2,)).fetchone()[0]
c.close()
chk(nf == 1, "얼굴 특징값은 담겼다")

print("── 18. 본인 확인용 이야기 ──")
ok, _, s1 = leads.remember(None, "이야기", "t@x.y", "010-7777-9999", True, True, emb(41),
                           meta={"quality": .8,
                                 "secret_note": "아들이 고1 때 자퇴하고 대안학교에 갔다"})
chk(leads.secret_note(s1) == "아들이 고1 때 자퇴하고 대안학교에 갔다", "처음 남긴 이야기가 있다")
chk(leads.remember(None, "무동의", "n@x.y", "010-7777-8888", True, face_consent=False,
                   meta={"secret_note": "담기면 안 된다"})[0], "기록 동의 없이 저장")
chk(leads.secret_note(leads.find_person(emb(41))[0]) is not None, "동의한 분 것은 그대로")
w1 = s1
leads.remember(w1, "이야기", "t@x.y", "010-7777-9999", True, True, emb(41),
               meta={"quality": .8, "secret_note": "나중에 슬쩍 바꾼 이야기"})
chk(leads.secret_note(w1) == "아들이 고1 때 자퇴하고 대안학교에 갔다",
    "★ remember 는 덮어쓰지 않는다 — 처음 것이 기준")
ok, msg = leads.update_secret(w1, "일부러 바꾼 이야기")
chk(ok and leads.secret_note(w1) == "일부러 바꾼 이야기", "update_secret 으로만 바뀐다")
chk(leads.update_secret(w1, "가"*900)[0] and
    len(leads.secret_note(w1)) == leads.SECRET_MAX, "%d자로 잘린다" % leads.SECRET_MAX)
b = leads.person_brief(w1)
chk(b["has_secret"] is True and "secret_note" not in b,
    "★ person_brief 는 '있다/없다'만 알린다 (원문 안 실림)")
chk(leads.secret_note(None) is None and leads.update_secret(None, "x")[0] is False,
    "빈 id 에 안 죽는다")

print("── 19. 이야기도 함께 지워지는가 ──")
leads.forget_person(w1)
chk(leads.secret_note(w1) is None and leads.person_brief(w1) is None, "★ forget 하면 이야기도 없다")
ok, _, w3 = leads.remember(None, "만료자", "z@x.y", "010-7777-3333", True, True, emb(33),
                           meta={"quality": .8, "secret_note": "지워져야 한다",
                                 "mood": "지워져야 한다"})
old2 = (datetime.datetime.now()
        - datetime.timedelta(days=leads.RETAIN_DAYS + 1)).isoformat(timespec="seconds")
c = sqlite3.connect(DB)
c.execute("UPDATE people SET last_seen_ts=? WHERE id=?", (old2, w3)); c.commit(); c.close()
leads.init()
chk(leads.secret_note(w3) is None and leads.history(w3) == [],
    "★ 보유기간이 지나면 이야기·기분까지 함께 사라진다")

print("── 20. 전화번호를 안 적어도 되는가 (제16조 3항) ──")
ok, msg, n1 = leads.remember(None, "번호없음", "no1@x.y", "", True, True, emb(51),
                             meta={"quality": .8})
chk(ok and n1, "빈 번호로 저장됨: " + msg)
ok, msg, n2 = leads.remember(None, "번호없음둘", "no2@x.y", None, True, True, emb(52),
                             meta={"quality": .8})
chk(ok and n2 != n1, "★ 번호 없는 다른 분이 같은 사람으로 뭉치지 않는다")
c = sqlite3.connect(DB)
mix = c.execute("SELECT COUNT(DISTINCT person_id) FROM leads WHERE phone=''").fetchone()[0]
c.close()
chk(mix == 2, "★ leads 줄도 각자에게 붙었다 (%d명)" % mix)
chk(leads.remember(None, "틀린번호", "b@x.y", "12345", True)[0] is False, "적었으면 제대로여야 한다")
chk(leads.save("번호없음", "no1@x.y", "", True)[0], "save() 도 빈 번호 허용")

print("── 21. numpy 배열을 넘겨도 안 터지는가 ──")
try:
    import numpy as np
    v = np.array(emb(61), dtype=np.float32)
    chk(leads.pack_embedding(v) is not None, "★ pack_embedding(numpy) — 예전에 여기서 터졌다")
    ok, _, q1 = leads.remember(None, "넘파이", "n@p.y", "010-6666-1111", True, True, v,
                               meta={"quality": .8})
    chk(leads.find_person(np.array(emb(61), dtype=np.float32))[0] == q1, "numpy 로 찾기도 된다")
except ImportError:
    print("  건너뜀 (numpy 없음)")

print("── 22. 옛 DB 에 새 칸이 붙는가 ──")
c = sqlite3.connect(DB)
vc = [r[1] for r in c.execute("PRAGMA table_info(visits)")]
pc = [r[1] for r in c.execute("PRAGMA table_info(people)")]
c.close()
chk("mood" in vc and "condition" in vc, "visits: %s" % vc)
chk("secret_note" in pc, "people: %s" % pc)

print()
print("  통과 %d · 실패 %d" % (OK[0], OK[1]))
sys.exit(1 if OK[1] else 0)
