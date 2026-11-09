/* Named collections group paths without moving their files on disk. */
(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  function create({ native, menu, entry, toast, icon }) {
    let records = [],
      context = null,
      pending = false;
    const unfiledCollapsed = { files: false, library: false };
    const dialog = $('category-dialog'),
      name = $('category-name'),
      destination = $('category-destination'),
      error = $('category-error');
    function call(method, args, done = () => {}) {
      if (!native()) return;
      native()[method](...args, (message) => {
        if (message) toast(message, true);
        done(message);
      });
    }
    function show(mode, values = {}) {
      if (pending) return;
      menu.close();
      context = { mode, ...values };
      const move = mode === 'move',
        renameFile = mode === 'rename-file';
      $('category-dialog-title').textContent = move
        ? `Move ${values.paths.length} file${values.paths.length === 1 ? '' : 's'} to category`
        : renameFile
          ? 'Rename file'
          : mode === 'rename'
            ? 'Rename category'
            : 'New category';
      $('category-name-fields').hidden = move;
      $('category-destination-fields').hidden = !move;
      $('category-name-label').textContent = renameFile ? 'File name' : 'Category name';
      $('category-dialog-help').textContent = renameFile
        ? 'Rename this file in its current folder.'
        : 'Group documents from any folder. Their original locations stay the same.';
      $('category-submit').textContent = move ? 'Move' : 'Save';
      name.required = !move;
      name.maxLength = renameFile ? 255 : 80;
      name.value = values.name || '';
      destination.replaceChildren(
        new Option('Uncategorized', ''),
        ...records.map((c) => new Option(c.name, c.id))
      );
      destination.value =
        values.paths?.length === 1 ? entry(values.paths[0])?.categoryId || '' : '';
      error.hidden = true;
      if (!dialog.open) dialog.showModal();
      (move ? destination : name).focus();
      if (!move) name.select();
    }
    $('category-form').onsubmit = (event) => {
      event.preventDefault();
      if (pending || !context || !native()) return;
      pending = true;
      $('category-submit').disabled = true;
      const current = context;
      const operation = {
        create: ['createCategory', [name.value, JSON.stringify(current.paths || [])]],
        rename: ['renameCategory', [current.id, name.value]],
        move: ['assignDocumentCategories', [JSON.stringify(current.paths), destination.value]],
        'rename-file': ['renameFile', [current.path, name.value]],
      }[current.mode];
      native()[operation[0]](...operation[1], (message) => {
        pending = false;
        $('category-submit').disabled = false;
        if (context !== current) return;
        error.textContent = message;
        error.hidden = !message;
        if (!message) dialog.close();
      });
    };
    $('category-cancel').onclick = () => dialog.close();
    dialog.addEventListener('close', () => {
      if (!dialog.open) context = null;
    });
    $('category-new-destination').onclick = () => show('create', { paths: context.paths });
    for (const scope of ['files', 'library'])
      $(scope + '-new-category').onclick = () => show('create');

    function categoryMenu(event, category, anchor, keyboard = false) {
      const index = records.findIndex((c) => c.id === category.id),
        previous = records[index - 1],
        next = records[index + 1];
      menu.open(
        event,
        anchor,
        `Actions for ${category.name}`,
        [
          { id: 'category-new', label: 'New category', run: () => show('create') },
          {
            id: 'category-rename',
            label: 'Rename category',
            disabled: !category.id,
            run: () => show('rename', category),
          },
          null,
          {
            id: 'category-up',
            label: 'Move category higher',
            disabled: !category.id || !previous,
            run: () => call('moveCategory', [category.id, previous.id, true]),
          },
          {
            id: 'category-down',
            label: 'Move category lower',
            disabled: !category.id || !next,
            run: () => call('moveCategory', [category.id, next.id, false]),
          },
          null,
          {
            id: 'category-delete',
            label: 'Delete category',
            disabled: !category.id,
            title: 'Files return to Uncategorized; documents and notes are kept',
            run: () => call('deleteCategory', [category.id]),
          },
        ],
        keyboard
      );
    }
    function render(container, items, categoryOf, makeRow, scope) {
      container.replaceChildren();
      if (!records.length) {
        items.forEach((item) => container.append(makeRow(item)));
        return;
      }
      const groups = records.map((category) => ({ ...category, items: [] })),
        unfiled = {
          id: '',
          name: 'Uncategorized',
          items: [],
          filesCollapsed: unfiledCollapsed.files,
          libraryCollapsed: unfiledCollapsed.library,
        },
        byId = new Map(groups.map((group) => [group.id, group]));
      for (const item of items) (byId.get(categoryOf(item)) || unfiled).items.push(item);
      // The default category is also a drop target when it currently has no files.
      groups.push(unfiled);
      for (const group of groups) {
        const section = document.createElement('section');
        section.className = 'file-category';
        section.dataset.categoryId = group.id;
        const heading = document.createElement('div');
        heading.className = 'category-heading';
        const toggle = document.createElement('button');
        toggle.type = 'button';
        toggle.className = 'category-toggle';
        toggle.innerHTML = icon('chevron') + icon('folder');
        const label = document.createElement('span');
        label.className = 'category-name';
        label.dir = 'auto';
        label.textContent = group.name;
        const count = document.createElement('span');
        count.className = 'category-count';
        count.textContent = group.items.length;
        toggle.append(label, count);
        toggle.title = group.name;
        toggle.setAttribute('aria-expanded', String(!group[scope + 'Collapsed']));
        const body = document.createElement('div');
        body.className = 'category-files';
        body.id = `${scope}-category-${group.id || 'unfiled'}`;
        body.hidden = Boolean(group[scope + 'Collapsed']);
        toggle.setAttribute('aria-controls', body.id);
        toggle.onclick = () => {
          if (group.id) call('collapseCategory', [group.id, scope, !body.hidden]);
          else {
            body.hidden = !body.hidden;
            unfiledCollapsed[scope] = body.hidden;
            toggle.setAttribute('aria-expanded', String(!body.hidden));
          }
        };
        const options = document.createElement('button');
        options.type = 'button';
        options.className = 'category-options';
        options.textContent = '⋯';
        options.title = `Category actions: ${group.name}`;
        options.setAttribute('aria-label', options.title);
        options.setAttribute('aria-haspopup', 'menu');
        options.onclick = (event) => categoryMenu(event, group, options, true);
        heading.addEventListener('contextmenu', (event) => categoryMenu(event, group, toggle));
        heading.addEventListener('keydown', (event) => {
          if (event.key === 'ContextMenu' || (event.shiftKey && event.key === 'F10'))
            categoryMenu(event, group, toggle, true);
        });
        heading.append(toggle, options);
        group.items.forEach((item) => body.append(makeRow(item)));
        if (!group.items.length) {
          const empty = document.createElement('div');
          empty.className = 'category-empty';
          empty.textContent =
            scope === 'files' ? 'No open files · Drop files here' : 'Drop files here';
          body.append(empty);
        }
        section.append(heading, body);
        container.append(section);
      }
    }
    return {
      render,
      receive(value, available) {
        records = value || [];
        for (const scope of ['files', 'library']) $(scope + '-new-category').disabled = !available;
      },
      choose: (paths) => show('move', { paths }),
      renameFile: (path, name) => show('rename-file', { path, name }),
      move(paths, identifier) {
        call('assignDocumentCategories', [JSON.stringify(paths), identifier]);
      },
    };
  }
  window.ReaderCategories = { create };
})();
