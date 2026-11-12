import { useEffect, useReducer, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';
import type { Collection, SceneItem } from '../../shared/types';
import type { Action } from '../state/reducer';
import { Compositor, sourceSize } from '../engine/compositor';
import { hub } from '../engine/hub';

interface Props {
  collection: Collection;
  selectedItemId: string | null;
  dispatch: (a: Action) => void;
  onFps: (fps: number) => void;
}

interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

interface DragState {
  mode: 'move' | 'resize';
  itemId: string;
  startX: number;
  startY: number;
  item: SceneItem;
  natW: number;
  natH: number;
}

const HANDLE_PX = 12; // 크기 손잡이(화면 픽셀)

/** 미리보기: 실제 1920x1080 캔버스 + 그 위에 얹은 선택 테두리(녹화에는 찍히지 않는 DOM 겹침) */
export function Preview({ collection, selectedItemId, dispatch, onFps }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const colRef = useRef(collection);
  colRef.current = collection;
  const onFpsRef = useRef(onFps);
  onFpsRef.current = onFps;
  const drag = useRef<DragState | null>(null);
  const [stage, setStage] = useState({ w: 640, h: 360 });
  const [, refresh] = useReducer((n: number) => n + 1, 0);

  const { width, height, fps } = collection.settings;
  const scene = collection.scenes.find((s) => s.id === collection.currentSceneId);

  // 합성기 만들기와 정리
  useEffect(() => {
    const canvas = canvasRef.current!;
    const comp = new Compositor(canvas, () => colRef.current, hub.media);
    comp.onFps = (f) => onFpsRef.current(f);
    hub.canvas = canvas;
    hub.compositor = comp;
    return () => {
      comp.stop();
      hub.compositor = null;
      hub.canvas = null;
    };
  }, []);

  // FPS 설정이 바뀌면 타이머를 다시 맞춤
  useEffect(() => {
    hub.compositor?.start(fps);
  }, [fps]);

  // 영상이 열리거나 닫힐 때 선택 테두리 크기를 다시 계산하도록 다시 그림
  useEffect(() => hub.media.subscribe(refresh), []);

  // 장면이 바뀔 때 이전 장면을 넘겨 전환 효과를 시작함
  const last = useRef({ id: collection.currentSceneId, scene });
  useEffect(() => {
    if (last.current.id !== collection.currentSceneId && last.current.scene) {
      hub.compositor?.startTransition(last.current.scene, collection.transition.kind, collection.transition.durationMs);
    }
  }, [collection.currentSceneId]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    last.current = { id: collection.currentSceneId, scene };
  });

  // 미리보기 영역에 16:9(또는 설정 비율)로 꽉 차게 크기를 맞춤
  useEffect(() => {
    const wrap = wrapRef.current!;
    const fit = () => {
      const cw = wrap.clientWidth - 16;
      const ch = wrap.clientHeight - 16;
      const ratio = width / height;
      const w = Math.max(160, Math.min(cw, ch * ratio));
      setStage({ w, h: w / ratio });
    };
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(wrap);
    return () => ro.disconnect();
  }, [width, height]);

  // ---------- 좌표와 크기 계산 ----------

  const natSize = (item: SceneItem): { w: number; h: number } => {
    const src = colRef.current.sources.find((s) => s.id === item.sourceId);
    return (src && sourceSize(src, hub.media)) || { w: 320, h: 180 };
  };

  const rectOf = (item: SceneItem): Rect => {
    const n = natSize(item);
    return { x: item.x, y: item.y, w: n.w * item.scaleX, h: n.h * item.scaleY };
  };

  /** 화면 좌표를 캔버스 좌표로 바꿈 */
  const toCanvas = (e: { clientX: number; clientY: number }) => {
    const box = overlayRef.current!.getBoundingClientRect();
    return {
      x: ((e.clientX - box.left) * width) / box.width,
      y: ((e.clientY - box.top) * height) / box.height,
      pxPerUnit: box.width / width,
    };
  };

  const selected = scene?.items.find((it) => it.id === selectedItemId) ?? null;

  const onPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!scene) return;
    const p = toCanvas(e);

    // 선택된 항목의 오른쪽 아래 손잡이를 눌렀는지
    if (selected && !selected.locked && selected.visible) {
      const r = rectOf(selected);
      if (Math.abs(p.x - (r.x + r.w)) * p.pxPerUnit <= HANDLE_PX && Math.abs(p.y - (r.y + r.h)) * p.pxPerUnit <= HANDLE_PX) {
        const n = natSize(selected);
        drag.current = { mode: 'resize', itemId: selected.id, startX: p.x, startY: p.y, item: selected, natW: n.w, natH: n.h };
        overlayRef.current!.setPointerCapture(e.pointerId);
        return;
      }
    }

    // 위쪽 항목부터 찾아서 눌린 항목 선택
    for (let i = scene.items.length - 1; i >= 0; i--) {
      const it = scene.items[i];
      if (!it.visible) continue;
      const r = rectOf(it);
      if (p.x >= r.x && p.x <= r.x + r.w && p.y >= r.y && p.y <= r.y + r.h) {
        dispatch({ type: 'selectItem', itemId: it.id });
        if (!it.locked) {
          const n = natSize(it);
          drag.current = { mode: 'move', itemId: it.id, startX: p.x, startY: p.y, item: it, natW: n.w, natH: n.h };
          overlayRef.current!.setPointerCapture(e.pointerId);
        }
        return;
      }
    }
    dispatch({ type: 'selectItem', itemId: null });
  };

  const onPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    const p = toCanvas(e);
    const d = drag.current;
    if (!d) {
      // 손잡이 위에서는 크기 조절 커서로 바꿈
      let cursor = 'default';
      if (selected && !selected.locked && selected.visible) {
        const r = rectOf(selected);
        const nearHandle =
          Math.abs(p.x - (r.x + r.w)) * p.pxPerUnit <= HANDLE_PX && Math.abs(p.y - (r.y + r.h)) * p.pxPerUnit <= HANDLE_PX;
        cursor = nearHandle ? 'nwse-resize' : 'default';
      }
      overlayRef.current!.style.cursor = cursor;
      return;
    }

    if (d.mode === 'move') {
      dispatch({
        type: 'updateItem',
        itemId: d.itemId,
        patch: { x: d.item.x + (p.x - d.startX), y: d.item.y + (p.y - d.startY) },
      });
      return;
    }

    // 크기 조절: Shift를 누르면 자유 비율, 아니면 비율 유지(대각선 방향으로 투영)
    const w0 = d.natW * d.item.scaleX;
    const h0 = d.natH * d.item.scaleY;
    if (e.shiftKey) {
      dispatch({
        type: 'updateItem',
        itemId: d.itemId,
        patch: {
          scaleX: Math.max(0.02, (p.x - d.item.x) / d.natW),
          scaleY: Math.max(0.02, (p.y - d.item.y) / d.natH),
        },
      });
    } else {
      const f = ((p.x - d.item.x) * w0 + (p.y - d.item.y) * h0) / (w0 * w0 + h0 * h0);
      const factor = Math.max(0.02, f);
      dispatch({
        type: 'updateItem',
        itemId: d.itemId,
        patch: { scaleX: d.item.scaleX * factor, scaleY: d.item.scaleY * factor },
      });
    }
  };

  const endDrag = () => {
    drag.current = null;
  };

  const sel = selected && selected.visible ? rectOf(selected) : null;

  return (
    <div className="preview-wrap" ref={wrapRef}>
      <div className="stage" style={{ width: stage.w, height: stage.h }}>
        <canvas ref={canvasRef} width={width} height={height} className="preview-canvas" />
        <div
          className="overlay"
          ref={overlayRef}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
        >
          {sel && (
            <div
              className={`sel-box${selected?.locked ? ' locked' : ''}`}
              style={{
                left: `${(sel.x / width) * 100}%`,
                top: `${(sel.y / height) * 100}%`,
                width: `${(sel.w / width) * 100}%`,
                height: `${(sel.h / height) * 100}%`,
              }}
            >
              {!selected?.locked && <span className="handle" />}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
