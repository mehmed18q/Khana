/* Heading navigation owns and replaces its observer whenever the view changes. */
(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  function create({ contentRoot, scroller }) {
    let observer;
    function renderOutline(doc) {
      observer?.disconnect();
      $('outline').replaceChildren();
      const headings =
        doc?.api && !doc.apiSource
          ? doc.api.operations.map((op) => ({
              id: op.id,
              title: `${op.method.toUpperCase()} ${op.path}`,
              level: 2,
            }))
          : doc?.headings || [];
      if (!headings.length) {
        const note = document.createElement('div');
        note.className = 'outline-empty';
        note.textContent = 'No headings in this document.';
        $('outline').append(note);
        return;
      }
      for (const heading of headings) {
        const button = document.createElement('button');
        button.textContent = heading.title;
        button.dir = 'auto';
        button.dataset.target = heading.id;
        if (heading.level > 2) button.classList.add('nested');
        button.onclick = () => {
          contentRoot()
            .querySelector(`[id="${CSS.escape(heading.id)}"]`)
            ?.scrollIntoView({ behavior: 'smooth', block: 'start' });
          setActiveHeading(heading.id);
        };
        $('outline').append(button);
      }
      observer = new IntersectionObserver(
        (entries) => {
          const visible = entries.filter((entry) => entry.isIntersecting);
          if (visible.length) setActiveHeading(visible[0].target.id);
        },
        { root: scroller, rootMargin: '0px 0px -65% 0px', threshold: 0 }
      );
      contentRoot()
        .querySelectorAll('h1,h2,h3,h4,h5,h6,[data-api-operation]')
        .forEach((heading) => observer.observe(heading));
      setActiveHeading(headings[0].id);
    }

    function setActiveHeading(id) {
      $('outline')
        .querySelectorAll('button')
        .forEach((button) => {
          const selected = button.dataset.target === id;
          button.classList.toggle('active', selected);
          button.setAttribute('aria-current', selected ? 'location' : 'false');
        });
    }

    return { render: renderOutline };
  }
  window.ReaderOutline = { create };
})();
