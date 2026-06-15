import type { AlgorithmStoryStep, AlgorithmVisualization } from '../types/artifacts';

export interface AlgorithmStoryPlaybackStep {
  rawStep: AlgorithmStoryStep;
  viewStep: AlgorithmStoryStep;
  changes: string[];
}

type StoryState = Record<string, unknown>;
type Family = AlgorithmVisualization['family'];

export function buildPlaybackSteps(story: AlgorithmVisualization | null): AlgorithmStoryPlaybackStep[] {
  if (!story?.supported) {
    return [];
  }

  let previousResolved: StoryState = {};

  return story.steps.map((rawStep) => {
    const resolvedState = resolveStepState(story.family, previousResolved, rawStep.state);
    const changes = summarizeStepChanges(story.family, previousResolved, resolvedState, rawStep);
    previousResolved = resolvedState;

    return {
      rawStep,
      viewStep: {
        ...rawStep,
        state: resolvedState,
      },
      changes,
    };
  });
}

function resolveStepState(family: Family, previous: StoryState, raw: StoryState): StoryState {
  switch (family) {
    case 'bfs':
      return resolveBfsStep(previous, raw);
    case 'dfs_recursion':
      return resolveDfsStep(previous, raw);
    case 'basic_dp':
      return resolveBasicDpStep(previous, raw);
    case 'two_pointers':
      return resolveTwoPointersStep(previous, raw);
    case 'sliding_window':
      return resolveSlidingWindowStep(previous, raw);
    case 'binary_search':
      return resolveBinarySearchStep(previous, raw);
    case 'prefix_sum':
      return resolvePrefixSumStep(previous, raw);
    case 'union_find':
      return resolveUnionFindStep(previous, raw);
    case 'topological_sort':
      return resolveTopologicalSortStep(previous, raw);
    case 'greedy_interval':
      return resolveGreedyIntervalStep(previous, raw);
    case 'monotonic_stack':
      return resolveMonotonicStackStep(previous, raw);
    case 'unsupported':
    default:
      return { ...previous, ...raw };
  }
}

function summarizeStepChanges(
  family: Family,
  previous: StoryState,
  current: StoryState,
  step: AlgorithmStoryStep,
): string[] {
  switch (family) {
    case 'bfs':
      return summarizeBfsChanges(previous, current);
    case 'dfs_recursion':
      return summarizeDfsChanges(current);
    case 'basic_dp':
      return summarizeBasicDpChanges(previous, current);
    case 'two_pointers':
      return summarizeTwoPointersChanges(previous, current);
    case 'sliding_window':
      return summarizeSlidingWindowChanges(previous, current);
    case 'binary_search':
      return summarizeBinarySearchChanges(previous, current);
    case 'prefix_sum':
      return summarizePrefixSumChanges(previous, current);
    case 'union_find':
      return summarizeUnionFindChanges(previous, current);
    case 'topological_sort':
      return summarizeTopologicalSortChanges(previous, current);
    case 'greedy_interval':
      return summarizeGreedyIntervalChanges(previous, current);
    case 'monotonic_stack':
      return summarizeMonotonicStackChanges(previous, current);
    case 'unsupported':
    default:
      return step.caption ? [step.caption] : [];
  }
}

function resolveBfsStep(previous: StoryState, raw: StoryState): StoryState {
  const n = numberValue(raw.n) ?? numberValue(previous.n);
  const edges = edgeList(raw.edges ?? previous.edges);
  const adjacency = adjacencyMap(raw.adjacency ?? previous.adjacency);
  const distance = numberRecord(raw.distance ?? previous.distance);
  const nodes = orderedNodes({
    count: n,
    edges,
    maps: [adjacency, distance],
  });

  return {
    n,
    m: numberValue(raw.m) ?? numberValue(previous.m),
    graph: { nodes, edges },
    edges,
    adjacency,
    queue: numberList(raw.queue ?? previous.queue),
    visited: numberList(raw.visited ?? previous.visited),
    distance,
    current: hasOwn(raw, 'current') ? numberValue(raw.current) : null,
    newly_visited: numberList(raw.newly_visited),
    target: numberValue(raw.target) ?? numberValue(previous.target),
    answer: raw.answer ?? previous.answer,
  };
}

function resolveDfsStep(previous: StoryState, raw: StoryState): StoryState {
  const rawTree = raw.tree;
  if (rawTree && typeof rawTree === 'object') {
    const tree = rawTree as { nodes?: unknown; edges?: unknown };
    const nodes = Array.isArray(tree.nodes) ? tree.nodes.map((item) => String(item)) : stringList((previous.tree as { nodes?: unknown })?.nodes);
    const edges = Array.isArray(tree.edges)
      ? tree.edges
        .map((edge) => Array.isArray(edge) && edge.length >= 2 ? [String(edge[0]), String(edge[1])] as [string, string] : null)
        .filter((edge): edge is [string, string] => edge !== null)
      : [];
    return {
      tree: { nodes, edges },
      highlighted_nodes: stringList(raw.highlighted_nodes ?? previous.highlighted_nodes),
      call_stack: Array.isArray(raw.call_stack) ? raw.call_stack as Array<Record<string, unknown>> : Array.isArray(previous.call_stack) ? previous.call_stack as Array<Record<string, unknown>> : [],
      current_call: hasOwn(raw, 'current_call') ? raw.current_call : previous.current_call ?? null,
      returned_values: raw.returned_values && typeof raw.returned_values === 'object'
        ? raw.returned_values as Record<string, unknown>
        : previous.returned_values && typeof previous.returned_values === 'object'
          ? previous.returned_values as Record<string, unknown>
          : {},
      subtree_size_root: numberValue(raw.answer) ?? numberValue(previous.subtree_size_root),
    };
  }

  const n = numberValue(raw.n) ?? numberValue(previous.n);
  const edges = edgeList(raw.edges ?? previous.edges);
  const nodes = orderedNodes({ count: n, edges });
  const root = numberValue(raw.root) ?? numberValue(previous.root);
  const highlightedNodes = numberList(raw.subtree_of_1 ?? previous.highlighted_nodes);
  const subtreeSizeRoot = numberValue(raw.subtree_size_root) ?? numberValue(previous.subtree_size_root);
  const currentCall = root === null ? null : { id: String(root), name: `dfs(${root})` };
  const callStack = subtreeSizeRoot !== null ? [] : currentCall ? [currentCall] : [];
  const returnedValues = subtreeSizeRoot !== null && root !== null
    ? { [`subtree_size(${root})`]: subtreeSizeRoot }
    : {};

  return {
    n,
    root,
    tree: { nodes: nodes.map(String), edges: edges.map(([from, to]) => [String(from), String(to)]) },
    highlighted_nodes: highlightedNodes.map(String),
    call_stack: callStack,
    current_call: subtreeSizeRoot !== null ? null : currentCall,
    returned_values: returnedValues,
    subtree_size_root: subtreeSizeRoot,
  };
}

function resolveBasicDpStep(previous: StoryState, raw: StoryState): StoryState {
  const grid = matrix(raw.grid ?? previous.grid);
  const table = matrix(raw.dp ?? previous.table);
  const changedCells = diffMatrix(
    matrix(previous.table),
    table,
  );
  const currentCell = pair(raw.current_cell);
  const highlightCells = currentCell
    ? [[currentCell[0] - 1, currentCell[1] - 1]]
    : changedCells;

  let transition = '';
  const fromTop = numberValue(raw.from_top);
  const fromLeft = numberValue(raw.from_left);
  const chosenBest = numberValue(raw.chosen_best);
  if (currentCell && fromTop !== null && fromLeft !== null && chosenBest !== null) {
    transition = `dp[${currentCell[0]}][${currentCell[1]}] = min(${fromTop}, ${fromLeft}) + grid[${currentCell[0]}][${currentCell[1]}], so the best incoming sum is ${chosenBest}.`;
  } else if (table.length > 0 && !previous.table) {
    transition = 'Initialize the base case at the top-left corner.';
  } else if (changedCells.length > 0) {
    transition = `Update ${changedCells.length} DP cell${changedCells.length > 1 ? 's' : ''} using previously solved subproblems.`;
  } else if (raw.answer !== undefined) {
    transition = `The minimum path sum is ${String(raw.answer)}.`;
  }

  return {
    n: numberValue(raw.n) ?? numberValue(previous.n),
    m: numberValue(raw.m) ?? numberValue(previous.m),
    grid,
    table,
    highlight_cells: highlightCells,
    current_transition: transition,
    input_view: { grid },
    answer: raw.answer ?? previous.answer,
  };
}

function resolveTwoPointersStep(previous: StoryState, raw: StoryState): StoryState {
  const array = numberList(raw.array ?? previous.array);
  const left = numberValue(raw.left_index) ?? numberValue(previous.left);
  const right = numberValue(raw.right_index) ?? numberValue(previous.right);

  return {
    array,
    left,
    right,
    left_value: numberValue(raw.left_value) ?? numberValue(previous.left_value) ?? valueAt(array, left),
    right_value: numberValue(raw.right_value) ?? numberValue(previous.right_value) ?? valueAt(array, right),
    target: numberValue(raw.target) ?? numberValue(previous.target),
    current_sum: numberValue(raw.current_sum) ?? previous.current_sum,
    relation: stringValue(raw.comparison) ?? stringValue(raw.action) ?? stringValue(previous.relation),
    action: stringValue(raw.action),
    comparison: stringValue(raw.comparison),
    answer: raw.answer ?? previous.answer,
  };
}

function resolveSlidingWindowStep(previous: StoryState, raw: StoryState): StoryState {
  const array = numberList(raw.array ?? previous.array);
  const left = numberValue(raw.left) ?? numberValue(previous.left) ?? 0;
  const right = numberValue(raw.right) ?? numberValue(previous.right) ?? -1;
  const target = numberValue(raw.x) ?? numberValue(previous.target);
  const currentSum = numberValue(raw.current_sum) ?? numberValue(previous.window_sum) ?? 0;
  const bestLength = raw.best_length ?? previous.best_length;
  const windowElements = numberList(raw.window_elements ?? previous.window_elements);

  let condition = '';
  if (raw.answer !== undefined) {
    condition = `Minimum valid length is ${String(raw.answer)}.`;
  } else if (target !== null) {
    condition = currentSum >= target
      ? `Window sum ${currentSum} reaches the target ${target}.`
      : `Window sum ${currentSum} is still below ${target}.`;
  }

  return {
    array,
    left,
    right,
    window_elements: windowElements,
    window_sum: currentSum,
    current_sum: currentSum,
    best_length: bestLength,
    target,
    condition,
    answer: raw.answer ?? previous.answer,
  };
}

function resolveBinarySearchStep(previous: StoryState, raw: StoryState): StoryState {
  const array = numberList(raw.array ?? previous.array);
  const low = numberValue(raw.left) ?? numberValue(previous.low);
  const high = numberValue(raw.right) ?? numberValue(previous.high);
  const mid = hasOwn(raw, 'mid') ? numberValue(raw.mid) : null;

  return {
    array,
    low,
    high,
    mid,
    target: numberValue(raw.x) ?? numberValue(previous.target),
    comparison: stringValue(raw.comparison),
    value: numberValue(raw.value),
    next_low: numberValue(raw.next_left),
    next_high: numberValue(raw.next_right),
    result: numberValue(raw.result) ?? previous.result,
  };
}

function resolvePrefixSumStep(previous: StoryState, raw: StoryState): StoryState {
  const array = numberList(raw.array ?? previous.array);
  const prefix = numberList(raw.prefix ?? previous.prefix);
  const l = numberValue(raw.l) ?? numberValue(previous.l);
  const r = numberValue(raw.r) ?? numberValue(previous.r);
  const activeRange = l !== null && r !== null ? { l: l - 1, r: r - 1 } : null;
  const prefixHighlights = r !== null && l !== null ? [r, l - 1] : [];

  return {
    n: numberValue(raw.n) ?? numberValue(previous.n),
    array,
    prefix,
    l,
    r,
    range: activeRange,
    prefix_highlights: prefixHighlights,
    running_total: prefix.length > 0 ? prefix[prefix.length - 1] : null,
    query: stringValue(raw.formula)
      ?? (l !== null && r !== null ? `sum(${l}..${r}) = prefix[${r}] - prefix[${l - 1}]` : ''),
    answer: raw.answer ?? previous.answer,
  };
}

function resolveUnionFindStep(previous: StoryState, raw: StoryState): StoryState {
  const groups = nestedNumberList(raw.components ?? previous.groups);
  const count = numberValue(raw.components_count) ?? numberValue(previous.components);
  const edge = pair(raw.edge);
  const n = numberValue(raw.n) ?? numberValue(previous.n);

  return {
    n,
    groups,
    components: count,
    current_union: edge ? `${edge[0]}-${edge[1]}` : null,
    edge,
    edges_processed: numberValue(raw.edges_processed) ?? numberValue(previous.edges_processed) ?? 0,
    output: raw.output ?? previous.output,
  };
}

function resolveTopologicalSortStep(previous: StoryState, raw: StoryState): StoryState {
  const edges = edgeList(raw.edges ?? previous.edges);
  const incoming = numberRecord(raw.indegree);
  const updatedIncoming = numberRecord(raw.updated_indegree);
  const indegree = {
    ...numberRecord(previous.indegree),
    ...incoming,
    ...updatedIncoming,
  };
  const queue = numberList(raw.available_zero_indegree ?? previous.queue);
  const processed = numberList(raw.ordering ?? previous.processed);
  const nodes = orderedNodes({
    edges,
    maps: [indegree],
    extras: [...queue, ...processed],
  });

  return {
    graph: { nodes, edges },
    edges,
    indegree,
    queue,
    processed,
    current: hasOwn(raw, 'chosen') ? numberValue(raw.chosen) : null,
  };
}

function resolveGreedyIntervalStep(previous: StoryState, raw: StoryState): StoryState {
  const originalIntervals = intervalList(raw.intervals ?? previous.original_intervals);
  const sortedIntervals = intervalList(raw.sorted_intervals ?? previous.sorted_intervals ?? originalIntervals);
  const chosen = intervalList(raw.chosen ?? raw.final_chosen ?? previous.chosen);
  const currentInterval = pair(raw.current_interval);
  const intervals = sortedIntervals.length > 0 ? sortedIntervals : originalIntervals;
  const currentIndex = currentInterval
    ? intervals.findIndex((interval) => samePair(interval, currentInterval))
    : chosen.length > 0
      ? intervals.findIndex((interval) => samePair(interval, chosen[chosen.length - 1]))
      : -1;

  return {
    original_intervals: originalIntervals,
    sorted_intervals: sortedIntervals,
    chosen,
    intervals: intervals.map(([start, end]) => ({
      start,
      end,
      selected: chosen.some((interval) => samePair(interval, [start, end])),
    })),
    current_index: currentIndex,
    current_interval: currentInterval,
    last_end: numberValue(raw.last_end) ?? numberValue(previous.last_end),
    decision: stringValue(raw.decision),
    count: numberValue(raw.count) ?? numberValue(previous.count),
    answer: numberValue(raw.maximum_count) ?? previous.answer,
  };
}

function resolveMonotonicStackStep(previous: StoryState, raw: StoryState): StoryState {
  const array = numberList(raw.array ?? previous.array);
  const stack = numberList(raw.stack ?? previous.stack);
  const popped = numberList(raw.popped);
  const currentIndex = hasOwn(raw, 'index') ? numberValue(raw.index) : null;
  const currentValue = numberValue(raw.value) ?? valueAt(array, currentIndex);
  const ans = numberOrNullList(raw.ans ?? previous.ans);

  let action = '';
  if (hasOwn(raw, 'ans') && !hasOwn(raw, 'index')) {
    action = `Finished scanning; the next-greater answers are ${ans.map(renderCell).join(', ')}.`;
  } else if (popped.length > 0 && currentValue !== null) {
    action = `Pop ${popped.join(', ')} because those values are not greater than ${currentValue}, then push ${currentValue}.`;
  } else if (currentValue !== null) {
    action = `Push ${currentValue} onto the stack as a candidate for elements to its left.`;
  }

  return {
    array,
    stack,
    current_index: currentIndex,
    current_value: currentValue,
    popped,
    ans,
    action,
  };
}

function summarizeBfsChanges(previous: StoryState, current: StoryState): string[] {
  const changes: string[] = [];
  const graph = current.graph as { nodes?: number[]; edges?: Array<[number, number]> } | undefined;
  const currentNode = numberValue(current.current);
  const newlyVisited = numberList(current.newly_visited);
  const answer = current.answer;
  const target = numberValue(current.target);

  if (!previous.graph && graph) {
    changes.push(`Load a graph with ${graph.nodes?.length || 0} nodes and ${graph.edges?.length || 0} edges.`);
  }
  if (!hasOwn(previous, 'visited') && numberList(current.visited).length > 0 && currentNode === null) {
    changes.push(`Initialize BFS from node ${numberList(current.queue)[0] ?? 1} with distance 0.`);
  }
  if (currentNode !== null) {
    changes.push(`Expand node ${currentNode}.`);
  }
  if (newlyVisited.length > 0) {
    changes.push(`Discover nodes ${newlyVisited.join(', ')} and push them into the queue.`);
  }
  if (target !== null && answer !== undefined) {
    changes.push(`Reach target ${target} with shortest distance ${String(answer)}.`);
  }

  return changes;
}

function summarizeDfsChanges(current: StoryState): string[] {
  const changes: string[] = [];
  const root = numberValue(current.root);
  const highlightedNodes = stringList(current.highlighted_nodes);
  const size = numberValue(current.subtree_size_root);

  if (root !== null && highlightedNodes.length === 0 && size === null) {
    changes.push(`Root the DFS at node ${root}.`);
  }
  if (highlightedNodes.length > 0) {
    changes.push(`Mark the subtree of node ${root} as nodes ${highlightedNodes.join(', ')}.`);
  }
  if (size !== null && root !== null) {
    changes.push(`Return subtree_size(${root}) = ${size}.`);
  }

  return changes;
}

function summarizeBasicDpChanges(previous: StoryState, current: StoryState): string[] {
  const changes: string[] = [];
  const previousTable = matrix(previous.table);
  const table = matrix(current.table);
  const diff = diffMatrix(previousTable, table);
  const transition = stringValue(current.current_transition);
  const answer = current.answer;

  if (!previous.grid && matrix(current.grid).length > 0) {
    changes.push(`Read a ${matrix(current.grid).length} x ${matrix(current.grid)[0]?.length || 0} grid for the DP problem.`);
  }
  if (diff.length > 0) {
    changes.push(`Write ${diff.length} new DP cell${diff.length > 1 ? 's' : ''}: ${diff.map(formatCellPosition).join(', ')}.`);
  }
  if (transition) {
    changes.push(transition);
  }
  if (answer !== undefined) {
    changes.push(`Finish with answer ${String(answer)}.`);
  }

  return uniqueStrings(changes);
}

function summarizeTwoPointersChanges(previous: StoryState, current: StoryState): string[] {
  const changes: string[] = [];
  const left = numberValue(current.left);
  const right = numberValue(current.right);
  const leftValue = numberValue(current.left_value);
  const rightValue = numberValue(current.right_value);
  const currentSum = numberValue(current.current_sum);
  const comparison = stringValue(current.comparison);
  const action = stringValue(current.action);

  if (!previous.array && left !== null && right !== null) {
    changes.push(`Place the two pointers at indices ${left} and ${right}.`);
  }
  if (currentSum !== null && leftValue !== null && rightValue !== null) {
    changes.push(`Check ${leftValue} + ${rightValue} = ${currentSum}.`);
  }
  if (comparison) {
    changes.push(comparison);
  }
  if (action) {
    changes.push(action.replace(/^./, (value) => value.toUpperCase()) + '.');
  }
  if (current.answer !== undefined) {
    changes.push(`Return ${String(current.answer)}.`);
  }

  return uniqueStrings(changes);
}

function summarizeSlidingWindowChanges(previous: StoryState, current: StoryState): string[] {
  const changes: string[] = [];
  const previousRight = numberValue(previous.right);
  const currentRight = numberValue(current.right);
  const previousLeft = numberValue(previous.left);
  const currentLeft = numberValue(current.left);
  const array = numberList(current.array);
  const bestLength = current.best_length;

  if (!previous.array && array.length > 0) {
    changes.push(`Start with an empty window over ${array.length} numbers.`);
  }
  if (currentRight !== null && previousRight !== currentRight && currentRight >= 0) {
    changes.push(`Extend the right edge to index ${currentRight} and include ${array[currentRight]}.`);
  }
  if (currentLeft !== null && previousLeft !== null && currentLeft > previousLeft) {
    changes.push(`Move the left edge forward to index ${currentLeft}.`);
  }
  if (bestLength !== undefined && bestLength !== previous.best_length && bestLength !== 'infinity') {
    changes.push(`Update the best valid window length to ${String(bestLength)}.`);
  }
  if (stringValue(current.condition)) {
    changes.push(stringValue(current.condition) || '');
  }
  if (current.answer !== undefined) {
    changes.push(`Return ${String(current.answer)}.`);
  }

  return uniqueStrings(changes);
}

function summarizeBinarySearchChanges(previous: StoryState, current: StoryState): string[] {
  const changes: string[] = [];
  const low = numberValue(current.low);
  const high = numberValue(current.high);
  const mid = numberValue(current.mid);
  const value = numberValue(current.value);
  const target = numberValue(current.target);
  const comparison = stringValue(current.comparison);
  const nextLow = numberValue(current.next_low);
  const nextHigh = numberValue(current.next_high);
  const result = numberValue(current.result);

  if (!previous.array && low !== null && high !== null && target !== null) {
    changes.push(`Search the full range [${low}, ${high}] for ${target}.`);
  }
  if (mid !== null && value !== null) {
    changes.push(`Check mid = ${mid}, where the value is ${value}.`);
  }
  if (comparison && nextLow !== null && nextHigh !== null) {
    changes.push(`Because ${comparison}, narrow the next range to [${nextLow}, ${nextHigh}].`);
  } else if (comparison) {
    changes.push(comparison);
  }
  if (result !== null) {
    changes.push(`Return index ${result}.`);
  }

  return uniqueStrings(changes);
}

function summarizePrefixSumChanges(previous: StoryState, current: StoryState): string[] {
  const changes: string[] = [];
  const l = numberValue(current.l);
  const r = numberValue(current.r);
  const prefix = numberList(current.prefix);
  const answer = current.answer;

  if (!previous.array && numberList(current.array).length > 0 && l !== null && r !== null) {
    changes.push(`Read the array and prepare to answer range [${l}, ${r}].`);
  }
  if (prefix.length === 1 && numberList(previous.prefix).length === 0) {
    changes.push('Initialize prefix[0] = 0.');
  }
  if (prefix.length > numberList(previous.prefix).length && prefix.length > 1) {
    changes.push(`Build prefix sums up to prefix[${prefix.length - 1}].`);
  }
  if (stringValue(current.query)) {
    changes.push(stringValue(current.query) || '');
  }
  if (answer !== undefined) {
    changes.push(`Return ${String(answer)}.`);
  }

  return uniqueStrings(changes);
}

function summarizeUnionFindChanges(previous: StoryState, current: StoryState): string[] {
  const changes: string[] = [];
  const components = numberValue(current.components);
  const edge = pair(current.edge);

  if (!previous.groups && nestedNumberList(current.groups).length > 0 && components !== null) {
    changes.push(`Start with ${components} singleton components.`);
  }
  if (edge && components !== null) {
    changes.push(`Merge the sets containing ${edge[0]} and ${edge[1]}, reducing the component count to ${components}.`);
  }
  if (current.output !== undefined && components !== null) {
    changes.push(`All edges are processed; ${components} connected components remain.`);
  }

  return changes;
}

function summarizeTopologicalSortChanges(previous: StoryState, current: StoryState): string[] {
  const changes: string[] = [];
  const queue = numberList(current.queue);
  const processed = numberList(current.processed);
  const currentNode = numberValue(current.current);
  const previousQueue = numberList(previous.queue);
  const unlocked = queue.filter((node) => !previousQueue.includes(node));

  if (!previous.graph && queue.length > 0) {
    changes.push(`Compute indegrees and start with node ${queue[0]} in the zero-indegree queue.`);
  }
  if (currentNode !== null && processed.length > 0) {
    if (unlocked.length > 0) {
      changes.push(`Remove node ${currentNode}, append it to the ordering, and unlock nodes ${unlocked.join(', ')}.`);
    } else {
      changes.push(`Remove node ${currentNode} and append it to the ordering.`);
    }
  }

  return changes;
}

function summarizeGreedyIntervalChanges(previous: StoryState, current: StoryState): string[] {
  const changes: string[] = [];
  const currentInterval = pair(current.current_interval);
  const decision = stringValue(current.decision);
  const lastEnd = numberValue(current.last_end);
  const answer = numberValue(current.answer);

  if (!previous.original_intervals && intervalList(current.original_intervals).length > 0) {
    changes.push(`Read ${intervalList(current.original_intervals).length} intervals.`);
  }
  if (!previous.sorted_intervals && intervalList(current.sorted_intervals).length > 0 && !currentInterval && !decision) {
    changes.push('Sort intervals by finishing time.');
  }
  if (currentInterval && decision === 'skip' && lastEnd !== null) {
    changes.push(`Skip interval [${currentInterval[0]}, ${currentInterval[1]}] because it overlaps with the last chosen end ${lastEnd}.`);
  } else if (currentInterval && decision === 'take' && lastEnd !== null) {
    changes.push(`Take interval [${currentInterval[0]}, ${currentInterval[1]}] and update the last chosen end to ${lastEnd}.`);
  } else if (!currentInterval && nestedNumberList(current.chosen).length === 1 && nestedNumberList(previous.chosen).length === 0) {
    const first = nestedNumberList(current.chosen)[0];
    changes.push(`Take interval [${first[0]}, ${first[1]}] as the first compatible choice.`);
  }
  if (answer !== null) {
    changes.push(`Finish with a maximum of ${answer} non-overlapping intervals.`);
  }

  return changes;
}

function summarizeMonotonicStackChanges(previous: StoryState, current: StoryState): string[] {
  const changes: string[] = [];
  const currentValue = numberValue(current.current_value);
  const currentIndex = numberValue(current.current_index);
  const popped = numberList(current.popped);
  const ans = numberOrNullList(current.ans);
  const previousAns = numberOrNullList(previous.ans);

  if (!previous.array && currentValue !== null && currentIndex !== null) {
    changes.push(`Start from index ${currentIndex} and push ${currentValue} onto the stack.`);
  }
  if (popped.length > 0 && currentValue !== null) {
    changes.push(`Pop ${popped.join(', ')} because those values are not greater than ${currentValue}.`);
  }
  if (currentIndex !== null && currentValue !== null && previous.array) {
    changes.push(`Process index ${currentIndex} with value ${currentValue}.`);
  }
  if (ans.length > 0 && !sameList(ans, previousAns)) {
    changes.push(`Current answer view: ${ans.map(renderCell).join(', ')}.`);
  }
  if (stringValue(current.action)) {
    changes.push(stringValue(current.action) || '');
  }

  return uniqueStrings(changes);
}

function hasOwn(object: StoryState, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(object, key);
}

function numberValue(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function stringValue(value: unknown): string | null {
  return typeof value === 'string' && value.length > 0 ? value : null;
}

function numberList(value: unknown): number[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => (typeof item === 'number' && Number.isFinite(item) ? item : null))
    .filter((item): item is number => item !== null);
}

function numberOrNullList(value: unknown): Array<number | null> {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((item) => (typeof item === 'number' && Number.isFinite(item) ? item : null));
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((item) => String(item));
}

function pair(value: unknown): [number, number] | null {
  if (!Array.isArray(value) || value.length < 2) {
    return null;
  }
  const first = numberValue(value[0]);
  const second = numberValue(value[1]);
  return first === null || second === null ? null : [first, second];
}

function edgeList(value: unknown): Array<[number, number]> {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => pair(item))
    .filter((item): item is [number, number] => item !== null);
}

function intervalList(value: unknown): Array<[number, number]> {
  return edgeList(value);
}

function nestedNumberList(value: unknown): number[][] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((item) => numberList(item)).filter((group) => group.length > 0);
}

function matrix(value: unknown): Array<Array<number | null>> {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((row) => {
    if (!Array.isArray(row)) {
      return [];
    }
    return row.map((cell) => (typeof cell === 'number' && Number.isFinite(cell) ? cell : null));
  });
}

function adjacencyMap(value: unknown): Record<string, number[]> {
  if (!value || typeof value !== 'object') {
    return {};
  }
  return Object.fromEntries(
    Object.entries(value).map(([key, neighbors]) => [key, numberList(neighbors)]),
  );
}

function numberRecord(value: unknown): Record<string, number> {
  if (!value || typeof value !== 'object') {
    return {};
  }
  return Object.fromEntries(
    Object.entries(value)
      .map(([key, item]) => [key, numberValue(item)])
      .filter((entry): entry is [string, number] => entry[1] !== null),
  );
}

function orderedNodes({
  count,
  edges,
  maps = [],
  extras = [],
}: {
  count?: number | null;
  edges?: Array<[number, number]>;
  maps?: Array<Record<string, unknown>>;
  extras?: number[];
}): number[] {
  const values = new Set<number>();
  if (count !== null && count !== undefined) {
    for (let node = 1; node <= count; node += 1) {
      values.add(node);
    }
  }
  for (const [from, to] of edges || []) {
    values.add(from);
    values.add(to);
  }
  for (const map of maps) {
    for (const key of Object.keys(map)) {
      const node = Number(key);
      if (Number.isFinite(node)) {
        values.add(node);
      }
    }
  }
  for (const node of extras) {
    values.add(node);
  }
  return Array.from(values).sort((left, right) => left - right);
}

function diffMatrix(
  previous: Array<Array<number | null>>,
  current: Array<Array<number | null>>,
): Array<[number, number]> {
  const changed: Array<[number, number]> = [];
  for (let row = 0; row < current.length; row += 1) {
    for (let col = 0; col < current[row].length; col += 1) {
      if ((previous[row] || [])[col] !== current[row][col]) {
        changed.push([row, col]);
      }
    }
  }
  return changed;
}

function formatCellPosition([row, col]: [number, number]): string {
  return `dp[${row + 1}][${col + 1}]`;
}

function renderCell(value: number | null): string {
  return value === null ? '·' : String(value);
}

function valueAt(values: number[], index: number | null): number | null {
  if (index === null || index < 0 || index >= values.length) {
    return null;
  }
  return values[index];
}

function samePair(left: [number, number], right: [number, number]): boolean {
  return left[0] === right[0] && left[1] === right[1];
}

function uniqueStrings(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean)));
}

function sameList(left: Array<number | null>, right: Array<number | null>): boolean {
  if (left.length !== right.length) {
    return false;
  }
  return left.every((item, index) => item === right[index]);
}
