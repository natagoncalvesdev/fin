// Service worker do Fin: existe para o Chrome tratar o app como instalável.
// Não guarda nada em cache — toda requisição continua indo à rede como antes.
// Só intercepta navegações (abrir páginas) para mostrar um aviso quando não
// há internet; API, scripts, estilos e imagens passam direto pelo navegador.

const PAGINA_OFFLINE = `<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="theme-color" content="#FFFFFF">
<title>Fin</title>
<style>
  body { margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center;
         background: #F7F8FA; color: #0f172a; font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
  main { text-align: center; padding: 24px; max-width: 320px; }
  h1 { font-size: 18px; margin: 0 0 8px; }
  p { font-size: 14px; color: #475569; margin: 0 0 20px; }
  button { font-family: inherit; font-size: 14px; font-weight: 600; padding: 10px 18px; border-radius: 10px; border: 0; background: #2563EB; color: #fff; }
</style>
</head>
<body>
<main>
  <h1>Sem conexão</h1>
  <p>O Fin precisa de internet para carregar seus dados. Verifique a conexão e tente novamente.</p>
  <button onclick="location.reload()">Tentar novamente</button>
</main>
</body>
</html>`;

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));

self.addEventListener('fetch', (event) => {
  if (event.request.mode !== 'navigate') return;
  event.respondWith(
    fetch(event.request).catch(() => new Response(PAGINA_OFFLINE, {
      status: 503,
      headers: { 'Content-Type': 'text/html; charset=utf-8' },
    })),
  );
});
