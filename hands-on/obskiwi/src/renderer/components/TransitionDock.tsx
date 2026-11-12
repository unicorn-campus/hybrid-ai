import type { TransitionSettings } from '../../shared/types';
import type { Action } from '../state/reducer';

interface Props {
  transition: TransitionSettings;
  dispatch: (a: Action) => void;
}

/** 장면 전환: 종류(자르기, 페이드)와 지속 시간 */
export function TransitionDock({ transition, dispatch }: Props) {
  return (
    <div className="dock-content">
      <label className="field">
        <span>종류</span>
        <select
          value={transition.kind}
          onChange={(e) =>
            dispatch({ type: 'setTransition', patch: { kind: e.target.value === 'cut' ? 'cut' : 'fade' } })
          }
        >
          <option value="cut">자르기</option>
          <option value="fade">페이드</option>
        </select>
      </label>
      <label className="field">
        <span>지속 시간(ms)</span>
        <input
          type="number"
          min={0}
          max={5000}
          step={50}
          disabled={transition.kind === 'cut'}
          value={transition.durationMs}
          onChange={(e) =>
            dispatch({
              type: 'setTransition',
              patch: { durationMs: Math.min(5000, Math.max(0, Number(e.target.value) || 0)) },
            })
          }
        />
      </label>
      <p className="hint">장면 목록에서 장면을 고르면 이 설정대로 바뀜</p>
    </div>
  );
}
