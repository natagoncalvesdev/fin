/**
 * Shell mobile — barra superior com hambúrguer, gráfico do resumo do mês e toast
 */
(function (global) {
  'use strict';

  const MOBILE_MAX = 768;
  const CHART_COLORS = ['#0F766E', '#B91C1C', '#3B82F6', '#B45309', '#8B5CF6', '#475569'];
  const MESES = [
    'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
  ];

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

  function obterPeriodoSalvo() {
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

  function urlFinanceiro(pagina) {
    const { mes, ano } = obterPeriodoSalvo();
    const params = new URLSearchParams();
    params.set('mes', mes);
    params.set('ano', ano);
    return `${pagina}?${params.toString()}`;
  }

  function navegarPara(url) {
    window.location.assign(url);
  }

  function irFinanceiroResumo() {
    navegarPara(urlFinanceiro('index.html'));
  }

  function irContas() {
    navegarPara(urlFinanceiro('contas.html'));
  }

  function irCartoes() {
    navegarPara(urlFinanceiro('cartoes.html'));
  }

  function irReservas() {
    navegarPara(urlFinanceiro('reservados.html'));
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

  const ICON_HAMBURGER = '<svg viewBox="0 0 24 24"><path d="M3 6h18M3 12h18M3 18h18"/></svg>';

  function criarTopBar() {
    const existente = document.getElementById('mobileTopBar');
    if (existente) existente.remove();

    const bar = document.createElement('header');
    bar.id = 'mobileTopBar';
    bar.className = 'mobile-top-bar mobile-only';
    bar.innerHTML = `
      <a href="index.html" class="mobile-top-bar-brand" aria-label="Início">
        <img src="img/logo%20sem%20escrita.png" alt="" class="mobile-top-bar-logo" width="28" height="28" />
      </a>
      <button type="button" id="mobileMenuToggle" class="mobile-hamburger" aria-label="Abrir menu" aria-expanded="false" aria-controls="mainSidebar">
        ${ICON_HAMBURGER}
      </button>
    `;
    document.body.insertBefore(bar, document.body.firstChild);

    bar.querySelector('#mobileMenuToggle')?.addEventListener('click', () => {
      global.finSidebar?.toggleDrawer();
    });
  }

  function aplicarShell() {
    const header = document.getElementById('mobileHeader');
    if (header) header.remove();

    if (!isMobile()) {
      document.body.classList.remove('mobile-shell');
      const bar = document.getElementById('mobileTopBar');
      if (bar) bar.remove();
      global.finSidebar?.fecharDrawer();
      return;
    }
    document.body.classList.add('mobile-shell');
    criarTopBar();
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
          c.fillStyle = '#0B1120';
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
    window.addEventListener('resize', aplicarShell);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // --- Toast não-bloqueante (substitui alert() para erros de fundo) ---
  let toastContainer = null;

  function finToast(mensagem, { type = 'info', duration = 4200 } = {}) {
    if (!toastContainer) {
      toastContainer = document.createElement('div');
      toastContainer.id = 'finToastContainer';
      toastContainer.setAttribute('aria-live', 'polite');
      document.body.appendChild(toastContainer);
    }

    const toast = document.createElement('div');
    toast.className = `fin-toast fin-toast--${type}`;
    toast.textContent = mensagem;
    toastContainer.appendChild(toast);

    requestAnimationFrame(() => toast.classList.add('fin-toast--visible'));

    const remover = () => {
      toast.classList.remove('fin-toast--visible');
      setTimeout(() => toast.remove(), 220);
    };

    const timer = setTimeout(remover, duration);
    toast.addEventListener('click', () => {
      clearTimeout(timer);
      remover();
    });
  }

  global.finToast = finToast;

  global.finMobileNav = {
    isMobile,
    aplicarShell,
    atualizarGraficoCategorias,
    refreshChartCategorias,
    formatarMoeda,
    urlFinanceiro,
    irFinanceiroResumo,
    irContas,
    irCartoes,
    irReservas,
    irHome,
    irRelatorio,
    irVeiculos,
    irConfiguracoes
  };
})(window);
