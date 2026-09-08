// Sidebar desktop (fixa à esquerda) + drawer mobile (desliza da direita)
const SIDEBAR_LOGO = 'img/logo%20sem%20escrita.png';

const SIDEBAR_ICONS = {
  home: '<path d="M4 11.5 12 4l8 7.5"/><path d="M6 10v9a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1v-9"/><path d="M9.5 20v-5.5a1 1 0 0 1 1-1h3a1 1 0 0 1 1 1V20"/>',
  resumo: '<path d="M3 12h4l2.5 7L14 5l2.5 7H21"/>',
  contas: '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/>',
  cartoes: '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20"/>',
  reservas: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/>',
  veiculos: '<path d="M7 17h.01M17 17h.01M5 11l1.5-4h11L19 11M5 11h14v6H5z"/>',
  saude: '<path d="M3 12h4l2-5 4 12 2-5h6"/>',
  relatorios: '<path d="M4 19V5M4 19h16M8 17V11M12 17V7M16 17v-4"/>',
  config: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82A1.65 1.65 0 0 0 3 13.09H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
};

function carregarSidebar() {
  const paginaAtual = (window.location.pathname.split('/').pop() || 'index.html').toLowerCase();

  const itens = [
    { href: 'index.html', label: 'Home', icon: 'home', ativo: paginaAtual === 'index.html' },
    { href: 'contas.html', label: 'Contas', icon: 'contas', ativo: paginaAtual === 'contas.html' },
    { href: 'cartoes.html', label: 'Cartões', icon: 'cartoes', ativo: paginaAtual === 'cartoes.html' },
    { href: 'reservados.html', label: 'Reservas', icon: 'reservas', ativo: paginaAtual === 'reservados.html' },
    { href: 'veiculos.html', label: 'Veículos', icon: 'veiculos', ativo: paginaAtual === 'veiculos.html' },
    { href: 'saude.html', label: 'Saúde', icon: 'saude', ativo: paginaAtual === 'saude.html' },
    { href: 'relatorio.html', label: 'Relatórios', icon: 'relatorios', ativo: paginaAtual === 'relatorio.html' },
    { href: 'configuracoes.html', label: 'Configurações', icon: 'config', ativo: paginaAtual === 'configuracoes.html' || paginaAtual === 'config.html' },
  ];

  const linksHTML = itens.map((item) => {
    const ativo = item.ativo ? ' active' : '';
    const icone = SIDEBAR_ICONS[item.icon] || '';
    return `<a href="${item.href}" class="btn-sidebar${ativo}" data-nav-fn="${item.nav || ''}"><span class="btn-sidebar-icon" aria-hidden="true"><svg viewBox="0 0 24 24">${icone}</svg></span><span>${item.label}</span></a>`;
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
