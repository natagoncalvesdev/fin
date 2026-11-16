(function () {
  if (!('serviceWorker' in navigator)) return;
  window.addEventListener('load', function () {
    navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(function (erro) {
      console.warn('Service worker não registrado:', erro);
    });
  });
})();
