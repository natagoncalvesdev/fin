// Sidebar desktop + logo (mobile usa barra inferior via mobile-nav.js)
const SIDEBAR_LOGO = 'img/logo%20sem%20escrita.png';

function carregarSidebar() {
  const paginaAtual = (window.location.pathname.split('/').pop() || 'index.html').toLowerCase();

  const itens = [
    { href: 'index.html', label: 'Home', paginas: ['index.html'] },
    { href: 'financeiro.html', label: 'Financeiro', paginas: ['financeiro.html'] },
    { href: 'relatorio.html', label: 'Relatório', paginas: ['relatorio.html'] },
    { href: 'veiculos.html', label: 'Veículos', paginas: ['veiculos.html'] },
    { href: 'configuracoes.html', label: 'Configurações', paginas: ['configuracoes.html', 'config.html'] },
  ];

  const linksHTML = itens.map((item) => {
    const ativo = item.paginas.includes(paginaAtual) ? ' active' : '';
    return `<a href="${item.href}" class="btn-sidebar${ativo}">${item.label}</a>`;
  }).join('\n        ');

  const sidebarHTML = `
    <aside class="sidebar" aria-label="Menu principal">
      <a href="index.html" class="sidebar-brand" aria-label="Início">
        <img src="${SIDEBAR_LOGO}" alt="Controle" class="sidebar-logo" />
      </a>

      <nav class="desktop-nav" aria-label="Navegação">
        ${linksHTML}
      </nav>
    </aside>
  `;

  const existente = document.querySelector('.sidebar');
  if (existente) existente.remove();

  document.body.insertAdjacentHTML('afterbegin', sidebarHTML);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', carregarSidebar);
} else {
  carregarSidebar();
}
