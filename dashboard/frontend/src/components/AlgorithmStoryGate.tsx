import AlgorithmStoryCard from './AlgorithmStoryCard';
import { useI18n } from '../i18n';
import type { AlgorithmVisualization } from '../types/artifacts';

interface AlgorithmStoryGateProps {
  story: AlgorithmVisualization | null;
  mode?: 'live' | 'replay' | 'idle';
  revision?: number;
}

function isPlayableStory(story: AlgorithmVisualization | null): story is AlgorithmVisualization {
  return Boolean(
    story
    && story.supported === true
    && story.family !== 'unsupported'
    && Array.isArray(story.steps)
    && story.steps.length > 0,
  );
}

function getPlaceholderMessage(story: AlgorithmVisualization | null, t: ReturnType<typeof useI18n>['t']): string {
  if (
    story
    && story.supported === true
    && typeof story.family === 'string'
    && story.family.trim() !== ''
    && story.family !== 'unsupported'
  ) {
    return t('algorithmStoryInsufficientTrace').replace('{family}', story.family);
  }

  return t('algorithmStoryUnsupportedPlaceholder');
}

export default function AlgorithmStoryGate({
  story,
  mode = 'idle',
  revision = 0,
}: AlgorithmStoryGateProps) {
  const { t } = useI18n();

  if (isPlayableStory(story)) {
    return <AlgorithmStoryCard story={story} mode={mode} revision={revision} />;
  }

  return (
    <section className="algorithm-story-gate" aria-live="polite">
      <p className="algorithm-story-gate__message">{getPlaceholderMessage(story, t)}</p>
    </section>
  );
}
