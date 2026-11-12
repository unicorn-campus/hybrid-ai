import { useEffect, useState, type ReactNode } from 'react';
import type { CaptureSourceInfo, OutputSettings, Source } from '../../shared/types';

/** 화면 가운데 뜨는 대화상자 틀 */
export function Modal(props: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  return (
    <div className="modal-backdrop" onMouseDown={props.onClose}>
      <div
        className={`modal${props.wide ? ' wide' : ''}`}
        onMouseDown={(e) => e.stopPropagation()}
        role="dialog"
        aria-label={props.title}
      >
        <div className="modal-title">{props.title}</div>
        {props.children}
      </div>
    </div>
  );
}

/** 이름 입력창 (Electron에서는 window.prompt를 쓸 수 없어서 직접 만듦) */
export function PromptDialog(props: {
  title: string;
  label: string;
  initial: string;
  onSubmit: (value: string) => void;
  onClose: () => void;
}) {
  const [value, setValue] = useState(props.initial);
  const submit = () => {
    const v = value.trim();
    if (v) props.onSubmit(v);
  };
  return (
    <Modal title={props.title} onClose={props.onClose}>
      <label className="field">
        <span>{props.label}</span>
        <input
          autoFocus
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && submit()}
        />
      </label>
      <div className="modal-actions">
        <button onClick={props.onClose}>취소</button>
        <button className="primary" onClick={submit}>
          확인
        </button>
      </div>
    </Modal>
  );
}

/** 화면 또는 창을 썸네일 격자에서 고르는 대화상자 */
export function CapturePickerDialog(props: {
  kind: 'display' | 'window';
  onPick: (info: CaptureSourceInfo) => void;
  onClose: () => void;
}) {
  const [list, setList] = useState<CaptureSourceInfo[] | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    window.obskiwi
      .listCaptureSources(props.kind === 'display' ? 'screen' : 'window')
      .then(setList)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '목록을 가져오지 못함'));
  }, [props.kind]);

  return (
    <Modal title={props.kind === 'display' ? '디스플레이 캡처: 화면 고르기' : '창 캡처: 창 고르기'} onClose={props.onClose} wide>
      {error && <p className="error-text">{error}</p>}
      {!list && !error && <p className="muted">목록을 불러오는 중...</p>}
      {list && list.length === 0 && <p className="muted">고를 수 있는 항목이 없음</p>}
      <div className="thumb-grid">
        {list?.map((s) => (
          <button key={s.id} className="thumb" onClick={() => props.onPick(s)} title={s.name}>
            <img src={s.thumbnail} alt={s.name} />
            <span>{s.name}</span>
          </button>
        ))}
      </div>
      <div className="modal-actions">
        <button onClick={props.onClose}>취소</button>
      </div>
    </Modal>
  );
}

/** 영상 장치 고르기 */
export function CameraPickerDialog(props: {
  onPick: (device: { deviceId: string; label: string }) => void;
  onClose: () => void;
}) {
  const [devices, setDevices] = useState<MediaDeviceInfo[] | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    (async () => {
      let list = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === 'videoinput');
      if (list.length > 0 && list.every((d) => !d.label)) {
        // 권한이 없으면 이름이 비어 있으므로 한 번 열어 권한을 받은 뒤 다시 읽음
        const tmp = await navigator.mediaDevices.getUserMedia({ video: true });
        tmp.getTracks().forEach((t) => t.stop());
        list = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === 'videoinput');
      }
      setDevices(list);
    })().catch((e: unknown) => setError(e instanceof Error ? e.message : '장치를 읽지 못함'));
  }, []);

  return (
    <Modal title="영상 장치 고르기" onClose={props.onClose}>
      {error && <p className="error-text">{error}</p>}
      {!devices && !error && <p className="muted">장치를 찾는 중...</p>}
      {devices && devices.length === 0 && <p className="muted">연결된 영상 장치가 없음</p>}
      <div className="list-pick">
        {devices?.map((d, i) => (
          <button key={d.deviceId} onClick={() => props.onPick({ deviceId: d.deviceId, label: d.label || `카메라 ${i + 1}` })}>
            {d.label || `카메라 ${i + 1}`}
          </button>
        ))}
      </div>
      <div className="modal-actions">
        <button onClick={props.onClose}>취소</button>
      </div>
    </Modal>
  );
}

/** 소스 속성 편집. 종류마다 보이는 입력칸이 다름 */
export function PropertiesDialog(props: {
  source: Source;
  onSave: (name: string, settings: Source['settings']) => void;
  onClose: () => void;
}) {
  const { source } = props;
  const [name, setName] = useState(source.name);
  const [s, setS] = useState<Source['settings']>(source.settings);
  const [picker, setPicker] = useState<'capture' | 'camera' | null>(null);
  const [error, setError] = useState('');
  const patch = (p: Partial<Source['settings']>) => setS((old) => ({ ...old, ...p }));

  const pickImage = async () => {
    try {
      const r = await window.obskiwi.openImage();
      if (r) patch({ filePath: r.dataUrl, fileName: r.name });
    } catch (e) {
      setError(e instanceof Error ? e.message : '이미지를 읽지 못함');
    }
  };

  return (
    <Modal title={`속성: ${source.name}`} onClose={props.onClose}>
      <label className="field">
        <span>이름</span>
        <input value={name} onChange={(e) => setName(e.target.value)} />
      </label>

      {(source.kind === 'display' || source.kind === 'window') && (
        <div className="field">
          <span>캡처 원본</span>
          <button onClick={() => setPicker('capture')}>다른 {source.kind === 'display' ? '화면' : '창'} 고르기</button>
        </div>
      )}
      {source.kind === 'camera' && (
        <div className="field">
          <span>영상 장치</span>
          <button onClick={() => setPicker('camera')}>다른 장치 고르기</button>
        </div>
      )}
      {source.kind === 'image' && (
        <div className="field">
          <span>이미지: {s.fileName ?? '(없음)'}</span>
          <button onClick={pickImage}>다른 이미지 고르기</button>
        </div>
      )}
      {source.kind === 'text' && (
        <>
          <label className="field">
            <span>글자 (줄바꿈 가능)</span>
            <textarea rows={3} value={s.text ?? ''} onChange={(e) => patch({ text: e.target.value })} />
          </label>
          <div className="field-row">
            <label className="field">
              <span>글자 크기(px)</span>
              <input
                type="number"
                min={8}
                max={600}
                value={s.fontSize ?? 96}
                onChange={(e) => patch({ fontSize: Math.max(8, Number(e.target.value) || 96) })}
              />
            </label>
            <label className="field">
              <span>글자 색</span>
              <input type="color" value={s.color ?? '#ffffff'} onChange={(e) => patch({ color: e.target.value })} />
            </label>
          </div>
        </>
      )}
      {source.kind === 'color' && (
        <div className="field-row">
          <label className="field">
            <span>색</span>
            <input type="color" value={s.color ?? '#7cc242'} onChange={(e) => patch({ color: e.target.value })} />
          </label>
          <label className="field">
            <span>너비</span>
            <input
              type="number"
              min={1}
              value={s.width ?? 1920}
              onChange={(e) => patch({ width: Math.max(1, Number(e.target.value) || 1) })}
            />
          </label>
          <label className="field">
            <span>높이</span>
            <input
              type="number"
              min={1}
              value={s.height ?? 1080}
              onChange={(e) => patch({ height: Math.max(1, Number(e.target.value) || 1) })}
            />
          </label>
        </div>
      )}
      {error && <p className="error-text">{error}</p>}

      <div className="modal-actions">
        <button onClick={props.onClose}>취소</button>
        <button className="primary" onClick={() => props.onSave(name.trim() || source.name, s)}>
          저장
        </button>
      </div>

      {picker === 'capture' && (
        <CapturePickerDialog
          kind={source.kind === 'display' ? 'display' : 'window'}
          onClose={() => setPicker(null)}
          onPick={(info) => {
            patch({ sourceId: info.id });
            setPicker(null);
          }}
        />
      )}
      {picker === 'camera' && (
        <CameraPickerDialog
          onClose={() => setPicker(null)}
          onPick={(d) => {
            patch({ deviceId: d.deviceId });
            setPicker(null);
          }}
        />
      )}
    </Modal>
  );
}

/** 출력 폴더, FPS, 기준 해상도 설정 */
export function SettingsDialog(props: {
  settings: OutputSettings;
  recording: boolean;
  onSave: (patch: Partial<OutputSettings>) => void;
  onClose: () => void;
}) {
  const [dir, setDir] = useState(props.settings.outputDir);
  const [fps, setFps] = useState(props.settings.fps);
  const [res, setRes] = useState(`${props.settings.width}x${props.settings.height}`);

  const chooseDir = async () => {
    const picked = await window.obskiwi.chooseFolder();
    if (picked) setDir(picked);
  };
  const save = () => {
    const [width, height] = res.split('x').map(Number);
    props.onSave({ outputDir: dir, fps, width, height });
  };

  return (
    <Modal title="설정" onClose={props.onClose}>
      <div className="field">
        <span>녹화 폴더</span>
        <div className="dir-row">
          <code title={dir}>{dir}</code>
          <button onClick={chooseDir}>폴더 고르기</button>
        </div>
      </div>
      <div className="field-row">
        <label className="field">
          <span>FPS</span>
          <select value={fps} disabled={props.recording} onChange={(e) => setFps(Number(e.target.value))}>
            <option value={24}>24</option>
            <option value={30}>30</option>
            <option value={60}>60</option>
          </select>
        </label>
        <label className="field">
          <span>기준 해상도</span>
          <select value={res} disabled={props.recording} onChange={(e) => setRes(e.target.value)}>
            <option value="1280x720">1280x720</option>
            <option value="1920x1080">1920x1080</option>
          </select>
        </label>
      </div>
      {props.recording && <p className="muted">녹화 중에는 FPS와 해상도를 바꿀 수 없음</p>}
      <div className="modal-actions">
        <button onClick={props.onClose}>취소</button>
        <button className="primary" onClick={save}>
          저장
        </button>
      </div>
    </Modal>
  );
}
