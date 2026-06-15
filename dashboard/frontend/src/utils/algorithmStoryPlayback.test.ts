import { describe, expect, it } from 'vitest';
import type { AlgorithmVisualization } from '../types/artifacts';
import { buildPlaybackSteps } from './algorithmStoryPlayback';

function createStory(
  family: AlgorithmVisualization['family'],
  steps: AlgorithmVisualization['steps'],
): AlgorithmVisualization {
  return {
    supported: true,
    family,
    mode: 'teaching',
    sampleSource: 'unit-test',
    sampleFocus: '',
    sampleInput: '',
    sampleOutput: '',
    title: 'test story',
    summary: 'test summary',
    steps,
    fallbackText: '',
  };
}

describe('buildPlaybackSteps', () => {
  it('normalizes BFS showcase states and carries graph context across steps', () => {
    const story = createStory('bfs', [
      {
        step: 1,
        label: 'Build the graph',
        caption: '',
        state: {
          n: 4,
          m: 3,
          edges: [[1, 2], [1, 3], [2, 4]],
          adjacency: { '1': [2, 3], '2': [1, 4], '3': [1], '4': [2] },
        },
      },
      {
        step: 2,
        label: 'Start BFS at node 1',
        caption: '',
        state: {
          queue: [1],
          visited: [1],
          distance: { '1': 0, '2': -1, '3': -1, '4': -1 },
        },
      },
      {
        step: 3,
        label: 'Expand node 1',
        caption: '',
        state: {
          current: 1,
          newly_visited: [2, 3],
          queue: [2, 3],
          visited: [1, 2, 3],
          distance: { '1': 0, '2': 1, '3': 1, '4': -1 },
        },
      },
    ]);

    const playback = buildPlaybackSteps(story);
    const first = playback[0].viewStep.state as {
      graph?: { nodes?: number[]; edges?: Array<[number, number]> };
    };
    const third = playback[2].viewStep.state as {
      graph?: { nodes?: number[]; edges?: Array<[number, number]> };
      newly_visited?: number[];
      queue?: number[];
    };

    expect(first.graph?.nodes).toEqual([1, 2, 3, 4]);
    expect(first.graph?.edges).toEqual([[1, 2], [1, 3], [2, 4]]);
    expect(playback[0].changes).toContain('Load a graph with 4 nodes and 3 edges.');

    expect(third.graph?.nodes).toEqual([1, 2, 3, 4]);
    expect(third.newly_visited).toEqual([2, 3]);
    expect(third.queue).toEqual([2, 3]);
    expect(playback[2].changes).toContain('Discover nodes 2, 3 and push them into the queue.');
  });

  it('maps DP table steps from real replay fields', () => {
    const story = createStory('basic_dp', [
      {
        step: 1,
        label: 'Read the grid',
        caption: '',
        state: {
          n: 2,
          m: 3,
          grid: [[1, 2, 3], [4, 5, 6]],
        },
      },
      {
        step: 2,
        label: 'Start at the first cell',
        caption: '',
        state: {
          dp: [[1, null, null], [null, null, null]],
        },
      },
      {
        step: 5,
        label: 'Compute the middle cell',
        caption: '',
        state: {
          current_cell: [2, 2],
          from_top: 3,
          from_left: 5,
          chosen_best: 5,
          dp: [[1, 3, 6], [5, 10, null]],
        },
      },
    ]);

    const playback = buildPlaybackSteps(story);
    const computed = playback[2].viewStep.state as {
      table?: Array<Array<number | null>>;
      highlight_cells?: Array<[number, number]>;
      current_transition?: string;
      input_view?: { grid?: number[][] };
    };

    expect(computed.table).toEqual([[1, 3, 6], [5, 10, null]]);
    expect(computed.highlight_cells).toEqual([[1, 1]]);
    expect(computed.current_transition).toBe('dp[2][2] = min(3, 5) + grid[2][2], so the best incoming sum is 5.');
    expect(computed.input_view?.grid).toEqual([[1, 2, 3], [4, 5, 6]]);
  });

  it('turns union-find component groups into visible state changes', () => {
    const story = createStory('union_find', [
      {
        step: 1,
        label: 'Initialize sets',
        caption: '',
        state: {
          n: 5,
          edges_processed: 0,
          components_count: 5,
          components: [[1], [2], [3], [4], [5]],
        },
      },
      {
        step: 2,
        label: 'Process edge 1-2',
        caption: '',
        state: {
          edge: [1, 2],
          edges_processed: 1,
          components_count: 4,
          components: [[1, 2], [3], [4], [5]],
        },
      },
    ]);

    const playback = buildPlaybackSteps(story);
    const merged = playback[1].viewStep.state as {
      groups?: number[][];
      current_union?: string;
      components?: number;
    };

    expect(merged.groups).toEqual([[1, 2], [3], [4], [5]]);
    expect(merged.current_union).toBe('1-2');
    expect(merged.components).toBe(4);
    expect(playback[1].changes).toContain('Merge the sets containing 1 and 2, reducing the component count to 4.');
  });

  it('keeps topological-sort graph context while indegrees evolve', () => {
    const story = createStory('topological_sort', [
      {
        step: 1,
        label: 'Build indegrees',
        caption: '',
        state: {
          edges: [[1, 2], [1, 3], [2, 4], [3, 4]],
          indegree: { '1': 0, '2': 1, '3': 1, '4': 2 },
          available_zero_indegree: [1],
          ordering: [],
        },
      },
      {
        step: 2,
        label: 'Take node 1',
        caption: '',
        state: {
          chosen: 1,
          ordering: [1],
          updated_indegree: { '2': 0, '3': 0, '4': 2 },
          available_zero_indegree: [2, 3],
        },
      },
    ]);

    const playback = buildPlaybackSteps(story);
    const second = playback[1].viewStep.state as {
      graph?: { nodes?: number[]; edges?: Array<[number, number]> };
      queue?: number[];
      processed?: number[];
      indegree?: Record<string, number>;
      current?: number;
    };

    expect(second.graph?.nodes).toEqual([1, 2, 3, 4]);
    expect(second.queue).toEqual([2, 3]);
    expect(second.processed).toEqual([1]);
    expect(second.indegree).toEqual({ '1': 0, '2': 0, '3': 0, '4': 2 });
    expect(second.current).toBe(1);
    expect(playback[1].changes).toContain('Remove node 1, append it to the ordering, and unlock nodes 2, 3.');
  });

  it('preserves explicit DFS recursion-stack states from deterministic traces', () => {
    const story = createStory('dfs_recursion', [
      {
        step: 1,
        label: 'Enter dfs(1)',
        caption: '',
        state: {
          tree: {
            nodes: ['1', '2', '3'],
            edges: [['1', '2'], ['1', '3']],
          },
          call_stack: [{ id: '1', name: 'dfs(1)' }],
          current_call: { id: '1', name: 'dfs(1)' },
          highlighted_nodes: ['1'],
          returned_values: {},
        },
      },
      {
        step: 2,
        label: 'Return from dfs(1)',
        caption: '',
        state: {
          tree: {
            nodes: ['1', '2', '3'],
            edges: [['1', '2'], ['1', '3']],
          },
          call_stack: [{ id: '1', name: 'dfs(1)' }],
          current_call: { id: '1', name: 'dfs(1)' },
          highlighted_nodes: ['1', '2', '3'],
          returned_values: { 'subtree_size(1)': 3 },
        },
      },
    ]);

    const playback = buildPlaybackSteps(story);
    const second = playback[1].viewStep.state as {
      tree?: { nodes?: string[]; edges?: Array<[string, string]> };
      call_stack?: Array<Record<string, unknown>>;
      current_call?: Record<string, unknown> | null;
      returned_values?: Record<string, unknown>;
      highlighted_nodes?: string[];
    };

    expect(second.tree?.nodes).toEqual(['1', '2', '3']);
    expect(second.call_stack?.[0]?.name).toBe('dfs(1)');
    expect(second.current_call?.id).toBe('1');
    expect(second.highlighted_nodes).toEqual(['1', '2', '3']);
    expect(second.returned_values?.['subtree_size(1)']).toBe(3);
  });
});
