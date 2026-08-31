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
      <div id="finItemModal" class="modal-overlay">
        <div class="modal-content" style="max-width: 460px;">
          <h3 id="finItemModalTitulo">Item</h3>
          <div class="form-row" style="flex-direction: column; gap: 14px;">
            <div>
              <label class="fin-field-label" for="finItemNome">Descrição</label>
              <input id="finItemNome" type="text" placeholder="Descrição" />
            </div>
            <div>
              <label class="fin-field-label" for="finItemValor">Valor</label>
              <input id="finItemValor" type="number" step="0.01" placeholder="Valor em R$" />
            </div>
            <div id="finItemCategoriaWrap">
              <label class="fin-field-label" for="finItemCategoria">Categoria</label>
              <select id="finItemCategoria"><option value="">Selecione uma categoria</option></select>
            </div>
            <div id="finItemStatusWrap" style="display:none;">
              <label class="fin-field-label">Status</label>
              <div class="fin-status-toggle">
                <button type="button" class="fin-status-opt" data-status="pendente">Pendente</button>
                <button type="button" class="fin-status-opt" data-status="pago">Pago</button>
              </div>
            </div>
            <div id="finItemParcelaInfo" class="fin-parcela-info" style="display:none;"></div>
          </div>
          <div class="modal-actions" style="justify-content: space-between;">
            <button type="button" class="btn-inline fin-btn-danger" id="finItemExcluir">🗑️ Excluir</button>
            <div style="display:flex; gap:10px;">
              <button type="button" class="btn-icon-inline copy" id="finItemCopiar" style="font-size:20px;" title="Copiar para outros meses">❐</button>
              <button type="button" class="btn-cancel" id="finItemCancelar">Cancelar</button>
              <button type="button" class="btn-confirm" id="finItemSalvar">Salvar</button>
            </div>
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
      valor: document.getElementById('finItemValor'),
      categoriaWrap: document.getElementById('finItemCategoriaWrap'),
      categoria: document.getElementById('finItemCategoria'),
      statusWrap: document.getElementById('finItemStatusWrap'),
      statusOpts: Array.from(document.querySelectorAll('.fin-status-opt')),
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
    modalEls.valor.value = opts.item.valor != null ? opts.item.valor : '';

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
    const valor = Number(modalEls.valor.value);
    if (!nome || !valor || valor <= 0) {
      toast('Preencha descrição e valor.', { type: 'error' });
      return;
    }
    const payload = { nome, valor };
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
    const idx = (mesIndexBase + offset) % 12;
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
    const payloadBase = { nome: item.nome, valor: item.valor };
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

  // --- Ponto de acesso global ---------------------------------------------

  let periodoAtualRef = { ano: '', mes: '' };

  global.finFinanceiro = {
    MESES,
    ANO_BASE,
    ANO_LIMITE,
    formatar,
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
    renderStatementRow,
    abrirModalItem,
    fecharModalItem,
    alternarStatusConta,
    atualizarStatusFatura,
    destinoMesOffset,
  };
})(window);
