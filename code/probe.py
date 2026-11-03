"""1-1 연결 시험: 입력별 열기 시간·첫 프레임 지연·실측 FPS·해상도·CPU 사용률
실행: python probe.py vigi:stream1 vigi:stream2 fake media/x.mp4 [--sec 20] [--out results/probe.json]
- 첫 프레임 지연 = VideoCapture를 만들기 시작한 때부터 첫 read()가 성공할 때까지
- 실측 FPS = sec초 동안 read()를 쉬지 않고 반복해 받은 프레임 수 ÷ 시간
- CPU = 이 프로세스가 쓴 CPU 시간 ÷ 경과 시간 (100% = 코어 1개, 보드는 6코어)
- 가짜 카메라는 프레임에 찍힌 시각으로 '받은 시각 − 보낸 시각'(수신 지연)도 잰다
"""
import argparse
import json
import os
import time

import cv2
import numpy as np

from camsrc import open_cap, read_stamp, cpu_times

ap = argparse.ArgumentParser()
ap.add_argument("sources", nargs="+")
ap.add_argument("--sec", type=float, default=20)
ap.add_argument("--transport", default="tcp")
ap.add_argument("--out", default=None)
args = ap.parse_args()


def sys_cpu():
    with open("/proc/stat") as f:
        v = list(map(int, f.readline().split()[1:]))
    return sum(v), v[3] + v[4]          # 전체, idle+iowait


rows = []
for src in args.sources:
    t0 = time.time()
    cap = open_cap(src, transport=args.transport)
    t_open = time.time() - t0
    if not cap.isOpened():
        print(f"{src}: 열기 실패")
        rows.append({"src": src, "ok": False})
        continue
    ok, f = cap.read()
    t_first = time.time() - t0
    shape = None if f is None else f.shape
    n, fails, lat = 0, 0, []
    c0, (s0, i0), tw = cpu_times(), sys_cpu(), time.time()
    while time.time() - tw < args.sec:
        ok, f = cap.read()
        if not ok:
            fails += 1
            if fails > 50:
                break
            continue
        n += 1
        ts = read_stamp(f)
        if ts is not None:
            lat.append(time.time() * 1000 - ts)
    el = time.time() - tw
    c1, (s1, i1) = cpu_times(), sys_cpu()
    r = {"src": src, "ok": True, "res": f"{shape[1]}x{shape[0]}" if shape else None,
         "open_s": round(t_open, 2), "first_frame_s": round(t_first, 2),
         "fps_prop": cap.get(cv2.CAP_PROP_FPS), "fps": round(n / el, 2), "frames": n, "fails": fails,
         "cpu_proc_pct": round(100 * (c1 - c0) / el, 1),
         "cpu_sys_pct": round(100 * (1 - (i1 - i0) / max(s1 - s0, 1)), 1),
         "transport": args.transport if src.startswith("vigi") else None}
    if lat:
        r["recv_lat_ms"] = {"mean": round(float(np.mean(lat)), 1), "p95": round(float(np.percentile(lat, 95)), 1)}
    cap.release()
    rows.append(r)
    print(json.dumps(r, ensure_ascii=False), flush=True)

if args.out:
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as fo:
        json.dump({"sec": args.sec, "rows": rows, "ts": time.strftime("%F %T")}, fo, ensure_ascii=False, indent=1)
