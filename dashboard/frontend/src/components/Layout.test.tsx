import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import Layout from './Layout';

describe('Layout', () => {
  it('marks the right rail as the prominent native scroll container', () => {
    const { container } = render(
      <Layout
        header={<div>Header</div>}
        main={<div>Main</div>}
        sidebar={<div>Sidebar</div>}
        footer={<div>Footer</div>}
      />,
    );

    const sidebar = container.querySelector(
      'aside.layout__sidebar.layout__sidebar--prominent-scrollbar',
    );

    expect(sidebar).not.toBeNull();
  });
});
