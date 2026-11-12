import { useEffect, useReducer, useState } from 'react';
import {
  AppWindow,
  ArrowDown,
  ArrowUp,
  Camera,
  Eye,
  EyeOff,
  Image as ImageIcon,
  Lock,
  Maximize,
  Monitor,
  Palette,
  Plus,
  Settings2,
  TriangleAlert,
  Trash2,
  Type,
  Unlock,
  type LucideIcon,
} from 'lucide-react';
import type { CaptureSourceInfo, Collection, Source, SourceKind } from '../../shared/types';
import { uid, uniqueSourceName, type Action } from '../state/reducer';
import { fitRect, sourceSize } from '../engine/compositor';
import { hub } from '../engine/hub';
import { CameraPickerDialog, CapturePickerDialog, PropertiesDialog } from './Dialogs';

interface Props {
  collection: Collection;
  selectedItemId: string | null;
  dispatch: (a: Action) => void;
}

const KIND_ICON: Record<SourceKind, LucideIcon> = {
  display: Monitor,
  window: AppWindow,
  camera: Camera,
  image: ImageIcon,
  text: Type,
  color: Palette,
};

const ADD_MENU: { kind: SourceKind; label: string }[] = [
  { kind: 'display', label: '디스플레이 캡처' },
  { kind: 'window', label: '창 캡처' },
  { kind: 'camera', label: '영상 장치' },
  { kind: 'image', label: '이미지' },
  { kind: 'text', label: '텍스트' },
  { kind: 'color', label: '색상' },
];

type DialogState =
  | { t: 'capture'; kind: 'display' | 'window' }
  | { t: 'camera' }
  | { t: 'props'; sourceId: string }
  | null;

/** 이미지를 읽어 원래 크기를 알아냄 */
function loadImageSize(url: string): Promise<{ w: number; h: number }> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve({ w: img.naturalWidth, h: img.naturalHeight });
    img.onerror = () => reject(new Error('이미지를 읽지 못함'));
    img.src = url;
  });
}

/** 소스 목록: 현재 장면의 항목. 위쪽이 화면에서 위에 놓인 항목 */
export function SourcesDock({ collection, selectedItemId, dispatch }: Props) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [dialog, setDialog] = useState<DialogState>(null);
  const [message, setMessage] = useState('');
  const [, refresh] = useReducer((n: number) => n + 1, 0);

  // 캡처 열기 실패 같은 상태가 바뀌면 목록을 다시 그림
  useEffect(() => hub.media.subscribe(refresh), []);

  const scene = collection.scenes.find((s) => s.id === collection.currentSceneId);
  const items = [...(scene?.items ?? [])].reverse();
  const sourceOf = (id: string) => collection.sources.find((s) => s.id === id);
  const selected = scene?.items.find((it) => it.id === selectedItemId) ?? null;
  const { width: cw, height: ch } = collection.settings;

  const addSource = (kind: SourceKind, name: string, settings: Source['settings']): { src: Source; itemId: string } => {
    const src: Source = { id: uid('src'), name: uniqueSourceName(collection.sources, name), kind, settings };
    const itemId = uid('item');
    dispatch({ type: 'addSource', source: src, itemId });
    return { src, itemId };
  };

  const addMedia = (kind: 'display' | 'window' | 'camera', name: string, settings: Source['settings']) => {
    const { src, itemId } = addSource(kind, name, settings);
    hub.pendingFit.set(src.id, itemId); // 첫 영상 크기를 알게 되면 화면에 맞춤
  };

  const startAdd = async (kind: SourceKind) => {
    setMenuOpen(false);
    setMessage('');
    try {
      if (kind === 'display' || kind === 'window') setDialog({ t: 'capture', kind });
      else if (kind === 'camera') setDialog({ t: 'camera' });
      else if (kind === 'text') {
        const { itemId } = addSource('text', '텍스트', { text: 'obskiwi', fontSize: 96, color: '#ffffff' });
        dispatch({ type: 'updateItem', itemId, patch: { x: 80, y: 80 } });
      } else if (kind === 'color') {
        addSource('color', '색상', { color: '#7cc242', width: cw, height: ch });
      } else if (kind === 'image') {
        const picked = await window.obskiwi.openImage();
        if (!picked) return;
        const size = await loadImageSize(picked.dataUrl);
        const { itemId } = addSource('image', picked.name, { filePath: picked.dataUrl, fileName: picked.name });
        const fit = fitRect(size.w, size.h, cw, ch);
        // 큰 그림만 줄이고 작은 그림은 원래 크기로 가운데에 둠
        const s = Math.min(1, fit.scaleX);
        dispatch({
          type: 'updateItem',
          itemId,
          patch: { scaleX: s, scaleY: s, x: (cw - size.w * s) / 2, y: (ch - size.h * s) / 2 },
        });
      }
    } catch (e) {
      setMessage(e instanceof Error ? e.message : '추가하지 못함');
    }
  };

  const onPickCapture = (kind: 'display' | 'window', info: CaptureSourceInfo) => {
    setDialog(null);
    addMedia(kind, info.name, { sourceId: info.id });
  };

  const fitSelected = () => {
    if (!selected) return;
    const src = sourceOf(selected.sourceId);
    const size = src ? sourceSize(src, hub.media) : null;
    if (!size) {
      setMessage('아직 크기를 알 수 없음(영상이 열리는 중이거나 실패함)');
      return;
    }
    dispatch({ type: 'updateItem', itemId: selected.id, patch: fitRect(size.w, size.h, cw, ch) });
  };

  const propsSource = dialog?.t === 'props' ? sourceOf(dialog.sourceId) : undefined;

  return (
    <div className="dock-content">
      <ul className="list">
        {items.length === 0 && <li className="empty">「+ 추가」로 소스를 넣어 보세요</li>}
        {items.map((it) => {
          const src = sourceOf(it.sourceId);
          if (!src) return null;
          const Icon = KIND_ICON[src.kind];
          const error = hub.media.getError(src.id);
          return (
            <li
              key={it.id}
              className={`row${it.id === selectedItemId ? ' selected' : ''}${it.visible ? '' : ' dim'}`}
              onClick={() => dispatch({ type: 'selectItem', itemId: it.id })}
              onDoubleClick={() => setDialog({ t: 'props', sourceId: src.id })}
            >
              <Icon size={14} className="row-icon" />
              <span className="row-name">{src.name}</span>
              {error && (
                <button
                  className="icon-btn small warn"
                  title={`${error} (눌러서 다시 시도)`}
                  onClick={(e) => {
                    e.stopPropagation();
                    hub.media.retry(src.id);
                  }}
                >
                  <TriangleAlert size={14} />
                </button>
              )}
              <button
                className="icon-btn small"
                title={it.visible ? '숨기기' : '보이기'}
                onClick={(e) => {
                  e.stopPropagation();
                  dispatch({ type: 'updateItem', itemId: it.id, patch: { visible: !it.visible } });
                }}
              >
                {it.visible ? <Eye size={14} /> : <EyeOff size={14} />}
              </button>
              <button
                className="icon-btn small"
                title={it.locked ? '잠금 풀기' : '잠그기'}
                onClick={(e) => {
                  e.stopPropagation();
                  dispatch({ type: 'updateItem', itemId: it.id, patch: { locked: !it.locked } });
                }}
              >
                {it.locked ? <Lock size={14} /> : <Unlock size={14} />}
              </button>
            </li>
          );
        })}
      </ul>

      <div className="toolbar">
        <div className="menu-wrap">
          <button className="icon-btn" title="소스 추가" onClick={() => setMenuOpen((v) => !v)}>
            <Plus size={16} />
          </button>
          {menuOpen && (
            <>
              <div className="menu-backdrop" onClick={() => setMenuOpen(false)} />
              <ul className="menu">
                {ADD_MENU.map((m) => {
                  const Icon = KIND_ICON[m.kind];
                  return (
                    <li key={m.kind}>
                      <button onClick={() => void startAdd(m.kind)}>
                        <Icon size={14} /> {m.label}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </>
          )}
        </div>
        <button
          className="icon-btn"
          title="위로"
          disabled={!selected}
          onClick={() => selected && dispatch({ type: 'moveItem', itemId: selected.id, direction: 'up' })}
        >
          <ArrowUp size={16} />
        </button>
        <button
          className="icon-btn"
          title="아래로"
          disabled={!selected}
          onClick={() => selected && dispatch({ type: 'moveItem', itemId: selected.id, direction: 'down' })}
        >
          <ArrowDown size={16} />
        </button>
        <button className="icon-btn" title="화면에 맞추기" disabled={!selected} onClick={fitSelected}>
          <Maximize size={16} />
        </button>
        <button
          className="icon-btn"
          title="속성"
          disabled={!selected}
          onClick={() => selected && setDialog({ t: 'props', sourceId: selected.sourceId })}
        >
          <Settings2 size={16} />
        </button>
        <button
          className="icon-btn"
          title="삭제"
          disabled={!selected}
          onClick={() => selected && dispatch({ type: 'removeItem', itemId: selected.id })}
        >
          <Trash2 size={16} />
        </button>
      </div>
      {message && <p className="error-text small">{message}</p>}

      {dialog?.t === 'capture' && (
        <CapturePickerDialog
          kind={dialog.kind}
          onClose={() => setDialog(null)}
          onPick={(info) => onPickCapture(dialog.kind, info)}
        />
      )}
      {dialog?.t === 'camera' && (
        <CameraPickerDialog
          onClose={() => setDialog(null)}
          onPick={(d) => {
            setDialog(null);
            addMedia('camera', d.label, { deviceId: d.deviceId });
          }}
        />
      )}
      {propsSource && (
        <PropertiesDialog
          source={propsSource}
          onClose={() => setDialog(null)}
          onSave={(name, settings) => {
            dispatch({ type: 'updateSource', id: propsSource.id, name, settings });
            setDialog(null);
          }}
        />
      )}
    </div>
  );
}
