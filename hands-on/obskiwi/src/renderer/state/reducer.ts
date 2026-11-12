import type {
  AudioChannelSettings,
  Collection,
  MicSettings,
  OutputSettings,
  Scene,
  SceneItem,
  Source,
  TransitionSettings,
} from '../../shared/types';

export function uid(prefix: string): string {
  return `${prefix}_${Math.random().toString(36).slice(2, 9)}${Date.now().toString(36).slice(-3)}`;
}

/** 처음 실행할 때 쓰는 기본 장면 모음 */
export function createDefaultCollection(outputDir: string): Collection {
  const scene: Scene = { id: uid('scene'), name: '장면 1', items: [] };
  return {
    name: '기본',
    sources: [],
    scenes: [scene],
    sceneOrder: [scene.id],
    currentSceneId: scene.id,
    transition: { kind: 'fade', durationMs: 300 },
    audio: {
      desktop: { volume: 1, muted: false },
      mic: { volume: 1, muted: false, deviceId: '' },
    },
    settings: { width: 1920, height: 1080, fps: 30, outputDir },
  };
}

export interface AppState {
  collection: Collection;
  selectedItemId: string | null;
}

export type Action =
  | { type: 'load'; collection: Collection }
  | { type: 'addScene'; id: string; name: string }
  | { type: 'renameScene'; id: string; name: string }
  | { type: 'deleteScene'; id: string }
  | { type: 'duplicateScene'; id: string; newId: string }
  | { type: 'selectScene'; id: string }
  | { type: 'addSource'; source: Source; itemId: string }
  | { type: 'updateSource'; id: string; name?: string; settings?: Source['settings'] }
  | { type: 'removeItem'; itemId: string }
  | { type: 'updateItem'; itemId: string; patch: Partial<Omit<SceneItem, 'id' | 'sourceId'>> }
  | { type: 'moveItem'; itemId: string; direction: 'up' | 'down' }
  | { type: 'selectItem'; itemId: string | null }
  | { type: 'setTransition'; patch: Partial<TransitionSettings> }
  | { type: 'setDesktopAudio'; patch: Partial<AudioChannelSettings> }
  | { type: 'setMicAudio'; patch: Partial<MicSettings> }
  | { type: 'setOutput'; patch: Partial<OutputSettings> };

/** 현재 장면 하나를 바꿔 새 Collection을 만드는 도우미 */
function mapScene(c: Collection, id: string, fn: (s: Scene) => Scene): Collection {
  return { ...c, scenes: c.scenes.map((s) => (s.id === id ? fn(s) : s)) };
}

function currentScene(c: Collection): Scene {
  return c.scenes.find((s) => s.id === c.currentSceneId) ?? c.scenes[0];
}

/** 소스 이름이 겹치지 않게 "이름 2", "이름 3"을 붙임 */
export function uniqueSourceName(sources: Source[], base: string): string {
  const names = new Set(sources.map((s) => s.name));
  if (!names.has(base)) return base;
  let n = 2;
  while (names.has(`${base} ${n}`)) n++;
  return `${base} ${n}`;
}

export function reducer(state: AppState, action: Action): AppState {
  const c = state.collection;
  switch (action.type) {
    case 'load':
      return { collection: action.collection, selectedItemId: null };

    case 'addScene': {
      const scene: Scene = { id: action.id, name: action.name, items: [] };
      return {
        selectedItemId: null,
        collection: {
          ...c,
          scenes: [...c.scenes, scene],
          sceneOrder: [...c.sceneOrder, scene.id],
          currentSceneId: scene.id,
        },
      };
    }

    case 'renameScene':
      return { ...state, collection: mapScene(c, action.id, (s) => ({ ...s, name: action.name })) };

    case 'deleteScene': {
      if (c.scenes.length <= 1) return state; // 마지막 1개는 지울 수 없음
      const scenes = c.scenes.filter((s) => s.id !== action.id);
      const sceneOrder = c.sceneOrder.filter((id) => id !== action.id);
      const currentSceneId =
        c.currentSceneId === action.id ? (sceneOrder[0] ?? scenes[0].id) : c.currentSceneId;
      return {
        selectedItemId: currentSceneId === c.currentSceneId ? state.selectedItemId : null,
        collection: pruneSources({ ...c, scenes, sceneOrder, currentSceneId }),
      };
    }

    case 'duplicateScene': {
      const src = c.scenes.find((s) => s.id === action.id);
      if (!src) return state;
      const copy: Scene = {
        id: action.newId,
        name: `${src.name} 복사`,
        items: src.items.map((it) => ({ ...it, id: uid('item') })), // 같은 소스를 함께 씀
      };
      const idx = c.sceneOrder.indexOf(action.id);
      const sceneOrder = [...c.sceneOrder];
      sceneOrder.splice(idx + 1, 0, copy.id);
      return {
        selectedItemId: null,
        collection: { ...c, scenes: [...c.scenes, copy], sceneOrder, currentSceneId: copy.id },
      };
    }

    case 'selectScene':
      if (action.id === c.currentSceneId || !c.scenes.some((s) => s.id === action.id)) return state;
      return { selectedItemId: null, collection: { ...c, currentSceneId: action.id } };

    case 'addSource': {
      const item: SceneItem = {
        id: action.itemId,
        sourceId: action.source.id,
        x: 0,
        y: 0,
        scaleX: 1,
        scaleY: 1,
        visible: true,
        locked: false,
      };
      const withSource = { ...c, sources: [...c.sources, action.source] };
      return {
        selectedItemId: item.id,
        collection: mapScene(withSource, c.currentSceneId, (s) => ({ ...s, items: [...s.items, item] })),
      };
    }

    case 'updateSource':
      return {
        ...state,
        collection: {
          ...c,
          sources: c.sources.map((s) =>
            s.id === action.id
              ? {
                  ...s,
                  name: action.name ?? s.name,
                  settings: action.settings ? { ...s.settings, ...action.settings } : s.settings,
                }
              : s,
          ),
        },
      };

    case 'removeItem': {
      const next = mapScene(c, c.currentSceneId, (s) => ({
        ...s,
        items: s.items.filter((it) => it.id !== action.itemId),
      }));
      return {
        selectedItemId: state.selectedItemId === action.itemId ? null : state.selectedItemId,
        collection: pruneSources(next),
      };
    }

    case 'updateItem':
      return {
        ...state,
        collection: mapScene(c, c.currentSceneId, (s) => ({
          ...s,
          items: s.items.map((it) => (it.id === action.itemId ? { ...it, ...action.patch } : it)),
        })),
      };

    case 'moveItem':
      return {
        ...state,
        collection: mapScene(c, c.currentSceneId, (s) => {
          const i = s.items.findIndex((it) => it.id === action.itemId);
          const j = action.direction === 'up' ? i + 1 : i - 1; // 배열 뒤쪽이 위
          if (i < 0 || j < 0 || j >= s.items.length) return s;
          const items = [...s.items];
          [items[i], items[j]] = [items[j], items[i]];
          return { ...s, items };
        }),
      };

    case 'selectItem':
      return { ...state, selectedItemId: action.itemId };

    case 'setTransition':
      return { ...state, collection: { ...c, transition: { ...c.transition, ...action.patch } } };

    case 'setDesktopAudio':
      return {
        ...state,
        collection: { ...c, audio: { ...c.audio, desktop: { ...c.audio.desktop, ...action.patch } } },
      };

    case 'setMicAudio':
      return {
        ...state,
        collection: { ...c, audio: { ...c.audio, mic: { ...c.audio.mic, ...action.patch } } },
      };

    case 'setOutput': {
      const patch = action.patch;
      const old = c.settings;
      const settings = { ...old, ...patch };
      // 기준 해상도가 바뀌면 항목의 위치와 크기를 같은 비율로 맞춰 화면 구성이 그대로 보이게 함
      if (settings.width !== old.width || settings.height !== old.height) {
        const r = settings.width / old.width;
        const scenes = c.scenes.map((s) => ({
          ...s,
          items: s.items.map((it) => ({
            ...it,
            x: it.x * r,
            y: it.y * r,
            scaleX: it.scaleX * r,
            scaleY: it.scaleY * r,
          })),
        }));
        return { ...state, collection: { ...c, scenes, settings } };
      }
      return { ...state, collection: { ...c, settings } };
    }
  }
}

/** 어느 장면에서도 쓰지 않는 소스를 정리함 */
function pruneSources(c: Collection): Collection {
  const used = new Set(c.scenes.flatMap((s) => s.items.map((it) => it.sourceId)));
  return { ...c, sources: c.sources.filter((s) => used.has(s.id)) };
}

export { currentScene };
