/**
 * Proteção contra cliques duplos em ações que gravam no banco.
 * Carregado antes do fin-sdk.js para ficar disponível em onclick inline.
 */
(function (global) {
  'use strict';

  const finBusyLocks = new Set();

  async function finRunOnce(trigger, action) {
    let btn = null;
    let lockKey = null;

    if (trigger && typeof trigger === 'object' && trigger.currentTarget instanceof HTMLElement) {
      btn = trigger.currentTarget;
    } else if (trigger instanceof HTMLElement) {
      btn = trigger;
    } else if (typeof trigger === 'string') {
      lockKey = trigger;
    }

    if (btn) {
      if (btn.disabled || btn.dataset.finBusy === '1') return;
      btn.disabled = true;
      btn.dataset.finBusy = '1';
      btn.setAttribute('aria-busy', 'true');
    } else if (lockKey) {
      if (finBusyLocks.has(lockKey)) return;
      finBusyLocks.add(lockKey);
    }

    try {
      return await action();
    } finally {
      if (btn) {
        btn.disabled = false;
        delete btn.dataset.finBusy;
        btn.removeAttribute('aria-busy');
      } else if (lockKey) {
        finBusyLocks.delete(lockKey);
      }
    }
  }

  global.finRunOnce = finRunOnce;
})(typeof window !== 'undefined' ? window : globalThis);
