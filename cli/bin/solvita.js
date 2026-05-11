#!/usr/bin/env node
// This file is the compiled CLI entry point.
// After `npm run build`, it is replaced by the transpiled dist/index.js.
// During development, use: node --loader ts-node/esm src/index.tsx
import('../dist/index.js').catch((err) => {
  console.error('solvita: failed to load CLI bundle', err.message);
  process.exit(1);
});
