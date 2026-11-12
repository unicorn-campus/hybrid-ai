import { useState } from 'react';
import { Copy, Plus, Trash2 } from 'lucide-react';
import type { Collection } from '../../shared/types';
import { uid, type Action } from '../state/reducer';
import { PromptDialog } from './Dialogs';

interface Props {
  collection: Collection;
  dispatch: (a: Action) => void;
}

/** 장면 목록: 추가, 이름 바꾸기(더블클릭), 삭제, 복제, 선택(전환 설정대로 바뀜) */
export function ScenesDock({ collection, dispatch }: Props) {
  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState('');

  const ordered = collection.sceneOrder
    .map((id) => collection.scenes.find((s) => s.id === id))
    .filter((s) => s !== undefined);
  const canDelete = collection.scenes.length > 1;

  const commitRename = (id: string) => {
    const name = draft.trim();
    if (name) dispatch({ type: 'renameScene', id, name });
    setEditingId(null);
  };

  const remove = () => {
    const scene = collection.scenes.find((s) => s.id === collection.currentSceneId);
    if (scene && canDelete && window.confirm(`장면 「${scene.name}」을 삭제할까요?`)) {
      dispatch({ type: 'deleteScene', id: scene.id });
    }
  };

  return (
    <div className="dock-content">
      <ul className="list">
        {ordered.map((s) => (
          <li
            key={s.id}
            className={s.id === collection.currentSceneId ? 'row selected' : 'row'}
            onClick={() => dispatch({ type: 'selectScene', id: s.id })}
            onDoubleClick={() => {
              setEditingId(s.id);
              setDraft(s.name);
            }}
          >
            {editingId === s.id ? (
              <input
                autoFocus
                className="inline-input"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onBlur={() => commitRename(s.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') commitRename(s.id);
                  if (e.key === 'Escape') setEditingId(null);
                }}
                onClick={(e) => e.stopPropagation()}
              />
            ) : (
              <span className="row-name">{s.name}</span>
            )}
          </li>
        ))}
      </ul>
      <div className="toolbar">
        <button className="icon-btn" title="장면 추가" onClick={() => setAdding(true)}>
          <Plus size={16} />
        </button>
        <button
          className="icon-btn"
          title="현재 장면 복제"
          onClick={() => dispatch({ type: 'duplicateScene', id: collection.currentSceneId, newId: uid('scene') })}
        >
          <Copy size={16} />
        </button>
        <button
          className="icon-btn"
          title={canDelete ? '현재 장면 삭제' : '마지막 장면은 삭제할 수 없음'}
          disabled={!canDelete}
          onClick={remove}
        >
          <Trash2 size={16} />
        </button>
      </div>
      <p className="hint">이름을 바꾸려면 더블클릭</p>

      {adding && (
        <PromptDialog
          title="장면 추가"
          label="장면 이름"
          initial={`장면 ${collection.scenes.length + 1}`}
          onClose={() => setAdding(false)}
          onSubmit={(name) => {
            dispatch({ type: 'addScene', id: uid('scene'), name });
            setAdding(false);
          }}
        />
      )}
    </div>
  );
}
