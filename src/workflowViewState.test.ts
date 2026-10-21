import { describe, expect, it } from 'vitest';
import { workflowViewState } from './workflowViewState';

describe('workflow view state', () => {
  it('shows loading before the first result arrives', () => {
    expect(workflowViewState(true, null, 0)).toBe('loading');
  });

  it('shows an error instead of an empty result after a failed request', () => {
    expect(workflowViewState(false, 'Request failed.', 0)).toBe('error');
  });

  it('shows the empty state only after a successful response with no runs', () => {
    expect(workflowViewState(false, null, 0)).toBe('empty');
  });

  it('shows run content when runs have loaded', () => {
    expect(workflowViewState(false, null, 2)).toBe('content');
  });
});
