import { describe, expect, it } from 'vitest';
import { parseProblemStatement } from './problemStatement';

describe('parseProblemStatement', () => {
  it('extracts structured fields from a Chinese statement', () => {
    const result = parseProblemStatement({
      description: `题目描述
给定一个长度为 n 的整数数组，请输出其中的最大值和最小值。

输入格式
第一行包含一个整数 n。
第二行包含 n 个整数。

输出格式
输出两个整数，分别表示最大值和最小值。

样例输入
5
3 9 1 7 4

样例输出
9 1

说明
数据保证至少包含一个整数。

约束
1 <= n <= 100000`,
      public_tests: [{ input: '2\n1 2\n', output: '2 1\n' }],
      time_limit: 1000,
      space_limit: 256,
      _metadata: { name: '最大值最小值', source: 'unit-test' },
    });

    expect(result.title).toBe('最大值最小值');
    expect(result.bodySections).toEqual([
      {
        heading: '题目描述',
        content: '给定一个长度为 n 的整数数组，请输出其中的最大值和最小值。',
      },
    ]);
    expect(result.inputFormat).toBe('第一行包含一个整数 n。\n第二行包含 n 个整数。');
    expect(result.outputFormat).toBe('输出两个整数，分别表示最大值和最小值。');
    expect(result.constraints).toBe('1 <= n <= 100000');
    expect(result.complexity).toBe('');
    expect(result.explanation).toBe('数据保证至少包含一个整数。');
    expect(result.samples).toEqual([
      {
        title: '样例 1',
        input: '5\n3 9 1 7 4',
        output: '9 1',
      },
    ]);
    expect(result.meta).toMatchObject({
      timeLimit: 1000,
      spaceLimit: 256,
      source: 'unit-test',
      usedFallback: false,
    });
  });

  it('treats top-level Chinese 输入 and 输出 headings as format sections', () => {
    const result = parseProblemStatement({
      description: `题目描述
读取两个整数并输出它们的和。

输入
一行两个整数 a 和 b。

输出
输出它们的和。`,
      public_tests: [],
      time_limit: 1000,
      space_limit: 256,
      _metadata: { name: '中文输入输出标题' },
    });

    expect(result.bodySections).toEqual([
      {
        heading: '题目描述',
        content: '读取两个整数并输出它们的和。',
      },
    ]);
    expect(result.inputFormat).toBe('一行两个整数 a 和 b。');
    expect(result.outputFormat).toBe('输出它们的和。');
  });

  it('extracts structured fields from an English statement including complexity', () => {
    const result = parseProblemStatement({
      description: `Problem
Given an array of n integers, return the sum of the largest two values.

Input
The first line contains n.
The second line contains n integers.

Output
Print one integer, the required sum.

Constraints
2 <= n <= 200000

Complexity
Expected time complexity: O(n).
Expected space complexity: O(1).

Sample Input
4
5 1 7 3

Sample Output
12

Explanation
The two largest values are 7 and 5.`,
      public_tests: [],
      time_limit: 2000,
      space_limit: 512,
      _metadata: { name: 'Largest Pair Sum', difficulty: 'easy' },
    });

    expect(result.title).toBe('Largest Pair Sum');
    expect(result.bodySections).toEqual([
      {
        heading: 'Problem',
        content: 'Given an array of n integers, return the sum of the largest two values.',
      },
    ]);
    expect(result.inputFormat).toBe('The first line contains n.\nThe second line contains n integers.');
    expect(result.outputFormat).toBe('Print one integer, the required sum.');
    expect(result.constraints).toBe('2 <= n <= 200000');
    expect(result.complexity).toBe('Expected time complexity: O(n).\nExpected space complexity: O(1).');
    expect(result.explanation).toBe('The two largest values are 7 and 5.');
    expect(result.samples).toEqual([
      {
        title: 'Sample 1',
        input: '4\n5 1 7 3',
        output: '12',
      },
    ]);
    expect(result.meta).toMatchObject({
      timeLimit: 2000,
      spaceLimit: 512,
      difficulty: 'easy',
      usedFallback: false,
    });
  });

  it('preserves free-form statements and falls back to public tests and limits', () => {
    const description = `Sort the values in ascending order and print them.

This statement is intentionally free-form and has no recognizable headings.
Keep every paragraph exactly as written.`;

    const result = parseProblemStatement({
      description,
      public_tests: [
        { input: '3\n3 1 2\n', output: '1 2 3\n' },
        { input: '1\n9\n', output: '9\n' },
      ],
      time_limit: 3000,
      space_limit: 128,
      _metadata: { name: 'Free Form Sort', source: 'custom' },
    });

    expect(result.title).toBe('Free Form Sort');
    expect(result.bodySections).toEqual([
      {
        heading: '',
        content: description,
      },
    ]);
    expect(result.inputFormat).toBe('');
    expect(result.outputFormat).toBe('');
    expect(result.constraints).toBe('');
    expect(result.complexity).toBe('');
    expect(result.explanation).toBe('');
    expect(result.samples).toEqual([
      {
        title: 'Sample 1',
        input: '3\n3 1 2\n',
        output: '1 2 3\n',
      },
      {
        title: 'Sample 2',
        input: '1\n9\n',
        output: '9\n',
      },
    ]);
    expect(result.meta).toMatchObject({
      timeLimit: 3000,
      spaceLimit: 128,
      source: 'custom',
      usedFallback: true,
    });
  });

  it('falls back to public tests for samples when structured sections have no sample headings', () => {
    const result = parseProblemStatement({
      description: `Problem
Find the maximum value.

Input
The first line contains n.

Output
Print the maximum value.

Constraints
1 <= n <= 1000`,
      public_tests: [{ input: '3\n1 9 4\n', output: '9\n' }],
      time_limit: 1000,
      space_limit: 256,
      _metadata: { name: 'Max Value' },
    });

    expect(result.samples).toEqual([
      {
        title: 'Sample 1',
        input: '3\n1 9 4\n',
        output: '9\n',
      },
    ]);
    expect(result.meta).toMatchObject({
      usedFallback: true,
    });
  });

  it('parses nested Input and Output markers inside a Sample block without polluting top-level formats', () => {
    const result = parseProblemStatement({
      description: `Problem
Find the sum.

Input
The first line contains two integers.

Output
Print their sum.

Sample
Input
2 3

Output
5`,
      public_tests: [],
      time_limit: 1000,
      space_limit: 256,
      _metadata: { name: 'Nested Sample' },
    });

    expect(result.inputFormat).toBe('The first line contains two integers.');
    expect(result.outputFormat).toBe('Print their sum.');
    expect(result.samples).toEqual([
      {
        title: 'Sample 1',
        input: '2 3',
        output: '5',
      },
    ]);
  });

  it('preserves prose inside a Sample block while still building the sample pair', () => {
    const result = parseProblemStatement({
      description: `Problem
Explain the mapping.

Sample
This example demonstrates the expected formatting.
Input
4 5

Output
9`,
      public_tests: [],
      time_limit: 1000,
      space_limit: 256,
      _metadata: { name: 'Sample With Note' },
    });

    expect(result.samples).toEqual([
      {
        title: 'Sample 1',
        input: '4 5',
        output: '9',
      },
    ]);
    expect(result.bodySections).toEqual([
      {
        heading: 'Problem',
        content: 'Explain the mapping.',
      },
      {
        heading: 'Sample',
        content: 'This example demonstrates the expected formatting.',
      },
    ]);
  });

  it('recognizes Sample 1 Input and Sample 1 Output heading pairs', () => {
    const result = parseProblemStatement({
      description: `Problem
Add two integers.

Input
Two integers a and b.

Output
Print their sum.

Sample 1 Input
2 3

Sample 1 Output
5

Example 2 Input
10 20

Example 2 Output
30`,
      public_tests: [],
      time_limit: 1000,
      space_limit: 256,
      _metadata: { name: 'A Plus B' },
    });

    expect(result.samples).toEqual([
      {
        title: 'Sample 1',
        input: '2 3',
        output: '5',
      },
      {
        title: 'Sample 2',
        input: '10 20',
        output: '30',
      },
    ]);
  });

  it('recognizes Sample Input 1 and Example Output 2 heading pairs', () => {
    const result = parseProblemStatement({
      description: `Problem
Add two integers.

Sample Input 1
2 3

Sample Output 1
5

Example Input 2
10 20

Example Output 2
30`,
      public_tests: [],
      time_limit: 1000,
      space_limit: 256,
      _metadata: { name: 'Suffix Numbered Samples' },
    });

    expect(result.samples).toEqual([
      {
        title: 'Sample 1',
        input: '2 3',
        output: '5',
      },
      {
        title: 'Sample 2',
        input: '10 20',
        output: '30',
      },
    ]);
  });

  it('pairs Sample 1 Input and Sample 1 Output sections by sample number instead of arrival order', () => {
    const result = parseProblemStatement({
      description: `Problem
Match numbered samples.

Sample 1 Input
2 3

Sample 2 Input
10 20

Sample 1 Output
5

Sample 2 Output
30`,
      public_tests: [],
      time_limit: 1000,
      space_limit: 256,
      _metadata: { name: 'Out Of Order Sample Numbers' },
    });

    expect(result.samples).toEqual([
      {
        title: 'Sample 1',
        input: '2 3',
        output: '5',
      },
      {
        title: 'Sample 2',
        input: '10 20',
        output: '30',
      },
    ]);
  });

  it('pairs Sample Input 1 and Sample Output 1 sections by sample number instead of arrival order', () => {
    const result = parseProblemStatement({
      description: `Problem
Match numbered samples.

Sample Input 1
2 3

Sample Input 2
10 20

Sample Output 1
5

Sample Output 2
30`,
      public_tests: [],
      time_limit: 1000,
      space_limit: 256,
      _metadata: { name: 'Out Of Order Suffix Sample Numbers' },
    });

    expect(result.samples).toEqual([
      {
        title: 'Sample 1',
        input: '2 3',
        output: '5',
      },
      {
        title: 'Sample 2',
        input: '10 20',
        output: '30',
      },
    ]);
  });

  it('treats Example 1 as a sample section and keeps nested input and output out of top-level formats', () => {
    const result = parseProblemStatement({
      description: `Problem
Compute the sum.

Input
Read two integers.

Output
Print one integer.

Example 1
Input
3 4

Output
7`,
      public_tests: [],
      time_limit: 1000,
      space_limit: 256,
      _metadata: { name: 'Example Heading' },
    });

    expect(result.inputFormat).toBe('Read two integers.');
    expect(result.outputFormat).toBe('Print one integer.');
    expect(result.samples).toEqual([
      {
        title: 'Sample 1',
        input: '3 4',
        output: '7',
      },
    ]);
  });

  it('treats Examples as a sample section and keeps nested input and output out of top-level formats', () => {
    const result = parseProblemStatement({
      description: `Problem
Compute the difference.

Input
Read two integers.

Output
Print one integer.

Examples
Input
9 4

Output
5`,
      public_tests: [],
      time_limit: 1000,
      space_limit: 256,
      _metadata: { name: 'Examples Heading' },
    });

    expect(result.inputFormat).toBe('Read two integers.');
    expect(result.outputFormat).toBe('Print one integer.');
    expect(result.samples).toEqual([
      {
        title: 'Sample 1',
        input: '9 4',
        output: '5',
      },
    ]);
  });

  it('recognizes numbered Chinese sample input and output headings', () => {
    const result = parseProblemStatement({
      description: `题目描述
计算两个数字之和。

样例 1 输入
2 3

样例 1 输出
5

样例2输入
10 20

样例2输出
30`,
      public_tests: [],
      time_limit: 1000,
      space_limit: 256,
      _metadata: { name: '中文样例' },
    });

    expect(result.samples).toEqual([
      {
        title: '样例 1',
        input: '2 3',
        output: '5',
      },
      {
        title: '样例 2',
        input: '10 20',
        output: '30',
      },
    ]);
  });

  it('treats 样例 1 as a sample section and keeps nested 输入 and 输出 out of top-level formats', () => {
    const result = parseProblemStatement({
      description: `题目描述
计算两个数字之和。

输入格式
读取两个整数。

输出格式
输出它们的和。

样例 1
输入
2 3

输出
5`,
      public_tests: [],
      time_limit: 1000,
      space_limit: 256,
      _metadata: { name: '中文样例标题' },
    });

    expect(result.inputFormat).toBe('读取两个整数。');
    expect(result.outputFormat).toBe('输出它们的和。');
    expect(result.samples).toEqual([
      {
        title: '样例 1',
        input: '2 3',
        output: '5',
      },
    ]);
  });

  it('splits multiple input and output groups inside one sample section into separate samples', () => {
    const result = parseProblemStatement({
      description: `Problem
+n numbers.

Sample
Input
1 2

Output
3

Input
5 7

Output
12`,
      public_tests: [],
      time_limit: 1000,
      space_limit: 256,
      _metadata: { name: 'Multi Pair Sample' },
    });

    expect(result.samples).toEqual([
      {
        title: 'Sample 1',
        input: '1 2',
        output: '3',
      },
      {
        title: 'Sample 2',
        input: '5 7',
        output: '12',
      },
    ]);
  });

  it('keeps multi-line textual output inside a sample block output without truncation', () => {
    const result = parseProblemStatement({
      description: `Problem
Describe the sample.

Sample
Input
1
Output
Alice wins.
Bob loses.`,
      public_tests: [],
      time_limit: 1000,
      space_limit: 256,
      _metadata: { name: 'Sample Multi Line Output' },
    });

    expect(result.samples).toEqual([
      {
        title: 'Sample 1',
        input: '1',
        output: 'Alice wins.\nBob loses.',
      },
    ]);
    expect(result.bodySections).toEqual([
      {
        heading: 'Problem',
        content: 'Describe the sample.',
      },
    ]);
  });

  it('preserves unsplittable Sample text in body sections instead of dropping it', () => {
    const result = parseProblemStatement({
      description: `Problem
Describe the transformation.

Sample
Input and output are shown inline: 1 2 3 -> 6.
This note should stay readable even without explicit marker lines.

Constraints
1 <= n <= 10`,
      public_tests: [],
      time_limit: 1000,
      space_limit: 256,
      _metadata: { name: 'Inline Sample Notes' },
    });

    expect(result.samples).toEqual([]);
    expect(result.bodySections).toEqual([
      {
        heading: 'Problem',
        content: 'Describe the transformation.',
      },
      {
        heading: 'Sample',
        content: 'Input and output are shown inline: 1 2 3 -> 6.\nThis note should stay readable even without explicit marker lines.',
      },
    ]);
  });

  it('parses inline Input and Output markers inside a sample section into a sample pair', () => {
    const result = parseProblemStatement({
      description: `Problem
Add the numbers.

Sample
Input: 2 3
Output: 5`,
      public_tests: [],
      time_limit: 1000,
      space_limit: 256,
      _metadata: { name: 'Inline English Sample' },
    });

    expect(result.samples).toEqual([
      {
        title: 'Sample 1',
        input: '2 3',
        output: '5',
      },
    ]);
    expect(result.bodySections).toEqual([
      {
        heading: 'Problem',
        content: 'Add the numbers.',
      },
    ]);
  });

  it('parses inline 输入 and 输出 markers inside a Chinese sample section into a sample pair', () => {
    const result = parseProblemStatement({
      description: `题目描述
计算两个数字之和。

样例1
输入：2 3
输出：5`,
      public_tests: [],
      time_limit: 1000,
      space_limit: 256,
      _metadata: { name: '中文行内样例' },
    });

    expect(result.samples).toEqual([
      {
        title: '样例 1',
        input: '2 3',
        output: '5',
      },
    ]);
    expect(result.bodySections).toEqual([
      {
        heading: '题目描述',
        content: '计算两个数字之和。',
      },
    ]);
  });

  it('parses exact Input Format and Output Format headings into the top-level format fields', () => {
    const result = parseProblemStatement({
      description: `Problem
Compute the answer.

Input Format
Read one integer n.

Output Format
Print one integer.`,
      public_tests: [],
      time_limit: 1000,
      space_limit: 256,
      _metadata: { name: 'Format Headings' },
    });

    expect(result.inputFormat).toBe('Read one integer n.');
    expect(result.outputFormat).toBe('Print one integer.');
  });

  it('parses a Chinese 复杂度 heading into the top-level complexity field', () => {
    const result = parseProblemStatement({
      description: `题目描述
计算答案。

复杂度
时间复杂度 O(n)，空间复杂度 O(1)。`,
      public_tests: [],
      time_limit: 1000,
      space_limit: 256,
      _metadata: { name: 'Chinese Complexity Heading' },
    });

    expect(result.complexity).toBe('时间复杂度 O(n)，空间复杂度 O(1)。');
  });
});
