import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { ChatMarkdown } from './ChatMarkdown';

describe('ChatMarkdown', () => {
  it('renders headings, bold text, lists, and GFM tables as HTML instead of raw Markdown', () => {
    const markdown = [
      '## Suggested checks',
      '',
      'Try **these steps**:',
      '- Reconnect to Wi-Fi',
      '- Check another location',
      '',
      '| Check | Result |',
      '| --- | --- |',
      '| Signal | Weak |',
    ].join('\n');

    const html = renderToStaticMarkup(<ChatMarkdown>{markdown}</ChatMarkdown>);
    expect(html).toContain('<h2>Suggested checks</h2>');
    expect(html).toContain('<strong>these steps</strong>');
    expect(html).toContain('<ul>');
    expect(html).toContain('<table>');
    expect(html).toContain('<th>Check</th>');
    expect(html).not.toContain('| --- | --- |');
    expect(html).not.toContain('**these steps**');
  });

  it('renders embedded HTML as text rather than executable markup', () => {
    const html = renderToStaticMarkup(<ChatMarkdown>{'<img src=x onerror=alert(1) />'}</ChatMarkdown>);
    expect(html).not.toContain('<img');
    expect(html).toContain('&lt;img');
  });
});
