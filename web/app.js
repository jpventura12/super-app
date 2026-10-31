// App del súper: login con Google, listas compartidas e invitaciones.
// La lista, los precios, las promos y el historial los dibuja el script de index.html;
// este módulo le conecta la lista elegida con window.__conectarLista(adapter, info).
import { initializeApp } from 'https://www.gstatic.com/firebasejs/10.14.1/firebase-app.js';
import { getAuth, GoogleAuthProvider, onAuthStateChanged, signInWithPopup, signInWithRedirect, getRedirectResult, signOut }
  from 'https://www.gstatic.com/firebasejs/10.14.1/firebase-auth.js';
import { initializeFirestore, persistentLocalCache, persistentMultipleTabManager, collection, doc, query, where,
  onSnapshot, addDoc, setDoc, getDoc, getDocs, updateDoc, deleteDoc, writeBatch, arrayUnion, arrayRemove, deleteField,
  serverTimestamp, Timestamp } from 'https://www.gstatic.com/firebasejs/10.14.1/firebase-firestore.js';
import { firebaseConfig } from './config.js';

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
// Caché local: la lista se ve y se puede tachar aunque en el súper no haya señal; se sincroniza al volver.
const db = initializeFirestore(app, { localCache: persistentLocalCache({ tabManager: persistentMultipleTabManager() }) });

const $ = id => document.getElementById(id);
const store = { get(k) { try { return localStorage.getItem('super-' + k); } catch (e) { return null; } },
                set(k, v) { try { localStorage.setItem('super-' + k, v); } catch (e) {} } };
const conectar = (a, info) => { if (window.__conectarLista) window.__conectarLista(a, info); };

let user = null, listas = [], listaId = null, lista = null, unsubListas = null, unsubLista = null;
const inviteCode = new URLSearchParams(location.search).get('c');

// Lo que el script de la página espera: collection('lista' | 'compras') con doc().set/update/delete y onSnapshot.
function adapter(id) {
  return {
    collection(name) {
      const c = collection(db, 'listas', id, name === 'lista' ? 'items' : name);
      return {
        doc(did) { const r = doc(c, did); return { set: d => setDoc(r, d), update: d => updateDoc(r, d), delete: () => deleteDoc(r) }; },
        onSnapshot(next, err) { return onSnapshot(c, next, err); }
      };
    }
  };
}

function show(view) { for (const v of ['vLoading', 'vLogin', 'vJoin', 'vApp']) $(v).hidden = v !== view; }
function fail(e, where) {
  console.error(where, e);
  $('shErr').textContent = e && e.code === 'permission-denied' ? 'No tenés permiso para hacer eso en esta lista.' : 'Algo salió mal. Probá de nuevo.';
  setTimeout(() => { $('shErr').textContent = ''; }, 6000);
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
  if (unsubListas) unsubListas(); if (unsubLista) unsubLista();
  unsubListas = unsubLista = null; listas = []; listaId = null; lista = null; conectar(null);
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
  let inv = null;
  try { const s = await getDoc(doc(db, 'invitaciones', code)); inv = s.exists() ? s.data() : null; } catch (e) {}
  if (!inv) { $('joinText').textContent = 'Este link no existe o ya no sirve. Pedile a quien te lo mandó uno nuevo.'; return; }
  if (inv.vence && inv.vence.toMillis() < Date.now()) { $('joinText').textContent = 'Este link venció. Pedile a quien te lo mandó uno nuevo.'; return; }
  try { const ls = await getDoc(doc(db, 'listas', inv.lista)); if (ls.exists()) { leaveJoin(inv.lista); return; } } catch (e) {}  // ya soy miembro
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
function leaveJoin(id) { history.replaceState(null, '', location.pathname); store.set('lista', id); startApp(id); }
$('joinNo').addEventListener('click', () => { history.replaceState(null, '', location.pathname); startApp(); });

// ---------- listas ----------
function startApp(prefer) {
  show('vApp');
  unsubListas = onSnapshot(query(collection(db, 'listas'), where('miembros', 'array-contains', user.uid)), snap => {
    listas = snap.docs.map(d => ({ id: d.id, ...d.data() })).sort((a, b) => a.nombre.localeCompare(b.nombre, 'es'));
    const want = prefer || listaId || store.get('lista'); prefer = null;
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
  $('listSel').hidden = !listas.length; $('newList').hidden = !listas.length;
  $('noLists').hidden = !!listas.length;
}
$('listSel').addEventListener('change', e => openList(e.target.value));

function openList(id) {
  if (unsubLista) unsubLista(); unsubLista = null;
  listaId = id; lista = null; $('invBox').hidden = true; $('listView').hidden = !id;
  if (!id) { conectar(null); return; }
  store.set('lista', id); $('listSel').value = id;
  const l = listas.find(x => x.id === id);
  conectar(adapter(id), { nombre: l ? l.nombre : '' });
  setDoc(doc(db, 'usuarios', user.uid), { ultima: id }, { merge: true }).catch(() => {});
  unsubLista = onSnapshot(doc(db, 'listas', id), s => {
    if (!s.exists()) return;
    lista = { id: s.id, ...s.data() }; renderHead();
  }, () => {});
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
  if (window.__nombreLista) window.__nombreLista(lista.nombre);
  $('invite').hidden = !owner;
  $('leave').textContent = owner ? 'Borrar lista' : 'Salir de la lista';
  const m = $('members'); m.innerHTML = '';
  const names = lista.nombres || {};
  if (lista.miembros.length < 2) { m.textContent = owner ? 'Solo vos. Tocá "Invitar a esta lista" para compartirla.' : ''; return; }
  m.append('Comparten: ');
  lista.miembros.forEach((uid, i) => {
    const s = document.createElement('span'); s.className = 'sh-mem';
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
    if (!confirm('¿Borrar "' + lista.nombre + '" para todos, con sus productos y su historial? No se puede deshacer.')) return;
    try {
      for (const sub of ['items', 'compras']) {
        const s = await getDocs(collection(db, 'listas', lista.id, sub));
        for (let i = 0; i < s.docs.length; i += 400) {
          const b = writeBatch(db); s.docs.slice(i, i + 400).forEach(d => b.delete(d.ref)); await b.commit();
        }
      }
      await deleteDoc(doc(db, 'listas', lista.id)); store.set('lista', '');
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
  try { navigator.clipboard.writeText(t.value).then(ok, () => t.select()); } catch (e) { t.select(); }
});
