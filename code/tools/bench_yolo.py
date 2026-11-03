#!/usr/bin/env python3
"""과제 2 벤치마크: 모델별 추론 시간(평균·p95)과 FPS를 CSV로 저장
  python bench_yolo.py --models yolo11n.pt yolo11s.pt --export
--export 는 TensorRT FP16·INT8 엔진 변환을 시도한다. 실패하면 이유를 적고 PyTorch 결과만 남긴다.
--map 은 coco8로 mAP50-95를 잰다 (데이터 내려받기 필요, 표본이 작아 참고값).
"""
import argparse, csv, time
import numpy as np
from ultralytics import YOLO

ap = argparse.ArgumentParser()
ap.add_argument("--models", nargs="+", default=["yolo11n.pt"])
ap.add_argument("--imgsz", type=int, default=640)
ap.add_argument("--frames", type=int, default=200)
ap.add_argument("--export", action="store_true")
ap.add_argument("--map", action="store_true")
ap.add_argument("--out", default="runs/bench.csv")
a = ap.parse_args()
img = (np.random.default_rng(0).random((720, 1280, 3)) * 255).astype(np.uint8)

def bench(path):
    m = YOLO(path)
    for _ in range(30):
        m.predict(img, imgsz=a.imgsz, verbose=False)
    ts = []
    for _ in range(a.frames):
        t = time.perf_counter(); m.predict(img, imgsz=a.imgsz, verbose=False); ts.append((time.perf_counter() - t) * 1000)
    row = {"model": path, "mean_ms": round(float(np.mean(ts)), 2), "p95_ms": round(float(np.percentile(ts, 95)), 2),
           "fps": round(1000 / float(np.mean(ts)), 1), "map50_95": ""}
    if a.map:
        try:
            row["map50_95"] = round(float(m.val(data="coco8.yaml", imgsz=a.imgsz, verbose=False).box.map), 3)
        except Exception as e:
            print("mAP 실패:", e)
    print(row, flush=True)
    return row

rows = []
for p in a.models:
    rows.append(bench(p))
    if a.export:
        for kw in ({"half": True}, {"int8": True, "data": "coco8.yaml"}):
            try:
                rows.append(bench(YOLO(p).export(format="engine", imgsz=a.imgsz, **kw)))
            except Exception as e:
                print(f"{p} {kw} 변환 실패: {e}", flush=True)
                rows.append({"model": f"{p} {kw}", "mean_ms": "", "p95_ms": "", "fps": "", "map50_95": "변환 실패"})
with open(a.out, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
print("저장:", a.out)
