/**
 * Navegação mobile — barra inferior + gráfico do resumo do mês
 */
(function (global) {
  'use strict';

  const MOBILE_MAX = 768;
  const CHART_COLORS = ['#10B981', '#EF4444', '#3B82F6', '#F59E0B', '#8B5CF6', '#64748B'];
  const MESES = [
    'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
  ];

  const ICONS = {
    financeiro: '<svg viewBox="0 0 24 24"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>',
    relatorio: '<svg viewBox="0 0 24 24"><path d="M4 19V5M4 19h16M8 17V11M12 17V7M16 17v-4"/></svg>',
    veiculos: '<svg viewBox="0 0 24 24"><path d="M7 17h.01M17 17h.01M5 11l1.5-4h11L19 11M5 11h14v6H5z"/></svg>',
    config: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/></svg>'
  };

  let dashChartInstance = null;
  let lastChartPayload = null;
  let chartRenderPending = false;

  function painelMesVisivel() {
    const panel = document.getElementById('tabPanelMes');
    if (!panel) return true;
    return panel.classList.contains('active') && !panel.hidden;
  }

  function obterCategoriaNome(item) {
    const cat = (item?.categoria || item?.categoriaNome || '').trim();
    return cat || 'Sem categoria';
  }

  function isMobile() {
    return window.innerWidth <= MOBILE_MAX;
  }

  function paginaAtual() {
    return (window.location.pathname.split('/').pop() || 'index.html').toLowerCase();
  }

  function obterPeriodoSalvo() {
    if (paginaAtual() === 'financeiro.html' && typeof global.getPeriodoFinanceiroAtual === 'function') {
      const atual = global.getPeriodoFinanceiroAtual();
      if (atual?.mes && atual?.ano) return { mes: atual.mes, ano: String(atual.ano) };
    }
    try {
      const salvo = JSON.parse(sessionStorage.getItem('financeiroPeriodo') || '{}');
      if (salvo.mes && salvo.ano) return { mes: salvo.mes, ano: String(salvo.ano) };
    } catch (e) { /* ignore */ }
    const params = new URLSearchParams(window.location.search);
    const mesUrl = params.get('mes');
    const anoUrl = params.get('ano');
    if (mesUrl && anoUrl) return { mes: mesUrl, ano: anoUrl };
    const hoje = new Date();
    return { mes: MESES[hoje.getMonth()], ano: String(hoje.getFullYear()) };
  }

  function urlFinanceiro(tab) {
    const { mes, ano } = obterPeriodoSalvo();
    const params = new URLSearchParams();
    if (tab) params.set('tab', tab);
    params.set('mes', mes);
    params.set('ano', ano);
    return `financeiro.html?${params.toString()}`;
  }

  function detectarAbaAtiva() {
    const page = paginaAtual();
    if (page === 'index.html') return 'home';
    if (page === 'financeiro.html') return 'financeiro';
    if (page === 'relatorio.html') return 'relatorio';
    if (page === 'veiculos.html') return 'veiculos';
    if (page === 'configuracoes.html' || page === 'config.html') return 'config';
    return '';
  }

  function navegarPara(url) {
    window.location.assign(url);
  }

  function marcarNavegacaoFinanceiro() {
    try {
      sessionStorage.setItem('finNavPermitido', '1');
    } catch (e) { /* ignore */ }
  }

  function navegarParaFinanceiro(url) {
    marcarNavegacaoFinanceiro();
    navegarPara(url);
  }

  function irFinanceiroResumo() {
    navegarParaFinanceiro(urlFinanceiro('mes'));
  }

  function irHome() {
    navegarPara('index.html');
  }

  function irRelatorio() {
    navegarPara('relatorio.html');
  }

  function irVeiculos() {
    navegarPara('veiculos.html');
  }

  function irConfiguracoes() {
    navegarPara('configuracoes.html');
  }

  function vincularNavBottom(nav) {
    nav.querySelector('[data-nav="financeiro"]')?.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      irFinanceiroResumo();
    });
    nav.querySelector('[data-nav="relatorio"]')?.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      irRelatorio();
    });
    nav.querySelector('[data-nav="home"]')?.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      irHome();
    });
    nav.querySelector('[data-nav="veiculos"]')?.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      irVeiculos();
    });
    nav.querySelector('[data-nav="config"]')?.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      irConfiguracoes();
    });
  }

  function criarBottomNav() {
    const existente = document.getElementById('mobileBottomNav');
    if (existente) existente.remove();

    const ativa = detectarAbaAtiva();
    const nav = document.createElement('nav');
    nav.id = 'mobileBottomNav';
    nav.className = 'mobile-bottom-nav mobile-only';
    nav.setAttribute('aria-label', 'Navegação principal');
    nav.innerHTML = `
      <button type="button" class="mobile-nav-item ${ativa === 'financeiro' ? 'active' : ''}" data-nav="financeiro" aria-label="Financeiro">
        ${ICONS.financeiro}<span>Financeiro</span>
      </button>
      <button type="button" class="mobile-nav-item ${ativa === 'relatorio' ? 'active' : ''}" data-nav="relatorio" aria-label="Relatório">
        ${ICONS.relatorio}<span>Relatório</span>
      </button>
      <div class="mobile-nav-item--fab">
        <button type="button" class="mobile-nav-fab ${ativa === 'home' ? 'active' : ''}" data-nav="home" aria-label="Home">
          <img src="img/logo.png" alt="" class="mobile-nav-fab-logo" width="36" height="36" />
        </button>
      </div>
      <button type="button" class="mobile-nav-item ${ativa === 'veiculos' ? 'active' : ''}" data-nav="veiculos" aria-label="Veículos">
        ${ICONS.veiculos}<span>Veículos</span>
      </button>
      <button type="button" class="mobile-nav-item ${ativa === 'config' ? 'active' : ''}" data-nav="config" aria-label="Configurações">
        ${ICONS.config}<span>Config</span>
      </button>
    `;
    document.body.appendChild(nav);
    vincularNavBottom(nav);
    criarEspacadorNav();
  }

  function calcularClearanceNav() {
    const nav = document.getElementById('mobileBottomNav');
    if (!nav) return 136;

    const navRect = nav.getBoundingClientRect();
    const fab = nav.querySelector('.mobile-nav-fab');
    let overhang = 0;
    if (fab) {
      const fabRect = fab.getBoundingClientRect();
      overhang = Math.max(0, navRect.top - fabRect.top);
    }

    return Math.ceil(navRect.height + overhang + 16);
  }

  function criarEspacadorNav() {
    let spacer = document.getElementById('mobileNavSpacer');
    if (!spacer) {
      spacer = document.createElement('div');
      spacer.id = 'mobileNavSpacer';
      spacer.className = 'mobile-nav-spacer mobile-only';
      spacer.setAttribute('aria-hidden', 'true');
    }
    document.body.appendChild(spacer);
    atualizarEspacadorNav();
  }

  function atualizarEspacadorNav() {
    const spacer = document.getElementById('mobileNavSpacer');
    if (!spacer) return;

    const clearance = calcularClearanceNav();
    const clearancePx = `${clearance}px`;
    spacer.style.height = clearancePx;
    document.documentElement.style.setProperty('--mobile-bottom-clearance', clearancePx);
  }

  function aplicarShell() {
    const header = document.getElementById('mobileHeader');
    if (header) header.remove();

    if (!isMobile()) {
      document.body.classList.remove('mobile-shell');
      const nav = document.getElementById('mobileBottomNav');
      const spacer = document.getElementById('mobileNavSpacer');
      if (nav) nav.remove();
      if (spacer) spacer.remove();
      document.documentElement.style.removeProperty('--mobile-bottom-clearance');
      return;
    }
    document.body.classList.add('mobile-shell');
    criarBottomNav();
    requestAnimationFrame(atualizarEspacadorNav);
  }

  function formatarMoeda(valor) {
    return Number(valor || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
  }

  function agregarDespesasPorCategoria(data) {
    const mapa = {};
    const add = (item) => {
      const cat = obterCategoriaNome(item);
      const val = Number(item.valor || 0);
      if (val <= 0) return;
      mapa[cat] = (mapa[cat] || 0) + val;
    };
    (data?.contas || []).forEach(add);
    (data?.cartao || []).forEach(add);
    (data?.debito || []).forEach(add);
    return Object.entries(mapa).sort((a, b) => b[1] - a[1]);
  }

  function montarChart(canvas, labels, values, cores, total) {
    if (typeof Chart === 'undefined') return false;

    if (dashChartInstance) {
      dashChartInstance.destroy();
      dashChartInstance = null;
    }

    const ctx = canvas.getContext('2d');
    if (!ctx) return false;

    dashChartInstance = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels,
        datasets: [{
          data: values,
          backgroundColor: cores,
          borderWidth: 0,
          hoverOffset: 4
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        cutout: '68%',
        animation: { duration: 400 },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label(tooltipItem) {
                const val = tooltipItem.parsed || 0;
                const pct = total > 0 ? Math.round((val / total) * 100) : 0;
                return ` ${formatarMoeda(val)} (${pct}%)`;
              }
            }
          }
        }
      },
      plugins: [{
        id: 'centerText',
        beforeDraw(chart) {
          const { ctx: c, chartArea } = chart;
          if (!chartArea) return;
          c.save();
          c.font = 'bold 14px Montserrat, sans-serif';
          c.fillStyle = '#0F172A';
          c.textAlign = 'center';
          c.textBaseline = 'middle';
          c.fillText(
            formatarMoeda(total),
            (chartArea.left + chartArea.right) / 2,
            (chartArea.top + chartArea.bottom) / 2
          );
          c.restore();
        }
      }]
    });

    dashChartInstance.update();
    return true;
  }

  function renderizarChartAgora() {
    if (!lastChartPayload) return;

    const { data, totalContas } = lastChartPayload;
    const canvas = document.getElementById('dashChartCategorias');
    const legend = document.getElementById('dashChartLegend');
    const empty = document.getElementById('dashChartEmpty');
    const wrap = canvas?.closest('.dash-chart-canvas');
    if (!canvas || !legend) return;

    const categorias = agregarDespesasPorCategoria(data || {});
    const total = Number(totalContas || 0);

    if (!categorias.length || total <= 0) {
      if (dashChartInstance) {
        dashChartInstance.destroy();
        dashChartInstance = null;
      }
      canvas.style.display = 'none';
      if (wrap) wrap.style.display = 'none';
      legend.innerHTML = '';
      if (empty) empty.style.display = 'block';
      chartRenderPending = false;
      return;
    }

    if (empty) empty.style.display = 'none';
    if (wrap) wrap.style.display = 'block';
    canvas.style.display = 'block';

    const top = categorias.slice(0, 5);
    const outros = categorias.slice(5).reduce((s, [, v]) => s + v, 0);
    const labels = top.map(([n]) => n);
    const values = top.map(([, v]) => v);
    if (outros > 0) {
      labels.push('Outros');
      values.push(outros);
    }

    const cores = labels.map((_, i) => CHART_COLORS[i % CHART_COLORS.length]);

    legend.innerHTML = labels.map((nome, i) => {
      const pct = Math.round((values[i] / total) * 100);
      return `
        <div class="dash-legend-item">
          <span class="dash-legend-left">
            <span class="dash-legend-dot" style="background:${cores[i]}"></span>
            <span class="dash-legend-nome">${nome}</span>
          </span>
          <span class="dash-legend-values">
            <strong class="dash-legend-valor">${formatarMoeda(values[i])}</strong>
            <span class="dash-legend-pct">${pct}%</span>
          </span>
        </div>`;
    }).join('');

    if (!painelMesVisivel()) {
      chartRenderPending = true;
      return;
    }

    chartRenderPending = false;
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        montarChart(canvas, labels, values, cores, total);
      });
    });
  }

  function atualizarGraficoCategorias(data, totalContas) {
    lastChartPayload = { data, totalContas };
    renderizarChartAgora();
  }

  function refreshChartCategorias() {
    if (lastChartPayload) renderizarChartAgora();
  }

  function init() {
    aplicarShell();
    window.addEventListener('resize', () => {
      aplicarShell();
      atualizarEspacadorNav();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  global.finMobileNav = {
    isMobile,
    aplicarShell,
    atualizarGraficoCategorias,
    refreshChartCategorias,
    formatarMoeda,
    urlFinanceiro,
    irFinanceiroResumo,
    irHome,
    irRelatorio,
    irVeiculos,
    irConfiguracoes
  };
})(window);
