/* Source transformations shared by toolbar buttons and keyboard shortcuts. */
(() => {
  'use strict';
  const escapeHtml = (text) =>
    text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const edit = (start, end, text, innerStart = 0, innerEnd = text.length) => ({
    start,
    end,
    text,
    selectionStart: start + innerStart,
    selectionEnd: start + innerEnd,
  });

  function wrap(source, start, end, before, after, placeholder, escapeContent = false) {
    let selected = source.slice(start, end);
    const singleStar = before === '*';
    const openingStars = selected.match(/^\*+/)?.[0].length || 0;
    const closingStars = selected.match(/\*+$/)?.[0].length || 0;
    const fullWrapper =
      selected.startsWith(before) &&
      selected.endsWith(after) &&
      selected.length >= before.length + after.length;
    if (fullWrapper && (!singleStar || (openingStars % 2 === 1 && closingStars % 2 === 1))) {
      return edit(start, end, selected.slice(before.length, -after.length));
    }
    const surrounded =
      source.slice(start - before.length, start) === before &&
      source.slice(end, end + after.length) === after;
    const leftStars = source.slice(0, start).match(/\*+$/)?.[0].length || 0;
    const rightStars = source.slice(end).match(/^\*+/)?.[0].length || 0;
    if (surrounded && (!singleStar || (leftStars % 2 === 1 && rightStars % 2 === 1))) {
      return edit(start - before.length, end + after.length, selected);
    }
    if (selected) {
      const leading = selected.match(/^\s*/)[0].length;
      const trailing = selected.match(/\s*$/)[0].length;
      if (leading + trailing < selected.length) {
        start += leading;
        end -= trailing;
        selected = source.slice(start, end);
      }
    }
    const content = selected || placeholder;
    const rendered = escapeContent ? escapeHtml(content) : content;
    return edit(
      start,
      end,
      before + rendered + after,
      before.length,
      before.length + rendered.length
    );
  }

  function lineSelection(source, start, end) {
    const first = source.lastIndexOf('\n', Math.max(0, start - 1)) + 1;
    const lastCharacter = end > start && source[end - 1] === '\n' ? end - 1 : end;
    const newline = source.indexOf('\n', lastCharacter);
    const last = newline === -1 ? source.length : newline;
    return {
      start: start === 0 ? 0 : first,
      end: last,
      text: source.slice(start === 0 ? 0 : first, last),
    };
  }

  function block(
    source,
    start,
    end,
    before,
    after,
    placeholder,
    escapeContent = false,
    contentOverride = null
  ) {
    const content = contentOverride ?? (source.slice(start, end) || placeholder);
    const leading =
      start && !source.slice(0, start).endsWith('\n\n')
        ? source[start - 1] === '\n'
          ? '\n'
          : '\n\n'
        : '';
    const trailing =
      end < source.length && !source.slice(end).startsWith('\n\n')
        ? source[end] === '\n'
          ? '\n'
          : '\n\n'
        : '';
    const rendered = escapeContent ? escapeHtml(content) : content;
    return edit(
      start,
      end,
      leading + before + rendered + after + trailing,
      leading.length + before.length,
      leading.length + before.length + rendered.length
    );
  }

  function transform(source, start, end, action, format = 'Markdown') {
    const html = format === 'HTML';
    const inline = {
      bold: html ? ['<strong>', '</strong>', 'bold text'] : ['**', '**', 'bold text'],
      italic: html ? ['<em>', '</em>', 'italic text'] : ['*', '*', 'italic text'],
      strike: html ? ['<s>', '</s>', 'strikethrough text'] : ['~~', '~~', 'strikethrough text'],
    };
    if (inline[action]) return wrap(source, start, end, ...inline[action]);
    if (action === 'code') {
      if (html) return wrap(source, start, end, '<code>', '</code>', 'code', true);
      const selected = source.slice(start, end);
      const existing = selected.match(/^(`+)([\s\S]+?)\1$/);
      if (existing)
        return edit(
          start,
          end,
          existing[2].startsWith(' ') && existing[2].endsWith(' ')
            ? existing[2].slice(1, -1)
            : existing[2]
        );
      const longest = Math.max(0, ...[...selected.matchAll(/`+/g)].map((match) => match[0].length));
      const delimiter = '`'.repeat(longest + 1);
      const pad = selected.startsWith('`') || selected.endsWith('`') ? ' ' : '';
      return wrap(source, start, end, delimiter + pad, pad + delimiter, 'code');
    }
    if (action === 'code-block') {
      if (html) return block(source, start, end, '<pre><code>', '</code></pre>', 'code', true);
      const longest = Math.max(
        2,
        ...[...source.slice(start, end).matchAll(/`+/g)].map((match) => match[0].length)
      );
      const fence = '`'.repeat(longest + 1);
      return block(source, start, end, fence + '\n', '\n' + fence, 'code');
    }
    if (action === 'rule') return block(source, start, end, html ? '<hr>\n' : '---\n', '', '');
    const heading = action.match(/^h([1-6])$/)?.[1];
    if (html) {
      if (heading) return wrap(source, start, end, `<h${heading}>`, `</h${heading}>`, 'Heading');
      if (action === 'quote')
        return wrap(source, start, end, '<blockquote>', '</blockquote>', 'Quote');
      if (action === 'bullet' || action === 'numbered') {
        const tag = action === 'bullet' ? 'ul' : 'ol';
        const lines = (source.slice(start, end) || 'List item').split('\n');
        const items = lines.map((line) => `  <li>${line}</li>`).join('\n');
        return block(source, start, end, `<${tag}>\n`, `\n</${tag}>`, items, false, items);
      }
      return null;
    }
    const selected = lineSelection(source, start, end);
    const lines = selected.text.split('\n');
    let pattern, prefix;
    if (heading) {
      pattern = new RegExp(`^ {0,3}#{${heading}} `);
      prefix = '#'.repeat(Number(heading)) + ' ';
    } else if (action === 'quote') {
      pattern = /^> ?/;
      prefix = '> ';
    } else if (action === 'bullet') {
      pattern = /^[-+*] /;
      prefix = '- ';
    } else if (action === 'numbered') {
      pattern = /^\d+[.)] /;
      prefix = '';
    } else return null;
    const nonempty = lines.filter((line) => line.trim());
    const remove = nonempty.length > 0 && nonempty.every((line) => pattern.test(line));
    const transformed = lines
      .map((line, index) => {
        if (remove) return line.replace(pattern, '');
        if (!line.trim() && lines.length > 1) return line;
        const bare = heading
          ? line.replace(/^ {0,3}#{1,6}\s+/, '')
          : action === 'bullet' || action === 'numbered'
            ? line.replace(/^(?:[-+*]|\d+[.)]) /, '')
            : line;
        return (
          (action === 'numbered' ? `${index + 1}. ` : prefix) +
          (bare || (heading ? 'Heading' : action === 'quote' ? 'Quote' : 'List item'))
        );
      })
      .join('\n');
    return edit(selected.start, selected.end, transformed);
  }

  function link(source, start, end, label, destination, format = 'Markdown') {
    const url = destination.trim();
    // Reject ASCII control characters as well as spaces in link destinations.
    // eslint-disable-next-line no-control-regex
    if (!url || /[\u0000-\u0020\u007f]/.test(url))
      throw new Error('Enter a URL or relative path without spaces. Use %20 for spaces.');
    const scheme = url.match(/^([a-z][a-z0-9+.-]*):/i)?.[1].toLowerCase();
    if (scheme && !['http', 'https', 'mailto'].includes(scheme))
      throw new Error('Use an https, http, mailto, anchor, or relative document link.');
    const text = label || source.slice(start, end) || url;
    if (format === 'HTML')
      return edit(start, end, `<a href="${escapeHtml(url)}">${escapeHtml(text)}</a>`);
    const safeLabel = text.replace(/([\\[\]])/g, '\\$1').replace(/\n/g, ' ');
    const safeUrl = url.replace(/</g, '%3C').replace(/>/g, '%3E').replace(/\\/g, '%5C');
    return edit(start, end, `[${safeLabel}](<${safeUrl}>)`);
  }

  const api = { transform, link };
  if (typeof module !== 'undefined') module.exports = api;
  if (typeof window !== 'undefined') window.ReaderFormatting = api;
})();
