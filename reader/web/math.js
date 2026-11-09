/* Formula sources are parsed before Markdown and rendered entirely offline. */
(() => {
  'use strict';
  function mount(root) {
    root.querySelectorAll('.math-expression').forEach((element) => {
      if (element.dataset.mathSource !== undefined) return;
      const source = element.textContent;
      element.dataset.mathSource = source;
      element.dir = 'ltr';
      try {
        const rendered = document.createElement('span');
        rendered.className = 'math-render';
        katex.render(source, rendered, {
          displayMode: element.classList.contains('math-display'),
          output: 'htmlAndMathml',
          throwOnError: true,
          trust: false,
          strict: 'ignore',
          maxExpand: 1000,
          maxSize: 20,
        });
        element.replaceChildren(rendered);
      } catch (error) {
        // Keep an invalid/incomplete expression readable during live editing.
        element.textContent = source;
        element.classList.add('math-error');
        element.title = `Could not render this formula: ${error.message}`;
      }
    });
  }
  window.ReaderMath = { mount };
})();
