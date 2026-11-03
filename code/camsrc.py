"""과제 1 공통 입력 모듈
- 입력 이름 하나로 VIGI RTSP·가짜 카메라(MJPEG)·동영상 파일·USB 웹캠을 같은 방식으로 연다.
- DirectReader  : (a) cap.read()를 그대로 반복
- LatestReader  : (b) 별도 스레드가 계속 읽고 최신 1장만 남김 + 끊기면 스스로 재연결
- stamp/read_stamp: 가짜 카메라 프레임에 보낸 시각(ms)을 칸 무늬로 찍고 읽는다 (지연 측정용)

입력 이름 예
  vigi:stream1   VIGI 메인 스트림 (2560x1440)
  vigi:stream2   VIGI 서브 스트림 (848x480)
  fake           보드 안의 가짜 카메라 (fakecam.py, http://127.0.0.1:8710)
  media/a.mp4    동영상 파일
  0              USB 웹캠 /dev/video0
"""
import os
import time
import threading
import cv2
import numpy as np

CAM_FILE = os.path.expanduser("~/eg2-lab/.camera_url")
FAKE_URL = "http://127.0.0.1:8710/video.mjpg"


def resolve(src):
    if src.startswith("vigi:"):
        base = open(CAM_FILE).read().strip().rsplit("/", 1)[0]
        return base + "/" + src.split(":", 1)[1]
    if src == "fake":
        return FAKE_URL
    return src


def open_cap(src, transport="tcp", timeout_ms=5000):
    """입력을 연다. 열기·읽기 시간 제한을 둬서 카메라가 빠져도 read()가 영원히 멈추지 않게 한다."""
    url = resolve(src)
    if url.isdigit():
        cap = cv2.VideoCapture(int(url), cv2.CAP_V4L2)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        return cap
    opts = []
    if url.startswith("rtsp"):
        opts.append(f"rtsp_transport;{transport}")
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "|".join(opts)
    return cv2.VideoCapture(url, cv2.CAP_FFMPEG,
                            [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout_ms,
                             cv2.CAP_PROP_READ_TIMEOUT_MSEC, timeout_ms])


def label(src):
    """로그용 이름 (계정 정보가 들어간 URL은 절대 출력하지 않는다)"""
    return src if not src.startswith("rtsp") else "rtsp(...)"


# ---------------- 가짜 카메라 시각 표시 ----------------
BITS, BX, X0, Y0 = 42, 20, 8, 8          # 42비트 ms 시각, 칸 20px


def stamp(img, t_ms):
    """맨 앞 두 칸은 흰/검 기준, 그 뒤 42칸에 시각(ms) 비트"""
    cells = [1, 0] + [(t_ms >> i) & 1 for i in range(BITS)]
    for i, b in enumerate(cells):
        x = X0 + i * BX
        cv2.rectangle(img, (x, Y0), (x + BX - 3, Y0 + BX - 3), (255, 255, 255) if b else (0, 0, 0), -1)


def read_stamp(img):
    """칸 가운데 밝기로 비트를 읽는다. 기준 칸이 안 맞으면 None"""
    if img is None or img.shape[1] < X0 + (BITS + 2) * BX:
        return None
    y = Y0 + BX // 2 - 1
    g = img[y, [X0 + i * BX + BX // 2 - 1 for i in range(BITS + 2)]].mean(axis=1)
    if not (g[0] > 160 and g[1] < 90):
        return None
    bits = (g[2:] > 128).astype(np.int64)
    return int((bits << np.arange(BITS)).sum())


# ---------------- (a) 직접 읽기 ----------------
class DirectReader:
    def __init__(self, src, **kw):
        self.src, self.cap = src, open_cap(src, **kw)
        self.n_read = 0

    def read(self):
        ok, f = self.cap.read()
        if ok:
            self.n_read += 1
        return ok, f, self.cap.get(cv2.CAP_PROP_POS_MSEC), time.time()

    def close(self):
        self.cap.release()


# ---------------- (b) 최신 1장 리더 + 자동 재연결 ----------------
class LatestReader:
    """스레드가 계속 읽어 최신 프레임 1장만 보관한다.
    - read()가 False이거나 stale_s 동안 새 프레임이 없으면 끊긴 것으로 보고 다시 연다.
    - 다시 열기는 1, 2, 4, 5, 5 ...초 간격으로 계속 시도한다 (프로세스는 죽지 않음).
    - events에 (시각, 종류, 내용)을 남긴다: open / lost / retry / recovered
    """

    def __init__(self, src, stale_s=3.0, **kw):
        self.src, self.kw, self.stale_s = src, kw, stale_s
        self.lock = threading.Condition()
        self.frame = None            # (frame, pts_ms, t_recv, seq)
        self.seq = self.taken = self.n_read = 0
        self.reconnects = 0
        self.connected = False
        self.events = []
        self.last_ok = time.time()
        self.stop = self.stale = False
        self.cap = None
        threading.Thread(target=self._loop, daemon=True).start()
        threading.Thread(target=self._watchdog, daemon=True).start()

    def _event(self, kind, msg=""):
        self.events.append((time.time(), kind, msg))

    def _open(self):
        delay = 1.0
        while not self.stop:
            t = time.time()
            cap = open_cap(self.src, **self.kw)
            if cap.isOpened():
                self.cap, self.last_ok = cap, time.time()
                self._event("open", f"{time.time() - t:.2f}s")
                return True
            cap.release()
            self._event("retry", f"{delay:.0f}s 뒤 다시")
            time.sleep(delay)
            delay = min(delay * 2, 5.0)
        return False

    def _mark_lost(self, why):
        if self.connected:
            self._event("lost", why)
            self.reconnects += 1
        self.connected = False

    def _drop(self, why):
        """읽기 스레드에서만 부른다 (읽는 중인 캡처를 다른 스레드가 닫으면 OpenCV가 죽을 수 있음)"""
        self._mark_lost(why)
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    def _loop(self):
        while not self.stop:
            if self.cap is None and not self._open():
                return
            ok, f = self.cap.read()
            if not ok or self.stale:
                self.stale = False
                self._drop("read 실패" if not ok else "새 프레임 끊김")
                continue
            now = time.time()
            if not self.connected:
                self._event("recovered" if self.reconnects else "first_frame")
                self.connected = True
            self.last_ok = now
            with self.lock:
                self.seq += 1
                self.n_read += 1
                self.frame = (f, self.cap.get(cv2.CAP_PROP_POS_MSEC), now, self.seq)
                self.lock.notify_all()
        if self.cap is not None:                 # close() 뒤 읽기 스레드가 직접 닫는다
            self.cap.release()
            self.cap = None

    def _watchdog(self):
        """read()가 막혀 있어도 새 프레임이 끊긴 것을 알아챈다"""
        while not self.stop:
            time.sleep(0.5)
            if self.connected and time.time() - self.last_ok > self.stale_s:
                self._mark_lost(f"{self.stale_s:.0f}초간 새 프레임 없음")
                self.stale = True        # 막힌 read()가 돌아오면 읽기 스레드가 닫고 다시 연다

    def read(self, timeout=1.0):
        """아직 안 가져간 최신 프레임을 돌려준다. timeout 안에 없으면 (False, None, None, None)"""
        with self.lock:
            end = time.time() + timeout
            while self.frame is None or self.frame[3] == self.taken:
                left = end - time.time()
                if left <= 0:
                    return False, None, None, None
                self.lock.wait(left)
            f, pts, t, seq = self.frame
            self.taken = seq
            return True, f, pts, t

    def close(self):
        """읽기 스레드에 멈추라고만 알린다. 캡처는 읽기 스레드가 닫는다
        (읽는 중인 캡처를 다른 스레드에서 release하면 프로세스가 죽는다 — 실제로 겪음)"""
        self.stop = True


def cpu_times():
    """이 프로세스의 (사용자+시스템) CPU 초"""
    t = os.times()
    return t.user + t.system
