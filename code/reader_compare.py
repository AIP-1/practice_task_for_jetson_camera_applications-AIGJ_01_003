"""1-2 수신 루프 비교: (a) read() 그대로 반복 vs (b) 최신 1장 리더, 둘 다 프레임마다 0.2초 '처리'를 흉내
실행: python reader_compare.py --src vigi:stream2 --mode a --delay 0.2 --dur 120 --out results/a_stream2.json

지연을 재는 방법
- 가짜 카메라: 프레임에 찍힌 보낸 시각 → 지금 처리하는 프레임의 나이 = 지금 − 보낸 시각 (절대값, ms)
- VIGI: 프레임 PTS(카메라 타임스탬프) → 나이 증가분 = (지금 − 첫 프레임 처리 시각) − (PTS − 첫 PTS)
  첫 프레임의 나이(약 0.1~0.3초)는 모르므로 '처음보다 얼마나 더 늦어졌나'를 잰다.
"""
import argparse
import json
import os
import time

import numpy as np

from camsrc import DirectReader, LatestReader, read_stamp, cpu_times

ap = argparse.ArgumentParser()
ap.add_argument("--src", required=True)
ap.add_argument("--mode", choices=["a", "b"], required=True)
ap.add_argument("--delay", type=float, default=0.2)
ap.add_argument("--dur", type=float, default=120)
ap.add_argument("--transport", default="tcp")
ap.add_argument("--out", default=None)
args = ap.parse_args()

rd = DirectReader(args.src, transport=args.transport) if args.mode == "a" else LatestReader(args.src, transport=args.transport)
series, used, base = [], 0, None
fails, first_fail = 0, None              # (a)에서 read()가 실패한 횟수와 처음 실패한 시각
t_start = time.time()
c0 = cpu_times()
last_print = 0
while time.time() - t_start < args.dur:
    ok, f, pts, t_recv = rd.read()
    if not ok:
        fails += 1
        if first_fail is None:
            first_fail = round(time.time() - t_start, 1)
            print(f"[{args.mode}] {first_fail}s 첫 read 실패 (연결 끊김?)", flush=True)
        if args.mode == "a":
            time.sleep(0.1)
        continue
    now = time.time()
    ts = read_stamp(f)
    age = (now * 1000 - ts) if ts is not None else None           # 가짜 카메라: 절대 나이(ms)
    if base is None:
        base = (now, pts)
    grow = ((now - base[0]) - (pts - base[1]) / 1000) * 1000 if pts and pts > 0 else None   # PTS 기준 증가분(ms)
    used += 1
    el = now - t_start
    series.append([round(el, 2), None if age is None else round(age), None if grow is None else round(grow)])
    if el - last_print >= 10:
        last_print = el
        print(f"[{args.mode}] {el:5.0f}s 처리 {used}장  나이 {age if age is None else round(age)}ms  "
              f"PTS증가 {grow if grow is None else round(grow)}ms  읽은 프레임 {rd.n_read}", flush=True)
    time.sleep(args.delay)                                        # 추론 0.2초 흉내
el = time.time() - t_start
cpu = 100 * (cpu_times() - c0) / el


def at(sec, col):
    v = [s[col] for s in series if s[col] is not None and sec - 5 <= s[0] <= sec + 5]
    return round(float(np.median(v))) if v else None


summ = {"src": args.src, "mode": args.mode, "delay": args.delay, "dur": round(el), "transport": args.transport,
        "used": used, "used_fps": round(used / el, 2), "read": rd.n_read,
        "dropped": rd.n_read - used, "cpu_proc_pct": round(cpu, 1),
        "read_fails": fails, "first_fail_s": first_fail}
for col, name in ((1, "age_ms"), (2, "grow_ms")):
    summ[name] = {f"{s}s": at(s, col) for s in (10, 30, 60, 90, int(el) - 5)}
if args.mode == "b":
    summ["reconnects"] = rd.reconnects
print(json.dumps(summ, ensure_ascii=False), flush=True)   # os._exit 전에 버퍼를 비워야 로그에 남음
if args.out:                              # 저장을 먼저 (닫다가 죽어도 결과는 남게)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as fo:
        json.dump({"summary": summ, "series": series}, fo, ensure_ascii=False)
rd.close()
os._exit(0)
