### 과제 1 심화 — 1080p 디코딩: 하드웨어(NVDEC) vs CPU

| 방식 | 흘리는 속도 | 처리 FPS | 프로세스 CPU (코어 1개=100%) | 걸린 시간 (s) | 성공 |
|---|---|---|---|---|---|
| gst-nvdec (하드웨어) | 최대 속도 | — | 64% | 5.0 | ✅ |
| gst-nvdec (하드웨어) | 실시간 30fps | — | 12% | 30.2 | ✅ |
| gst-cpu (avdec_h264) | 최대 속도 | — | 226% | 9.2 | ✅ |
| gst-cpu (avdec_h264) | 실시간 30fps | — | 94% | 30.2 | ✅ |
| opencv-cpu (FFmpeg) | 최대 속도 | 157.4 | 266% | 5.7 | ✅ |
| opencv-cpu (FFmpeg) | 실시간 30fps | 30.0 | 65% | 30.0 | ✅ |

입력: runs/test1080p.mp4 (None프레임, 1920x1080 H.264 High, GOP 30, B-프레임 없음). GStreamer는 출력까지 BGRx로 변환(OpenCV에 넘길 수 있는 형태)한 뒤 버림. CPU 사용률 = 그 프로세스의 (user+sys) CPU 시간 ÷ 걸린 시간. 보드 전력 모드 MAXN_SUPER.