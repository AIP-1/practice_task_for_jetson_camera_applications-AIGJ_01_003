"""가짜 카메라: 보드 안에서만 열리는 MJPEG(HTTP) 카메라
- 웹캠이 없어서 대신 쓴다. 프레임마다 보낸 시각(ms)을 칸 무늬로 찍어, 받는 쪽이 지연을 ms 단위로 잴 수 있다.
- 카메라처럼 일정한 FPS로 '밀어 보낸다'. 받는 쪽이 느리면 소켓 버퍼가 찰 때까지 쌓이고, 그 뒤에는 보내기가 막힌다.
실행: python fakecam.py [--fps 30] [--size 1280x720] [--port 8710]
"""
import argparse
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np

from camsrc import stamp

ap = argparse.ArgumentParser()
ap.add_argument("--fps", type=float, default=30)
ap.add_argument("--size", default="1280x720")
ap.add_argument("--port", type=int, default=8710)
ap.add_argument("--quality", type=int, default=80)
args = ap.parse_args()
W, H = map(int, args.size.split("x"))

cond = threading.Condition()
latest = (0, b"")                      # (seq, jpeg)


def producer():
    global latest
    base = np.zeros((H, W, 3), np.uint8)
    base[:] = np.linspace(40, 120, W, dtype=np.uint8)[None, :, None]    # 무늬 있는 배경
    seq, period, nxt = 0, 1.0 / args.fps, time.time()
    while True:
        nxt += period
        img = base.copy()
        t = time.time()
        x = int((t * 300) % W)
        cv2.circle(img, (x, H // 2), 60, (0, 200, 255), -1)                       # 움직이는 공
        cv2.putText(img, time.strftime("%H:%M:%S", time.localtime(t)) + f".{int(t * 1000) % 1000:03d}",
                    (40, H - 60), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (255, 255, 255), 4)
        cv2.putText(img, f"FAKE CAM #{seq}", (40, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (255, 255, 255), 3)
        stamp(img, int(time.time() * 1000))                                        # 인코딩 직전 시각
        ok, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, args.quality])
        seq += 1
        with cond:
            latest = (seq, jpg.tobytes())
            cond.notify_all()
        d = nxt - time.time()
        if d > 0:
            time.sleep(d)
        else:
            nxt = time.time()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if not self.path.startswith("/video.mjpg"):
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.end_headers()
        last = 0
        try:
            while True:
                with cond:
                    while latest[0] == last:
                        cond.wait()
                    last, jpg = latest
                self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                 + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n")
        except (BrokenPipeError, ConnectionResetError):
            pass


threading.Thread(target=producer, daemon=True).start()
print(f"[fakecam] http://127.0.0.1:{args.port}/video.mjpg  {W}x{H} @ {args.fps}fps", flush=True)
ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
