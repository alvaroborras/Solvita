interface PlaybackControlsProps {
  playing: boolean;
  speed: number;
  onPlay: () => void;
  onPause: () => void;
  onStep: (dir: 1 | -1) => void;
  onSpeedChange: (speed: number) => void;
}

const speeds = [0.5, 1, 2, 4, 8];

export default function PlaybackControls({
  playing, speed, onPlay, onPause, onStep, onSpeedChange,
}: PlaybackControlsProps) {
  return (
    <div className="playback">
      <button className="playback__btn" onClick={() => onStep(-1)} title="Step back">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <polygon points="19,20 9,12 19,4" /><line x1="5" y1="4" x2="5" y2="20" />
        </svg>
      </button>
      <button className="playback__btn playback__btn--main" onClick={playing ? onPause : onPlay} title={playing ? 'Pause' : 'Play'}>
        {playing ? (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16" /><rect x="14" y="4" width="4" height="16" /></svg>
        ) : (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><polygon points="5,3 19,12 5,21" /></svg>
        )}
      </button>
      <button className="playback__btn" onClick={() => onStep(1)} title="Step forward">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <polygon points="5,4 15,12 5,20" /><line x1="19" y1="4" x2="19" y2="20" />
        </svg>
      </button>
      <div className="playback__speeds">
        {speeds.map((s) => (
          <button
            key={s}
            className={`playback__speed ${s === speed ? 'playback__speed--active' : ''}`}
            onClick={() => onSpeedChange(s)}
          >
            {s}x
          </button>
        ))}
      </div>

      <style>{`
        .playback {
          display: flex;
          align-items: center;
          gap: var(--space-xs);
          padding: 0 var(--space-lg);
        }
        .playback__btn {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 32px;
          height: 32px;
          background: var(--color-bg-glass);
          border: 1px solid var(--color-border-subtle);
          border-radius: var(--radius-sm);
          color: var(--color-text-secondary);
          cursor: pointer;
          transition: all var(--transition-fast);
        }
        .playback__btn:hover {
          background: var(--color-bg-elevated);
          color: var(--color-text-primary);
          border-color: var(--color-border-hover);
          transform: scale(1.05);
        }
        .playback__btn--main {
          width: 40px;
          height: 40px;
          border-radius: var(--radius-md);
          background: var(--color-accent-blue);
          border-color: transparent;
          color: white;
        }
        .playback__btn--main:hover {
          background: #0060d0;
          border-color: transparent;
          color: white;
        }
        .playback__speeds {
          display: flex;
          gap: 2px;
          margin-left: var(--space-md);
          background: var(--color-bg-glass);
          border: 1px solid var(--color-border-subtle);
          border-radius: var(--radius-sm);
          padding: 2px;
        }
        .playback__speed {
          padding: 4px 8px;
          font-size: var(--font-size-xs);
          font-family: var(--font-mono);
          background: transparent;
          border: none;
          border-radius: 4px;
          color: var(--color-text-muted);
          cursor: pointer;
          transition: all var(--transition-fast);
        }
        .playback__speed:hover {
          color: var(--color-text-primary);
        }
        .playback__speed--active {
          background: var(--color-accent-blue);
          color: white;
        }
      `}</style>
    </div>
  );
}
