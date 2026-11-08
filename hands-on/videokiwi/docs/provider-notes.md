# MiniMax H3 로컬 연동

## 연동 방식

VideoKiwi 서버가 같은 컴퓨터에서 실행되는 ComfyUI HTTP API를 직접 호출합니다.  
브라우저는 VideoKiwi 서버를 통해 입력과 결과를 주고받습니다. 외부 API 키는 필요하지 않습니다.

| 기능 | ComfyUI 경로 | 구분 | 제한 장치 |
|---|---|---|---|
| 엔진 상태 확인 | `GET /system_stats`, `GET /object_info`, `GET /queue` | 읽기 | 10초 제한 시간 |
| 입력 이미지 저장 | `POST /upload/image` | 쓰기 | 로컬 루프백만 허용, 파일명 정리 |
| 생성 요청 | `POST /prompt` | 쓰기 | 검증된 워크플로, 자동 재시도 없음 |
| 작업 상태 확인 | `GET /history/{id}`, `GET /queue` | 읽기 | UUID 형식 검사 |
| 대기 작업 취소 | `POST /queue` | 쓰기 | 지정 ID만 삭제 |
| 실행 작업 취소 | `POST /interrupt` | 쓰기 | 실행 큐에서 같은 ID를 확인한 뒤 지정 ID 전송 |
| 결과 영상 읽기 | `GET /view` | 읽기 | 서버가 돌려준 파일 참조만 사용 |

## 워크플로

기본 경로는 Q4 모델, Q2 텍스트 인코더, 영상 VAE와 음성 VAE를 사용합니다.  
샘플러는 `res_multistep`이며 균형 프로파일은 20단계, 품질 탐색은 30단계로 실행합니다.  
빠른 경로는 같은 모델에 Turbo 8단계 LoRA와 `MiniMaxH3SigmaShift`를 연결합니다.  
샘플러는 `euler`이며 생성 단계는 8회입니다.

시작 이미지와 끝 이미지는 각각 `LoadImage` 노드를 만들어  
`MiniMaxH3ImageToVideo.first_frame`과 `last_frame`에 연결합니다.  
영상 길이는 24fps와 `17k+5` 프레임 규칙을 검사합니다.

## 모델 준비 판정

다음 네 모델이 `/object_info`의 선택 목록에 모두 있을 때 기본 모델을 준비된 상태로 판정합니다.

- `minimax_h3_fl2va_pruned-Q4_K.gguf`
- `qwen3vl-32B-MiniMax-H3-Q2_K.gguf`
- `minimax_h3_video_vae_fp16.safetensors`
- `minimax_h3_audio_vae_fp32.safetensors`

빠른 모드는 아래 LoRA와 `MiniMaxH3SigmaShift` 노드를 별도로 확인합니다.

- `minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors`

## 취소 경쟁 조건

대기 작업을 확인한 직후 실행으로 바뀔 수 있어, 대기 작업을 삭제한 뒤 큐를 다시 읽습니다.  
그 사이 같은 ID가 실행 상태로 바뀌면 지정 ID를 담은 `/interrupt` 요청을 보냅니다.  
다른 ID의 실행 작업에는 전역 중단 요청을 보내지 않습니다.

## 확인 결과

2026-11-08 최초 읽기 확인에서는 ComfyUI `0.43.0` 연결, RTX 4090 Laptop GPU와 모델 선택 목록을 확인했습니다.  
당시에는 기존 Skyfish 작업이 실행 중이어서 제출이나 취소를 수행하지 않았습니다.  
사용자가 이후 GPU 사용을 허용했고, 큐가 비었을 때 이미지 입력과 텍스트 입력을 실제로 생성했습니다.  
두 경로의 업로드와 제출, 결과 조회와 영상 재생이 성공했습니다. 실제 취소 동작은 이번 GPU 시험에 포함하지 않았습니다.  
작업 완료 기록에서는 `SaveVideo`가 `outputs[14].images`에 MP4 참조를 남기는 것도 확인했습니다.  
측정값과 실행 근거는 [검증 기록](verification.md)에 있습니다.
