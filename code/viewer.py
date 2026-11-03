"""1-5 헤드리스 뷰어 + 1-4 glass-to-glass 측정 페이지
- 보드에 화면이 없어도 PC 브라우저로 본다. 보드의 127.0.0.1에만 열고 PC에서는 SSH 터널로 접속한다
  (학교 와이파이에 영상이 노출되지 않게).
    보드:  python viewer.py --src vigi:stream2
    PC:    ssh -N -L 8720:127.0.0.1:8720 jetson   →  http://localhost:8720
- /          카메라 영상 + 상태
- /g2g       왼쪽에 ms 시계, 오른쪽에 카메라 영상. 카메라가 이 화면(시계)을 찍게 두고 화면을 캡처하면
             '시계 숫자 − 영상 속 시계 숫자' = glass-to-glass 지연
- /stats     상태 JSON (FPS, 재연결 횟수, 이벤트)
"""
import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2

from camsrc import LatestReader

ap = argparse.ArgumentParser()
ap.add_argument("--src", default="vigi:stream2")
ap.add_argument("--port", type=int, default=8720)
ap.add_argument("--width", type=int, default=960, help="브라우저로 보낼 폭 (원본이 크면 줄임)")
ap.add_argument("--quality", type=int, default=80)
ap.add_argument("--no-overlay", action="store_true", help="g2g 측정 때 글자를 가리지 않게")
args = ap.parse_args()

rd = LatestReader(args.src)
cond = threading.Condition()
state = {"seq": 0, "jpg": b"", "fps": 0.0, "res": None}


def encoder():
    n, t0 = 0, time.time()
    while True:
        ok, f, _, _ = rd.read(timeout=1.0)
        if not ok:
            continue
        n += 1
        if time.time() - t0 >= 2:
            state["fps"], n, t0 = n / (time.time() - t0), 0, time.time()
        state["res"] = f"{f.shape[1]}x{f.shape[0]}"
        if f.shape[1] > args.width:
            f = cv2.resize(f, (args.width, int(f.shape[0] * args.width / f.shape[1])), interpolation=cv2.INTER_AREA)
        if not args.no_overlay:
            cv2.putText(f, f"{args.src.split(':')[-1]} {state['res']} {state['fps']:.1f}fps  reconnect {rd.reconnects}",
                        (10, f.shape[0] - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        jpg = cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, args.quality])[1].tobytes()
        with cond:
            state["seq"] += 1
            state["jpg"] = jpg
            cond.notify_all()


INDEX = """<!doctype html><meta charset=utf-8><title>카메라 뷰어</title>
<body style="background:#111;color:#ddd;font-family:sans-serif;margin:16px">
<img src="/video.mjpg" style="max-width:100%"><pre id=s></pre>
<script>setInterval(async()=>{const j=await (await fetch('/stats')).json();
document.getElementById('s').textContent=JSON.stringify(j,null,1)},1000)</script>"""

G2G = """<!doctype html><meta charset=utf-8><title>glass-to-glass</title>
<body style="background:#000;color:#fff;margin:0;display:flex;align-items:center;gap:24px;padding:16px;font-family:monospace">
<div><div id=c style="font-size:64px;background:#fff;color:#000;padding:8px 16px">0</div>
<div style="font-size:14px;color:#aaa;margin-top:8px">카메라가 이 시계를 찍게 두세요 (단위 ms, 마지막 5자리)</div></div>
<img src="/video.mjpg" style="width:60vw">
<script>const c=document.getElementById('c');
(function t(){c.textContent=String(Date.now()%100000).padStart(5,'0');requestAnimationFrame(t)})()</script>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, ctype):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            return self._send(INDEX.encode(), "text/html; charset=utf-8")
        if self.path == "/g2g":
            return self._send(G2G.encode(), "text/html; charset=utf-8")
        if self.path == "/stats":
            s = {"src": args.src, "res": state["res"], "fps": round(state["fps"], 1), "connected": rd.connected,
                 "reconnects": rd.reconnects,
                 "events": [(time.strftime("%H:%M:%S", time.localtime(t)), k, m) for t, k, m in rd.events[-8:]]}
            return self._send(json.dumps(s, ensure_ascii=False).encode(), "application/json")
        if self.path.startswith("/video.mjpg"):
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=f")
            self.end_headers()
            last = 0
            try:
                while True:
                    with cond:
                        cond.wait_for(lambda: state["seq"] != last, timeout=5)
                        last, jpg = state["seq"], state["jpg"]
                    self.wfile.write(b"--f\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                     + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                return
        self.send_error(404)


threading.Thread(target=encoder, daemon=True).start()
print(f"[viewer] {args.src} → http://127.0.0.1:{args.port}  (PC: ssh -N -L {args.port}:127.0.0.1:{args.port} jetson)", flush=True)
ThreadingHTTPServer(("127.0.0.1", args.port), H).serve_forever()
