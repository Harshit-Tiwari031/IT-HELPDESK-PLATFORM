export type WorkflowViewState = 'loading' | 'error' | 'empty' | 'content';

export function workflowViewState(loading: boolean, error: string | null, runCount: number): WorkflowViewState {
  if (loading && runCount === 0) return 'loading';
  if (error) return 'error';
  if (runCount === 0) return 'empty';
  return 'content';
}
