"""1-3 재연결 시험: 입력이 끊겼다 돌아와도 프로세스 재시작 없이 30초 안에 복구되는가
실행
  자동(가짜 카메라): python reconnect_test.py --auto-fake --cycles 3
      → 이 스크립트가 가짜 카메라(포트 8711)를 직접 켜고, 20초마다 끄고(10초) 다시 켠다
  수동(VIGI):       python reconnect_test.py --src vigi:stream2 --dur 150
      → 도는 동안 사람이 카메라 랜선(또는 전원)을 뽑았다가 다시 꽂는다
복구 시간 = 입력이 돌아온 때(가짜: 서버 재시작 / VIGI: 알 수 없으므로 끊김 감지 시각부터)부터 새 프레임이 다시 들어올 때까지
"""
import argparse
import json
import os
import subprocess
import sys
import time

from camsrc import LatestReader

ap = argparse.ArgumentParser()
ap.add_argument("--src", default=None)
ap.add_argument("--auto-fake", action="store_true")
ap.add_argument("--cycles", type=int, default=3)
ap.add_argument("--off", type=float, default=10, help="가짜 카메라를 꺼 두는 시간(초)")
ap.add_argument("--dur", type=float, default=150)
ap.add_argument("--out", default=None)
ap.add_argument("--iface", default=None, help="VIGI 시험 때 랜 케이블 꽂힘(carrier)을 기록할 인터페이스, 예: enP8p1s0")
args = ap.parse_args()


def carrier():
    try:
        return open(f"/sys/class/net/{args.iface}/carrier").read().strip() == "1"
    except OSError:
        return False

here = os.path.dirname(os.path.abspath(__file__))
fake = None
marks = []                                   # (시각, "off"/"on")


def fake_on():
    global fake
    fake = subprocess.Popen([sys.executable, os.path.join(here, "fakecam.py"), "--port", "8711"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    marks.append((time.time(), "on"))


def fake_off():
    fake.kill()
    fake.wait()
    marks.append((time.time(), "off"))


if args.auto_fake:
    fake_on()
    time.sleep(1.5)
    src = "http://127.0.0.1:8711/video.mjpg"
    plan = []
    t = time.time() + 20
    for _ in range(args.cycles):
        plan += [(t, "off"), (t + args.off, "on")]
        t += args.off + 20
    dur = t - time.time() + 2
else:
    src, plan, dur = args.src, [], args.dur

rd = LatestReader(src, stale_s=3.0)
t0, got, last_print = time.time(), 0, 0
per_sec = []
link = carrier() if args.iface else None
while time.time() - t0 < dur:
    now = time.time()
    while plan and now >= plan[0][0]:
        (fake_off if plan.pop(0)[1] == "off" else fake_on)()
    if args.iface:                                   # 케이블 뽑힘/꽂힘 순간 기록
        c = carrier()
        if c != link:
            link = c
            marks.append((now, "on" if c else "off"))
            print(f"---- 랜 케이블 {'꽂힘' if c else '뽑힘'} ({now - t0:.1f}s)", flush=True)
    ok, f, _, _ = rd.read(timeout=0.2)
    got += ok
    if now - t0 - last_print >= 1:
        last_print = int(now - t0)
        per_sec.append([last_print, got, rd.connected])
        print(f"{last_print:4d}s  받은 프레임 누적 {got:5d}  연결 {'O' if rd.connected else 'X'}", flush=True)

rd.close()
if fake:
    fake_off()

ev = [(round(t - t0, 2), k, m) for t, k, m in rd.events]
mk = [(round(t - t0, 2), k) for t, k in marks]
# 복구 시간 계산
rec = []
for i, (t, k, _) in enumerate(ev):
    if k != "lost":
        continue
    back = next((e for e in ev[i + 1:] if e[1] == "recovered"), None)
    src_on = next((m[0] for m in mk if m[1] == "on" and m[0] > t), None)    # 가짜 카메라 재시작 또는 케이블 꽂힘
    rec.append({"lost_at": t, "recovered_at": back[0] if back else None,
                "down_s": round(back[0] - t, 2) if back else None,
                "after_source_back_s": round(back[0] - src_on, 2) if back and src_on else None})
out = {"src": "fake(8711)" if args.auto_fake else args.src, "events": ev, "source_marks": mk,
       "recoveries": rec, "frames": got, "process_restarts": 0}
print(json.dumps({"recoveries": rec, "frames": got}, ensure_ascii=False))
if args.out:
    with open(args.out, "w") as fo:
        json.dump(out | {"per_sec": per_sec}, fo, ensure_ascii=False, indent=1)
os._exit(0)
