/**
 * Fin SDK — camada de compatibilidade com Firebase Auth/Firestore
 * Conecta o frontend existente à API REST Python.
 */
(function (global) {
  'use strict';

  const TOKEN_KEY = 'fin_token';
  const USER_KEY = 'fin_user';
  const POLL_INTERVAL = 2500;

  const API_BASE = global.FIN_API_BASE || '';

  function getToken() {
    return localStorage.getItem(TOKEN_KEY);
  }

  function setSession(token, user) {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  }

  function clearSession() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  }

  function getStoredUser() {
    try {
      const raw = localStorage.getItem(USER_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  }

  function makeFirebaseError(code, message) {
    const err = new Error(message);
    err.code = code;
    return err;
  }

  async function apiRequest(path, options = {}) {
    const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;

    const response = await fetch(`${API_BASE}${path}`, { ...options, headers });

    if (response.status === 204) return null;

    let payload = null;
    const text = await response.text();
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch {
        payload = { detail: text };
      }
    }

    if (!response.ok) {
      const detail = payload?.detail || 'Erro na requisição';
      const message = typeof detail === 'string' ? detail : JSON.stringify(detail);
      if (response.status === 401) throw makeFirebaseError('auth/invalid-credential', message);
      if (response.status === 400 && message.includes('email')) {
        throw makeFirebaseError('auth/email-already-in-use', message);
      }
      if (response.status === 400 && message.includes('senha')) {
        throw makeFirebaseError('auth/weak-password', message);
      }
      throw makeFirebaseError('unknown', message);
    }

    return payload;
  }

  // --- Timestamp ---
  class FinTimestamp {
    constructor(date) {
      this._date = date instanceof Date ? date : new Date(date);
    }

    toDate() {
      return new Date(this._date);
    }

    static fromDate(date) {
      return new FinTimestamp(date);
    }

    static now() {
      return new FinTimestamp(new Date());
    }
  }

  function wrapTimestamps(data) {
    if (data === null || data === undefined) return data;
    if (Array.isArray(data)) return data.map(wrapTimestamps);
    if (typeof data !== 'object') return data;

    const result = {};
    for (const [key, value] of Object.entries(data)) {
      if (key === 'data' || key === 'dataCriacao' || key === 'createdAt') {
        if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}/.test(value)) {
          result[key] = new FinTimestamp(value);
          continue;
        }
      }
      if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
        result[key] = wrapTimestamps(value);
      } else if (Array.isArray(value)) {
        result[key] = value.map((item) =>
          typeof item === 'object' && item !== null ? wrapTimestamps(item) : item
        );
      } else {
        result[key] = value;
      }
    }
    return result;
  }

  // --- FieldValue ---
  const FieldValue = {
    arrayUnion(...items) {
      return { __finOp: 'arrayUnion', items };
    },
    arrayRemove(...items) {
      return { __finOp: 'arrayRemove', items };
    },
    serverTimestamp() {
      return { __finOp: 'serverTimestamp' };
    },
  };

  function itemsEqual(a, b) {
    return JSON.stringify(a) === JSON.stringify(b);
  }

  function applyFieldOperations(current, updates) {
    const result = { ...current };

    for (const [field, value] of Object.entries(updates)) {
      if (value && value.__finOp === 'serverTimestamp') {
        result[field] = new Date().toISOString();
        continue;
      }

      if (value && value.__finOp === 'arrayUnion') {
        const arr = Array.isArray(result[field]) ? [...result[field]] : [];
        for (const item of value.items) {
          if (!arr.some((existing) => itemsEqual(existing, item))) {
            arr.push(item);
          }
        }
        result[field] = arr;
        continue;
      }

      if (value && value.__finOp === 'arrayRemove') {
        const arr = Array.isArray(result[field]) ? [...result[field]] : [];
        result[field] = arr.filter(
          (existing) => !value.items.some((item) => itemsEqual(existing, item))
        );
        continue;
      }

      result[field] = value;
    }

    return result;
  }

  // --- Path parsing ---
  function parsePath(segments) {
    return {
      segments,
      type: detectPathType(segments),
    };
  }

  function detectPathType(segments) {
    if (segments.length === 2 && segments[0] === 'users') return 'user';
    if (segments.length === 3 && segments[0] === 'users' && segments[2] === 'categorias') {
      return 'categorias_collection';
    }
    if (segments.length === 4 && segments[2] === 'categorias') return 'categoria_doc';
    if (segments.length === 3 && segments[2] === 'cartoes') return 'cartoes_collection';
    if (segments.length === 4 && segments[2] === 'cartoes') return 'cartao_doc';
    if (segments.length === 3 && segments[2] === 'veiculos') return 'veiculos_collection';
    if (segments.length === 4 && segments[2] === 'veiculos') return 'veiculo_doc';
    if (segments.length === 5 && segments[2] === 'veiculos' && segments[4] === 'abastecimentos') {
      return 'abastecimentos_collection';
    }
    if (segments.length === 5 && segments[2] === 'veiculos' && segments[4] === 'manutencoes') {
      return 'manutencoes_collection';
    }
    if (segments.length === 6 && segments[4] === 'abastecimentos') return 'abastecimento_doc';
    if (segments.length === 6 && segments[4] === 'manutencoes') return 'manutencao_doc';
    if (segments.length === 4 && segments[2] === 'anos') return 'ano_doc';
    if (segments.length === 6 && segments[2] === 'anos' && segments[4] === 'meses') return 'mes_doc';
    return 'unknown';
  }

  function serializeValue(value) {
    if (value instanceof FinTimestamp) return value._date.toISOString();
    if (value && value.__finOp === 'serverTimestamp') return new Date().toISOString();
    if (value && typeof value.toDate === 'function') return value.toDate().toISOString();
    return value;
  }

  function serializeUpdates(updates) {
    const result = {};
    for (const [key, value] of Object.entries(updates)) {
      if (value && value.__finOp) {
        result[key] = value;
      } else if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
        result[key] = serializeUpdates(value);
      } else {
        result[key] = serializeValue(value);
      }
    }
    return result;
  }

  function toComparableDate(value) {
    if (!value) return null;
    if (value instanceof FinTimestamp) return value._date;
    if (typeof value.toDate === 'function') return value.toDate();
    return new Date(value);
  }

  // --- Document snapshot ---
  class DocumentSnapshot {
    constructor(id, data, exists = true, ref = null) {
      this.id = id;
      this._data = data;
      this.exists = exists;
      this.ref = ref;
    }

    data() {
      return this._data ? wrapTimestamps({ ...this._data }) : undefined;
    }
  }

  class QuerySnapshot {
    constructor(docs) {
      this.docs = docs;
      this.empty = docs.length === 0;
      this.size = docs.length;
    }

    forEach(callback) {
      this.docs.forEach(callback);
    }
  }

  // --- Query ---
  class FinQuery {
    constructor(collectionRef) {
      this._collection = collectionRef;
      this._filters = [];
      this._orderBy = null;
      this._orderDir = 'asc';
      this._limit = null;
    }

    where(field, op, value) {
      this._filters.push({ field, op, value });
      return this;
    }

    orderBy(field, direction = 'asc') {
      this._orderBy = field;
      this._orderDir = direction;
      return this;
    }

    limit(n) {
      this._limit = n;
      return this;
    }

    async get() {
      return this._collection._fetchQuery(this);
    }

    onSnapshot(onNext, onError) {
      let active = true;
      let lastJson = '';

      const poll = async () => {
        if (!active) return;
        try {
          const snap = await this.get();
          const json = JSON.stringify(snap.docs.map((d) => ({ id: d.id, data: d.data() })));
          if (json !== lastJson) {
            lastJson = json;
            onNext(snap);
          }
        } catch (err) {
          if (onError) onError(err);
        }
      };

      poll();
      const interval = setInterval(poll, POLL_INTERVAL);
      return () => {
        active = false;
        clearInterval(interval);
      };
    }
  }

  // --- Document reference ---
  class DocumentReference {
    constructor(db, segments) {
      this._db = db;
      this._path = parsePath(segments);
      this.id = segments[segments.length - 1];
      this.path = segments.join('/');
    }

    collection(name) {
      return new CollectionReference(this._db, [...this._path.segments.slice(0, -1), this.id, name]);
    }

    async get() {
      const { type, segments } = this._path;

      if (type === 'user') {
        const res = await apiRequest(`/api/users/${segments[1]}`);
        return new DocumentSnapshot(segments[1], res.data, res.exists);
      }

      if (type === 'veiculo_doc') {
        const items = await apiRequest('/api/veiculos');
        const found = items.find((v) => v.id === segments[3]);
        return new DocumentSnapshot(segments[3], found ? found.data : null, !!found, this);
      }

      if (type === 'ano_doc') {
        const ano = segments[3];
        const res = await apiRequest(`/api/financeiro/anos/${ano}/exists`);
        return new DocumentSnapshot(ano, { ano: Number(ano) }, res.exists, this);
      }

      if (type === 'mes_doc') {
        const ano = segments[3];
        const mes = segments[5];
        const res = await apiRequest(`/api/financeiro/anos/${ano}/meses/${encodeURIComponent(mes)}`);
        return new DocumentSnapshot(`${ano}_${mes}`, res.data, res.exists, this);
      }

      if (type === 'cartao_doc') {
        const res = await apiRequest(`/api/cartoes/${segments[3]}`);
        return new DocumentSnapshot(res.id, res.data, true);
      }

      if (type === 'categoria_doc') {
        const cats = await apiRequest('/api/categorias');
        const found = cats.find((c) => c.id === segments[3]);
        return new DocumentSnapshot(segments[3], found ? { nome: found.nome } : null, !!found);
      }

      if (type === 'abastecimento_doc') {
        const veiculoId = segments[3];
        const abId = segments[5];
        const items = await apiRequest(`/api/veiculos/${veiculoId}/abastecimentos`);
        const found = items.find((a) => a.id === abId);
        return new DocumentSnapshot(abId, found ? found.data : null, !!found);
      }

      if (type === 'manutencao_doc') {
        const veiculoId = segments[3];
        const mId = segments[5];
        const items = await apiRequest(`/api/veiculos/${veiculoId}/manutencoes`);
        const found = items.find((m) => m.id === mId);
        return new DocumentSnapshot(mId, found ? found.data : null, !!found);
      }

      return new DocumentSnapshot(this.id, null, false);
    }

    async set(data, options = {}) {
      const { type, segments } = this._path;

      if (type === 'mes_doc') {
        const ano = segments[3];
        const mes = segments[5];

        const isEmptyTemplate =
          (!data.contas || data.contas.length === 0) &&
          (!data.adicionais || data.adicionais.length === 0) &&
          (!data.cartao || data.cartao.length === 0) &&
          (!data.debito || data.debito.length === 0) &&
          (!data.reservado || data.reservado.length === 0);

        // Nunca gravar template vazio (evita apagar dados ao recarregar a página)
        if (isEmptyTemplate) {
          return;
        }

        await apiRequest(`/api/financeiro/anos/${ano}/meses/${encodeURIComponent(mes)}`, {
          method: 'PUT',
          body: JSON.stringify({ data }),
        });
        return;
      }

      if (type === 'ano_doc') {
        await apiRequest(`/api/financeiro/anos/${segments[3]}/init`, { method: 'POST' });
        return;
      }

      if (type === 'user' && options.merge) {
        return;
      }

      if (type === 'user') {
        return;
      }
    }

    async update(updates) {
      const { type, segments } = this._path;
      const payload = serializeUpdates(updates);

      if (type === 'mes_doc') {
        const ano = segments[3];
        const mes = segments[5];
        const current = await apiRequest(
          `/api/financeiro/anos/${ano}/meses/${encodeURIComponent(mes)}`
        );
        const merged = applyFieldOperations(current.data || {}, payload);
        await apiRequest(`/api/financeiro/anos/${ano}/meses/${encodeURIComponent(mes)}`, {
          method: 'PUT',
          body: JSON.stringify({ data: merged }),
        });
        return;
      }

      if (type === 'cartao_doc') {
        await apiRequest(`/api/cartoes/${segments[3]}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        });
        return;
      }

      if (type === 'abastecimento_doc') {
        await apiRequest(`/api/veiculos/${segments[3]}/abastecimentos/${segments[5]}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        });
        return;
      }

      if (type === 'manutencao_doc') {
        await apiRequest(`/api/veiculos/${segments[3]}/manutencoes/${segments[5]}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        });
      }
    }

    async delete() {
      const { type, segments } = this._path;

      if (type === 'cartao_doc') {
        await apiRequest(`/api/cartoes/${segments[3]}`, { method: 'DELETE' });
      } else if (type === 'categoria_doc') {
        await apiRequest(`/api/categorias/${segments[3]}`, { method: 'DELETE' });
      } else if (type === 'abastecimento_doc') {
        await apiRequest(`/api/veiculos/${segments[3]}/abastecimentos/${segments[5]}`, {
          method: 'DELETE',
        });
      } else if (type === 'manutencao_doc') {
        await apiRequest(`/api/veiculos/${segments[3]}/manutencoes/${segments[5]}`, {
          method: 'DELETE',
        });
      }
    }

    onSnapshot(onNext, onError) {
      let active = true;
      let lastJson = '';

      const poll = async () => {
        if (!active) return;
        try {
          const snap = await this.get();
          const json = JSON.stringify(snap.data());
          if (json !== lastJson) {
            lastJson = json;
            onNext(snap);
          }
        } catch (err) {
          if (onError) onError(err);
        }
      };

      poll();
      const interval = setInterval(poll, POLL_INTERVAL);

      return () => {
        active = false;
        clearInterval(interval);
      };
    }
  }

  // --- Collection reference ---
  class CollectionReference {
    constructor(db, segments) {
      this._db = db;
      this._path = parsePath(segments);
      this.id = segments[segments.length - 1];
    }

    doc(id) {
      return new DocumentReference(this._db, [...this._path.segments, id]);
    }

    orderBy(field, direction = 'asc') {
      const q = new FinQuery(this);
      return q.orderBy(field, direction);
    }

    where(field, op, value) {
      const q = new FinQuery(this);
      return q.where(field, op, value);
    }

    limit(n) {
      const q = new FinQuery(this);
      return q.limit(n);
    }

    async get() {
      return this._fetchQuery(new FinQuery(this));
    }

    async _fetchQuery(query) {
      const { type, segments } = this._path;

      if (type === 'categorias_collection') {
        const items = await apiRequest('/api/categorias');
        const docs = items.map((c) => {
          const ref = new DocumentReference(this._db, [
            'users',
            getStoredUser()?.id || 'anonymous',
            'categorias',
            c.id,
          ]);
          return new DocumentSnapshot(c.id, { nome: c.nome }, true, ref);
        });
        return new QuerySnapshot(docs);
      }

      if (type === 'cartoes_collection') {
        const items = await apiRequest('/api/cartoes');
        const docs = items.map((c) => {
          const ref = new DocumentReference(this._db, [
            'users',
            getStoredUser()?.id || 'anonymous',
            'cartoes',
            c.id,
          ]);
          return new DocumentSnapshot(c.id, c.data, true, ref);
        });
        return new QuerySnapshot(docs);
      }

      if (type === 'veiculos_collection') {
        let items = await apiRequest('/api/veiculos');
        if (query._orderBy === 'nome') {
          items.sort((a, b) => a.data.nome.localeCompare(b.data.nome, 'pt-BR'));
        }
        const docs = items.map((v) => {
          const ref = new DocumentReference(this._db, [
            'users',
            getStoredUser()?.id || 'anonymous',
            'veiculos',
            v.id,
          ]);
          return new DocumentSnapshot(v.id, v.data, true, ref);
        });
        return new QuerySnapshot(docs);
      }

      if (type === 'abastecimentos_collection') {
        const veiculoId = segments[3];
        const params = new URLSearchParams();
        const serverFilters = [];
        for (const f of query._filters) {
          if (f.field === 'ano' && f.op === '==') params.set('ano', f.value);
          else if (f.field === 'mes' && f.op === '==') params.set('mes', f.value);
          else serverFilters.push(f);
        }
        if (query._orderBy && query._orderBy !== 'data') {
          params.set('order_by', query._orderBy);
        }
        if (query._orderBy === 'data' || query._orderBy === 'kmAtual') {
          params.set('order_by', query._orderBy);
          params.set('order_dir', query._orderDir || 'desc');
        }

        const qs = params.toString();
        let items = await apiRequest(
          `/api/veiculos/${veiculoId}/abastecimentos${qs ? `?${qs}` : ''}`
        );

        for (const f of serverFilters) {
          items = items.filter((item) => {
            const raw = item.data[f.field];
            const left = f.field === 'data' ? toComparableDate(raw) : raw;
            const right = f.field === 'data' ? toComparableDate(f.value) : f.value;
            if (f.op === '==') return left === right;
            if (f.op === '<') return left < right;
            if (f.op === '>') return left > right;
            return true;
          });
        }

        if (query._orderBy === 'data') {
          items.sort((a, b) => {
            const da = toComparableDate(a.data.data);
            const db = toComparableDate(b.data.data);
            return query._orderDir === 'asc' ? da - db : db - da;
          });
        }

        if (query._limit) {
          items = items.slice(0, query._limit);
        }

        const docs = items.map((a) => {
          const ref = new DocumentReference(this._db, [
            'users',
            getStoredUser()?.id || 'anonymous',
            'veiculos',
            veiculoId,
            'abastecimentos',
            a.id,
          ]);
          return new DocumentSnapshot(a.id, a.data, true, ref);
        });
        return new QuerySnapshot(docs);
      }

      if (type === 'manutencoes_collection') {
        const veiculoId = segments[3];
        const params = new URLSearchParams();
        for (const f of query._filters) {
          if (f.field === 'ano') params.set('ano', f.value);
          if (f.field === 'mes') params.set('mes', f.value);
        }
        params.set('order_dir', query._orderDir || 'desc');

        const qs = params.toString();
        const items = await apiRequest(
          `/api/veiculos/${veiculoId}/manutencoes${qs ? `?${qs}` : ''}`
        );
        const docs = items.map((m) => new DocumentSnapshot(m.id, m.data, true));
        return new QuerySnapshot(docs);
      }

      return new QuerySnapshot([]);
    }

    async add(data) {
      const { type, segments } = this._path;
      const payload = applyFieldOperations({}, data);

      if (type === 'categorias_collection') {
        const res = await apiRequest('/api/categorias', {
          method: 'POST',
          body: JSON.stringify({ nome: payload.nome }),
        });
        return new DocumentReference(this._db, [...segments, res.id]);
      }

      if (type === 'cartoes_collection') {
        const res = await apiRequest('/api/cartoes', {
          method: 'POST',
          body: JSON.stringify(payload),
        });
        return new DocumentReference(this._db, [...segments, res.id]);
      }

      if (type === 'veiculos_collection') {
        const res = await apiRequest('/api/veiculos', {
          method: 'POST',
          body: JSON.stringify(payload),
        });
        return new DocumentReference(this._db, [...segments, res.id]);
      }

      if (type === 'abastecimentos_collection') {
        const veiculoId = segments[3];
        if (payload.data && payload.data.__finOp === 'serverTimestamp') {
          payload.data = new Date().toISOString();
        }
        const res = await apiRequest(`/api/veiculos/${veiculoId}/abastecimentos`, {
          method: 'POST',
          body: JSON.stringify(payload),
        });
        return new DocumentReference(this._db, [...segments, res.id]);
      }

      if (type === 'manutencoes_collection') {
        const veiculoId = segments[3];
        if (payload.data && payload.data.__finOp === 'serverTimestamp') {
          payload.data = new Date().toISOString();
        }
        const res = await apiRequest(`/api/veiculos/${veiculoId}/manutencoes`, {
          method: 'POST',
          body: JSON.stringify(payload),
        });
        return new DocumentReference(this._db, [...segments, res.id]);
      }

      throw new Error('Collection add não suportado para este caminho');
    }

    onSnapshot(onNext, onError) {
      let active = true;
      let lastJson = '';

      const poll = async () => {
        if (!active) return;
        try {
          const snap = await this.get();
          const json = JSON.stringify(snap.docs.map((d) => ({ id: d.id, data: d.data() })));
          if (json !== lastJson) {
            lastJson = json;
            onNext(snap);
          }
        } catch (err) {
          if (onError) onError(err);
        }
      };

      poll();
      const interval = setInterval(poll, POLL_INTERVAL);

      return () => {
        active = false;
        clearInterval(interval);
      };
    }
  }

  // --- Batch ---
  class WriteBatch {
    constructor(db) {
      this._db = db;
      this._ops = [];
    }

    set(ref, data) {
      this._ops.push({ type: 'set', ref, data });
      return this;
    }

    update(ref, data) {
      this._ops.push({ type: 'update', ref, data });
      return this;
    }

    delete(ref) {
      this._ops.push({ type: 'delete', ref });
      return this;
    }

    async commit() {
      for (const op of this._ops) {
        if (op.type === 'set') await op.ref.set(op.data);
        else if (op.type === 'update') await op.ref.update(op.data);
        else if (op.type === 'delete') await op.ref.delete();
      }
    }
  }

  // --- Firestore ---
  class FinFirestore {
    collection(name) {
      return new CollectionReference(this, [name]);
    }

    batch() {
      return new WriteBatch(this);
    }
  }

  // --- Auth ---
  const authListeners = new Set();
  let currentAuthUser = null;

  function buildAuthUser(user) {
    return {
      uid: user.id,
      email: user.email,
      displayName: user.name,
    };
  }

  function notifyAuthListeners() {
    authListeners.forEach((cb) => {
      try {
        cb(currentAuthUser);
      } catch (e) {
        console.error(e);
      }
    });
  }

  function initAuth() {
    const stored = getStoredUser();
    const token = getToken();
    if (stored && token) {
      currentAuthUser = buildAuthUser(stored);
    } else {
      currentAuthUser = null;
    }
    setTimeout(notifyAuthListeners, 0);
  }

  const authService = {
    onAuthStateChanged(callback) {
      authListeners.add(callback);
      callback(currentAuthUser);
      return () => authListeners.delete(callback);
    },

    async signInWithEmailAndPassword(email, password) {
      const res = await apiRequest('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      });
      setSession(res.token, res.user);
      currentAuthUser = buildAuthUser(res.user);
      notifyAuthListeners();
      return { user: currentAuthUser };
    },

    async createUserWithEmailAndPassword(email, password) {
      const nameInput = document.getElementById('name');
      const name = nameInput ? nameInput.value.trim() : email.split('@')[0];

      const res = await apiRequest('/api/auth/register', {
        method: 'POST',
        body: JSON.stringify({ name, email, password }),
      });
      setSession(res.token, res.user);
      currentAuthUser = buildAuthUser(res.user);
      notifyAuthListeners();
      return { user: currentAuthUser };
    },

    async signOut() {
      clearSession();
      currentAuthUser = null;
      notifyAuthListeners();
    },
  };

  // --- Firebase global ---
  const firestoreInstance = new FinFirestore();

  global.firebase = {
    initializeApp() {},
    auth: () => authService,
    firestore: () => firestoreInstance,
  };

  global.firebase.firestore.FieldValue = FieldValue;
  global.firebase.firestore.Timestamp = FinTimestamp;

  initAuth();
})(window);
