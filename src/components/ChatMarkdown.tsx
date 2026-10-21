import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

type ChatMarkdownProps = { children: string };

const isTableDivider = (line: string) =>
  /^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)*\|?\s*$/.test(line);

const isPipeRow = (line: string) => line.includes('|');

/** Repairs common spacing omissions from generated Markdown without changing its wording. */
function normalizeChatMarkdown(markdown: string): string {
  const lines = markdown.replace(/\r\n?/g, '\n').split('\n');
  const joined: string[] = [];

  for (let i = 0; i < lines.length; i += 1) {
    const number = lines[i].match(/^(\s*)(\d+)\.\s*$/);
    if (number) {
      let next = i + 1;
      while (next < lines.length && !lines[next].trim()) next += 1;
      if (next < lines.length && /^\s*\*\*.+\*\*\s*$/.test(lines[next])) {
        joined.push(`${number[1]}${number[2]}. ${lines[next].trim()}`);
        let item = next + 1;
        while (item < lines.length && !lines[item].trim()) item += 1;
        if (item < lines.length && /^\s*[-*+]\s+/.test(lines[item])) {
          joined.push('');
          while (item < lines.length) {
            if (/^\s*\d+\.\s*$/.test(lines[item])) break;
            if (!lines[item].trim()) {
              let following = item + 1;
              while (following < lines.length && !lines[following].trim()) following += 1;
              if (following < lines.length && /^\s*[-*+]\s+/.test(lines[following])) {
                joined.push('');
                item += 1;
                continue;
              }
              break;
            }
            if (!/^\s*[-*+]\s+/.test(lines[item])) break;
            joined.push(`   ${lines[item].trim()}`);
            item += 1;
          }
          i = item - 1;
        } else {
          i = next;
        }
        continue;
      }
    }
    joined.push(lines[i]);
  }

  const normalized: string[] = [];
  for (let i = 0; i < joined.length;) {
    if (i + 1 < joined.length && isPipeRow(joined[i]) && isTableDivider(joined[i + 1])) {
      if (normalized.length && normalized[normalized.length - 1].trim()) normalized.push('');
      while (i < joined.length && isPipeRow(joined[i])) normalized.push(joined[i++]);
      if (i < joined.length && joined[i].trim()) normalized.push('');
      continue;
    }
    normalized.push(joined[i]);
    i += 1;
  }

  return normalized.join('\n');
}

export function ChatMarkdown({ children }: ChatMarkdownProps) {
  return <div className="chat-markdown"><ReactMarkdown remarkPlugins={[remarkGfm]}>{normalizeChatMarkdown(children)}</ReactMarkdown></div>;
}
