/* Report slow browser tasks and failures without copying document contents. */
(() => {
  'use strict';
  function create(native) {
    let activity = 'startup',
      last = 0;
    const report = (kind, message, elapsed = 0) =>
      native()?.reportDiagnostic(kind, message, elapsed);
    for (const name of [
      'beforeinput',
      'input',
      'contextmenu',
      'copy',
      'cut',
      'paste',
      'keydown',
      'click',
    ])
      document.addEventListener(
        name,
        (event) => {
          activity = `${name}${event.inputType ? ':' + event.inputType : ''} ${event.target.id || event.target.className || event.target.tagName}`;
        },
        { capture: true, passive: true }
      );
    window.addEventListener('error', (event) =>
      report('error', `${event.message} ${event.filename}:${event.lineno}`)
    );
    window.addEventListener('unhandledrejection', (event) =>
      report('error', String(event.reason?.stack || event.reason))
    );
    if (PerformanceObserver.supportedEntryTypes.includes('longtask'))
      new PerformanceObserver((list) => {
        for (const entry of list.getEntries())
          if (entry.duration >= 100 && performance.now() - last >= 1000) {
            last = performance.now();
            report('slow-task', activity, entry.duration);
          }
      }).observe({ type: 'longtask', buffered: true });
  }
  window.ReaderDiagnostics = { create };
})();
