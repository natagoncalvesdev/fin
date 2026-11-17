/**
 * Lógica compartilhada entre as páginas do financeiro (index.html,
 * contas.html, cartoes.html, reservados.html): seletor de mês/ano,
 * categorias, cartões, o modal único de item (editar/copiar/status/excluir)
 * e o polling leve que mantém a tela atualizada.
 *
 * Fala direto com os endpoints granulares novos (window.finApi, exposto por
 * fin-sdk.js) — cada gravação é um INSERT/UPDATE/DELETE atômico de uma linha,
 * ao contrário do antigo padrão de "ler o mês inteiro, mesclar, regravar o
 * mês inteiro" (a causa da duplicação/perda de dados sob concorrência).
 */
(function (global) {
  'use strict';

  const MESES = [
    'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
  ];
  const ANO_BASE = 2025;
  const ANO_LIMITE = ANO_BASE + 10;
  const POLL_INTERVAL = 20000;

  const moeda = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
  const formatar = (valor) => moeda.format(Number(valor) || 0);

  function centavosParaTexto(centavos) {
    return (centavos / 100).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function ajustarFonteValor(input) {
    const tamanho = (input.value || '').length;
    input.dataset.largo = tamanho > 11 ? '2' : tamanho > 8 ? '1' : '';
  }

  /** Máscara de moeda: só dígitos, empurrando os centavos (1 → 0,01 → 0,12 → 1,23). */
  function ligarMascaraMoeda(input) {
    if (!input || input.dataset.moedaLigada) return;
    input.dataset.moedaLigada = '1';
    input.setAttribute('inputmode', 'numeric');
    input.setAttribute('autocomplete', 'off');
    input.addEventListener('input', () => {
      const centavos = parseInt(String(input.value).replace(/\D/g, '') || '0', 10);
      input.dataset.centavos = String(centavos);
      input.value = centavos ? centavosParaTexto(centavos) : '';
      ajustarFonteValor(input);
    });
  }

  function definirMoeda(input, valorNumero) {
    if (!input) return;
    const numero = Number(valorNumero);
    const centavos = Number.isFinite(numero) && numero > 0 ? Math.round(numero * 100) : 0;
    input.dataset.centavos = String(centavos);
    input.value = centavos ? centavosParaTexto(centavos) : '';
    ajustarFonteValor(input);
  }

  function lerMoeda(input) {
    if (!input) return 0;
    const guardado = input.dataset.centavos;
    const centavos = guardado != null && guardado !== ''
      ? parseInt(guardado, 10)
      : parseInt(String(input.value).replace(/\D/g, '') || '0', 10);
    return (Number.isFinite(centavos) ? centavos : 0) / 100;
  }

  function api(path, options) {
    return global.finApi.request(path, options);
  }

  function toast(msg, opts) {
    if (global.finToast) global.finToast(msg, opts);
  }

  function erroMsg(err, fallback) {
    return (err && err.message) || fallback || 'Não foi possível concluir a ação.';
  }

  // --- Período (ano/mês) ------------------------------------------------

  function periodoSalvo() {
    try {
      const salvo = JSON.parse(sessionStorage.getItem('financeiroPeriodo') || '{}');
      if (salvo.mes && salvo.ano && MESES.includes(salvo.mes)) {
        return { mes: salvo.mes, ano: String(salvo.ano) };
      }
    } catch (e) { /* ignore */ }
    const hoje = new Date();
    return { mes: MESES[hoje.getMonth()], ano: String(hoje.getFullYear()) };
  }

  function salvarPeriodo(ano, mes) {
    try {
      sessionStorage.setItem('financeiroPeriodo', JSON.stringify({ ano, mes }));
    } catch (e) { /* ignore */ }
  }

  /**
   * Cria o controlador de período: popula os <select> de ano/mês, sincroniza
   * com a URL (?ano=&mes=) e sessionStorage, e chama onChange(ano, mes)
   * sempre que o período muda (inclusive na primeira carga).
   */
  function criarControladorPeriodo({ selectAno, selectMes, onChange }) {
    if (selectAno) {
      selectAno.innerHTML = '';
      for (let ano = ANO_BASE; ano <= ANO_LIMITE; ano++) {
        const opt = document.createElement('option');
        opt.value = String(ano);
        opt.textContent = String(ano);
        selectAno.appendChild(opt);
      }
    }
    if (selectMes) {
      selectMes.innerHTML = '';
      MESES.forEach((mes) => {
        const opt = document.createElement('option');
        opt.value = mes;
        opt.textContent = mes;
        selectMes.appendChild(opt);
      });
    }

    const params = new URLSearchParams(window.location.search);
    const inicial = periodoSalvo();
    let ano = params.get('ano') || inicial.ano;
    let mes = params.get('mes') && MESES.includes(params.get('mes')) ? params.get('mes') : inicial.mes;
    if (Number(ano) < ANO_BASE) ano = String(ANO_BASE);
    if (Number(ano) > ANO_LIMITE) ano = String(ANO_LIMITE);

    function aplicar(novoAno, novoMes) {
      ano = novoAno;
      mes = novoMes;
      if (selectAno) selectAno.value = ano;
      if (selectMes) selectMes.value = mes;
      salvarPeriodo(ano, mes);
      onChange(ano, mes);
    }

    if (selectAno) {
      selectAno.addEventListener('change', () => aplicar(selectAno.value, mes));
    }
    if (selectMes) {
      selectMes.addEventListener('change', () => aplicar(ano, selectMes.value));
    }

    // Adiado: dispara depois que a chamada atual (que ainda está atribuindo o
    // valor de retorno desta função à variável do chamador) tiver terminado —
    // senão o primeiro onChange roda com essa variável ainda undefined/null.
    setTimeout(() => aplicar(ano, mes), 0);

    return {
      get ano() { return ano; },
      get mes() { return mes; },
      irPara(novoAno, novoMes) { aplicar(novoAno, novoMes); },
      navegar(offset) {
        const idx = MESES.indexOf(mes);
        let novoIdx = idx + offset;
        let novoAno = Number(ano);
        if (novoIdx < 0) { novoIdx = 11; novoAno -= 1; }
        if (novoIdx > 11) { novoIdx = 0; novoAno += 1; }
        if (novoAno < ANO_BASE || novoAno > ANO_LIMITE) return;
        aplicar(String(novoAno), MESES[novoIdx]);
      },
      recarregar() { onChange(ano, mes); },
    };
  }

  // --- Dados do mês (leitura) --------------------------------------------

  async function carregarMes(ano, mes) {
    const res = await api(`/api/financeiro/anos/${ano}/meses/${encodeURIComponent(mes)}`);
    return res.data;
  }

  /**
   * Ano inteiro numa única requisição. Retorna um objeto
   * { "Janeiro": { contas, adicionais, cartao, reservado, debito, cartaoStatus }, ... }.
   * Muito mais rápido que 12 chamadas a carregarMes em série.
   */
  async function carregarAno(ano) {
    const res = await api(`/api/financeiro/anos/${ano}/resumo`);
    return res.meses;
  }

  /**
   * Poll leve (substitui o onSnapshot do shim antigo): busca o mês a cada
   * poucos segundos e só chama o callback quando algo de fato mudou.
   * Pausa quando a aba está em segundo plano.
   */
  function observarMes(getAnoMes, callback) {
    let ativo = true;
    let ultimoJson = '';
    let timer = null;

    async function tick() {
      if (!ativo || document.hidden) return;
      const { ano, mes } = getAnoMes();
      if (!ano || !mes) return;
      try {
        const data = await carregarMes(ano, mes);
        const json = JSON.stringify(data);
        if (json !== ultimoJson) {
          ultimoJson = json;
          callback(data);
        }
      } catch (err) {
        if (err.code !== 'auth/invalid-credential') {
          console.error('Erro ao atualizar mês:', err);
        }
      }
    }

    function forcar() {
      ultimoJson = '';
      return tick();
    }

    const onVisible = () => { if (ativo && !document.hidden) tick(); };
    document.addEventListener('visibilitychange', onVisible);
    tick();
    timer = setInterval(tick, POLL_INTERVAL);

    return {
      parar() {
        ativo = false;
        clearInterval(timer);
        document.removeEventListener('visibilitychange', onVisible);
      },
      forcar,
    };
  }

  // --- Categorias ---------------------------------------------------------

  let categoriasCache = [];

  async function carregarCategorias() {
    try {
      categoriasCache = await api('/api/categorias');
      categoriasCache.sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR'));
    } catch (err) {
      console.error('Erro ao carregar categorias:', err);
    }
    return categoriasCache;
  }

  const ICONES_CATEGORIA = [
    ['alimentacao', 'Alimentação', '<path d="M4 3v7a2 2 0 0 0 2 2v9"/><path d="M4 7h4"/><path d="M6 3v7"/><path d="M16 3c-1.6 2.2-2 4.2-2 6a2 2 0 0 0 2 2v10"/>'],
    ['mercado', 'Mercado', '<circle cx="8" cy="20" r="1"/><circle cx="17" cy="20" r="1"/><path d="M3 4h2l2.4 11.2a1 1 0 0 0 1 .8h9.2a1 1 0 0 0 1-.8L21 8H7"/>'],
    ['transporte', 'Transporte', '<path d="M4 16V9l2.2-4h11.6L20 9v7"/><path d="M3 16h18"/><circle cx="7.5" cy="16.5" r="1.5"/><circle cx="16.5" cy="16.5" r="1.5"/>'],
    ['combustivel', 'Combustível', '<path d="M4 21V5a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v16"/><path d="M4 21h10"/><path d="M14 8h2.5a2 2 0 0 1 2 2v3a2 2 0 0 0 2 2H21"/><path d="M7 8h4"/>'],
    ['moradia', 'Moradia', '<path d="m4 10.5 8-6.5 8 6.5V20H4z"/><path d="M10 20v-6h4v6"/>'],
    ['contas', 'Contas', '<path d="M13 2 4 14h7l-1 8 9-12h-7l1-8z"/>'],
    ['saude', 'Saúde', '<path d="M12 20s-7-4.4-7-9a4 4 0 0 1 7-2 4 4 0 0 1 7 2c0 4.6-7 9-7 9z"/>'],
    ['educacao', 'Educação', '<path d="m3 8 9-4 9 4-9 4-9-4z"/><path d="M7 10.5V16c0 1 2.2 3 5 3s5-2 5-3v-5.5"/>'],
    ['lazer', 'Lazer', '<rect x="3" y="6" width="18" height="14" rx="2"/><path d="M8 6V4M16 6V4M3 11h18"/>'],
    ['vestuario', 'Vestuário', '<path d="m8 4-4 3 2 2 2-2v11h8V7l2 2 2-2-4-3"/><path d="M9 4a3 3 0 0 0 6 0"/>'],
    ['eletronicos', 'Eletrônicos', '<rect x="7" y="2" width="10" height="20" rx="2"/><path d="M11 18h2"/>'],
    ['viagem', 'Viagem', '<path d="m10 20 2-6-8-3 16-7-4 16-4-3-2 3z"/>'],
    ['pet', 'Pet', '<circle cx="6" cy="8" r="2"/><circle cx="12" cy="6" r="2"/><circle cx="18" cy="8" r="2"/><path d="M8 14c0 3 1.8 5 4 5s4-2 4-5c-1.2 1-2.5 1.5-4 1.5S9.2 15 8 14z"/>'],
    ['dinheiro', 'Dinheiro', '<rect x="3" y="6" width="18" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/><path d="M6 9v.01M18 15v.01"/>'],
    ['presente', 'Presente', '<rect x="4" y="10" width="16" height="10" rx="1"/><path d="M4 14h16M12 10v10"/><path d="M12 10c-2 0-4-1.6-3.2-3.2S12 7.2 12 10c0-2.8 2.2-4 3.2-3.2S14 10 12 10z"/>'],
    ['beleza', 'Beleza', '<path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1"/>'],
    ['familia', 'Família', '<circle cx="9" cy="8" r="3"/><circle cx="17" cy="9" r="2"/><path d="M3 19c0-3 2.5-5 6-5s6 2 6 5"/><path d="M15 14.2c1.8.3 4 1.6 4 4.3"/>'],
    ['outros', 'Outros', '<path d="M20 13V7a2 2 0 0 0-2-2h-3l-1-2H8L7 5H4a2 2 0 0 0-2 2v6"/><path d="M4 13v6a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-6"/><circle cx="12" cy="13" r="3"/>'],
  ];

  function svgIcone(chave) {
    const item = ICONES_CATEGORIA.find((icone) => icone[0] === chave);
    if (!item) return '';
    return `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${item[2]}</svg>`;
  }

  function svgDaCategoria(nome) {
    const alvo = String(nome || '').trim().toLowerCase();
    if (!alvo) return '';
    const cat = categoriasCache.find((item) => String(item.nome || '').trim().toLowerCase() === alvo);
    return cat ? svgIcone(cat.icone) : '';
  }

  function popularSelectsCategoria(selectIds) {
    selectIds.forEach((id) => {
      const select = document.getElementById(id);
      if (!select) return;
      const atual = select.value;
      select.innerHTML = '<option value="">Selecione uma categoria</option>';
      categoriasCache.forEach((cat) => {
        const opt = document.createElement('option');
        opt.value = cat.nome;
        opt.textContent = cat.nome;
        select.appendChild(opt);
      });
      if (atual) select.value = atual;
    });
  }

  // --- Renderização de linha de extrato (statement-row) -------------------

  const ICONE_PADRAO = '<svg viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/></svg>';

  /**
   * Monta uma .statement-row clicável. `status` (opcional) mostra o pill
   * pendente/pago; se `onToggleStatus` for passado, o pill vira clicável
   * (alterna sozinho, sem precisar abrir o modal) e para propagação pro
   * onClick da linha.
   */
  /** Subtítulo da linha: descrição (se houver) e categoria, truncado para caber na lista. */
  function subtituloFinanceiro(item) {
    const partes = [];
    const desc = (item && item.descricao || '').trim();
    if (desc) partes.push(desc.length > 80 ? `${desc.slice(0, 77)}…` : desc);
    const cat = (item && item.categoria || '').trim();
    if (cat) partes.push(cat);
    return partes.join(' · ');
  }

  function renderStatementRow({ icone, titulo, subtitulo, valor, valorClasse, status, onClick, onToggleStatus }) {
    const row = document.createElement('button');
    row.type = 'button';
    row.className = 'statement-row';

    const subtituloHtml = subtitulo ? `<span class="statement-row-subtitle">${subtitulo}</span>` : '';
    const statusHtml = status
      ? `<span class="status-pill ${status === 'pago' ? 'pago' : 'pendente'}${onToggleStatus ? ' status-pill-clickable' : ''}" data-role="status">${status === 'pago' ? 'Pago' : 'Pendente'}</span>`
      : '';

    row.innerHTML = `
      <span class="statement-row-icon">${icone || ICONE_PADRAO}</span>
      <span class="statement-row-body">
        <span class="statement-row-title">${titulo}</span>
        ${subtituloHtml}
      </span>
      <span class="statement-row-end">
        <span class="statement-row-value ${valorClasse || ''}">${formatar(valor)}</span>
        ${statusHtml}
      </span>
    `;

    if (onToggleStatus) {
      const pill = row.querySelector('[data-role="status"]');
      pill.addEventListener('click', (ev) => {
        ev.stopPropagation();
        onToggleStatus(pill);
      });
    }
    if (onClick) row.addEventListener('click', onClick);
    return row;
  }

  // --- Modal único de item (editar / copiar / status / excluir) ----------

  const TIPO_CONFIG = {
    conta: { base: '/api/financeiro/contas', temStatus: true, temCategoria: true, temCopia: true },
    entrada: { base: '/api/financeiro/entradas', temStatus: false, temCategoria: false, temCopia: true },
    debito: { base: '/api/financeiro/debitos', temStatus: false, temCategoria: true, temCopia: true },
    reservado: { base: '/api/financeiro/reservados', temStatus: false, temCategoria: true, temCopia: true },
    compraCartao: { base: '/api/financeiro/compras-cartao', temStatus: false, temCategoria: true, temCopia: false },
  };

  let modalEls = null;
  let modalEstado = null;

  function injetarModal() {
    if (document.getElementById('finItemModal')) return;
    document.body.insertAdjacentHTML('beforeend', `
      <div id="finItemModal" class="modal-overlay fin-entry-overlay">
        <div class="modal-content fin-entry-modal">
          <div class="fin-entry-head">
            <h3 id="finItemModalTitulo">Item</h3>
            <button type="button" class="fin-entry-x" id="finItemFechar" aria-label="Fechar">&times;</button>
          </div>
          <div class="fin-entry-valor">
            <label for="finItemValor">Valor</label>
            <div class="fin-entry-valor-linha">
              <span class="fin-entry-moeda">R$</span>
              <input id="finItemValor" class="fin-entry-valor-input" inputmode="numeric" autocomplete="off" placeholder="0,00" />
            </div>
          </div>
          <div class="fin-entry-campo">
            <label for="finItemNome">Título</label>
            <input id="finItemNome" class="fin-entry-input" type="text" autocomplete="off" placeholder="Ex.: Conta de luz" />
          </div>
          <div class="fin-entry-campo" id="finItemCategoriaWrap">
            <label for="finItemCategoria">Categoria</label>
            <select id="finItemCategoria" class="fin-entry-input"><option value="">Selecione uma categoria</option></select>
          </div>
          <div class="fin-entry-campo">
            <label for="finItemDescricao">Observação <small>(opcional)</small></label>
            <textarea id="finItemDescricao" class="fin-entry-input" placeholder="Algum detalhe?"></textarea>
          </div>
          <div class="fin-entry-campo" id="finItemStatusWrap" style="display:none;">
            <span class="fin-entry-legend">Status</span>
            <div class="fin-entry-seg">
              <button type="button" class="fin-entry-seg-opt" data-status="pendente">Pendente</button>
              <button type="button" class="fin-entry-seg-opt" data-status="pago">Pago</button>
            </div>
          </div>
          <div id="finItemParcelaInfo" class="fin-parcela-info" style="display:none;"></div>
          <div class="fin-entry-acoes fin-entry-acoes-edit">
            <button type="button" class="btn-inline fin-btn-danger" id="finItemExcluir">Excluir</button>
            <button type="button" class="btn-icon-inline copy" id="finItemCopiar" style="font-size:20px;" title="Copiar para outros meses">❐</button>
            <button type="button" class="fin-entry-btn fin-entry-btn-sec" id="finItemCancelar">Cancelar</button>
            <button type="button" class="fin-entry-btn fin-entry-btn-pri" id="finItemSalvar">Salvar</button>
          </div>
        </div>
      </div>
      <div id="finCopyModal" class="modal-overlay">
        <div class="modal-content">
          <h3>Copiar para outros meses</h3>
          <div id="finCopyMonthList" class="modal-month-list"></div>
          <div class="modal-actions">
            <button type="button" class="btn-cancel" id="finCopyCancelar">Cancelar</button>
            <button type="button" class="btn-confirm" id="finCopyConfirmar">Concluir</button>
          </div>
        </div>
      </div>
    `);

    modalEls = {
      overlay: document.getElementById('finItemModal'),
      titulo: document.getElementById('finItemModalTitulo'),
      nome: document.getElementById('finItemNome'),
      descricao: document.getElementById('finItemDescricao'),
      valor: document.getElementById('finItemValor'),
      categoriaWrap: document.getElementById('finItemCategoriaWrap'),
      categoria: document.getElementById('finItemCategoria'),
      statusWrap: document.getElementById('finItemStatusWrap'),
      statusOpts: Array.from(document.querySelectorAll('#finItemStatusWrap .fin-entry-seg-opt')),
      fechar: document.getElementById('finItemFechar'),
      parcelaInfo: document.getElementById('finItemParcelaInfo'),
      excluir: document.getElementById('finItemExcluir'),
      copiar: document.getElementById('finItemCopiar'),
      cancelar: document.getElementById('finItemCancelar'),
      salvar: document.getElementById('finItemSalvar'),
      copyOverlay: document.getElementById('finCopyModal'),
      copyList: document.getElementById('finCopyMonthList'),
      copyCancelar: document.getElementById('finCopyCancelar'),
      copyConfirmar: document.getElementById('finCopyConfirmar'),
    };

    modalEls.statusOpts.forEach((btn) => {
      btn.addEventListener('click', () => {
        modalEls.statusOpts.forEach((b) => b.classList.toggle('active', b === btn));
      });
    });
    ligarMascaraMoeda(modalEls.valor);
    modalEls.fechar.addEventListener('click', fecharModalItem);
    modalEls.cancelar.addEventListener('click', fecharModalItem);
    modalEls.excluir.addEventListener('click', () => finRunOnce(modalEls.excluir, excluirItemAtual));
    modalEls.salvar.addEventListener('click', () => finRunOnce(modalEls.salvar, salvarItemAtual));
    modalEls.copiar.addEventListener('click', abrirCopiaDoItemAtual);
    modalEls.copyCancelar.addEventListener('click', () => modalEls.copyOverlay.classList.remove('visible'));
    modalEls.copyConfirmar.addEventListener('click', () => finRunOnce(modalEls.copyConfirmar, confirmarCopiaDoItemAtual));

    [modalEls.overlay, modalEls.copyOverlay].forEach((overlay) => {
      overlay.addEventListener('click', (ev) => {
        if (ev.target === overlay) overlay.classList.remove('visible');
      });
    });
  }

  function statusSelecionado() {
    const ativo = modalEls.statusOpts.find((b) => b.classList.contains('active'));
    return ativo ? ativo.dataset.status : 'pendente';
  }

  /**
   * Abre o modal único para um item existente.
   * opts: { tipo, item, onSalvo, onExcluido }
   * `item` precisa ter `id` (uuid) e os campos nome/valor/categoria/status.
   */
  function abrirModalItem(opts) {
    injetarModal();
    const cfg = TIPO_CONFIG[opts.tipo];
    if (!cfg) throw new Error(`Tipo de item desconhecido: ${opts.tipo}`);

    modalEstado = { tipo: opts.tipo, cfg, item: opts.item, onSalvo: opts.onSalvo, onExcluido: opts.onExcluido };

    modalEls.titulo.textContent = opts.item.nome || 'Editar item';
    modalEls.nome.value = opts.item.nome || '';
    modalEls.descricao.value = opts.item.descricao || '';
    definirMoeda(modalEls.valor, opts.item.valor);

    modalEls.categoriaWrap.style.display = cfg.temCategoria ? '' : 'none';
    if (cfg.temCategoria) {
      popularSelectsCategoria(['finItemCategoria']);
      modalEls.categoria.value = opts.item.categoria || '';
    }

    modalEls.statusWrap.style.display = cfg.temStatus ? '' : 'none';
    if (cfg.temStatus) {
      const statusAtual = opts.item.status || 'pendente';
      modalEls.statusOpts.forEach((b) => b.classList.toggle('active', b.dataset.status === statusAtual));
    }

    modalEls.copiar.style.display = cfg.temCopia ? '' : 'none';

    if (opts.tipo === 'compraCartao' && opts.item.parcelas) {
      modalEls.parcelaInfo.style.display = '';
      modalEls.parcelaInfo.textContent = opts.item.recorrente
        ? 'Compra recorrente — excluir remove também as próximas ocorrências.'
        : `Parcela ${opts.item.parcelas}`;
    } else {
      modalEls.parcelaInfo.style.display = 'none';
    }

    modalEls.overlay.classList.add('visible');
  }

  function fecharModalItem() {
    if (modalEls) modalEls.overlay.classList.remove('visible');
    modalEstado = null;
  }

  async function salvarItemAtual() {
    if (!modalEstado) return;
    const { tipo, cfg, item, onSalvo } = modalEstado;
    const nome = modalEls.nome.value.trim();
    const descricao = modalEls.descricao.value.trim();
    const valor = lerMoeda(modalEls.valor);
    if (!nome || !valor || valor <= 0) {
      toast('Preencha título e valor.', { type: 'error' });
      return;
    }
    const payload = { nome, valor, descricao };
    if (cfg.temCategoria) payload.categoria = modalEls.categoria.value.trim();
    if (cfg.temStatus) payload.status = statusSelecionado();

    try {
      const res = await api(`${cfg.base}/${item.id}`, { method: 'PUT', body: JSON.stringify(payload) });
      toast('Salvo.', { type: 'success' });
      fecharModalItem();
      if (onSalvo) onSalvo(res.data);
    } catch (err) {
      toast(erroMsg(err, 'Não foi possível salvar.'), { type: 'error' });
    }
  }

  async function excluirItemAtual() {
    if (!modalEstado) return;
    const { tipo, cfg, item, onExcluido } = modalEstado;
    const cascata = tipo === 'compraCartao' && item.recorrente;
    const label = cascata
      ? `Excluir "${item.nome}"? Esta e todas as próximas ocorrências desta compra recorrente serão removidas.`
      : `Excluir "${item.nome}"?`;
    if (!window.confirm(label)) return;

    const qs = cascata ? '?futuras=true' : '';
    try {
      await api(`${cfg.base}/${item.id}${qs}`, { method: 'DELETE' });
      toast('Removido.', { type: 'success' });
      fecharModalItem();
      if (onExcluido) onExcluido();
    } catch (err) {
      toast(erroMsg(err, 'Não foi possível excluir.'), { type: 'error' });
    }
  }

  function destinoMesOffset(anoBase, mesIndexBase, offset) {
    const idx = (((mesIndexBase + offset) % 12) + 12) % 12;
    const ano = anoBase + Math.floor((mesIndexBase + offset) / 12);
    return { ano, mes: MESES[idx] };
  }

  function abrirCopiaDoItemAtual() {
    if (!modalEstado) return;
    const { ano, mes } = global.finFinanceiro.periodoAtual();
    const mesIndex = MESES.indexOf(mes);
    modalEls.copyList.innerHTML = '';
    for (let i = 1; i <= 12; i++) {
      const { ano: targetAno, mes: targetMes } = destinoMesOffset(Number(ano), mesIndex, i);
      if (targetAno > ANO_LIMITE) break;
      const id = `fin-copy-${targetAno}-${targetMes}`;
      const item = document.createElement('div');
      item.className = 'modal-month-item';
      item.innerHTML = `<input type="checkbox" id="${id}" data-ano="${targetAno}" data-mes="${targetMes}"><label for="${id}">${targetMes} / ${targetAno}</label>`;
      modalEls.copyList.appendChild(item);
    }
    modalEls.overlay.classList.remove('visible');
    modalEls.copyOverlay.classList.add('visible');
  }

  async function confirmarCopiaDoItemAtual() {
    if (!modalEstado) return;
    const { cfg, item } = modalEstado;
    const checks = Array.from(modalEls.copyList.querySelectorAll('input[type="checkbox"]:checked'));
    if (checks.length === 0) {
      toast('Selecione pelo menos um mês.', { type: 'error' });
      return;
    }
    const payloadBase = { nome: item.nome, valor: item.valor, descricao: item.descricao || '' };
    if (cfg.temCategoria) payloadBase.categoria = item.categoria || '';
    if (modalEstado.tipo === 'conta') payloadBase.status = 'pendente';

    let ok = 0;
    for (const check of checks) {
      try {
        await api(cfg.base, {
          method: 'POST',
          body: JSON.stringify({ ...payloadBase, ano: Number(check.dataset.ano), mes: check.dataset.mes }),
        });
        ok += 1;
      } catch (err) {
        console.error('Erro ao copiar para', check.dataset.mes, check.dataset.ano, err);
      }
    }
    toast(`Copiado para ${ok} mês(es).`, { type: ok === checks.length ? 'success' : 'error' });
    modalEls.copyOverlay.classList.remove('visible');
    modalEstado = null;
  }

  // --- Toggle de status direto na linha -----------------------------------

  async function alternarStatusConta(item, onAtualizado) {
    const novoStatus = item.status === 'pago' ? 'pendente' : 'pago';
    try {
      const res = await api(`/api/financeiro/contas/${item.id}`, {
        method: 'PUT',
        body: JSON.stringify({ status: novoStatus }),
      });
      if (onAtualizado) onAtualizado(res.data);
    } catch (err) {
      toast(erroMsg(err, 'Não foi possível atualizar o status.'), { type: 'error' });
    }
  }

  async function atualizarStatusFatura(ano, mes, status) {
    return api(`/api/financeiro/anos/${ano}/meses/${encodeURIComponent(mes)}/status-fatura`, {
      method: 'PUT',
      body: JSON.stringify({ status }),
    });
  }

  function centavosDe(valor) {
    return Math.round((Number(valor) || 0) * 100);
  }

  /**
   * Liga o bloco "Usar reserva" de um modal de lançamento.
   * No registro, o valor da reserva escolhida é abatido do valor digitado.
   * A reserva continua no mês: ela já entra no saldo, e o lançamento guarda a diferença.
   */
  function ligarUsoReserva(raiz, valorInput, obterItens, opcoes) {
    const opts = opcoes || {};
    const botao = raiz.querySelector('[data-role="abrir"]');
    const box = raiz.querySelector('[data-role="box"]');
    const select = raiz.querySelector('[data-role="select"]');
    const resumo = raiz.querySelector('[data-role="resumo"]');
    let aberto = false;

    function itens() {
      const lista = typeof obterItens === 'function' ? obterItens() : obterItens;
      return (lista || []).filter((item) => item && centavosDe(item.valor) > 0);
    }

    function nomeReserva(item) {
      return String((item && item.nome) || '').trim() || 'Reserva';
    }

    function textoReserva(item) {
      return `${nomeReserva(item)} — ${formatar(item.valor)}`;
    }

    function selecionado() {
      const id = select.value;
      if (!id) return null;
      return itens().find((item) => item.id === id) || null;
    }

    function popular() {
      const lista = itens();
      const atual = select.value;
      select.replaceChildren();
      const placeholder = document.createElement('option');
      placeholder.value = '';
      placeholder.textContent = lista.length ? 'Selecione uma reserva' : 'Nenhuma reserva neste mês';
      select.appendChild(placeholder);
      lista.forEach((item) => {
        const opt = document.createElement('option');
        opt.value = item.id;
        opt.textContent = textoReserva(item);
        select.appendChild(opt);
      });
      if (atual && lista.some((item) => item.id === atual)) select.value = atual;
    }

    function atualizarResumo() {
      if (!aberto) return;
      resumo.classList.remove('alerta');
      const lista = itens();
      const item = selecionado();
      if (!lista.length) {
        resumo.textContent = 'Nenhuma reserva neste mês.';
        return;
      }
      if (!item) {
        resumo.textContent = select.value ? 'Essa reserva não está mais disponível.' : '';
        if (select.value) resumo.classList.add('alerta');
        return;
      }
      const digitado = centavosDe(lerMoeda(valorInput));
      const abate = centavosDe(item.valor);
      const liquido = digitado - abate;
      if (digitado <= 0) {
        resumo.textContent = `Abate ${formatar(item.valor)} de ${nomeReserva(item)}.`;
        return;
      }
      if (liquido <= 0) {
        resumo.textContent = `A reserva de ${formatar(item.valor)} cobre todo o valor informado.`;
        resumo.classList.add('alerta');
        return;
      }
      const extra = typeof opts.detalhe === 'function' ? (opts.detalhe() || '') : '';
      resumo.textContent = `Abate ${formatar(abate / 100)}. O lançamento entra como ${formatar(liquido / 100)}.${extra}`;
    }

    function definirAberto(proximo) {
      aberto = proximo;
      box.hidden = !aberto;
      botao.classList.toggle('on', aberto);
      botao.setAttribute('aria-expanded', aberto ? 'true' : 'false');
      botao.textContent = aberto ? 'Cancelar uso da reserva' : 'Usar reserva';
      if (aberto) {
        popular();
        atualizarResumo();
      } else {
        select.value = '';
        resumo.textContent = '';
        resumo.classList.remove('alerta');
      }
    }

    botao.addEventListener('click', () => definirAberto(!aberto));
    select.addEventListener('change', atualizarResumo);
    valorInput.addEventListener('input', atualizarResumo);
    (opts.observar || []).forEach((el) => {
      if (!el) return;
      el.addEventListener('input', atualizarResumo);
      el.addEventListener('change', atualizarResumo);
    });

    return {
      reset() { definirAberto(false); },
      valorLiquido(valorDigitado) {
        const centavos = centavosDe(valorDigitado);
        if (!aberto) return { ok: true, valor: centavos / 100, usou: false };
        if (!itens().length) return { ok: false, erro: 'Não há reserva neste mês para abater.' };
        if (select.value && !selecionado()) {
          return { ok: false, erro: 'Essa reserva não está mais disponível. Escolha outra.' };
        }
        const item = selecionado();
        if (!item) return { ok: false, erro: 'Selecione qual reserva usar.' };
        const liquido = centavos - centavosDe(item.valor);
        if (liquido <= 0) {
          return { ok: false, erro: 'A reserva cobre todo o valor. O lançamento ficaria zerado.' };
        }
        return { ok: true, valor: liquido / 100, usou: true, reserva: item };
      },
    };
  }

  // --- Ponto de acesso global ---------------------------------------------

  let periodoAtualRef = { ano: '', mes: '' };

  global.finFinanceiro = {
    MESES,
    ANO_BASE,
    ANO_LIMITE,
    formatar,
    ligarMascaraMoeda,
    definirMoeda,
    lerMoeda,
    api,
    criarControladorPeriodo(config) {
      const ctrl = criarControladorPeriodo(config);
      periodoAtualRef = ctrl;
      return ctrl;
    },
    periodoAtual: () => ({ ano: periodoAtualRef.ano, mes: periodoAtualRef.mes }),
    carregarMes,
    carregarAno,
    observarMes,
    carregarCategorias,
    popularSelectsCategoria,
    ICONES_CATEGORIA,
    svgIcone,
    svgDaCategoria,
    renderStatementRow,
    subtituloFinanceiro,
    abrirModalItem,
    fecharModalItem,
    alternarStatusConta,
    atualizarStatusFatura,
    ligarUsoReserva,
    destinoMesOffset,
  };
})(window);
