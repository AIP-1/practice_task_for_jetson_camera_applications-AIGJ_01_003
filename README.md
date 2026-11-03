# Jetson 카메라 응용 실습 (practice_task_for_jetson_camera_applications)

Jetson Orin Nano Super 한 대와 카메라 2대(VIGI C540-W IP 카메라, Logitech C920 USB 웹캠)로 물체 인식·재실 인원·행동 패턴·거리 측정을 만들고, 재실 인원과 키오스크 행동 패턴을 **상시 서비스**로 12시간 운영한 기록입니다(team2). 영상은 보드 밖으로 내보내지 않고 숫자만 내보냅니다.

👉 **결과 보고서: [docs/결과보고서.md](docs/결과보고서.md)**

## 핵심 결과

| 과제 | 결과 |
|---|---|
| 1 카메라 연동 | 최신 1장 리더 (b)로 2분 뒤 지연 **96초 → 1초 미만**. 재연결 1.2~2.0초 |
| 2 물체 인식 | TensorRT FP16 **5.1ms·60fps** (PyTorch 25.1ms), INT8 mAP −0.025. 비COCO 5종: 재라벨 4/5, YOLOE 최대 3/5 |
| 3 재실 인원 | 서비스 v1(MQTT retain 10초). 군중 데이터 MAE 16.2 → 10.4(설정) → 3.1(보정). 12시간 빈 방 오판 0/716 |
| 4 행동 패턴 | 키오스크 판정기 가동. 안정화로 깜빡임 21 → 8, 올림 기준 변경으로 만세 63.7% → 93.4% |
| 5 거리 측정 | 가상 세 지점 오차 0.1 / 0.2 / 0.0%. 방 좌표 방식 2대 보정 재투영 0.44 / 0.39px |
| 6 응용 서비스 | **12시간 무중단**(718/720행, 재연결 0), 재부팅 후 10~13초 복귀, 영상 저장 0건, 평균 9.1W |

## 문서

| 문서 | 내용 |
|---|---|
| [docs/결과보고서.md](docs/결과보고서.md) | 과제 1~6 결과, 측정 조건, 왜 틀렸고 무엇을 바꿨는지, 하지 않은 것 |
| [docs/결과형식문서.md](docs/결과형식문서.md) | 다른 팀용 MQTT 토픽·필드·단위·예시·갱신 주기, REST |
| [docs/자원계획표.md](docs/자원계획표.md) | GPU·CPU·메모리·전력 계산치 대 12시간 실측치 |
| [docs/과제1_결과.md](docs/과제1_결과.md) | 과제 1 상세 기록 |
| [docs/확인문제_답안.md](docs/확인문제_답안.md) | 확인 문제 1~6 답안 |

## 코드

| 위치 | 내용 |
|---|---|
| `code/camsrc.py`, `probe.py`, `reader_compare.py`, `reconnect_test.py`, `fakecam.py`, `viewer.py` | 과제 1: 공통 입력 모듈(최신 1장 리더 + 자동 재연결), 연결 시험, (a)/(b) 비교, 재연결 시험, 가짜 카메라, 브라우저 뷰어 |
| `code/service/occupancy_service.py`, `occupancy.service` | 과제 3·6: 재실 인원 서비스와 systemd 유닛 |
| `code/service/pose_app.py`, `pose_model.py`, `pose-service.service` | 과제 4·6: 키오스크 동작·행동 판정 서비스와 systemd 유닛 |
| `code/tools/` | 과제 1~5 시험 스크립트 (벤치마크 `bench2.py`, 조명×거리 `light2.py`, 선 통과 `line2.py`, 개방 어휘 `vocab2.py`, 재실 평가 `occ_eval.py`·`occ_calib.py`, 계수 비교 `vcount.py`, 가상 스테레오 `vstereo.py`·`vprox.py`, 12시간 요약 `occ_summary.py` 등) |

## 결과 파일

| 위치 | 내용 |
|---|---|
| `results/*.json`, `*.log` | 과제 1 연결 시험·리더 비교·재연결 원자료 |
| `results/runs/` | 과제 1~6 시험 결과 표(md), 원자료(csv, jsonl) |
| `results/service_logs/` | 12시간 가동 원자료: 1분마다 서비스 상태(`service_*.jsonl`), 이벤트(`events.jsonl`), 전력·GPU(`tegrastats.log`) |

## 실행 환경

| 항목 | 값 |
|---|---|
| 보드 | Jetson Orin Nano Super 8GB, JetPack 7.2.1, MAXN_SUPER |
| 카메라 | VIGI C540-W (보드 유선 직결, RTSP), Logitech C920 (USB, MJPG) |
| 실행 | 호스트 venv, systemd (`Restart=always`) |

카메라 비밀번호는 서비스 유닛의 `EnvironmentFile`(권한 600)에서 읽고, 코드·저장소에는 넣지 않았습니다.

## 올리지 않은 것

- **사람이 나올 수 있는 사진·영상**: 보정 화면, 조명 시험 사진, 동작 영상
- **카메라 계정 정보**: `.env`, `.camera_url`
- **모델 파일**: `.pt`, `.engine`, `.onnx`
