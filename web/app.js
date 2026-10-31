// App del súper: login con Google y listas compartidas en Firestore.
import { initializeApp } from 'https://www.gstatic.com/firebasejs/10.14.1/firebase-app.js';
import { getAuth, GoogleAuthProvider, onAuthStateChanged, signInWithPopup, signInWithRedirect, getRedirectResult, signOut }
  from 'https://www.gstatic.com/firebasejs/10.14.1/firebase-auth.js';
import { initializeFirestore, persistentLocalCache, persistentMultipleTabManager, collection, doc, query, where, orderBy,
  onSnapshot, addDoc, setDoc, getDoc, updateDoc, deleteDoc, writeBatch, arrayUnion, arrayRemove, deleteField,
  serverTimestamp, Timestamp } from 'https://www.gstatic.com/firebasejs/10.14.1/firebase-firestore.js';
import { firebaseConfig } from './config.js';

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
// Caché local: la lista se ve y se puede tachar aunque en el súper no haya señal; se sincroniza al volver.
const db = initializeFirestore(app, { localCache: persistentLocalCache({ tabManager: persistentMultipleTabManager() }) });

const $ = id => document.getElementById(id);
const norm = s => String(s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').trim();
const cap = s => s.charAt(0).toLocaleUpperCase('es-AR') + s.slice(1);
const store = { get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
                set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} } };

let user = null, listas = [], listaId = null, lista = null, items = null, q = '';
let unsubListas = null, unsubLista = null, unsubItems = null, armed = null, armT = null;
const inviteCode = new URLSearchParams(location.search).get('c');

function show(view) {
  for (const v of ['vLoading', 'vLogin', 'vJoin', 'vApp']) $(v).hidden = v !== view;
}
function fail(e, where) {
  console.error(where, e);
  const msg = e && e.code === 'permission-denied' ? 'No tenés permiso para hacer eso en esta lista.'
    : e && e.code === 'unavailable' ? 'Sin conexión: el cambio se guarda cuando vuelva la señal.'
    : 'Algo salió mal. Probá de nuevo.';
  $('err').textContent = msg; setTimeout(() => { $('err').textContent = ''; }, 6000);
}
const myName = () => (user.displayName || user.email || 'Alguien').split(' ')[0];

// ---------- login ----------
$('login').addEventListener('click', async () => {
  $('loginErr').textContent = '';
  const p = new GoogleAuthProvider(); p.setCustomParameters({ prompt: 'select_account' });
  try { await signInWithPopup(auth, p); }
  catch (e) {
    if (['auth/popup-blocked', 'auth/operation-not-supported-in-this-environment'].includes(e.code)) {
      try { await signInWithRedirect(auth, p); return; } catch (e2) { e = e2; }
    }
    if (e.code !== 'auth/popup-closed-by-user' && e.code !== 'auth/cancelled-popup-request')
      $('loginErr').textContent = 'No se pudo entrar (' + e.code + ').';
  }
});
getRedirectResult(auth).catch(e => { $('loginErr').textContent = 'No se pudo entrar (' + e.code + ').'; });
$('logout').addEventListener('click', () => signOut(auth));

onAuthStateChanged(auth, async u => {
  user = u;
  [unsubListas, unsubLista, unsubItems].forEach(f => f && f());
  unsubListas = unsubLista = unsubItems = null; listas = []; listaId = null; lista = null; items = null;
  $('who').hidden = !u;
  if (!u) {
    $('loginLead').textContent = inviteCode ? 'Te invitaron a una lista del súper. Entrá con tu cuenta de Google para sumarte.'
      : 'Entrá con tu cuenta de Google para ver tus listas.';
    show('vLogin'); return;
  }
  $('whoName').textContent = u.displayName || u.email;
  if (inviteCode) { await startJoin(inviteCode); return; }
  startApp();
});

// ---------- unirse con un link ----------
async function startJoin(code) {
  show('vJoin'); $('joinErr').textContent = ''; $('joinYes').disabled = true;
  $('joinTitle').textContent = 'Te invitaron a una lista'; $('joinText').textContent = 'Buscando la invitación…';
  let inv;
  try { const s = await getDoc(doc(db, 'invitaciones', code)); inv = s.exists() ? s.data() : null; }
  catch (e) { inv = null; }
  if (!inv) { $('joinText').textContent = 'Este link no existe o ya no sirve. Pedile a quien te lo mandó uno nuevo.'; return; }
  if (inv.vence && inv.vence.toMillis() < Date.now()) { $('joinText').textContent = 'Este link venció. Pedile a quien te lo mandó uno nuevo.'; return; }
  // ¿ya soy miembro? Si puedo leer la lista, sí.
  try { const ls = await getDoc(doc(db, 'listas', inv.lista)); if (ls.exists()) { leaveJoin(inv.lista); return; } } catch (e) {}
  $('joinTitle').textContent = 'Te invitaron a "' + (inv.nombreLista || 'una lista') + '"';
  $('joinText').textContent = 'Si te sumás, vas a ver y editar esta lista junto con quienes ya están.';
  $('joinYes').disabled = false;
  $('joinYes').onclick = async () => {
    $('joinYes').disabled = true;
    try {
      await updateDoc(doc(db, 'listas', inv.lista), { miembros: arrayUnion(user.uid), ['nombres.' + user.uid]: myName(), inv: code });
      leaveJoin(inv.lista);
    } catch (e) {
      console.error(e); $('joinYes').disabled = false;
      $('joinErr').textContent = 'No se pudo sumar a la lista. Puede que el link haya vencido: pedí uno nuevo.';
    }
  };
}
function leaveJoin(id) {
  history.replaceState(null, '', location.pathname);
  store.set('lista', id); startApp(id);
}
$('joinNo').addEventListener('click', () => { history.replaceState(null, '', location.pathname); startApp(); });

// ---------- listas ----------
function startApp(prefer) {
  show('vApp');
  unsubListas = onSnapshot(query(collection(db, 'listas'), where('miembros', 'array-contains', user.uid)), snap => {
    listas = snap.docs.map(d => ({ id: d.id, ...d.data() })).sort((a, b) => a.nombre.localeCompare(b.nombre, 'es'));
    const want = prefer || listaId || store.get('lista');
    prefer = null;
    renderSelector();
    const pick = listas.find(l => l.id === want) || listas[0];
    if (!pick) { openList(null); return; }
    if (pick.id !== listaId) openList(pick.id);
  }, e => fail(e, 'listas'));
}
function renderSelector() {
  const sel = $('listSel'); sel.innerHTML = '';
  for (const l of listas) {
    const o = document.createElement('option'); o.value = l.id;
    o.textContent = l.nombre + (l.miembros.length > 1 ? ' (compartida)' : ''); sel.appendChild(o);
  }
  sel.value = listaId || '';
  sel.hidden = !listas.length; $('newList').hidden = !listas.length;
  $('noLists').hidden = !!listas.length;
}
$('listSel').addEventListener('change', e => openList(e.target.value));

function openList(id) {
  if (unsubLista) unsubLista(); if (unsubItems) unsubItems();
  unsubLista = unsubItems = null; listaId = id; lista = null; items = null; q = ''; $('search').value = '';
  $('invBox').hidden = true;
  $('listView').hidden = !id;
  if (!id) return;
  store.set('lista', id); $('listSel').value = id;
  setDoc(doc(db, 'usuarios', user.uid), { ultima: id }, { merge: true }).catch(() => {});
  unsubLista = onSnapshot(doc(db, 'listas', id), s => {
    if (!s.exists()) return;   // me sacaron o la borraron: la consulta de listas lo resuelve
    lista = { id: s.id, ...s.data() }; renderHead();
  }, () => {});
  unsubItems = onSnapshot(query(collection(db, 'listas', id, 'items'), orderBy('o')), s => {
    items = s.docs.map(d => ({ id: d.id, ...d.data() })); renderItems();
  }, e => fail(e, 'items'));
  renderItems();
}

async function newList() {
  const nombre = (prompt('¿Cómo se llama la lista?', listas.length ? '' : 'Casa') || '').trim().slice(0, 60);
  if (!nombre) return;
  try {
    const r = await addDoc(collection(db, 'listas'), { nombre, owner: user.uid, miembros: [user.uid],
      nombres: { [user.uid]: myName() }, creada: serverTimestamp() });
    store.set('lista', r.id); listaId = null; openList(r.id);
  } catch (e) { fail(e, 'nueva'); }
}
$('newList').addEventListener('click', newList);
$('newList2').addEventListener('click', newList);

function renderHead() {
  if (!lista) return;
  const owner = lista.owner === user.uid;
  $('listName').textContent = lista.nombre;
  $('invite').hidden = !owner;
  $('leave').textContent = owner ? 'Borrar lista' : 'Salir de la lista';
  const m = $('members'); m.innerHTML = '';
  const names = lista.nombres || {};
  if (lista.miembros.length < 2) { m.textContent = owner ? 'Solo vos. Tocá "Invitar" para compartirla.' : ''; return; }
  m.append('Comparten: ');
  lista.miembros.forEach((uid, i) => {
    const s = document.createElement('span'); s.className = 'mem';
    s.append((uid === user.uid ? 'vos' : (names[uid] || 'alguien')) + (uid === lista.owner ? ' (dueño)' : ''));
    if (owner && uid !== user.uid) {
      const b = document.createElement('button'); b.type = 'button'; b.textContent = '×';
      b.setAttribute('aria-label', 'Sacar a ' + (names[uid] || 'esta persona'));
      b.addEventListener('click', async () => {
        if (!confirm('¿Sacar a ' + (names[uid] || 'esta persona') + ' de la lista?')) return;
        try { await updateDoc(doc(db, 'listas', lista.id), { miembros: arrayRemove(uid), ['nombres.' + uid]: deleteField() }); }
        catch (e) { fail(e, 'sacar'); }
      });
      s.append(b);
    }
    m.append(s); if (i < lista.miembros.length - 1) m.append(', ');
  });
}

$('rename').addEventListener('click', async () => {
  if (!lista) return;
  const nombre = (prompt('Nuevo nombre de la lista', lista.nombre) || '').trim().slice(0, 60);
  if (!nombre || nombre === lista.nombre) return;
  try { await updateDoc(doc(db, 'listas', lista.id), { nombre }); } catch (e) { fail(e, 'renombrar'); }
});

$('leave').addEventListener('click', async () => {
  if (!lista) return;
  if (lista.owner === user.uid) {
    if (!confirm('¿Borrar "' + lista.nombre + '" para todos? No se puede deshacer.')) return;
    try {
      const b = writeBatch(db);
      (items || []).forEach(it => b.delete(doc(db, 'listas', lista.id, 'items', it.id)));
      await b.commit();
      await deleteDoc(doc(db, 'listas', lista.id));
      store.set('lista', '');
    } catch (e) { fail(e, 'borrar'); }
  } else {
    if (!confirm('¿Salir de "' + lista.nombre + '"? Para volver vas a necesitar un link nuevo.')) return;
    try { await updateDoc(doc(db, 'listas', lista.id), { miembros: arrayRemove(user.uid), ['nombres.' + user.uid]: deleteField() }); store.set('lista', ''); }
    catch (e) { fail(e, 'salir'); }
  }
});

// ---------- invitar ----------
function newCode() {
  const a = new Uint8Array(18); crypto.getRandomValues(a);
  return btoa(String.fromCharCode(...a)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
$('invite').addEventListener('click', async () => {
  if (!lista) return;
  const code = newCode();
  try {
    await setDoc(doc(db, 'invitaciones', code), { lista: lista.id, nombreLista: lista.nombre, creadaPor: user.uid,
      vence: Timestamp.fromMillis(Date.now() + 7 * 864e5) });
  } catch (e) { fail(e, 'invitar'); return; }
  const link = location.origin + location.pathname + '?c=' + code;
  $('invLink').value = link;
  $('invWa').href = 'https://wa.me/?text=' + encodeURIComponent('Te invito a mi lista del súper "' + lista.nombre + '": ' + link);
  $('invBox').hidden = false;
});
$('invCopy').addEventListener('click', () => {
  const t = $('invLink'); const ok = () => { $('invCopy').textContent = 'Copiado'; setTimeout(() => { $('invCopy').textContent = 'Copiar link'; }, 2000); };
  try { navigator.clipboard.writeText(t.value).then(ok, () => { t.select(); }); } catch (e) { t.select(); }
});

// ---------- productos ----------
$('addForm').addEventListener('submit', async e => {
  e.preventDefault();
  const inp = $('addInput'); const t = cap(inp.value.trim()).slice(0, 80);
  if (!t || !listaId) return;
  inp.value = '';
  try { await addDoc(collection(db, 'listas', listaId, 'items'), { t, q: 1, d: false, o: Date.now(), por: user.uid }); }
  catch (er) { fail(er, 'agregar'); }
});
$('search').addEventListener('input', e => { q = e.target.value.trim(); renderItems(); });
$('clearDone').addEventListener('click', async () => {
  const done = (items || []).filter(i => i.d); if (!done.length) return;
  try { const b = writeBatch(db); done.forEach(i => b.delete(doc(db, 'listas', listaId, 'items', i.id))); await b.commit(); }
  catch (e) { fail(e, 'sacar tachados'); }
});

const upd = (id, data) => updateDoc(doc(db, 'listas', listaId, 'items', id), data).catch(e => fail(e, 'editar'));

function renderItems() {
  const box = $('items'); box.innerHTML = '';
  if (items === null) { box.className = 'list'; box.innerHTML = '<div class="nomatch">Cargando…</div>'; return; }
  box.className = 'list' + (items.length ? '' : ' empty');
  $('searchBox').hidden = items.length < 6;
  $('clearDone').hidden = !items.some(i => i.d);
  if (!items.length) { box.textContent = 'La lista está vacía. Agregá lo que hay que comprar.'; return; }
  const nq = norm(q);
  const shown = items.filter(i => !nq || norm(i.t).includes(nq)).sort((a, b) => (a.d - b.d) || (a.o - b.o));
  if (!shown.length) { const d = document.createElement('div'); d.className = 'nomatch'; d.textContent = 'No hay nada que diga "' + q + '".'; box.append(d); return; }
  for (const it of shown) {
    const row = document.createElement('div'); row.className = 'item' + (it.d ? ' done' : '');
    const cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = !!it.d; cb.id = 'i-' + it.id;
    cb.setAttribute('aria-label', 'Tachar ' + it.t);
    cb.addEventListener('change', () => {
      upd(it.id, { d: cb.checked, dt: cb.checked ? Date.now() : 0 });
      if (q) { q = ''; $('search').value = ''; renderItems(); }
    });
    const nm = document.createElement('label'); nm.className = 'name'; nm.htmlFor = cb.id; nm.textContent = it.t;
    const qv = it.q || 1, qb = document.createElement('div'); qb.className = 'qty'; qb.setAttribute('role', 'group'); qb.setAttribute('aria-label', 'Cantidad de ' + it.t);
    const mk = (txt, lab, dq) => { const b = document.createElement('button'); b.type = 'button'; b.textContent = txt; b.setAttribute('aria-label', lab);
      b.disabled = qv + dq < 1 || qv + dq > 99; b.addEventListener('click', () => upd(it.id, { q: qv + dq })); return b; };
    const n = document.createElement('span'); n.textContent = qv;
    qb.append(mk('−', 'Uno menos', -1), n, mk('+', 'Uno más', 1));
    const del = document.createElement('button'); del.type = 'button'; del.className = 'del' + (armed === it.id ? ' armed' : '');
    del.textContent = armed === it.id ? '¿Borrar?' : 'Borrar';
    del.addEventListener('click', () => {
      if (armed !== it.id) { armed = it.id; clearTimeout(armT); armT = setTimeout(() => { armed = null; renderItems(); }, 3000); renderItems(); return; }
      armed = null; deleteDoc(doc(db, 'listas', listaId, 'items', it.id)).catch(e => fail(e, 'borrar'));
    });
    row.append(cb, nm, qb, del); box.append(row);
  }
}
