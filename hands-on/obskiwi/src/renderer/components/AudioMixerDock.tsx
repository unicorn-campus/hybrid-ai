import { useEffect, useReducer, useRef, useState } from 'react';
import { Mic, Volume2, VolumeX } from 'lucide-react';
import type { Collection } from '../../shared/types';
import type { Action } from '../state/reducer';
import type { ChannelId } from '../engine/audio';
import { hub } from '../engine/hub';

interface Props {
  audio: Collection['audio'];
  dispatch: (a: Action) => void;
}

function dbText(volume: number): string {
  return volume <= 0 ? '-∞ dB' : `${(20 * Math.log10(volume)).toFixed(1)} dB`;
}

/** 음량 막대. 초록 → 노랑 → 빨강. 값은 requestAnimationFrame으로 직접 그려 React 갱신을 피함 */
function LevelMeter({ channel }: { channel: ChannelId }) {
  const coverRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let raf = 0;
    let shown = 0;
    const loop = () => {
      const level = hub.audio.getLevel(channel);
      // 올라갈 때는 바로, 내려갈 때는 천천히
      shown = level > shown ? level : Math.max(level, shown - 0.02);
      if (coverRef.current) coverRef.current.style.width = `${(1 - shown) * 100}%`;
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [channel]);
  return (
    <div className="meter">
      <div className="meter-cover" ref={coverRef} />
    </div>
  );
}

function useAudioStatus(): void {
  const [, refresh] = useReducer((n: number) => n + 1, 0);
  useEffect(() => hub.audio.subscribe(refresh), []);
}

/** 오디오 믹서: 데스크톱 소리와 마이크 두 채널 */
export function AudioMixerDock({ audio, dispatch }: Props) {
  useAudioStatus();
  const [desktopError, setDesktopError] = useState('');
  const [micDevices, setMicDevices] = useState<MediaDeviceInfo[]>([]);
  const micActive = hub.audio.isActive('mic');
  const micError = hub.audio.getError('mic');

  // 마이크 목록은 마이크가 열린 뒤(이름이 보이는 때)에 다시 읽음
  useEffect(() => {
    navigator.mediaDevices
      .enumerateDevices()
      .then((list) => setMicDevices(list.filter((d) => d.kind === 'audioinput')))
      .catch(() => setMicDevices([]));
  }, [micActive]);

  const enableDesktop = async () => {
    setDesktopError('');
    try {
      await hub.audio.resume();
      await hub.media.openDesktopAudio();
    } catch (e) {
      setDesktopError(e instanceof Error ? e.message : '데스크톱 소리를 켜지 못함');
    }
  };

  const channelRow = (
    id: ChannelId,
    label: string,
    settings: { volume: number; muted: boolean },
    onVolume: (v: number) => void,
    onMute: (m: boolean) => void,
  ) => (
    <div className="channel">
      <div className="channel-head">
        <span className="channel-name">
          {id === 'mic' ? <Mic size={14} /> : <Volume2 size={14} />} {label}
        </span>
        <span className="db">{settings.muted ? '음소거' : dbText(settings.volume)}</span>
      </div>
      <LevelMeter channel={id} />
      <div className="channel-controls">
        <button
          className={`icon-btn${settings.muted ? ' active-danger' : ''}`}
          title={settings.muted ? '음소거 해제' : '음소거'}
          onClick={() => onMute(!settings.muted)}
        >
          {settings.muted ? <VolumeX size={16} /> : <Volume2 size={16} />}
        </button>
        <input
          type="range"
          min={0}
          max={100}
          value={Math.round(settings.volume * 100)}
          onChange={(e) => onVolume(Number(e.target.value) / 100)}
          aria-label={`${label} 음량`}
        />
        <span className="pct">{Math.round(settings.volume * 100)}%</span>
      </div>
    </div>
  );

  return (
    <div className="dock-content mixer">
      {channelRow(
        'desktop',
        '데스크톱 소리',
        audio.desktop,
        (volume) => dispatch({ type: 'setDesktopAudio', patch: { volume } }),
        (muted) => dispatch({ type: 'setDesktopAudio', patch: { muted } }),
      )}
      {!hub.audio.isActive('desktop') && (
        <div className="channel-extra">
          <button onClick={() => void enableDesktop()}>데스크톱 소리 켜기</button>
          {desktopError && <span className="error-text small">{desktopError}</span>}
        </div>
      )}

      {channelRow(
        'mic',
        '마이크',
        audio.mic,
        (volume) => dispatch({ type: 'setMicAudio', patch: { volume } }),
        (muted) => dispatch({ type: 'setMicAudio', patch: { muted } }),
      )}
      <div className="channel-extra">
        <select
          value={audio.mic.deviceId}
          onChange={(e) => dispatch({ type: 'setMicAudio', patch: { deviceId: e.target.value } })}
          aria-label="마이크 장치"
        >
          <option value="">기본 장치</option>
          {micDevices
            .filter((d) => d.deviceId !== 'default' && d.deviceId !== 'communications')
            .map((d, i) => (
              <option key={d.deviceId} value={d.deviceId}>
                {d.label || `마이크 ${i + 1}`}
              </option>
            ))}
        </select>
        {!micActive && (
          <button onClick={() => void hub.audio.resume().then(() => hub.audio.enableMic(audio.mic.deviceId))}>
            마이크 켜기
          </button>
        )}
      </div>
      {!micActive && micError && <p className="error-text small">{micError}</p>}
    </div>
  );
}
