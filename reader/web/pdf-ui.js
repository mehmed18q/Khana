(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  function create({ article, scroller, current, native, toast, changed }) {
    const pages = ReaderPDFPages.create({
      article,
      scroller,
      current,
      native,
      onError: (error) => toast(error, true),
    });
    let context;
    function mount() {
      pages.mount();
      if (current()?.format !== 'PDF') return;
      article.querySelectorAll('.pdf-block').forEach((block) => {
        block.addEventListener('dblclick', () => edit(block));
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'pdf-edit';
        button.title = 'Edit PDF text';
        button.setAttribute('aria-label', 'Edit PDF text');
        button.dataset.label = 'Edit text';
        button.onclick = (event) => {
          event.stopPropagation();
          edit(block);
        };
        if (block.dataset.editable === 'true') block.append(button);
      });
    }
    function edit(block) {
      const doc = current();
      if (
        doc.previewPending ||
        block.dataset.editable !== 'true' ||
        document.querySelector('dialog[open]')
      )
        return;
      context = { id: doc.id, source: doc.source, block: block.dataset.pdfBlock };
      $('pdf-text-input').value = block.querySelector('.pdf-text').textContent;
      $('pdf-error').hidden = true;
      $('pdf-apply').disabled = false;
      $('pdf-dialog').showModal();
      $('pdf-text-input').focus();
    }
    $('pdf-cancel').onclick = () => $('pdf-dialog').close();
    $('pdf-form').onsubmit = (event) => {
      event.preventDefault();
      if (!context || context.id !== current()?.id || context.source !== current().source) return;
      const state = JSON.parse(context.source);
      state.edits[context.block] = $('pdf-text-input').value;
      const source = JSON.stringify(state),
        captured = context;
      $('pdf-apply').disabled = true;
      native()?.validatePdfEdit(current().id, source, (error) => {
        $('pdf-apply').disabled = false;
        if (context !== captured) return;
        if (error) {
          $('pdf-error').textContent = error;
          $('pdf-error').hidden = false;
          return;
        }
        changed(source);
        $('pdf-dialog').close();
        toast('PDF text updated. Save to keep your changes.');
      });
    };
    return { mount, receive: pages.receive, dispose: pages.dispose };
  }
  window.ReaderPDF = { create };
})();
