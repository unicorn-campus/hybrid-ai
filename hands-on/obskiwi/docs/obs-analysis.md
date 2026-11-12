# OBS Studio 분석 결과 (REA MCP)

obskiwi 설계 근거로 삼기 위해 이 PC에 설치된 OBS Studio를 REA MCP로 정적 분석한 결과임.  
실행 중인 OBS를 관찰한 것이 아니라 **설치된 파일(바이너리, 설정, 리소스)을 읽은 결과**임.

## 1. 분석 대상과 방법

| 대상 | 경로 | 사용한 REA 도구 | Evidence ID(앞 12자리) |
|------|------|----------------|----------------------|
| 설치 폴더 전체 | `C:\Program Files\obs-studio` | `inspect_desktop_application` | `ev_abadde46315a` |
| 화면 프로그램 | `bin\64bit\obs64.exe` | `inspect_pe_imports` | `ev_1dd46de9e6be` |
| 핵심 엔진 | `bin\64bit\obs.dll` (libobs) | `inspect_native_exports` | `ev_1b45f502194c` |

- 설치 폴더: 파일 2,245개 검사, Electron이나 .NET 같은 런타임 후보 없음(네이티브 C/C++ 앱)  
- 보조 확인: 플러그인 폴더 목록, 사용자 장면 모음 JSON의 키 구조, 한국어 번역 파일(ko-KR.ini)

## 2. 구조: 엔진과 화면이 나뉨

```text
obs64.exe (Qt6 화면)  ──부름──▶  obs.dll (libobs 엔진)  ──불러옴──▶  obs-plugins\64bit\*.dll
   메뉴, 도크, 버튼               장면, 소스, 출력, 인코더            화면 캡처, 웹캠, 텍스트, 필터 등
```

- `obs.dll`은 내보내는 함수가 1,782개이며 엔진 기능 전체를 담당함  
- `obs64.exe`는 그중 765개를 가져다 쓰며 Qt6Widgets 함수 1,536개로 화면을 구성함  
- 실제 기능(캡처, 인코딩)은 대부분 플러그인 DLL에 있음

### obs.dll 내보내기 함수 묶음(상위)

| 묶음 | 개수 | 뜻 |
|------|-----:|----|
| `obs_data_*` | 156 | 설정값 저장과 읽기(JSON 형태) |
| `obs_source_*` | 156 | 소스(화면, 웹캠, 이미지 등) 만들기, 음량, 음소거 |
| `obs_property_*` | 81 | 소스 속성 창 항목 |
| `obs_output_*` | 75 | 녹화, 방송 출력 시작과 중지 |
| `obs_sceneitem_*` | 67 | 장면 안 항목의 위치, 크기, 보임 여부 |
| `obs_encoder_*` | 61 | 영상과 음성 인코더 |
| `obs_hotkey_*` | 36 | 단축키 |
| `obs_transition_*` | 25 | 장면 전환 효과 |
| `obs_scene_*` | 24 | 장면 만들기, 복제, 항목 추가 |
| `obs_fader_*`, `obs_volmeter_*` | 13 이상 | 음량 조절기와 음량 막대 |

### 화면 프로그램이 실제로 쓰는 핵심 함수(가져오기 표에서 확인)

- 장면: `obs_scene_create`, `obs_scene_add`, `obs_scene_duplicate`, `obs_scene_add_group`  
- 장면 항목: `obs_sceneitem_set_pos`, `obs_sceneitem_set_scale`, `obs_sceneitem_set_visible`  
- 소스: `obs_source_create`, `obs_source_update`, `obs_source_set_volume`, `obs_source_set_muted`  
- 오디오 믹서: `obs_fader_create`, `obs_fader_attach_source`, `obs_volmeter_create`, `obs_volmeter_add_callback`  
- 출력: `obs_output_create`, `obs_output_start`, `obs_output_stop`  
- 전환: `obs_transition_start`  
- 프런트엔드 API: `obs_frontend_recording_active`, `obs_frontend_streaming_active`,  
  `obs_frontend_preview_program_mode_active`(스튜디오 모드), `obs_frontend_recording_split_file`

### 화면 구성(Qt 클래스와 번역 문자열로 추정)

- `QMainWindow` + `QDockWidget` + `QSplitter`: 가운데 미리보기, 아래쪽 도크 배치  
- 번역 파일의 도크 이름: 「장면 목록」, 「소스 목록」, 「장면 전환」, 「제어」(녹화 시작, 방송 시작, 가상 카메라 시작)  
- `QSlider`, `QProgressBar` 계열: 오디오 믹서의 음량 조절기와 막대

## 3. 플러그인(obs-plugins\64bit)

| 플러그인 | 역할 |
|---------|------|
| `win-capture.dll` | 모니터 캡처, 창 캡처, 게임 캡처 |
| `win-dshow.dll` | 웹캠 같은 영상 장치 |
| `win-wasapi.dll` | 데스크톱 소리, 마이크 |
| `image-source.dll`, `obs-text.dll`, `text-freetype2.dll` | 이미지, 텍스트 |
| `obs-transitions.dll` | 페이드 같은 전환 효과 |
| `obs-ffmpeg.dll`, `obs-x264.dll`, `obs-nvenc.dll`, `obs-qsv11.dll` | 인코딩, 파일 저장 |
| `obs-outputs.dll`, `rtmp-services.dll`, `obs-webrtc.dll` | 방송 송출 |
| `obs-websocket.dll` | 외부 원격 제어 |

## 4. 장면 모음 저장 형식(사용자 JSON 키)

`%APPDATA%\obs-studio\basic\scenes\*.json`의 최상위 키 일부:  
`name`, `sources`, `scene_order`, `current_scene`, `current_transition`, `transition_duration`, `transitions`

- **장면도 소스의 한 종류**임: `sources` 배열 안에 `id: "scene"` 항목이 있고 `settings.items`에 장면 항목 목록을 담음  
- 일반 소스는 `id: "monitor_capture"`처럼 종류 ID와 `settings`를 가짐

## 5. obskiwi로 옮기는 개념

| OBS 개념 | obskiwi 구현 |
|---------|-------------|
| 장면 = 소스 묶음, 장면 항목 = 위치, 크기, 보임 여부 | 같은 모델을 TypeScript 타입으로 정의 |
| 렌더 그래프(`gs_*`) | HTML Canvas 2D 합성(30fps) |
| `win-capture` | Electron `desktopCapturer` + `getDisplayMedia` |
| `win-dshow`, `win-wasapi` | `getUserMedia`(웹캠, 마이크), 데스크톱 소리는 loopback |
| `obs_fader`, `obs_volmeter` | Web Audio `GainNode`, `AnalyserNode` |
| `obs_output` + 인코더 | `MediaRecorder`(WebM) |
| `obs_transition_start` | 자르기, 페이드 전환 |
| 장면 모음 JSON | 같은 발상의 JSON 파일(사용자 데이터 폴더) |

범위 밖: 방송 송출(RTMP), 가상 카메라, 필터, 플러그인 구조, 단축키

## 6. 한계

- 정적 분석이므로 실제 실행 흐름은 관찰하지 않음  
- 함수 이름으로 역할을 추정했으며 함수 내부(디컴파일)는 보지 않음  
- 화면 배치는 Qt 클래스와 번역 문자열로 추정한 것임
