// Sidebar desktop (fixa à esquerda) + drawer mobile (desliza da direita)
const SIDEBAR_LOGO = 'img/logo%20sem%20escrita.png';

function carregarSidebar() {
  const paginaAtual = (window.location.pathname.split('/').pop() || 'index.html').toLowerCase();
  const tabAtual = new URLSearchParams(window.location.search).get('tab') || 'mes';

  const itens = [
    { href: 'index.html', label: 'Home', ativo: paginaAtual === 'index.html' },
    { href: 'financeiro.html?tab=contas', label: 'Contas', nav: 'irContas', ativo: paginaAtual === 'financeiro.html' && tabAtual === 'contas' },
    { href: 'financeiro.html?tab=reservados', label: 'Reservas', nav: 'irReservas', ativo: paginaAtual === 'financeiro.html' && tabAtual === 'reservados' },
    { href: 'veiculos.html', label: 'Veículos', ativo: paginaAtual === 'veiculos.html' },
    { href: 'relatorio.html', label: 'Relatórios', ativo: paginaAtual === 'relatorio.html' },
    { href: 'configuracoes.html', label: 'Configurações', ativo: paginaAtual === 'configuracoes.html' || paginaAtual === 'config.html' },
  ];

  const linksHTML = itens.map((item) => {
    const ativo = item.ativo ? ' active' : '';
    return `<a href="${item.href}" class="btn-sidebar${ativo}" data-nav-fn="${item.nav || ''}">${item.label}</a>`;
  }).join('\n        ');

  const sidebarHTML = `
    <aside class="sidebar" id="mainSidebar" aria-label="Menu principal">
      <div class="sidebar-header">
        <a href="index.html" class="sidebar-brand" aria-label="Início">
          <img src="${SIDEBAR_LOGO}" alt="Controle" class="sidebar-logo" />
        </a>
        <button type="button" class="sidebar-close mobile-only" aria-label="Fechar menu">&times;</button>
      </div>

      <nav class="desktop-nav" aria-label="Navegação">
        ${linksHTML}
      </nav>

      <button type="button" class="btn-sidebar-logout mobile-only" id="sidebarLogout">Sair</button>
    </aside>
    <div class="sidebar-backdrop mobile-only" id="sidebarBackdrop" aria-hidden="true"></div>
  `;

  const existente = document.querySelector('.sidebar');
  if (existente) existente.remove();
  document.getElementById('sidebarBackdrop')?.remove();

  document.body.insertAdjacentHTML('afterbegin', sidebarHTML);

  const sidebar = document.getElementById('mainSidebar');
  const backdrop = document.getElementById('sidebarBackdrop');

  const abrirDrawer = () => {
    document.body.classList.add('mobile-drawer-open');
    document.getElementById('mobileMenuToggle')?.setAttribute('aria-expanded', 'true');
  };

  const fecharDrawer = () => {
    document.body.classList.remove('mobile-drawer-open');
    document.getElementById('mobileMenuToggle')?.setAttribute('aria-expanded', 'false');
  };

  const toggleDrawer = () => {
    if (document.body.classList.contains('mobile-drawer-open')) fecharDrawer();
    else abrirDrawer();
  };

  backdrop?.addEventListener('click', fecharDrawer);
  sidebar.querySelector('.sidebar-close')?.addEventListener('click', fecharDrawer);
  sidebar.querySelectorAll('[data-nav-fn]').forEach((link) => {
    link.addEventListener('click', (e) => {
      fecharDrawer();
      const navFn = link.getAttribute('data-nav-fn');
      if (navFn && window.finMobileNav?.[navFn]) {
        e.preventDefault();
        window.finMobileNav[navFn]();
      }
    });
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') fecharDrawer();
  });

  sidebar.querySelector('#sidebarLogout')?.addEventListener('click', () => {
    fecharDrawer();
    if (window.firebase?.auth) {
      firebase.auth().signOut().then(() => window.location.href = 'login.html');
    } else {
      window.location.href = 'login.html';
    }
  });

  window.finSidebar = { abrirDrawer, fecharDrawer, toggleDrawer };
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', carregarSidebar);
} else {
  carregarSidebar();
}
