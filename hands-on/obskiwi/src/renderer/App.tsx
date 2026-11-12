import { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import type { OutputSettings } from '../shared/types';
import { createDefaultCollection, reducer, type AppState } from './state/reducer';
import { fitRect } from './engine/compositor';
import { hub } from './engine/hub';
import { Preview } from './components/Preview';
import { ScenesDock } from './components/ScenesDock';
import { SourcesDock } from './components/SourcesDock';
import { AudioMixerDock } from './components/AudioMixerDock';
import { TransitionDock } from './components/TransitionDock';
import { ControlsDock } from './components/ControlsDock';
import { StatusBar } from './components/StatusBar';
import { SettingsDialog } from './components/Dialogs';

function Dock(props: { title: string; children: React.ReactNode }) {
  return (
    <section className="dock">
      <header className="dock-title">{props.title}</header>
      {props.children}
    </section>
  );
}

export function App() {
  const [state, dispatch] = useReducer(reducer, undefined, (): AppState => ({
    collection: createDefaultCollection(''),
    selectedItemId: null,
  }));
  const [loaded, setLoaded] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [recordingStartedAt, setRecordingStartedAt] = useState<number | null>(null);
  const [recordBusy, setRecordBusy] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const [renderFps, setRenderFps] = useState(0);
  const [toast, setToast] = useState<{ text: string; error: boolean } | null>(null);

  const { collection } = state;
  const colRef = useRef(collection);
  colRef.current = collection;

  const showToast = useCallback((text: string, error = false) => {
    setToast({ text, error });
  }, []);
  useEffect(() => {
    if (!toast) return;
    const t = window.setTimeout(() => setToast(null), toast.error ? 8000 : 10000);
    return () => window.clearTimeout(t);
  }, [toast]);

  // ---------- 불러오기와 저장(500ms 디바운스) ----------

  useEffect(() => {
    (async () => {
      const [saved, defaultDir] = await Promise.all([
        window.obskiwi.loadCollection(),
        window.obskiwi.getDefaultOutputDir(),
      ]);
      const base = saved ?? createDefaultCollection(defaultDir);
      if (!base.settings.outputDir) base.settings.outputDir = defaultDir;
      dispatch({ type: 'load', collection: base });
      setLoaded(true);
    })().catch((e: unknown) => {
      showToast(e instanceof Error ? e.message : '장면 모음을 불러오지 못함', true);
      setLoaded(true);
    });
  }, [showToast]);

  useEffect(() => {
    if (!loaded) return;
    const t = window.setTimeout(() => {
      window.obskiwi.saveCollection(collection).catch((e: unknown) => {
        showToast(e instanceof Error ? e.message : '저장하지 못함', true);
      });
    }, 500);
    return () => window.clearTimeout(t);
  }, [collection, loaded, showToast]);

  // ---------- 엔진과 상태 맞추기 ----------

  // 음량과 음소거를 믹서에 반영
  const { desktop, mic } = collection.audio;
  useEffect(() => {
    hub.audio.setVolume('desktop', desktop.volume);
    hub.audio.setMuted('desktop', desktop.muted);
  }, [desktop.volume, desktop.muted]);
  useEffect(() => {
    hub.audio.setVolume('mic', mic.volume);
    hub.audio.setMuted('mic', mic.muted);
  }, [mic.volume, mic.muted]);

  // 마이크 장치가 정해지면(불러온 뒤 또는 바뀔 때) 마이크를 엶
  useEffect(() => {
    if (loaded) void hub.audio.enableMic(mic.deviceId);
  }, [loaded, mic.deviceId]);

  // 어느 장면에서도 쓰지 않는 소스의 캡처는 닫음
  useEffect(() => {
    hub.media.releaseUnused(new Set(collection.sources.map((s) => s.id)));
  }, [collection.sources]);

  // 새로 추가한 미디어 소스는 첫 영상 크기를 알게 되면 화면에 맞춤
  useEffect(() => {
    hub.media.onReady = (sourceId, w, h) => {
      const itemId = hub.pendingFit.get(sourceId);
      if (!itemId || w <= 0 || h <= 0) return;
      hub.pendingFit.delete(sourceId);
      const { width, height } = colRef.current.settings;
      dispatch({ type: 'updateItem', itemId, patch: fitRect(w, h, width, height) });
    };
    return () => {
      hub.media.onReady = null;
    };
  }, []);

  // 녹화 경과 시간 표시용 시계
  useEffect(() => {
    if (recordingStartedAt === null) return;
    const t = window.setInterval(() => setNow(Date.now()), 500);
    return () => window.clearInterval(t);
  }, [recordingStartedAt]);

  // ---------- 녹화 ----------

  const toggleRecord = async () => {
    setRecordBusy(true);
    try {
      if (hub.recorder.isRecording()) {
        const path = await hub.recorder.stop();
        setRecordingStartedAt(null);
        showToast(`녹화 파일을 저장했음: ${path}`);
      } else {
        if (!hub.canvas) throw new Error('미리보기가 아직 준비되지 않음');
        await hub.audio.resume();
        const { fps, outputDir } = colRef.current.settings;
        await hub.recorder.start(hub.canvas, fps, hub.audio.getMixedTrack(), outputDir, (m) => showToast(m, true));
        setNow(Date.now());
        setRecordingStartedAt(Date.now());
      }
    } catch (e) {
      showToast(e instanceof Error ? e.message : '녹화 처리 중 오류', true);
      if (!hub.recorder.isRecording()) setRecordingStartedAt(null);
    } finally {
      setRecordBusy(false);
    }
  };

  const openFolder = () => {
    window.obskiwi.openFolder(collection.settings.outputDir).catch((e: unknown) => {
      showToast(e instanceof Error ? e.message : '폴더를 열지 못함', true);
    });
  };

  const saveSettings = (patch: Partial<OutputSettings>) => {
    dispatch({ type: 'setOutput', patch });
    setShowSettings(false);
  };

  const recording = recordingStartedAt !== null;

  return (
    <div className="app">
      <main className="preview-area">
        <Preview
          collection={collection}
          selectedItemId={state.selectedItemId}
          dispatch={dispatch}
          onFps={setRenderFps}
        />
      </main>

      <div className="docks">
        <Dock title="장면 목록">
          <ScenesDock collection={collection} dispatch={dispatch} />
        </Dock>
        <Dock title="소스 목록">
          <SourcesDock collection={collection} selectedItemId={state.selectedItemId} dispatch={dispatch} />
        </Dock>
        <Dock title="오디오 믹서">
          <AudioMixerDock audio={collection.audio} dispatch={dispatch} />
        </Dock>
        <Dock title="장면 전환">
          <TransitionDock transition={collection.transition} dispatch={dispatch} />
        </Dock>
        <Dock title="제어">
          <ControlsDock
            recording={recording}
            busy={recordBusy}
            outputDir={collection.settings.outputDir}
            onToggleRecord={() => void toggleRecord()}
            onOpenSettings={() => setShowSettings(true)}
            onOpenFolder={openFolder}
          />
        </Dock>
      </div>

      <StatusBar
        recordingStartedAt={recordingStartedAt}
        now={now}
        renderFps={renderFps}
        targetFps={collection.settings.fps}
        width={collection.settings.width}
        height={collection.settings.height}
      />

      {toast && (
        <div className={`toast${toast.error ? ' error' : ''}`} role="status" onClick={() => setToast(null)}>
          {toast.text}
        </div>
      )}
      {showSettings && (
        <SettingsDialog
          settings={collection.settings}
          recording={recording}
          onClose={() => setShowSettings(false)}
          onSave={saveSettings}
        />
      )}
    </div>
  );
}
