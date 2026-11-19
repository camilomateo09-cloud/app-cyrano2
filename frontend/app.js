const state = {
  user: null,
  selectedProduct: null,
  entries: [],
  isAdmin: false,
  sessionId: null,
  unsynced: new Set(), // P06: pendientes que no se pudieron guardar en el servidor
  reception: null, // P02: recepción abierta del usuario
  editingId: null, // P07: pendiente que se está corrigiendo
  providerNames: [],
};

const elements = {
  loginSection: document.getElementById("loginSection"),
  mainSection: document.getElementById("mainSection"),
  userBadge: document.getElementById("userBadge"),
  userName: document.getElementById("userName"),
  todayDate: document.getElementById("todayDate"),
  usuarioInput: document.getElementById("usuario"),
  claveInput: document.getElementById("clave"),
  loginForm: document.getElementById("loginForm"),
  loginButton: document.getElementById("loginButton"),
  logoutButton: document.getElementById("logoutButton"),
  loginMessage: document.getElementById("loginMessage"),
  barcodeInput: document.getElementById("barcodeInput"),
  searchBarcodeButton: document.getElementById("searchBarcodeButton"),
  scannerResult: document.getElementById("scannerResult"),
  scannerActions: document.getElementById("scannerActions"),
  scannerQty: document.getElementById("scannerQty"),
  scannerLote: document.getElementById("scannerLote"),
  scannerCaducidad: document.getElementById("scannerCaducidad"),
  saveScannerButton: document.getElementById("saveScannerButton"),
  autocompleteDropdown: document.getElementById("autocompleteDropdown"),
  onlyNoBarcode: document.getElementById("onlyNoBarcode"),
  filterLote: document.getElementById("filterLote"),
  filterCaducidad: document.getElementById("filterCaducidad"),
  clearFiltersButton: document.getElementById("clearFiltersButton"),
  labelsList: document.getElementById("labelsList"),
  printTestMode: document.getElementById("printTestMode"),
  printerConfig: document.getElementById("printerConfig"),
  zplPreview: document.getElementById("zplPreview"),
  printLabelsButton: document.getElementById("printLabelsButton"),
  previewLabelsButton: document.getElementById("previewLabelsButton"),
  closePreviewButton: document.getElementById("closePreviewButton"),
  bulkButton: document.getElementById("bulkButton"),
  labelPreviewContainer: document.getElementById("labelPreviewContainer"),
  pendingEntries: document.getElementById("pendingEntries"),
  entriesTableBody: document.getElementById("entriesTableBody"),
  adminTab: document.getElementById("adminTab"),
  adminIntro: document.getElementById("adminIntro"),
  adminSummary: document.getElementById("adminSummary"),
  refreshAdminButton: document.getElementById("refreshAdminButton"),
  adminUserFilter: document.getElementById("adminUserFilter"),
  statusBar: document.getElementById("statusBar"),
  statusIcon: document.getElementById("statusIcon"),
  statusText: document.getElementById("statusText"),
  statusClose: document.getElementById("statusClose"),
  appDialog: document.getElementById("appDialog"),
  appDialogTitle: document.getElementById("appDialogTitle"),
  appDialogText: document.getElementById("appDialogText"),
  appDialogActions: document.getElementById("appDialogActions"),
  topAlerts: document.getElementById("topAlerts"),
  offlineBanner: document.getElementById("offlineBanner"),
  offlineDetail: document.getElementById("offlineDetail"),
  retryButton: document.getElementById("retryButton"),
  receptionCard: document.getElementById("receptionCard"),
  receptionNew: document.getElementById("receptionNew"),
  receptionOpen: document.getElementById("receptionOpen"),
  recProveedor: document.getElementById("recProveedor"),
  recProveedores: document.getElementById("recProveedores"),
  recDocTipo: document.getElementById("recDocTipo"),
  recDocNumero: document.getElementById("recDocNumero"),
  recLlegada: document.getElementById("recLlegada"),
  openReceptionButton: document.getElementById("openReceptionButton"),
  recCounts: document.getElementById("recCounts"),
  recProveedorText: document.getElementById("recProveedorText"),
  recDocText: document.getElementById("recDocText"),
  recLlegadaText: document.getElementById("recLlegadaText"),
  recInicioText: document.getElementById("recInicioText"),
  recFinText: document.getElementById("recFinText"),
  startUnloadButton: document.getElementById("startUnloadButton"),
  closeReceptionButton: document.getElementById("closeReceptionButton"),
  receptionActions: document.querySelector(".reception-actions"),
  exportDesde: document.getElementById("exportDesde"),
  exportHasta: document.getElementById("exportHasta"),
  exportButton: document.getElementById("exportButton"),
  actionBar: document.getElementById("actionBar"),
  confirmBarButton: document.getElementById("confirmBarButton"),
  pendingSection: document.getElementById("pendingSection"),
  pendingCount: document.getElementById("pendingCount"),
  pendingCards: document.getElementById("pendingCards"),
  scannerEstadoGroup: document.getElementById("scannerEstadoGroup"),
  statusAction: document.getElementById("statusAction"),
  cancelEditButton: document.getElementById("cancelEditButton"),
  confirmBox: document.getElementById("confirmBox"),
  confirmBoxCount: document.getElementById("confirmBoxCount"),
};

// ---------- P01 · Mensajes y respuesta del sistema ----------
// Antes todos los avisos se escribían en #loginMessage, que queda oculto al entrar:
// el operador tocaba «Guardar» y no veía nada (FH 1). Ahora van a una barra fija.
// P11 / U23: íconos propios (SVG) en lugar de emojis, que cambian según la versión de Android.
const svg = (path) => `<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${path}</svg>`;
const ICONS = {
  ok: svg('<path d="M4 12.5l5 5L20 6.5"/>'),
  error: svg('<circle cx="12" cy="12" r="9"/><path d="M9 9l6 6M15 9l-6 6"/>'),
  warn: svg('<path d="M12 3.5L2.5 20h19z"/><path d="M12 10v4.5M12 17.5v.01"/>'),
  info: svg('<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5M12 7.5v.01"/>'),
  busy: svg('<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'),
  print: svg('<path d="M7 9V3.5h10V9"/><rect x="3.5" y="9" width="17" height="8" rx="1.5"/><path d="M7 14h10v6.5H7z"/>'),
};
const STATUS_ICONS = ICONS;
let statusTimer = null;

function notify(text, type = "info", options = {}) {
  window.clearTimeout(statusTimer);
  const bar = elements.statusBar;
  bar.className = `status-bar status-${type}`;
  bar.setAttribute("aria-live", type === "error" ? "assertive" : "polite");
  elements.statusIcon.innerHTML = STATUS_ICONS[type] || ""; // SVG fijo de la app
  elements.statusText.textContent = text;
  // P07 / FH 23: acción opcional en el aviso (p. ej. «Deshacer» después de quitar).
  const action = options.action;
  elements.statusAction.classList.toggle("hidden", !action);
  elements.statusAction.onclick = action ? () => { clearStatus(); action.run(); } : null;
  if (action) elements.statusAction.textContent = action.label;
  // Los avisos de éxito se van solos; los errores y advertencias se quedan hasta la siguiente acción.
  if (!options.persist && (type === "ok" || type === "info")) {
    statusTimer = window.setTimeout(clearStatus, options.action ? 9000 : 6000);
  }
}

function clearStatus() {
  window.clearTimeout(statusTimer);
  elements.statusBar.classList.add("hidden");
}

// Compatibilidad con las llamadas anteriores.
function showMessage(_element, text, isError = false) {
  notify(text, isError ? "error" : "ok");
}

// Marca el campo que falta, lo lleva a la vista y explica qué hacer.
function markInvalid(input, text) {
  input.classList.add("invalid");
  input.setAttribute("aria-invalid", "true");
  notify(text, "error");
  scrollBelowStatus(document.querySelector(`label[for="${input.id}"]`) || input);
  input.focus({ preventScroll: true });
}

function clearInvalid(input) {
  input.classList.remove("invalid");
  input.removeAttribute("aria-invalid");
}

// Bloquea el botón y cambia su texto mientras se espera al servidor (U12).
async function withBusy(button, busyText, task) {
  const original = button.innerHTML; // conserva los íconos SVG del botón (P11)
  button.disabled = true;
  button.textContent = busyText;
  try {
    return await task();
  } finally {
    button.disabled = false;
    button.innerHTML = original;
  }
}

// fetch con mensaje claro cuando no hay respuesta del servidor.
async function apiFetch(url, options = {}) {
  // P21: toda petición lleva la sesión en la cabecera X-Session-Id.
  const headers = new Headers(options.headers || {});
  if (state.sessionId) headers.set("X-Session-Id", state.sessionId);
  let response;
  try {
    response = await fetch(url, { ...options, headers });
  } catch (error) {
    setOnline(false);
    throw new Error("No hay conexión. Revisa el Wi-Fi e intenta de nuevo.");
  }
  if (!connection.online) setOnline(true);
  // Sesión vencida o no válida: volver a la pantalla de clave (los pendientes quedan en el servidor).
  if (response.status === 401 && state.user && !url.startsWith("/api/login")) {
    resetToLogin();
    notify("La sesión venció o no es válida. Vuelve a entrar con tu PIN; tus pendientes siguen guardados.", "error");
    throw new Error("La sesión venció. Vuelve a entrar con tu PIN.");
  }
  return response;
}

// ---------- P14 · Aviso sin conexión ----------
// U4: antes, si se caía la red no pasaba nada en pantalla. Ahora hay un aviso fijo,
// un botón «Reintentar», revisión automática cada 10 s y, al volver la red, se suben
// los pendientes que no habían llegado al servidor.
const connection = { online: true, timer: null };

function setOnline(isOnline, detail) {
  const changed = connection.online !== isOnline;
  connection.online = isOnline;
  if (!isOnline) {
    elements.offlineDetail.textContent = detail || (navigator.onLine === false
      ? "El equipo no tiene Wi-Fi. Buscar y confirmar no funcionan; lo que ya agregaste no se pierde."
      : "Sin conexión: buscar y confirmar no funcionan por ahora. Lo que ya agregaste no se pierde.");
    elements.offlineBanner.classList.remove("hidden");
    if (!connection.timer) connection.timer = window.setInterval(checkServer, 10000);
    return;
  }
  elements.offlineBanner.classList.add("hidden");
  window.clearInterval(connection.timer);
  connection.timer = null;
  if (changed) onReconnect();
}

async function checkServer() {
  try {
    const response = await fetch("/api/health", { cache: "no-store" });
    if (!response.ok) throw new Error();
    setOnline(true);
    return true;
  } catch (error) {
    setOnline(false);
    return false;
  }
}

async function onReconnect() {
  const pendingToSync = pendingList().filter((entry) => state.unsynced.has(String(entry.id)));
  if (!state.user || !pendingToSync.length) {
    notify("Conexión recuperada.", "ok");
    return;
  }
  let ok = 0;
  for (const entry of pendingToSync) {
    if (await syncPending(entry)) ok += 1;
  }
  notify(`Conexión recuperada. ${ok} pendiente(s) quedaron a salvo.`, ok === pendingToSync.length ? "ok" : "warn");
}

async function retryConnection() {
  const ok = await withBusy(elements.retryButton, "Probando…", checkServer);
  if (!ok) notify("Todavía sin conexión. Revisa el Wi-Fi y vuelve a intentar.", "error");
}

// Lleva la pantalla hasta la tarjeta y la resalta, para que se note que algo cambió (FH 2).
function revealCard(container, className = "found") {
  container.classList.remove("found", "not-found");
  void container.offsetWidth; // reinicia la animación si se escanea dos veces seguidas
  container.classList.add(className);
  // P04: se deja arriba la fila de escaneo; debajo caben la tarjeta, el formulario y «Guardar».
  scrollBelowStatus(container === elements.scannerResult ? document.querySelector(".scan-row") : container);
}

// Desplaza hasta el elemento dejando espacio para la barra de mensajes fija.
function scrollBelowStatus(element) {
  const alertsHeight = elements.topAlerts.offsetHeight;
  const barSpace = alertsHeight ? alertsHeight + 20 : 12;
  const top = element.getBoundingClientRect().top + window.scrollY - barSpace;
  window.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
}

function showTab(target) {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.target === target);
  });
  document.querySelectorAll(".panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === target);
  });
  if (target === "scannerPanel") focusScanner();
  updateActionBar();
}

// Formato único de presentación del producto: siempre [código] — [nombre].
function formatProducto(codigo, nombre) {
  return `${codigo || "—"} — ${nombre || ""}`.trim();
}

// ---------- P05 · Cantidad, unidad y conversión ----------
// Regla del catálogo (hoja Reglas_validacion, D9):
//   cantidad en unidad de planta = cantidad que llega × unidades por empaque × factor.
// Antes se usaba solo cantidad × factor (R1): 1 caja de 6 × 3,785 L quedaba en 3,785 L.
const numberFormat = new Intl.NumberFormat("es-EC", { maximumFractionDigits: 3 });

function fmtNum(value) {
  return numberFormat.format(Number(value) || 0);
}

function unitText(unit) {
  const u = (unit || "").toLowerCase();
  return { l: "L", unid: "unid.", unidad: "unid." }[u] || unit || "";
}

function pluralUnit(unit, quantity = 2) {
  if (!unit) return "";
  if (unit === "lamina") return Number(quantity) === 1 ? "lámina" : "láminas";
  if (Number(quantity) === 1) return unit;
  return /[aeiou]$/i.test(unit) ? `${unit}s` : `${unit}es`;
}

function packSize(product) {
  const n = Number(product.cantidad_por_caja);
  return n > 0 ? n : 1;
}

function convertQty(quantity, product) {
  const value = Number(quantity) * packSize(product) * Number(product.factor_conversion);
  return Math.round(value * 1000) / 1000;
}

// «× 6 × 3,785 L»: cómo se llega a la cantidad en unidad de planta (se omiten los 1).
function conversionFactors(product) {
  const parts = [];
  const pack = packSize(product);
  const factor = Number(product.factor_conversion);
  if (pack !== 1) parts.push(fmtNum(pack));
  if (factor !== 1) parts.push(`${fmtNum(factor)} ${unitText(product.unidad_planta)}`);
  return parts;
}

// Pone la unidad junto al campo y en la etiqueta: «Cantidad que llega (cajas) *».
function setQtyUnit(prefix, product) {
  document.getElementById(`${prefix}QtyLabel`).textContent =
    `Cantidad (${pluralUnit(product.unidad_llega)}) *`;
  document.getElementById(`${prefix}QtyUnit`).textContent = pluralUnit(product.unidad_llega);
}

// Recalcula la conversión cada vez que se escribe la cantidad.
function updateConversion(prefix) {
  const line = document.getElementById(`${prefix}Conversion`);
  const product = state.selectedProduct;
  if (!product) {
    line.textContent = "";
    line.classList.remove("has-value");
    return;
  }
  const qty = Number(document.getElementById(`${prefix}Qty`).value);
  const plant = unitText(product.unidad_planta);
  if (!qty || qty <= 0) {
    line.classList.remove("has-value");
    line.textContent = `Escribe la cantidad para ver cuánto es en ${plant}.`;
    return;
  }
  const factors = conversionFactors(product);
  const detail = factors.length
    ? `${fmtNum(qty)} ${pluralUnit(product.unidad_llega, qty)} × ${factors.join(" × ")}`
    : "";
  line.classList.add("has-value");
  line.innerHTML = `= <strong>${escapeHtml(fmtNum(convertQty(qty, product)))} ${escapeHtml(plant)}</strong>` +
    (detail ? `<span class="conversion-detail">${escapeHtml(detail)}</span>` : "");
}

// ---------- P20 · Reglas de validación (las mismas que backend/reglas.py) ----------
// El servidor es el que manda; aquí se repiten para avisar al tocar «Guardar» y no
// recién al confirmar toda la lista.
const REGLAS = {
  topeCantidad: 10000,          // SUPUESTO: tope general en la unidad de llegada
  loteMax: 30,
  lotePatron: /^[A-Z0-9][A-Z0-9\-/.]*$/,
  tempMin: -30, tempMax: 60,
  tempOkMin: -25, tempOkMax: 25, // SUPUESTO: hasta tener tipo de bodega en el catálogo
  diasMinVencimiento: 30,        // SUPUESTO (P08): aviso si vence antes; Cyrano define el valor
};

// ---------- P08 · Validaciones de uso ----------
function daysUntil(isoDate) {
  const [y, m, d] = isoDate.split("-").map(Number);
  const hoy = new Date();
  const a = Date.UTC(hoy.getFullYear(), hoy.getMonth(), hoy.getDate());
  return Math.round((Date.UTC(y, m - 1, d) - a) / 86400000);
}

const fechaLarga = new Intl.DateTimeFormat("es-EC", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });

// FH 14: la fecha se muestra en palabras (evita confundir día y mes) con los días que faltan.
function updateCaducidadHint() {
  const hint = document.getElementById("scannerCadHint");
  const value = elements.scannerCaducidad.value;
  hint.className = "field-hint";
  if (!value) { hint.textContent = ""; return; }
  const dias = daysUntil(value);
  const [y, m, d] = value.split("-").map(Number);
  const texto = fechaLarga.format(new Date(Date.UTC(y, m - 1, d)));
  if (dias <= 0) {
    hint.textContent = `${texto} · ya venció`;
    hint.classList.add("hint-error");
  } else if (dias < REGLAS.diasMinVencimiento) {
    hint.textContent = `${texto} · vence en ${dias} día(s): menos de ${REGLAS.diasMinVencimiento}`;
    hint.classList.add("hint-warn");
  } else {
    hint.textContent = `${texto} · vence en ${dias} días`;
  }
}

// FH 18: limpia todo el formulario al cambiar de producto (antes quedaban el lote y la caducidad).
function resetProductForm() {
  elements.scannerLote.classList.remove("from-code");
  elements.scannerCaducidad.classList.remove("from-code");
  elements.scannerQty.value = "";
  elements.scannerLote.value = "";
  elements.scannerCaducidad.value = "";
  resetQc("scanner");
  document.querySelector(".qc-details")?.removeAttribute("open");
  ["scannerQty", "scannerLote", "scannerCaducidad", "scannerEstadoGroup"].forEach((id) => clearInvalid(document.getElementById(id)));
  updateCaducidadHint();
}

// ¿Hay datos escritos que se perderían al cambiar de producto?
function productFormDirty() {
  if (!state.selectedProduct || elements.scannerActions.classList.contains("hidden")) return false;
  return Boolean(elements.scannerQty.value || elements.scannerLote.value || elements.scannerCaducidad.value || qcEl("scanner", "EstadoQc").value);
}

async function confirmDiscard() {
  if (!productFormDirty()) return true;
  const actual = state.selectedProduct;
  const choice = await askDialog({
    title: state.editingId ? "Hay cambios sin guardar" : "Hay datos sin guardar",
    text: `${formatProducto(actual.codigo_cyrano, actual.nombre_producto)} tiene datos escritos que no se guardaron. Si cambias de producto, se borran.`,
    actions: [
      { label: "Seguir con este producto", value: "keep" },
      { label: "Descartar y cambiar", value: "discard", variant: "secondary" },
    ],
  });
  return choice === "discard";
}

// FH 19 / R6: si el código de barras está en varios productos, se elige el que llegó.
async function chooseProduct(products, barcode) {
  const choice = await askDialog({
    title: `El código ${barcode} está en ${products.length} productos`,
    text: "Elige la presentación que llegó: mira en la etiqueta si es la unidad suelta, el paquete o la caja.",
    actions: [
      ...products.map((p, i) => ({ label: `${p.codigo_cyrano} — ${p.nombre_producto} (1 ${p.unidad_llega} = ${fmtNum(convertQty(1, p))} ${unitText(p.unidad_planta)})`, value: String(i), variant: "btn-outline choice-button" })),
      { label: "Cancelar", value: "cancel", variant: "link" },
    ],
  });
  return choice === "cancel" ? null : products[Number(choice)] || null;
}

function normalizarLote(valor) {
  return (valor || "").trim().toUpperCase();
}

// Id único por línea, creado en la tablet: el servidor ignora el reenvío de la misma
// línea (doble toque) pero guarda dos líneas iguales y legítimas (D11).
function newLineId() {
  return Date.now() * 1000 + Math.floor(Math.random() * 1000);
}

// ---------- Control de calidad (QC) ----------
// QC genérico para todos los productos. Los campos viven en cada panel (scanner|provider)
// con IDs prefijados, así que se leen/limpian por prefijo.
//
// FUTURO — QC por producto: aquí se resolvería una plantilla por ArticuloID
// (state.selectedProduct.id) para pintar checks específicos del producto en vez de
// los genéricos; el resto del flujo (semáforo, bloqueo, guardado) no cambiaría.
const QC_ESTADO_CONFIRMABLE = "aprobado";

function qcEl(prefix, name) {
  return document.getElementById(prefix + name);
}

function readQc(prefix) {
  const temp = qcEl(prefix, "TempRecepcion").value;
  return {
    estado_qc: qcEl(prefix, "EstadoQc").value,
    responsable_qc: qcEl(prefix, "ResponsableQc").value.trim(),
    observaciones_qc: qcEl(prefix, "ObservacionesQc").value.trim(),
    empaque_ok: qcEl(prefix, "EmpaqueOk").checked,
    sin_humedad: qcEl(prefix, "SinHumedad").checked,
    temperatura_ok: qcEl(prefix, "TemperaturaOk").checked,
    aspecto_olor_ok: qcEl(prefix, "AspectoOlorOk").checked,
    documentacion_proveedor_ok: qcEl(prefix, "DocProveedorOk").checked,
    temperatura_recepcion: temp === "" ? null : Number(temp),
    // P16: el motivo solo va si el lote no queda aprobado.
    motivo_qc: qcEl(prefix, "EstadoQc").value && qcEl(prefix, "EstadoQc").value !== QC_ESTADO_CONFIRMABLE
      ? qcEl(prefix, "MotivoQc").value.trim() : "",
  };
}

function resetQc(prefix) {
  qcEl(prefix, "EstadoQc").value = "";
  // P12 / FH 17: el responsable de calidad se llena con quien entró a la app (se puede cambiar).
  qcEl(prefix, "ResponsableQc").value = state.user?.nombre || "";
  qcEl(prefix, "ObservacionesQc").value = "";
  ["EmpaqueOk", "SinHumedad", "TemperaturaOk", "AspectoOlorOk", "DocProveedorOk"]
    .forEach((n) => { qcEl(prefix, n).checked = false; });
  qcEl(prefix, "TempRecepcion").value = "";
  qcEl(prefix, "MotivoQc").value = "";
  updateSemaforo(prefix);
}

// Semáforo en el formulario: verde (aprobado), amarillo (cuarentena), rojo (rechazado).
function updateSemaforo(prefix) {
  const estado = qcEl(prefix, "EstadoQc").value;
  const sem = qcEl(prefix, "Semaforo");
  sem.className = "semaforo " + (estado ? `semaforo-${estado}` : "semaforo-vacio");
  sem.title = estado ? `Calidad: ${estado}` : "Estado de calidad";
  // P04: estado en tres botones (un toque); el select oculto sigue siendo el valor.
  document.querySelectorAll(`#${prefix}EstadoGroup .seg`).forEach((button) => {
    const on = button.dataset.estado === estado;
    button.classList.toggle("is-on", on);
    button.setAttribute("aria-checked", on ? "true" : "false");
  });
  // P16: al elegir cuarentena o rechazado se avisa qué significa y se pide el motivo.
  const box = qcEl(prefix, "MotivoBox");
  if (box) {
    const aviso = AVISOS_QC[estado];
    box.classList.toggle("hidden", !aviso);
    box.classList.toggle("is-rechazado", estado === "rechazado");
    qcEl(prefix, "QcAviso").innerHTML = aviso || "";
    qcEl(prefix, "MotivoLabel").textContent = estado === "rechazado" ? "Motivo del rechazo *" : "Motivo de la cuarentena *";
  }
}

const AVISOS_QC = {
  cuarentena: "<strong>Cuarentena:</strong> se registra, pero <strong>no queda disponible</strong> hasta que se libere. Sepáralo del resto y avisa al supervisor.",
  rechazado: "<strong>Rechazado:</strong> se registra con su motivo y <strong>no entra al inventario</strong>. No lo guardes junto a lo aprobado.",
};

// Badge de estado QC con su color para la tabla y la trazabilidad.
function qcBadge(estado) {
  const e = (estado || "").toLowerCase();
  const clase = e === "aprobado" ? "qc-aprobado"
    : e === "cuarentena" ? "qc-cuarentena"
    : e === "rechazado" ? "qc-rechazado" : "qc-sin";
  const texto = e ? e.charAt(0).toUpperCase() + e.slice(1) : "Sin estado";
  return `<span class="qc-badge ${clase}">${escapeHtml(texto)}</span>`;
}

// P16: motivo de cuarentena/rechazo y, si la cuarentena se resolvió, quién y por qué.
function qcNote(entry) {
  const partes = [];
  if (entry.motivo_qc) partes.push(escapeHtml(entry.motivo_qc));
  if (entry.qc_resuelto_por) {
    const verbo = (entry.estado_qc || "").toLowerCase() === "aprobado" ? "Liberado" : "Rechazado";
    partes.push(`${verbo} por ${escapeHtml(entry.qc_resuelto_por)} a las ${escapeHtml(hhmm(entry.qc_resuelto_at))}: ${escapeHtml(entry.qc_resolucion || "")}`);
  }
  return partes.length ? `<span class="qc-note">${partes.join("<br>")}</span>` : "";
}

// ---------- P12 / U3 · Ayudas cortas al tocar un campo ----------
// Una sola línea gris debajo del campo que se está usando: ayuda a quien recién empieza
// sin alargar el formulario para quien ya sabe (se muestra solo la del campo enfocado).
const AYUDAS = {
  usuario: "Tu nombre, como te lo dio el supervisor.",
  clave: "Los 6 números que te entregaron. No los compartas.",
  recProveedor: "Escribe parte del nombre y elige de la lista. Si no está, escríbelo completo.",
  recDocNumero: "El número que está en la factura o en la guía de remisión.",
  recLlegada: "La hora en que llegó el camión a la planta, no la hora en que empiezan a descargar.",
  barcodeInput: "Escanea la etiqueta. Si no tiene código, escribe parte del nombre.",
  scannerQty: "En la unidad del proveedor.",
  scannerLote: "Como está en la etiqueta o en la caja.",
  scannerCaducidad: "La fecha de vencimiento de la etiqueta. Si solo trae mes y año, pon el último día de ese mes.",
  scannerMotivoQc: "Por qué no se aprueba. Elige un motivo de arriba o escríbelo.",
  scannerResponsableQc: "Ya está tu nombre. Cámbialo si revisó otra persona.",
  scannerTempRecepcion: "Solo si el producto se recibe frío o congelado.",
};

function showFieldHelp(input) {
  const texto = AYUDAS[input.id];
  if (!texto) return;
  let hint = document.getElementById(`${input.id}Ayuda`);
  if (!hint) {
    hint = document.createElement("p");
    hint.id = `${input.id}Ayuda`;
    hint.className = "field-help";
    // Va debajo de la fila completa si el campo comparte fila (cantidad + unidad, tipo + número, escanear + Buscar).
    const ancla = input.closest(".qty-row, .doc-row, .scan-row") || input;
    ancla.insertAdjacentElement("afterend", hint);
    const previo = input.getAttribute("aria-describedby");
    input.setAttribute("aria-describedby", previo ? `${previo} ${hint.id}` : hint.id);
  }
  hint.textContent = texto;
  hint.hidden = false;
}

// La ayuda NO se cierra al salir del campo: si se cerrara, lo de abajo subiría justo cuando
// el dedo toca un botón (p. ej. «Abrir recepción») y el toque caería en otro lado.
// Se cierra cuando se toca otro campo con ayuda.
function setupFieldHelp() {
  Object.keys(AYUDAS).forEach((id) => {
    const input = document.getElementById(id);
    if (!input) return;
    input.addEventListener("focus", () => {
      document.querySelectorAll(".field-help").forEach((h) => { if (h.id !== `${id}Ayuda`) h.hidden = true; });
      showFieldHelp(input);
    });
  });
}

// ---------- P06 · No perder trabajo ----------
const SESSION_KEY = "cyrano.sesion";

function isPendingEntry(entry) {
  return Boolean(entry.id) && String(entry.id).length > 8;
}

function pendingList() {
  return state.entries.filter(isPendingEntry);
}

// Recuerda la sesión en esta pestaña: recargar la página ya no saca al operador.
function saveSession() {
  try {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify({ user: state.user, sessionId: state.sessionId }));
  } catch (error) { /* almacenamiento no disponible: solo se pierde la comodidad */ }
}

function clearSession() {
  try { sessionStorage.removeItem(SESSION_KEY); } catch (error) { /* nada */ }
}

function readSession() {
  try { return JSON.parse(sessionStorage.getItem(SESSION_KEY) || "null"); } catch (error) { return null; }
}

// Diálogo propio. Devuelve el valor del botón tocado ("cancel" si se cierra).
// Con `input`, muestra un campo de texto (p. ej. el motivo de una anulación) y
// devuelve { value, text }; los botones con requiresInput exigen el largo mínimo.
function askDialog({ title, text, actions, input = null, html = null }) {
  return new Promise((resolve) => {
    const dialog = elements.appDialog;
    elements.appDialogTitle.textContent = title;
    if (html !== null) elements.appDialogText.innerHTML = html; // armado con escapeHtml
    else elements.appDialogText.textContent = text;
    elements.appDialogText.classList.toggle("is-html", html !== null);
    elements.appDialogActions.innerHTML = "";
    dialog.querySelector(".dialog-field")?.remove();
    let field = null;
    let fieldError = null;
    if (input) {
      const wrap = document.createElement("div");
      wrap.className = "dialog-field";
      const label = document.createElement("label");
      label.textContent = input.label;
      label.htmlFor = "appDialogInput";
      field = document.createElement("textarea");
      field.id = "appDialogInput";
      field.rows = 3;
      field.maxLength = input.maxLength || 300;
      field.placeholder = input.placeholder || "";
      fieldError = document.createElement("p");
      fieldError.className = "dialog-field-error";
      field.addEventListener("input", () => { field.classList.remove("invalid"); fieldError.textContent = ""; });
      wrap.append(label, field, fieldError);
      elements.appDialogActions.before(wrap);
    }
    actions.forEach((action) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = action.label;
      if (action.variant) button.className = action.variant;
      button.addEventListener("click", () => {
        if (action.requiresInput && field && field.value.trim().length < (input.minLength || 1)) {
          field.classList.add("invalid");
          fieldError.textContent = input.minLengthMessage || `Escribe al menos ${input.minLength} caracteres.`;
          field.focus();
          return;
        }
        dialog.close(action.value);
      });
      elements.appDialogActions.appendChild(button);
    });
    dialog.addEventListener("close", () => {
      const value = dialog.returnValue || "cancel";
      resolve(input ? { value, text: field.value.trim() } : value);
    }, { once: true });
    dialog.returnValue = "";
    dialog.showModal();
    if (field) field.focus();
  });
}

// Guarda (o actualiza) un pendiente en el servidor.
async function syncPending(entry) {
  try {
    const response = await apiFetch(`/api/pending/${encodeURIComponent(entry.id)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: state.sessionId, datos: entry }),
    });
    if (!response.ok) throw new Error();
    state.unsynced.delete(String(entry.id));
    return true;
  } catch (error) {
    state.unsynced.add(String(entry.id));
    return false;
  }
}

// Trae los pendientes guardados del usuario (al entrar o al recargar).
async function loadPending() {
  const response = await apiFetch(`/api/pending?session_id=${encodeURIComponent(state.sessionId)}`);
  if (response.status === 401) {
    const error = new Error("La sesión venció. Vuelve a entrar con tu PIN.");
    error.sessionExpired = true;
    throw error;
  }
  if (!response.ok) throw new Error("No se pudieron cargar los pendientes guardados.");
  const pending = await response.json();
  state.entries = [...pending.filter(isPendingEntry), ...state.entries.filter((e) => !isPendingEntry(e))];
  return pending.length;
}

// ¿Hay un producto a medio llenar en el formulario?
function formHasData() {
  if (!state.selectedProduct) return false;
  return ["scanner"].some((prefix) =>
    document.getElementById(`${prefix}Qty`).value || document.getElementById(`${prefix}Lote`).value);
}

// Botón atrás de Android (U13): dentro de la app vuelve a la pantalla de escaneo
// en vez de salir; nunca saca al operador ni borra nada.
function armBackGuard() {
  history.pushState({ cyranoGuard: true }, "");
}

function onBackButton() {
  if (!state.user) return;
  if (elements.appDialog.open) {
    elements.appDialog.close("cancel");
  } else if (!document.getElementById("scannerPanel").classList.contains("active")) {
    showTab("scannerPanel");
  } else {
    const n = pendingList().length;
    notify(
      "Para salir usa el botón de apagado, arriba a la derecha." +
        (n ? ` Tus ${n} ingreso(s) pendientes están guardados.` : ""),
      "info"
    );
  }
  armBackGuard();
}

// Aviso del navegador antes de cerrar o recargar solo si algo se perdería de verdad:
// un producto a medio llenar o pendientes que no llegaron al servidor.
function onBeforeUnload(event) {
  if (!state.user) return;
  if (state.unsynced.size || formHasData()) {
    event.preventDefault();
    event.returnValue = "";
  }
}

// ---------- P02 · Recepción como unidad ----------
// U1: la app trabajaba producto por producto. Ahora primero se abre la recepción
// (proveedor, factura o guía, hora de llegada), los productos cuelgan de ella y al
// cerrarla se guarda la hora de fin. Las horas se guardan con zona (-05:00) en el servidor.

// "2026-11-10T08:15:00-05:00" → "08:15" (la hora ya viene en hora de Ecuador).
function hhmm(iso) {
  return iso ? String(iso).slice(11, 16) : "--:--";
}

function minutesBetween(a, b) {
  if (!a || !b) return null;
  return Math.round((new Date(b) - new Date(a)) / 60000);
}

function nowHHMM() {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function docLabel(tipo) {
  return tipo === "guia" ? "Guía de remisión" : "Factura";
}

function receptionPending() {
  if (!state.reception) return [];
  return pendingList().filter((entry) => Number(entry.recepcion_id) === Number(state.reception.id));
}

function renderReception() {
  const rec = state.reception;
  document.body.classList.toggle("no-reception", !rec);
  elements.receptionCard.classList.toggle("is-open", Boolean(rec));
  elements.receptionNew.classList.toggle("hidden", Boolean(rec));
  elements.receptionOpen.classList.toggle("hidden", !rec);
  if (!rec) {
    if (!elements.recLlegada.value) elements.recLlegada.value = nowHHMM();
    renderPendingCards();
    updateActionBar();
    return;
  }
  elements.recProveedorText.textContent = rec.proveedor;
  elements.recDocText.textContent = `${docLabel(rec.documento_tipo)} ${rec.documento_numero}`;
  elements.recLlegadaText.textContent = hhmm(rec.hora_llegada);
  elements.recInicioText.innerHTML = rec.hora_inicio_descarga
    ? `${hhmm(rec.hora_inicio_descarga)}${rec.inicio_automatico ? '<span class="time-auto">(con el 1.er producto)</span>' : ""}`
    : "--:--";
  elements.recFinText.textContent = hhmm(rec.hora_fin);
  elements.startUnloadButton.classList.toggle("hidden", Boolean(rec.hora_inicio_descarga));
  elements.receptionActions.style.gridTemplateColumns = rec.hora_inicio_descarga ? "1fr" : "1fr 1fr";
  const pend = receptionPending().length;
  elements.recCounts.textContent = `${pend} pendiente(s) · ${rec.ingresos_confirmados || 0} confirmado(s)`;
  renderPendingCards();
  updateActionBar();
}

async function loadReception() {
  try {
    const response = await apiFetch(`/api/recepciones/abierta?session_id=${encodeURIComponent(state.sessionId)}`);
    if (response.ok) state.reception = await response.json();
  } catch (error) { /* sin conexión: se mantiene lo último conocido */ }
  renderReception();
}

async function loadProviderList() {
  try {
    const response = await apiFetch("/api/proveedores");
    if (!response.ok) return;
    state.providerNames = await response.json();
    elements.recProveedores.innerHTML = state.providerNames
      .map((name) => `<option value="${escapeHtml(name)}"></option>`).join("");
  } catch (error) { /* el aviso de conexión ya está a la vista */ }
}

async function openReception() {
  const proveedor = elements.recProveedor.value.trim().replace(/\s+/g, " ");
  const numero = elements.recDocNumero.value.trim();
  const llegada = elements.recLlegada.value;
  if (!proveedor) { markInvalid(elements.recProveedor, "Falta el proveedor."); return; }
  if (!numero) { markInvalid(elements.recDocNumero, `Falta el número de la ${elements.recDocTipo.value === "guia" ? "guía" : "factura"}.`); return; }
  if (!llegada) { markInvalid(elements.recLlegada, "Falta la hora de llegada del camión."); return; }
  if (llegada > nowHHMM()) { markInvalid(elements.recLlegada, "La hora de llegada no puede ser futura."); return; }

  const known = state.providerNames.some((name) => name.toLowerCase() === proveedor.toLowerCase());
  if (state.providerNames.length && !known) {
    const choice = await askDialog({
      title: "Proveedor fuera de la lista",
      text: `«${proveedor}» no está en la lista de proveedores (compras de SAP). Revisa cómo está escrito o úsalo igual si es un proveedor nuevo.`,
      actions: [
        { label: "Corregir", value: "fix" },
        { label: "Usarlo igual", value: "use", variant: "secondary" },
      ],
    });
    if (choice !== "use") { elements.recProveedor.focus(); return; }
  }

  try {
    const response = await withBusy(elements.openReceptionButton, "Abriendo…", () => apiFetch("/api/recepciones", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: state.sessionId,
        proveedor,
        documento_tipo: elements.recDocTipo.value,
        documento_numero: numero,
        hora_llegada: llegada,
      }),
    }));
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "No se pudo abrir la recepción");
    state.reception = data;
    elements.recProveedor.value = "";
    elements.recDocNumero.value = "";
    elements.recLlegada.value = "";
    renderReception();
    notify(`Recepción abierta: ${data.proveedor} · ${docLabel(data.documento_tipo)} ${data.documento_numero}. Toca «Empezar descarga» y escanea los productos.`, "ok");
    focusScanner();
  } catch (error) {
    notify(error.message, "error");
  }
}

async function startUnload() {
  if (!state.reception) return;
  try {
    const response = await withBusy(elements.startUnloadButton, "Marcando…", () => apiFetch(`/api/recepciones/${state.reception.id}/inicio`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: state.sessionId }),
    }));
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "No se pudo marcar el inicio");
    state.reception = data;
    renderReception();
    notify(`Inicio de descarga: ${hhmm(data.hora_inicio_descarga)}.`, "ok");
    focusScanner();
  } catch (error) {
    notify(error.message, "error");
  }
}

async function closeReception() {
  const rec = state.reception;
  if (!rec) return;
  const pend = receptionPending().length;
  if (pend) {
    const choice = await askDialog({
      title: `Tienes ${pend} producto(s) sin confirmar`,
      text: "Confírmalos antes de cerrar la recepción: están en la lista de pendientes, abajo.",
      actions: [
        { label: "Ver pendientes", value: "ver" },
        { label: "Cancelar", value: "cancel", variant: "link" },
      ],
    });
    if (choice === "ver") showPendingList();
    return;
  }
  const sinProductos = !rec.ingresos_confirmados;
  const choice = await askDialog({
    title: `¿Cerrar la recepción de ${rec.proveedor}?`,
    text: `Se guarda la hora de fin (${nowHHMM()}) y ya no se pueden agregar productos.` +
      (sinProductos ? " Ojo: esta recepción no tiene productos confirmados." : ""),
    actions: [
      { label: "Cerrar recepción", value: "close" },
      { label: "Cancelar", value: "cancel", variant: "link" },
    ],
  });
  if (choice !== "close") return;
  try {
    const response = await withBusy(elements.closeReceptionButton, "Cerrando…", () => apiFetch(`/api/recepciones/${rec.id}/cerrar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: state.sessionId }),
    }));
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "No se pudo cerrar la recepción");
    const total = minutesBetween(data.hora_llegada, data.hora_fin);
    const descarga = minutesBetween(data.hora_inicio_descarga, data.hora_fin);
    state.reception = null;
    renderReception();
    notify(`Recepción cerrada a las ${hhmm(data.hora_fin)}: ${data.ingresos_confirmados} producto(s), ${total} min desde la llegada (descarga ${descarga} min).`, "ok", { persist: true });
    window.scrollTo({ top: 0, behavior: "smooth" });
  } catch (error) {
    notify(error.message, "error");
  }
}

// ---------- P03 · Exportar a Excel ----------
function todayISO() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

async function exportExcel() {
  const desde = elements.exportDesde.value;
  const hasta = elements.exportHasta.value;
  if (!desde) { markInvalid(elements.exportDesde, "Elige la fecha «desde»."); return; }
  if (!hasta) { markInvalid(elements.exportHasta, "Elige la fecha «hasta»."); return; }
  if (hasta < desde) { markInvalid(elements.exportHasta, "La fecha «hasta» no puede ser anterior a «desde»."); return; }
  try {
    const blob = await withBusy(elements.exportButton, "Preparando…", async () => {
      const query = new URLSearchParams({ session_id: state.sessionId, desde, hasta });
      const response = await apiFetch(`/api/export?${query.toString()}`);
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "No se pudo preparar el Excel");
      }
      return response.blob();
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `cyrano_recepciones_${desde}_a_${hasta}.xlsx`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 2000);
    notify(`Excel descargado: recepciones del ${desde} al ${hasta}.`, "ok");
  } catch (error) {
    notify(error.message, "error");
  }
}

async function login() {
  const usuario = elements.usuarioInput.value.trim();
  const clave = elements.claveInput.value.trim();
  if (!usuario) { markInvalid(elements.usuarioInput, "Escribe tu usuario."); return; }
  if (!clave) { markInvalid(elements.claveInput, "Escribe tu PIN de 6 números."); return; }

  try {
    state.sessionId = null;
    const response = await withBusy(elements.loginButton, "Entrando…", () => apiFetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ usuario, clave }),
    }));
    const data = await response.json();
    if (!response.ok) {
      // P24: si falla, se borra el PIN (no el usuario) para volver a escribirlo.
      elements.claveInput.value = "";
      elements.claveInput.focus();
      throw new Error(data.detail || "Usuario o PIN incorrecto.");
    }

    // P21: el identificador de sesión lo crea el servidor.
    state.sessionId = data.session_id;
    state.user = data;
    saveSession();
    await enterApp();
  } catch (error) {
    showMessage(elements.loginMessage, error.message, true);
  }
}

// Muestra la app para el usuario de la sesión (después de la clave o al recargar).
async function enterApp({ restored = false } = {}) {
  const data = state.user;
  try {
    state.isAdmin = Boolean(data.is_admin);
    elements.adminUserFilter.innerHTML = '<option value="">Todos</option>';
    elements.userName.textContent = data.nombre;
    elements.todayDate.textContent = data.fecha;
    elements.userBadge.classList.remove("hidden");
    elements.adminTab.classList.toggle("hidden", !state.isAdmin);
    elements.adminTab.parentElement.classList.toggle("tabs-4", state.isAdmin); // P13: 4 pestañas → 2 filas en el EDA52
    elements.adminIntro.textContent = state.isAdmin
      ? "Aquí se revisa lo registrado, el catálogo, los lotes en cuarentena y la impresora."
      : "Esta parte es solo para el administrador.";
    elements.loginSection.classList.add("hidden");
    elements.mainSection.classList.remove("hidden");
    elements.loginMessage.textContent = "";
    clearStatus();
    const recovered = await loadPending();
    await loadReception();
    await loadProviderList();
    await loadEntries();
    await loadPrinterConfig();
    if (state.isAdmin) {
      await loadAdminSummary();
    }
    if (recovered) {
      notify(`Tienes ${recovered} ingreso(s) pendientes de confirmar${restored ? "" : " de una sesión anterior"}. Están en la lista de pendientes; confírmalos con «Confirmar».`, "warn");
    }
    // P20: el calendario de caducidad empieza mañana (no se aceptan productos vencidos).
    const manana = new Date(Date.now() + 86400000);
    const minCad = `${manana.getFullYear()}-${String(manana.getMonth() + 1).padStart(2, "0")}-${String(manana.getDate()).padStart(2, "0")}`;
    elements.scannerCaducidad.min = minCad;
    if (!elements.exportDesde.value) elements.exportDesde.value = todayISO();
    if (!elements.exportHasta.value) elements.exportHasta.value = todayISO();
    armBackGuard();
    // El panel de escaneo es el activo al entrar: enfocamos el campo para el escáner HID.
    focusScanner();
  } catch (error) {
    if (error.sessionExpired) {
      resetToLogin();
    }
    notify(error.message, "error");
  }
}

async function searchByBarcode() {
  const barcode = elements.barcodeInput.value.trim();
  if (!barcode) {
    markInvalid(elements.barcodeInput, "Escanea o escribe un código de barras.");
    return;
  }
  clearInvalid(elements.barcodeInput);
  notify(`Buscando el código ${barcode}…`, "busy", { persist: true });

  let products;
  let gs1 = null;
  let digitoValido = null;
  try {
    const data = await withBusy(elements.searchBarcodeButton, "Buscando…", async () => {
      // P09: el servidor reconoce el GS1-128 (lote y caducidad) y busca por el GTIN de la caja.
      const response = await apiFetch(`/api/products/scan?code=${encodeURIComponent(barcode)}`);
      if (!response.ok) throw new Error("No se pudo buscar el producto. Intenta de nuevo.");
      return response.json();
    });
    products = data.productos || [];
    gs1 = data.gs1 || null;
    digitoValido = data.digito_valido ?? null;
  } catch (error) {
    notify(error.message, "error");
    return;
  }

  clearStatus(); // la búsqueda terminó: se quita «Buscando…»
  // P08 / FH 18: no perder sin aviso lo escrito del producto anterior.
  if (!(await confirmDiscard())) {
    elements.barcodeInput.value = "";
    clearStatus();
    elements.scannerQty.focus({ preventScroll: true });
    return;
  }
  if (state.editingId) exitEdit({ silent: true });

  if (!products.length) {
    state.selectedProduct = null;
    elements.scannerActions.classList.add("hidden");
    notify(digitoValido === false
      ? `El código ${barcode} se leyó mal (el último dígito no cuadra). Vuelve a escanear.`
      : `Código ${barcode} no encontrado en el catálogo.`, "error");
    renderNotFound(barcode, digitoValido);
    updateActionBar();
    return;
  }

  const product = products.length > 1 ? await chooseProduct(products, barcode) : products[0];
  if (!product) {
    clearStatus();
    focusScanner();
    return;
  }
  state.selectedProduct = product;
  // FH 5: la cantidad ya no se llena sola con «1»; FH 18: formulario limpio con cada producto.
  resetProductForm();
  setQtyUnit("scanner", product);
  updateConversion("scanner");
  renderProductCard(elements.scannerResult, product, true);
  elements.scannerActions.classList.remove("hidden");
  clearStatus(); // la tarjeta resaltada es la respuesta (FH 2); el aviso sobraba y quitaba espacio
  revealCard(elements.scannerResult);
  if (gs1) applyGs1(gs1);
  updateActionBar();
  // P04: el campo cantidad queda listo para escribir (Flujo_tarea).
  elements.scannerQty.focus({ preventScroll: true });
}

// P09 / FH 13: con el GS1-128, lote y caducidad se llenan solos (se pueden corregir).
function applyGs1(gs1) {
  const leidos = [];
  if (gs1.lote) {
    elements.scannerLote.value = normalizarLote(gs1.lote);
    elements.scannerLote.classList.add("from-code");
    leidos.push("lote");
  }
  if (gs1.caducidad) {
    elements.scannerCaducidad.value = gs1.caducidad;
    elements.scannerCaducidad.classList.add("from-code");
    leidos.push(gs1.caducidad_fuente === "15" ? "fecha «consumir antes de»" : "caducidad");
    elements.scannerCaducidad.title = gs1.caducidad_fuente === "15" ? "Fecha «consumir preferentemente antes de» (IA 15) del código" : "Caducidad (IA 17) del código";
    updateCaducidadHint();
  }
  if (leidos.length) {
    elements.scannerResult.insertAdjacentHTML("beforeend",
      `<p class="from-code-note" title="Revisa que coincida con la etiqueta">${ICONS.ok} Del código: ${escapeHtml(leidos.join(" y "))}</p>`);
  }
}

// Código no encontrado: muestra lo que se leyó y dos salidas (FH 20).
function renderNotFound(barcode, digitoValido = null) {
  const card = elements.scannerResult;
  card.classList.remove("hidden");
  // P25: el dígito verificador GS1 dice si fue una mala lectura (el último número no cuadra).
  const causa = digitoValido === false
    ? "<p><strong>El último dígito no cuadra</strong>: casi seguro es una mala lectura. Limpia la etiqueta y vuelve a escanear."
    : "<p>Puede ser una mala lectura o un producto que no está en el catálogo.</p>";
  card.innerHTML = `
    <p class="not-found-title">${digitoValido === false ? "Código mal leído" : "Código no encontrado"}</p>
    <p>Código leído: <span class="not-found-code">${escapeHtml(barcode)}</span></p>
    ${causa}
    <div class="not-found-actions">
      <button type="button" data-nf="retry">Escanear de nuevo</button>
      <button type="button" class="secondary" data-nf="byname">Buscar por nombre</button>
    </div>
    <p class="not-found-help">Si es un producto nuevo, anota el código y avisa al supervisor.</p>
  `;
  card.querySelector('[data-nf="retry"]').addEventListener("click", () => {
    elements.barcodeInput.value = "";
    card.classList.add("hidden");
    clearStatus();
    elements.barcodeInput.scrollIntoView({ behavior: "smooth", block: "center" });
    focusScanner();
  });
  card.querySelector('[data-nf="byname"]').addEventListener("click", () => {
    card.classList.add("hidden");
    elements.barcodeInput.value = "";
    notify("Escribe el nombre del producto en el mismo campo y elige de la lista.", "info");
    focusScanner();
  });
  revealCard(card, "not-found");
}

// Rellena el formulario de la Opción B con un producto (igual que la búsqueda por catálogo).
// Reutilizado por la lista de productos del proveedor y por el autocompletado.
// P04 / U9: elegir un producto por nombre llena el mismo formulario que el escaneo.
function selectProduct(product) {
  state.selectedProduct = product;
  resetProductForm();
  setQtyUnit("scanner", product);
  updateConversion("scanner");
  renderProductCard(elements.scannerResult, product, true);
  elements.scannerActions.classList.remove("hidden");
  clearStatus();
  revealCard(elements.scannerResult);
  updateActionBar();
  elements.scannerQty.focus({ preventScroll: true });
}

// ---------- Autocompletado en vivo (productos + proveedores) ----------

let autocompleteTimer = null;
let autocompleteResults = [];

function hideAutocomplete() {
  elements.autocompleteDropdown.classList.add("hidden");
  elements.autocompleteDropdown.innerHTML = "";
  autocompleteResults = [];
}

// El mismo campo sirve para escanear y para buscar por nombre: solo se busca por nombre
// cuando lo escrito tiene letras (el escáner manda solo números), desde 2 caracteres.
function looksLikeName(term) {
  return /[a-záéíóúñ]/i.test(term) && term.length >= 2 && !/^\(?\d{2}\)?\d{8,}/.test(term);
}

function onAutocompleteInput() {
  const term = elements.barcodeInput.value.trim();
  window.clearTimeout(autocompleteTimer);
  if (!looksLikeName(term)) {
    hideAutocomplete();
    return;
  }
  // Pequeño debounce para no consultar en cada tecla.
  autocompleteTimer = window.setTimeout(() => runAutocomplete(term), 150);
}

async function runAutocomplete(term) {
  try {
    const response = await apiFetch(`/api/search?q=${encodeURIComponent(term)}`);
    const data = await response.json();
    autocompleteResults = (data.resultados || []).filter((item) => item.type === "producto");
    renderAutocomplete();
  } catch (error) {
    hideAutocomplete();
  }
}

function renderAutocomplete() {
  const dropdown = elements.autocompleteDropdown;
  dropdown.classList.remove("hidden");

  if (!autocompleteResults.length) {
    dropdown.innerHTML = '<div class="autocomplete-empty">Sin coincidencias</div>';
    return;
  }

  dropdown.innerHTML = autocompleteResults
    .map((item, index) => {
      if (item.type === "producto") {
        return `
          <div class="autocomplete-item" data-index="${index}">
            <div class="item-text">
              <div class="item-title">${escapeHtml(formatProducto(item.codigo_cyrano, item.nombre_producto))}</div>
              ${item.del_proveedor ? `<div class="item-del">${ICONS.ok} Lo trae este proveedor</div>` : `<div class="item-sub">${escapeHtml(provText(item))}</div>`}
            </div>
          </div>`;
      }
      return `
        <div class="autocomplete-item" data-index="${index}">
          <div class="item-text">
            <div class="item-title">${escapeHtml(item.proveedor)}</div>
            <div class="item-sub">Ver productos de este proveedor</div>
          </div>
          <span class="badge badge-proveedor">Proveedor</span>
        </div>`;
    })
    .join("");

  dropdown.querySelectorAll(".autocomplete-item").forEach((el) => {
    el.addEventListener("mousedown", (event) => {
      // mousedown (no click) para que se dispare antes del blur del input.
      event.preventDefault();
      const item = autocompleteResults[Number(el.dataset.index)];
      selectAutocompleteItem(item);
    });
  });
}

async function selectAutocompleteItem(item) {
  if (!item || item.type !== "producto") return;
  elements.barcodeInput.value = "";
  hideAutocomplete();
  if (!(await confirmDiscard())) return;
  if (state.editingId) exitEdit({ silent: true });
  selectProduct(item);
}

// P10: quién trae el producto, según las compras de SAP (MovCompras).
function provText(product) {
  const lista = product.proveedores && product.proveedores.length ? product.proveedores
    : (product.proveedor && product.proveedor !== "Sin asignar" ? [product.proveedor] : []);
  return lista.length ? `Lo trae: ${lista.join(" · ")}` : "Sin proveedor registrado";
}

function renderProductCard(container, product, isBarcode) {
  const factors = conversionFactors(product);
  const presentacion = `1 ${product.unidad_llega} = ${fmtNum(convertQty(1, product))} ${unitText(product.unidad_planta)}` +
    (factors.length > 1 ? ` (${factors.join(" × ")})` : "");
  container.classList.remove("hidden");
  container.innerHTML = `
    <p class="product-name">${escapeHtml(product.nombre_producto)}</p>
    <p class="product-meta"><span class="product-code">${escapeHtml(product.codigo_cyrano)}</span>
      ${escapeHtml(presentacion)}${product.codigo_sap && product.codigo_sap !== product.codigo_cyrano ? ` · SAP ${escapeHtml(product.codigo_sap)}` : ""}</p>
    ${product.del_proveedor === false && state.reception ? `<p class="prov-note">${ICONS.warn}<span>No se le ha comprado a este proveedor. ${escapeHtml(provText(product).replace(/\.$/, ""))}.</span></p>` : ""}
  `;
}

async function saveEntry(type) {
  if (!state.reception) {
    notify("Primero abre una recepción: proveedor, factura o guía y hora de llegada.", "error");
    scrollBelowStatus(elements.receptionCard);
    return;
  }
  if (!state.selectedProduct) {
    notify("Primero escanea o elige un producto.", "error");
    return;
  }

  const qtyInput = elements.scannerQty;
  const loteInput = elements.scannerLote;
  const caducidadInput = elements.scannerCaducidad;
  const amount = Number(qtyInput.value);
  if (!amount || amount <= 0) {
    markInvalid(qtyInput, `Falta la cantidad que llega, en ${pluralUnit(state.selectedProduct.unidad_llega)} (mayor que 0).`);
    return;
  }
  if (amount > REGLAS.topeCantidad) {
    markInvalid(qtyInput, `${fmtNum(amount)} ${pluralUnit(state.selectedProduct.unidad_llega)} pasa el tope de ${fmtNum(REGLAS.topeCantidad)}: revisa si está bien escrita.`);
    return;
  }

  // Lote y fecha de caducidad son obligatorios: cada entrada lleva su propio lote
  // (clave del FIFO en despacho), no el producto genérico.
  const lote = normalizarLote(loteInput.value);
  loteInput.value = lote;
  const fechaCaducidad = caducidadInput.value;
  if (!lote) {
    markInvalid(loteInput, "Falta el lote. Escríbelo tal como viene en la etiqueta.");
    return;
  }
  if (lote.length > REGLAS.loteMax) {
    markInvalid(loteInput, `El lote tiene ${lote.length} caracteres; el máximo es ${REGLAS.loteMax}.`);
    return;
  }
  if (!REGLAS.lotePatron.test(lote)) {
    markInvalid(loteInput, "El lote solo puede tener letras, números, guion (-), barra (/) y punto (.), sin espacios.");
    return;
  }
  if (!fechaCaducidad) {
    markInvalid(caducidadInput, "Falta la fecha de caducidad.");
    return;
  }
  if (fechaCaducidad <= todayISO()) {
    markInvalid(caducidadInput, `La caducidad (${fechaCaducidad}) ya pasó o es hoy: el producto está vencido.`);
    return;
  }
  const diasVence = daysUntil(fechaCaducidad);
  if (diasVence < REGLAS.diasMinVencimiento) {
    const choice = await askDialog({
      title: `Vence en ${diasVence} día(s)`,
      text: `La caducidad es ${fechaCaducidad}: menos de ${REGLAS.diasMinVencimiento} días. Revisa la fecha de la etiqueta. Si está bien y se acepta el producto, regístralo igual.`,
      actions: [
        { label: "Corregir la fecha", value: "fix" },
        { label: "Registrar igual", value: "ok", variant: "secondary" },
      ],
    });
    if (choice !== "ok") { caducidadInput.focus(); return; }
  }

  // Control de calidad, ligado al lote. El estado es obligatorio.
  const qc = readQc(type);
  if (!qc.estado_qc) {
    markInvalid(elements.scannerEstadoGroup, "Falta el estado de calidad: toca Aprobado, Cuarentena o Rechazado.");
    return;
  }
  if (qc.estado_qc !== QC_ESTADO_CONFIRMABLE && qc.motivo_qc.length < 3) {
    markInvalid(qcEl(type, "MotivoQc"), qc.estado_qc === "rechazado" ? "Escribe o elige el motivo del rechazo." : "Escribe o elige el motivo de la cuarentena.");
    return;
  }
  const temp = qc.temperatura_recepcion;
  if (temp !== null && (Number.isNaN(temp) || temp < REGLAS.tempMin || temp > REGLAS.tempMax)) {
    markInvalid(qcEl(type, "TempRecepcion"), `La temperatura debe estar entre ${REGLAS.tempMin} y ${REGLAS.tempMax} °C.`);
    return;
  }
  if (qc.temperatura_ok && temp !== null && (temp < REGLAS.tempOkMin || temp > REGLAS.tempOkMax)) {
    markInvalid(qcEl(type, "TempRecepcion"), `«Temperatura OK» está marcada pero la lectura es ${fmtNum(temp)} °C (aceptado: ${REGLAS.tempOkMin} a ${REGLAS.tempOkMax} °C).`);
    return;
  }
  // Los 5 puntos del checklist son opcionales (no aplican a todos los productos);
  // solo el estado es obligatorio. Decisión de Mateo, 10-nov.

  const editing = state.editingId;
  const pendingEntry = {
    id: editing || newLineId(), // P07: al corregir se conserva el id de la línea
    producto_id: state.selectedProduct.id,
    nombre_producto: state.selectedProduct.nombre_producto,
    codigo_cyrano: state.selectedProduct.codigo_cyrano,
    cantidad_ingresada: amount,
    unidad_llega: state.selectedProduct.unidad_llega,
    cantidad_convertida: convertQty(amount, state.selectedProduct),
    unidad_planta: state.selectedProduct.unidad_planta,
    codigo_barra: state.selectedProduct.codigo_barra || "",
    lote,
    fecha_caducidad: fechaCaducidad,
    cantidad_por_caja: state.selectedProduct.cantidad_por_caja,
    factor_conversion: state.selectedProduct.factor_conversion,
    codigo_sap: state.selectedProduct.codigo_sap || "",
    session_id: state.sessionId,
    usuario_nombre: state.user?.nombre || "",
    recepcion_id: state.reception.id,
    ...qc,
  };

  if (editing) {
    state.entries = state.entries.map((e) => (e.id === editing ? pendingEntry : e));
  } else {
    state.entries = [pendingEntry, ...state.entries];
  }
  const synced = await syncPending(pendingEntry);
  // El primer producto marca el inicio de descarga si no se tocó el botón.
  if (synced && !state.reception.hora_inicio_descarga) await loadReception();
  // Aviso según el semáforo: si no está aprobado, no podrá confirmarse en el ingreso masivo.
  const agregado = `${formatProducto(pendingEntry.codigo_cyrano, pendingEntry.nombre_producto)} · ${fmtNum(amount)} ${pluralUnit(pendingEntry.unidad_llega, amount)} (${fmtNum(pendingEntry.cantidad_convertida)} ${unitText(pendingEntry.unidad_planta)}) · lote ${lote}`;
  if (editing) {
    exitEdit();
    notify(`Pendiente corregido: ${agregado}.`, synced ? "ok" : "warn");
  } else if (!synced) {
    notify(`Agregado sin conexión: ${pendingEntry.codigo_cyrano} · lote ${lote}. Se guardará solo cuando vuelva la red; no recargues la página.`, "warn");
  } else if (qc.estado_qc === QC_ESTADO_CONFIRMABLE) {
    notify(`Agregado: ${agregado}. Escanea el siguiente o toca «Confirmar» abajo.`, "ok");
  } else {
    notify(`Agregado con calidad «${qc.estado_qc}»: ${agregado}. No se podrá confirmar hasta que quede aprobado.`, "warn");
  }
  qtyInput.value = "";
  updateConversion(type);
  loteInput.value = "";
  document.getElementById("scannerCadHint").textContent = "";
  caducidadInput.value = "";
  resetQc(type);
  elements.scannerResult.classList.add("hidden");
  elements.scannerActions.classList.add("hidden");
  document.querySelector(".qc-details")?.removeAttribute("open");
  elements.barcodeInput.value = "";
  state.selectedProduct = null;
  await loadEntries();
  updateActionBar();
  focusScanner();
}

async function loadEntries() {
  if (!state.sessionId) {
    elements.entriesTableBody.innerHTML = '<tr><td colspan="7">No hay ingresos</td></tr>';
    elements.pendingEntries.textContent = "Sin ingresos pendientes para etiquetar";
    return;
  }

  const onlyNoBarcode = elements.onlyNoBarcode.checked;
  const filtroLote = elements.filterLote.value.trim();
  const filtroCaducidad = elements.filterCaducidad.value;

  // Los filtros de lote/caducidad se envían al backend para los ingresos ya guardados...
  const query = new URLSearchParams({
    filter_no_barcode: String(onlyNoBarcode),
    session_id: state.sessionId,
  });
  if (filtroLote) query.set("lote", filtroLote);
  if (filtroCaducidad) query.set("fecha_caducidad", filtroCaducidad);
  // Sin conexión se sigue mostrando lo último que se cargó, más los pendientes.
  let persistedEntries = state.entries.filter((entry) => !isPendingEntry(entry));
  try {
    const response = await apiFetch(`/api/entries?${query.toString()}`);
    if (response.ok) persistedEntries = await response.json();
  } catch (error) { /* el aviso «Sin conexión» ya está a la vista */ }

  // ...y también a las entradas pendientes (aún en memoria) para que el filtro sea coherente.
  const pendingEntries = state.entries
    .filter((entry) => entry.id && String(entry.id).length > 8)
    .filter((entry) => (!filtroLote || (entry.lote || "").toLowerCase().includes(filtroLote.toLowerCase())))
    .filter((entry) => (!filtroCaducidad || entry.fecha_caducidad === filtroCaducidad))
    .filter((entry) => (!onlyNoBarcode || !entry.codigo_barra));

  const allPending = state.entries.filter((entry) => entry.id && String(entry.id).length > 8);
  if (state.reception) window.setTimeout(renderReception, 0);
  const entries = [...pendingEntries, ...persistedEntries];
  // Conservamos en el estado todas las pendientes (incluidas las ocultas por el filtro).
  state.entries = [...allPending, ...persistedEntries];
  elements.entriesTableBody.innerHTML = "";

  if (!entries.length) {
    elements.entriesTableBody.innerHTML = '<tr><td colspan="7">No hay ingresos</td></tr>';
    elements.pendingEntries.textContent = "";
    renderPendingCards();
    renderLabels();
    updateActionBar();
    return;
  }

  const visibleEntries = [...entries];
  visibleEntries.forEach((entry) => {
    // El botón de imprimir solo aplica a ingresos ya guardados (tienen id de BD).
    // Las entradas pendientes usan un id de reloj (Date.now(), >8 dígitos).
    const isPending = String(entry.id).length > 8;
    const isVoided = entry.estado_registro === "anulado";
    // P22: un pendiente se puede quitar (aún no es un registro); un confirmado se anula con motivo.
    let actionHtml;
    if (isVoided) {
      actionHtml = `<span class="voided-note">Anulado por ${escapeHtml(entry.anulado_por || "—")} a las ${escapeHtml(hhmm(entry.anulado_at))}: ${escapeHtml(entry.anulado_motivo || "")}</span>`;
    } else if (isPending) {
      actionHtml = `<button class="btn-outline small-button" data-action="edit" data-entry-id="${escapeHtml(entry.id)}" title="Corregir este pendiente">Editar</button>` +
        `<button class="link-danger" data-action="delete" data-entry-id="${escapeHtml(entry.id)}" title="Quitar de la lista de pendientes">Quitar</button>`;
    } else {
      actionHtml = `<button class="void-button small-button" data-action="void" data-entry-id="${escapeHtml(entry.id)}" title="Anular este ingreso con un motivo">Anular</button>`;
    }
    // FH 10: el pendiente se distingue del confirmado con una etiqueta de color.
    const estadoHtml = isVoided
      ? '<span class="qc-badge qc-anulado">Anulado</span>'
      : `${isPending ? '<span class="pending-badge" title="Pendiente de confirmar">Por confirmar</span>' : ""}${qcBadge(entry.estado_qc)}${qcNote(entry)}`;
    const row = document.createElement("tr");
    if (isVoided) row.classList.add("is-voided");
    if (isPending) row.classList.add("is-pending");
    row.innerHTML = `
      <td class="c-prod" data-label="Producto">${escapeHtml(formatProducto(entry.codigo_cyrano, entry.nombre_producto))}</td>
      <td class="c-cant" data-label="Cantidad">${fmtNum(entry.cantidad_ingresada)} ${escapeHtml(pluralUnit(entry.unidad_llega, entry.cantidad_ingresada))}</td>
      <td class="c-conv" data-label="Convertida">${fmtNum(entry.cantidad_convertida)} ${escapeHtml(unitText(entry.unidad_planta))}</td>
      <td class="c-lote" data-label="Lote">${escapeHtml(entry.lote || "—")}</td>
      <td class="c-cad" data-label="Caducidad">${escapeHtml(entry.fecha_caducidad || "—")}</td>
      <td class="c-acc" data-label="Estado y acciones"><span class="c-estado">${estadoHtml}</span><span class="c-botones">${actionHtml}</span></td>
      <td class="c-bar" data-label="¿Código de barras?">${entry.codigo_barra ? "Sí" : "No"}</td>
    `;
    elements.entriesTableBody.appendChild(row);
  });

  document.querySelectorAll("[data-action='void']").forEach((button) => {
    button.addEventListener("click", () => voidEntry(Number(button.dataset.entryId)));
  });

  elements.entriesTableBody.querySelectorAll("[data-action='delete']").forEach((button) => {
    button.addEventListener("click", () => removePending(Number(button.dataset.entryId)));
  });
  elements.entriesTableBody.querySelectorAll("[data-action='edit']").forEach((button) => {
    button.addEventListener("click", () => editPending(Number(button.dataset.entryId)));
  });
  // P13: lo de etiquetas ya no se muestra en «Registrados»; va en su propia pestaña.
  elements.pendingEntries.textContent = "";
  renderPendingCards();
  renderLabels();
  updateActionBar();
}

// P22: un pendiente (aún no confirmado) se quita de la lista con un diálogo propio.
async function removePending(entryId) {
  const entry = state.entries.find((e) => e.id === entryId);
  const choice = await askDialog({
    title: "¿Quitar de pendientes?",
    text: entry ? `${formatProducto(entry.codigo_cyrano, entry.nombre_producto)} · lote ${entry.lote}. Todavía no está confirmado, así que se quita de la lista.` : "Se quita de la lista de pendientes.",
    actions: [
      { label: "Quitar", value: "quitar", variant: "secondary" },
      { label: "Cancelar", value: "cancel", variant: "link" },
    ],
  });
  if (choice !== "quitar") return;
  try {
    if (!state.unsynced.has(String(entryId))) {
      const response = await apiFetch(`/api/pending/${entryId}`, { method: "DELETE" });
      if (!response.ok) throw new Error("No se pudo quitar el pendiente");
    }
    state.unsynced.delete(String(entryId));
    state.entries = state.entries.filter((e) => e.id !== entryId);
    if (state.editingId === entryId) exitEdit({ silent: true });
    await loadEntries();
    notify("Pendiente quitado de la lista.", "ok", {
      action: entry ? { label: "Deshacer", run: () => restorePending(entry) } : null,
    });
  } catch (error) {
    notify(error.message, "error");
  }
}

// P07: los pendientes de la recepción están en «Recibir»; si no hay recepción abierta, en «Registrados».
function showPendingList() {
  if (state.reception && receptionPending().length) {
    showTab("scannerPanel");
    scrollBelowStatus(elements.pendingSection);
  } else {
    showTab("entriesPanel");
  }
}

// ---------- P07 · Corregir un pendiente sin borrarlo ----------
function productFromEntry(entry) {
  const pack = Number(entry.cantidad_por_caja) > 0 ? Number(entry.cantidad_por_caja) : 1;
  const factor = entry.factor_conversion ?? (entry.cantidad_convertida / (entry.cantidad_ingresada * pack));
  return {
    id: entry.producto_id,
    codigo_cyrano: entry.codigo_cyrano,
    nombre_producto: entry.nombre_producto,
    unidad_llega: entry.unidad_llega,
    unidad_planta: entry.unidad_planta,
    cantidad_por_caja: pack,
    factor_conversion: Number(factor),
    codigo_barra: entry.codigo_barra,
    codigo_sap: entry.codigo_sap || "",
  };
}

function editPending(entryId) {
  const entry = state.entries.find((e) => e.id === entryId);
  if (!entry) return;
  showTab("scannerPanel");
  state.editingId = entryId;
  const product = productFromEntry(entry);
  state.selectedProduct = product;
  setQtyUnit("scanner", product);
  elements.scannerQty.value = entry.cantidad_ingresada;
  elements.scannerLote.value = entry.lote || "";
  elements.scannerCaducidad.value = entry.fecha_caducidad || "";
  qcEl("scanner", "EstadoQc").value = entry.estado_qc || "";
  qcEl("scanner", "ResponsableQc").value = entry.responsable_qc || "";
  qcEl("scanner", "ObservacionesQc").value = entry.observaciones_qc || "";
  qcEl("scanner", "MotivoQc").value = entry.motivo_qc || "";
  qcEl("scanner", "TempRecepcion").value = entry.temperatura_recepcion ?? "";
  qcEl("scanner", "EmpaqueOk").checked = Boolean(entry.empaque_ok);
  qcEl("scanner", "SinHumedad").checked = Boolean(entry.sin_humedad);
  qcEl("scanner", "TemperaturaOk").checked = Boolean(entry.temperatura_ok);
  qcEl("scanner", "AspectoOlorOk").checked = Boolean(entry.aspecto_olor_ok);
  qcEl("scanner", "DocProveedorOk").checked = Boolean(entry.documentacion_proveedor_ok);
  updateSemaforo("scanner");
  updateConversion("scanner");
  updateCaducidadHint();
  renderProductCard(elements.scannerResult, product, true);
  elements.scannerResult.insertAdjacentHTML("afterbegin", '<span class="editing-tag">Corrigiendo pendiente</span>');
  elements.scannerActions.classList.remove("hidden");
  revealCard(elements.scannerResult);
  notify("Corrige lo que haga falta y toca «Guardar cambios». Se conserva la misma línea.", "info", { persist: true });
  updateActionBar();
  elements.scannerQty.focus({ preventScroll: true });
}

function exitEdit({ silent = false } = {}) {
  state.editingId = null;
  if (!silent) {
    elements.scannerResult.classList.add("hidden");
    elements.scannerActions.classList.add("hidden");
    state.selectedProduct = null;
  }
  updateActionBar();
}

function cancelEdit() {
  resetProductForm();
  exitEdit();
  clearStatus();
  focusScanner();
}

async function restorePending(entry) {
  state.entries = [entry, ...state.entries.filter((e) => e.id !== entry.id)];
  const ok = await syncPending(entry);
  await loadEntries();
  notify(ok ? "Pendiente recuperado." : "Pendiente recuperado de este equipo (no había conexión).", ok ? "ok" : "warn");
}

// FH 12: revisión antes de confirmar, en tabla y con totales por unidad de planta.
function reviewTableHtml(entries) {
  const totals = {};
  const esAprobado = (e) => (e.estado_qc || "").toLowerCase() === QC_ESTADO_CONFIRMABLE;
  entries.filter(esAprobado).forEach((e) => {
    const u = unitText(e.unidad_planta);
    totals[u] = (totals[u] || 0) + Number(e.cantidad_convertida || 0);
  });
  const retenidos = entries.filter((e) => (e.estado_qc || "").toLowerCase() === "cuarentena").length;
  const rechazados = entries.filter((e) => (e.estado_qc || "").toLowerCase() === "rechazado").length;
  const rows = entries.map((e) => `
    <tr class="${esAprobado(e) ? "" : "review-noinv"}">
      <td><strong>${escapeHtml(e.codigo_cyrano)}</strong> ${escapeHtml(e.nombre_producto)}${esAprobado(e) ? "" : `<br>${qcBadge(e.estado_qc)} <small>${escapeHtml(e.motivo_qc || "")}</small>`}</td>
      <td class="num">${escapeHtml(fmtNum(e.cantidad_ingresada))} ${escapeHtml(pluralUnit(e.unidad_llega, e.cantidad_ingresada))}<br><small>${escapeHtml(fmtNum(e.cantidad_convertida))} ${escapeHtml(unitText(e.unidad_planta))}</small></td>
      <td>${escapeHtml(e.lote)}<br><small>${escapeHtml(e.fecha_caducidad)}</small></td>
    </tr>`).join("");
  const totalText = Object.entries(totals).map(([u, v]) => `${fmtNum(v)} ${u}`).join(" · ");
  return `
    <table class="review-table">
      <thead><tr><th>Producto</th><th>Cantidad</th><th>Lote / vence</th></tr></thead>
      <tbody>${rows}</tbody>
      <tfoot><tr><td colspan="3"><strong>${entries.length} línea(s)</strong> · a inventario: ${escapeHtml(totalText || "nada")}</td></tr></tfoot>
    </table>
    ${retenidos || rechazados ? `<p class="review-note review-warn">${retenidos ? `${retenidos} en cuarentena (retenido${retenidos > 1 ? "s" : ""})` : ""}${retenidos && rechazados ? " y " : ""}${rechazados ? `${rechazados} rechazado${rechazados > 1 ? "s" : ""}` : ""}: se registran con su motivo y no pasan a inventario.</p>` : ""}
    <p class="review-note">Se guardan en la base y salen de la lista de pendientes.</p>`;
}

// ---------- P22 · Anular un ingreso confirmado ----------
async function voidEntry(entryId) {
  const entry = state.entries.find((e) => e.id === entryId);
  const result = await askDialog({
    title: "Anular ingreso",
    text: `${entry ? `${formatProducto(entry.codigo_cyrano, entry.nombre_producto)} · lote ${entry.lote}. ` : ""}El registro no se borra: queda marcado como anulado, con el motivo, tu usuario y la hora.`,
    input: { label: "Motivo de la anulación *", placeholder: "Ej.: se contó mal, eran 3 cajas", minLength: 5, minLengthMessage: "Escribe el motivo (al menos 5 caracteres)." },
    actions: [
      { label: "Anular ingreso", value: "anular", requiresInput: true },
      { label: "Cancelar", value: "cancel", variant: "link" },
    ],
  });
  if (result.value !== "anular") return;
  try {
    const response = await apiFetch(`/api/entries/${entryId}/anular`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ motivo: result.text }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "No se pudo anular el ingreso");
    notify(`Ingreso anulado a las ${hhmm(data.anulado_at)}. Queda en la lista tachado, con el motivo.`, "ok");
    await loadReception();
    await loadEntries();
  } catch (error) {
    notify(error.message, "error");
  }
}

// ---------- P04 · Pendientes en la misma pantalla y una acción principal fija ----------
function renderPendingCards() {
  const pend = receptionPending();
  elements.pendingSection.classList.toggle("hidden", !state.reception || !pend.length);
  elements.pendingCount.textContent = pend.length ? `${pend.length}` : "";
  elements.pendingCards.innerHTML = pend.map((entry) => `
    <li class="pending-card">
      <div class="pending-text">
        <strong>${escapeHtml(formatProducto(entry.codigo_cyrano, entry.nombre_producto))}</strong>
        <span>${escapeHtml(fmtNum(entry.cantidad_ingresada))} ${escapeHtml(pluralUnit(entry.unidad_llega, entry.cantidad_ingresada))} (${escapeHtml(fmtNum(entry.cantidad_convertida))} ${escapeHtml(unitText(entry.unidad_planta))}) · lote ${escapeHtml(entry.lote)} · vence ${escapeHtml(entry.fecha_caducidad)}</span>
        ${(entry.estado_qc || "").toLowerCase() !== QC_ESTADO_CONFIRMABLE ? `<span>${qcBadge(entry.estado_qc)} ${escapeHtml(entry.motivo_qc || "")}</span>` : ""}
      </div>
      <span class="pending-actions">
        <button type="button" class="btn-outline small-button" data-action="edit" data-entry-id="${escapeHtml(entry.id)}">Editar</button>
        <button type="button" class="link-danger" data-action="delete" data-entry-id="${escapeHtml(entry.id)}">Quitar</button>
      </span>
    </li>`).join("");
  elements.pendingCards.querySelectorAll("[data-action='delete']").forEach((button) => {
    button.addEventListener("click", () => removePending(Number(button.dataset.entryId)));
  });
  elements.pendingCards.querySelectorAll("[data-action='edit']").forEach((button) => {
    button.addEventListener("click", () => editPending(Number(button.dataset.entryId)));
  });
  // Recuadro «Confirmar» en Registrados (todos los pendientes del usuario)
  const totalPend = pendingList().length;
  elements.confirmBox.classList.toggle("hidden", !totalPend);
  elements.confirmBoxCount.textContent = String(totalPend);
  elements.bulkButton.textContent = `Confirmar ${totalPend} ingreso(s)`;
}

// Una sola acción principal a la vista (U14): guardar el producto abierto o confirmar la lista.
function updateActionBar() {
  const onReceive = document.getElementById("scannerPanel").classList.contains("active");
  const pend = receptionPending().length;
  const saving = Boolean(state.selectedProduct) && !elements.scannerActions.classList.contains("hidden");
  const show = Boolean(state.user && state.reception && onReceive && (saving || pend));
  elements.actionBar.classList.toggle("hidden", !show);
  document.body.classList.toggle("has-action-bar", show);
  elements.saveScannerButton.classList.toggle("hidden", !saving);
  elements.saveScannerButton.textContent = state.editingId ? "Guardar cambios" : "Guardar producto";
  elements.cancelEditButton.classList.toggle("hidden", !(saving && state.editingId));
  elements.confirmBarButton.classList.toggle("hidden", saving || !pend);
  elements.confirmBarButton.textContent = `Confirmar ${pend} ingreso(s)`;
}

function buildLabelMarkup() {
  // P13: solo confirmados y vigentes (no se etiqueta algo que todavía no está registrado).
  const noBarcodeEntries = labelableEntries().filter((entry) => !entry.codigo_barra);
  if (!noBarcodeEntries.length) {
    return "";
  }

  return noBarcodeEntries.map((entry) => {
    const copies = suggestedLabels(entry);
    const items = [];
    const codeValue = entry.codigo_barra || entry.codigo_cyrano || "CYRANO";
    for (let index = 0; index < copies; index += 1) {
      items.push(`
        <div class="label-card">
          <h3>${escapeHtml(entry.nombre_producto)}</h3>
          <p>${escapeHtml(entry.codigo_cyrano)}</p>
          <p>Etiquetas: ${copies}</p>
          <svg class="barcode" data-code="${escapeHtml(codeValue)}"></svg>
        </div>
      `);
    }
    return items.join("");
  }).join("");
}

function renderPreview() {
  const labels = buildLabelMarkup();
  if (!labels) {
    notify("No hay productos confirmados sin código de barras para la hoja A4.", "warn");
    elements.labelPreviewContainer.classList.add("hidden");
    elements.labelPreviewContainer.innerHTML = "";
    return;
  }

  elements.labelPreviewContainer.classList.remove("hidden");
  elements.closePreviewButton.classList.remove("hidden");
  elements.labelPreviewContainer.innerHTML = `
    <div class="preview-sheet">
      ${labels}
    </div>
  `;

  window.setTimeout(() => {
    document.querySelectorAll(".barcode").forEach((el) => {
      const code = el.getAttribute("data-code");
      if (code) {
        JsBarcode(el, code, { format: "CODE128", displayValue: true });
      }
    });
  }, 50);
}

function openPrintView() {
  const labels = buildLabelMarkup();
  if (!labels) {
    notify("No hay productos confirmados sin código de barras para la hoja A4.", "warn");
    return;
  }

  const printWindow = window.open("", "_blank", "width=900,height=700");
  if (!printWindow) return;
  printWindow.document.write(`<!DOCTYPE html><html><head><style>body{font-family:Arial;padding:20px}.label-card{border:1px solid #000;padding:10px;margin:10px;display:inline-block;width:220px;text-align:center}.barcode{width:180px;height:60px}</style><script src="${location.origin}/vendor/JsBarcode.all.min.js"></script></head><body><div class="label-page">${labels}</div><script>setTimeout(()=>{document.querySelectorAll('.barcode').forEach((el)=>{JsBarcode(el, el.getAttribute('data-code'), {format:'CODE128', displayValue:true});});}, 100);</script></body></html>`);
  printWindow.document.close();
  printWindow.focus();
  printWindow.print();
}

async function bulkSave() {
  if (state.editingId) {
    notify("Termina o cancela la corrección del pendiente antes de confirmar.", "warn");
    return;
  }
  const pendingEntries = state.entries.filter((entry) => entry.id && String(entry.id).length > 8);
  if (!pendingEntries.length) {
    notify("No hay ingresos pendientes para confirmar.", "warn");
    return;
  }

  // P16: cuarentena y rechazo ya no bloquean: se registran con su motivo y no pasan a inventario.
  const choice = await askDialog({
    title: `Revisa y confirma ${pendingEntries.length} ingreso(s)`,
    html: reviewTableHtml(pendingEntries),
    actions: [
      { label: `Confirmar ${pendingEntries.length} ingreso(s)`, value: "ok" },
      { label: "Revisar otra vez", value: "cancel", variant: "link" },
    ],
  });
  if (choice !== "ok") return;

  const payload = {
    entries: pendingEntries.map((entry) => ({
      producto_id: entry.producto_id,
      cantidad_ingresada: entry.cantidad_ingresada,
      lote: entry.lote,
      fecha_caducidad: entry.fecha_caducidad,
      estado_qc: entry.estado_qc,
      responsable_qc: entry.responsable_qc,
      observaciones_qc: entry.observaciones_qc,
      motivo_qc: entry.motivo_qc || "",
      empaque_ok: entry.empaque_ok,
      sin_humedad: entry.sin_humedad,
      temperatura_ok: entry.temperatura_ok,
      aspecto_olor_ok: entry.aspecto_olor_ok,
      documentacion_proveedor_ok: entry.documentacion_proveedor_ok,
      temperatura_recepcion: entry.temperatura_recepcion,
      session_id: state.sessionId,
      usuario_nombre: state.user?.nombre || "",
      recepcion_id: entry.recepcion_id,
      linea_id: String(entry.id),
    })),
    pending_ids: pendingEntries.map((entry) => String(entry.id)),
  };
  notify(`Guardando ${pendingEntries.length} ingreso(s)…`, "busy", { persist: true });
  let response;
  try {
    response = await withBusy(elements.confirmBarButton, "Guardando…", () => apiFetch("/api/entries/bulk", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }));
  } catch (error) {
    notify(`${error.message} Los ingresos siguen en la lista pendiente.`, "error");
    return;
  }
  if (response.ok) {
    const result = await response.json().catch(() => ({}));
    state.entries = state.entries.filter((entry) => String(entry.id).length <= 8);
    state.unsynced.clear();
    const yaGuardados = result.ya_guardados ? ` (${result.ya_guardados} ya estaban guardados)` : "";
    notify(`${result.guardados ?? pendingEntries.length} ingreso(s) confirmados y guardados${yaGuardados}.${state.reception ? " Cuando termine la descarga, toca «Cerrar recepción»." : ""}`, "ok", { persist: true });
    await loadReception();
    await loadEntries();
  } else {
    const data = await response.json().catch(() => ({}));
    notify(`${data.detail || "No se pudo confirmar el ingreso"}. Los ingresos siguen en la lista pendiente.`, "error");
  }
}

async function loadAdminSummary() {
  const userFilter = elements.adminUserFilter.value;
  const query = userFilter ? `?usuario=${encodeURIComponent(userFilter)}` : "";
  let summary;
  try {
    const response = await apiFetch(`/api/admin/summary${query}`);
    summary = await response.json();
    if (!response.ok) throw new Error(summary.detail || "No se pudo cargar el resumen");
  } catch (error) {
    notify(error.message, "error");
    return;
  }
  const entries = summary.ultimos_ingresos || [];
  const users = summary.usuarios || [];
  const e = escapeHtml;
  elements.adminUserFilter.innerHTML = '<option value="">Todos los usuarios</option>' + users.map((user) => `<option value="${e(user)}" ${userFilter === user ? "selected" : ""}>${e(user)}</option>`).join("");
  elements.adminSummary.innerHTML = `
    <p><strong>Usuarios:</strong> ${e(summary.totales.usuarios)}</p>
    <p><strong>Productos:</strong> ${e(summary.totales.productos)}</p>
    <p><strong>Ingresos:</strong> ${e(summary.totales.ingresos)}</p>
    <p><strong>Filtro:</strong> ${e(summary.filtro_actual || "todos")}</p>
    <h3>Catálogo</h3>
    <div id="catalogInfo" class="catalog-info">Cargando…</div>
    <h3>Auditoría (últimos 30 eventos)</h3>
    <ul class="audit-list" id="auditList"><li>Cargando…</li></ul>
    <h3>Últimos ingresos</h3>
    <ul>
      ${entries.map((entry) => `<li>${entry.estado_registro === "anulado" ? '<span class="qc-badge qc-anulado">Anulado</span>' : qcBadge(entry.estado_qc)} ${e(formatProducto(entry.codigo_cyrano, entry.nombre_producto))} · ${e(fmtNum(entry.cantidad_ingresada))} ${e(entry.unidad_llega)} · lote ${e(entry.lote || "—")} · ${e(entry.created_at)} · usuario: ${e(entry.usuario_resuelto || entry.usuario || entry.usuario_nombre || "desconocido")}</li>`).join("")}
    </ul>
  `;
  loadAuditList();
  loadCatalogInfo();
  loadQuarantine();
}

// P16: lotes en cuarentena; el administrador los libera (pasan a inventario) o los rechaza.
async function loadQuarantine() {
  const list = document.getElementById("quarantineList");
  if (!list) return;
  try {
    const response = await apiFetch("/api/admin/cuarentena");
    const items = await response.json();
    if (!response.ok) throw new Error(items.detail || "No se pudo leer la cuarentena");
    list.innerHTML = items.length ? items.map((x) => `
      <li class="label-item">
        <div class="label-info">
          <strong>${escapeHtml(formatProducto(x.codigo_cyrano, x.nombre_producto))}</strong>
          <span>Lote ${escapeHtml(x.lote)} · ${escapeHtml(fmtNum(x.cantidad_ingresada))} ${escapeHtml(pluralUnit(x.unidad_llega, x.cantidad_ingresada))} · ${escapeHtml(x.proveedor || "")}</span>
          <span>Motivo: ${escapeHtml(x.motivo_qc || "—")} · ${escapeHtml(x.usuario_nombre || "")}, ${escapeHtml((x.created_at || "").slice(0, 16).replace("T", " "))}</span>
        </div>
        <div class="quarantine-actions">
          <button type="button" class="btn-outline" data-resolver="aprobado" data-id="${escapeHtml(x.id)}">Liberar</button>
          <button type="button" class="void-button" data-resolver="rechazado" data-id="${escapeHtml(x.id)}">Rechazar</button>
        </div>
      </li>`).join("") : '<li class="labels-empty">No hay lotes en cuarentena.</li>';
    list.querySelectorAll("[data-resolver]").forEach((b) => b.addEventListener("click", () => resolveQuarantine(Number(b.dataset.id), b.dataset.resolver)));
  } catch (error) {
    list.innerHTML = `<li class="labels-empty">${escapeHtml(error.message)}</li>`;
  }
}

async function resolveQuarantine(entryId, estado) {
  const liberar = estado === "aprobado";
  const result = await askDialog({
    title: liberar ? "Liberar el lote" : "Rechazar el lote",
    text: liberar ? "El lote pasa a inventario (queda como aprobado)." : "El lote no entra al inventario (queda como rechazado).",
    input: { label: liberar ? "¿Por qué se libera? *" : "¿Por qué se rechaza? *", placeholder: liberar ? "Ej.: análisis de laboratorio conforme" : "Ej.: humedad confirmada en el análisis", minLength: 3, minLengthMessage: "Escribe el motivo." },
    actions: [
      { label: liberar ? "Liberar" : "Rechazar", value: "ok", requiresInput: true },
      { label: "Cancelar", value: "cancel", variant: "link" },
    ],
  });
  if (result.value !== "ok") return;
  try {
    const response = await apiFetch(`/api/admin/ingresos/${entryId}/calidad`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ estado, motivo: result.text }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "No se pudo guardar la decisión");
    notify(data.message, "ok");
    await loadAdminSummary();
    await loadEntries();
  } catch (error) {
    notify(error.message, "error");
  }
}

// P25: versión del catálogo, avisos de calidad y últimas cargas (solo administrador).
const CATALOG_ESTADOS = { aplicado: ["ok", "Aplicado"], parcial: ["warn", "Cargado en parte"], rechazado: ["error", "Rechazado"] };
async function loadCatalogInfo() {
  const box = document.getElementById("catalogInfo");
  if (!box) return;
  try {
    const response = await apiFetch("/api/admin/catalogo");
    const c = await response.json();
    if (!response.ok) throw new Error(c.detail || "No se pudo leer el catálogo");
    const e = escapeHtml;
    const av = c.avisos || {};
    const [tono, texto] = CATALOG_ESTADOS[c.estado] || ["info", c.estado || "—"];
    const lista = (items, fmt) => items && items.length ? `<ul>${items.map((x) => `<li>${fmt(x)}</li>`).join("")}</ul>` : "";
    const aviso = (titulo, items, fmt, ayuda) => items && items.length
      ? `<details class="catalog-warning"><summary>${e(titulo)}: <strong>${items.length}</strong></summary><p class="panel-help">${e(ayuda)}</p>${lista(items, fmt)}</details>` : "";
    const rechazo = c.ultimo_rechazo || "";
    box.innerHTML = `
      <p><strong>Versión ${e(c.version || "—")}</strong> · ${e(fmtNum(c.filas || 0))} productos · <span class="catalog-state catalog-${e(tono)}">${e(texto)}</span></p>
      <p class="panel-help">Cargada el ${e((c.cargado_at || "").replace("T", " ").slice(0, 16))}${c.fuente ? ` · fuente: ${e(c.fuente)}` : ""}</p>
      ${rechazo ? `<p class="catalog-reject">${e(rechazo)}</p>` : ""}
      ${aviso("Código de barras con dígito inválido", av.digito_invalido, (x) => `${e(x.codigo)} ${e(x.nombre)} · ${e(x.codigo_barra)} (el último dígito debería ser ${e(x.digito_esperado)})`, "Al escanear la etiqueta real no se van a encontrar. Hay que corregir el código en el Libro11 con Cyrano.")}
      ${aviso("Código de barras en productos distintos", av.barras_repetidas, (x) => `${e(x.codigo_barra)}: ${e(x.productos.join(" | "))}`, "Al escanearlo, la app pide elegir el producto. Hay que confirmar con Cyrano cuál es el correcto.")}
      ${aviso("Código con dos nombres", av.codigos_con_dos_nombres, (x) => `${e(x.codigo)}: ${e(x.nombres.join(" | "))}`, "El mismo código SAP aparece con nombres distintos en el Libro11.")}
      ${c.codigos_total ? `<p class="panel-help">Con proveedor (de las compras en SAP): ${e(fmtNum(c.codigos_con_proveedor))} de ${e(fmtNum(c.codigos_total))} códigos. Los demás dicen «Sin proveedor registrado».</p>` : ""}
      ${av.nombres_limpiados ? `<p class="panel-help">Se limpiaron espacios sobrantes en ${e(av.nombres_limpiados)} nombre(s).</p>` : ""}
    `;
  } catch (error) {
    box.textContent = error.message;
  }
}

// P22: eventos de la auditoría para el administrador.
const AUDIT_ACCIONES = { alta: "registró", anulacion: "anuló", apertura: "abrió la recepción", inicio_descarga: "marcó el inicio de descarga", cierre: "cerró la recepción", liberacion: "liberó de cuarentena", rechazo_cuarentena: "rechazó tras cuarentena" };
async function loadAuditList() {
  const list = document.getElementById("auditList");
  if (!list) return;
  try {
    const response = await apiFetch("/api/admin/auditoria?limite=30");
    const events = await response.json();
    if (!response.ok) throw new Error(events.detail || "No se pudo cargar la auditoría");
    list.innerHTML = events.length ? events.map((ev) => {
      const d = ev.detalle || {};
      const extra = [d.producto, d.lote ? `lote ${d.lote}` : "", d.proveedor, d.documento, d.motivo ? `motivo: ${d.motivo}` : ""].filter(Boolean).join(" · ");
      return `<li><strong>${escapeHtml(hhmm(ev.fecha))}</strong> ${escapeHtml(ev.usuario)} ${escapeHtml(AUDIT_ACCIONES[ev.accion] || ev.accion)} (${escapeHtml(ev.entidad)} ${escapeHtml(ev.entidad_id ?? "")})${extra ? ` — ${escapeHtml(extra)}` : ""}</li>`;
    }).join("") : "<li>Sin eventos todavía.</li>";
  } catch (error) {
    list.innerHTML = `<li>${escapeHtml(error.message)}</li>`;
  }
}

async function refreshAdminData() {
  try {
    // P25 / T22: la recarga dice si aplicó el catálogo nuevo o por qué no.
    const response = await withBusy(elements.refreshAdminButton, "Recargando…", () => apiFetch("/api/admin/reload", { method: "POST" }));
    const data = await response.json();
    const tono = !response.ok || data.resultado === "rechazado" ? "error" : data.resultado === "parcial" ? "warn" : data.resultado === "sin cambios" ? "info" : "ok";
    notify(data.message || data.detail, tono, { persist: tono === "error" || tono === "warn" });
  } catch (error) {
    notify(error.message, "error");
    return;
  }
  await loadAdminSummary();
}

function closePreview() {
  elements.labelPreviewContainer.classList.add("hidden");
  elements.closePreviewButton.classList.add("hidden");
  elements.labelPreviewContainer.innerHTML = "";
}

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (ch) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]
  ));
}

// ---------- Impresión ZPL en la Zebra ZD230 ----------

// P13: la IP de la impresora solo la ve el administrador (en «Administración»).
async function loadPrinterConfig() {
  if (!state.isAdmin) return;
  try {
    const response = await apiFetch("/api/print/config");
    if (!response.ok) return;
    const cfg = await response.json();
    elements.printerConfig.textContent = `IP ${cfg.ip}, puerto ${cfg.port}. Se cambia con las variables ZEBRA_IP y ZEBRA_PORT del servidor.`;
  } catch (error) {
    /* silencioso: la config es informativa */
  }
}

// P13: ingresos que se pueden etiquetar = confirmados y vigentes de la sesión.
function labelableEntries() {
  // P16: un lote rechazado no entra a la bodega, así que no lleva etiqueta.
  return state.entries.filter((entry) => String(entry.id).length <= 8 && entry.estado_registro !== "anulado"
    && (entry.estado_qc || "").toLowerCase() !== "rechazado");
}

// Una etiqueta por bulto: se propone la cantidad recibida (redondeada hacia arriba), hasta 50.
function suggestedLabels(entry) {
  return Math.min(50, Math.max(1, Math.ceil(Number(entry.cantidad_ingresada) || 1)));
}

function renderLabels() {
  const list = elements.labelsList;
  if (!list) return;
  const entries = labelableEntries();
  if (!entries.length) {
    list.innerHTML = '<li class="labels-empty">Todavía no hay productos confirmados en esta sesión. Confírmalos en «Registrados» y aquí aparecen para imprimir su etiqueta.</li>';
    return;
  }
  list.innerHTML = entries.map((entry) => {
    const id = escapeHtml(entry.id);
    const sinBarra = entry.codigo_barra ? "" : '<span class="label-nobar">Sin código de barras</span>';
    return `
      <li class="label-item">
        <div class="label-info">
          <strong>${escapeHtml(formatProducto(entry.codigo_cyrano, entry.nombre_producto))}</strong>
          <span>Lote ${escapeHtml(entry.lote || "—")} · vence ${escapeHtml(entry.fecha_caducidad || "—")} · ${fmtNum(entry.cantidad_ingresada)} ${escapeHtml(pluralUnit(entry.unidad_llega, entry.cantidad_ingresada))}</span>
          ${sinBarra}
        </div>
        <div class="label-actions">
          <label for="labelQty-${id}">Etiquetas</label>
          <input id="labelQty-${id}" type="number" inputmode="numeric" min="1" max="50" step="1" value="${suggestedLabels(entry)}" />
          <button type="button" class="print-button" data-print="${id}">${ICONS.print} Imprimir</button>
        </div>
      </li>`;
  }).join("");
  list.querySelectorAll("[data-print]").forEach((button) => {
    button.addEventListener("click", () => {
      const input = document.getElementById(`labelQty-${button.dataset.print}`);
      printLabel(Number(button.dataset.print), input, button);
    });
  });
}

// Imprime las etiquetas de un ingreso en la Zebra.
async function printLabel(entryId, qtyInput, button) {
  const cantidad = Number(qtyInput?.value);
  if (!Number.isInteger(cantidad) || cantidad < 1 || cantidad > 50) {
    markInvalid(qtyInput, "Escribe cuántas etiquetas: un número entero de 1 a 50.");
    return;
  }
  clearInvalid(qtyInput);
  const testMode = Boolean(state.isAdmin && elements.printTestMode?.checked);
  await withBusy(button, "Imprimiendo…", async () => {
    try {
      const response = await apiFetch("/api/print/label", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ entry_id: entryId, cantidad, test_mode: testMode }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "No se pudo imprimir la etiqueta.");
      if (data.test_mode) {
        elements.zplPreview.classList.remove("hidden");
        elements.zplPreview.innerHTML =
          `<p><strong>Modo prueba (solo administrador)</strong>: ZPL de ${data.cantidad} etiqueta(s); no se envió a la impresora. ` +
          `Se puede revisar en labelary.com.</p><pre>${escapeHtml(data.zpl)}</pre>`;
        notify("ZPL generado en modo prueba; no se imprimió.", "info");
      } else {
        elements.zplPreview.classList.add("hidden");
        notify(data.message || "Etiquetas enviadas a la impresora.", "ok");
      }
    } catch (error) {
      notify(error.message, "error", { persist: true });
    }
  });
}

// ---------- Escáner HID del EDA52 ----------

// Re-enfoca (y selecciona) el campo de escaneo si el panel de escaneo está visible,
// para dejarlo listo antes/después de cada lectura del escáner integrado.
function focusScanner() {
  const panel = document.getElementById("scannerPanel");
  if (panel && panel.classList.contains("active")) {
    elements.barcodeInput.focus({ preventScroll: true });
    elements.barcodeInput.select();
  }
}

// FH 8: si hay pendientes, avisa antes de salir. Los guardados en el servidor no se pierden.
async function logout() {
  const pending = pendingList();
  if (pending.length) {
    const lost = pending.filter((entry) => state.unsynced.has(String(entry.id))).length;
    const choice = await askDialog({
      title: `Tienes ${pending.length} ingreso(s) sin confirmar`,
      text: lost
        ? `${lost} no se pudieron guardar por falta de conexión y se perderán si sales. Confírmalos antes de salir.`
        : "Quedan guardados y vuelven a aparecer cuando entres otra vez con tu PIN. Lo mejor es confirmarlos antes de salir.",
      actions: [
        { label: "Ver pendientes", value: "ver" },
        { label: lost ? "Salir y perderlos" : "Salir (quedan guardados)", value: "salir", variant: "secondary" },
        { label: "Cancelar", value: "cancel", variant: "link" },
      ],
    });
    if (choice === "ver") {
      showPendingList();
      return;
    }
    if (choice !== "salir") return;
  }
  apiFetch("/api/logout", { method: "POST" }).catch(() => {}); // si no hay red, la sesión vence sola
  resetToLogin();
  notify(
    pending.length
      ? "Sesión cerrada. Los pendientes quedaron guardados para cuando vuelvas a entrar."
      : "Sesión cerrada.",
    "info"
  );
}

function resetToLogin() {
  clearSession();
  state.unsynced.clear();
  state.reception = null;
  document.body.classList.remove("no-reception");
  state.user = null;
  state.selectedProduct = null;
  state.entries = [];
  state.isAdmin = false;
  state.sessionId = null;
  elements.claveInput.value = "";
  elements.barcodeInput.value = "";
  hideAutocomplete();
  elements.scannerQty.value = "";
  elements.scannerLote.value = "";
  elements.scannerCaducidad.value = "";
  resetQc("scanner");
  elements.onlyNoBarcode.checked = false;
  elements.filterLote.value = "";
  elements.filterCaducidad.value = "";
  elements.userBadge.classList.add("hidden");
  elements.loginSection.classList.remove("hidden");
  elements.mainSection.classList.add("hidden");
  elements.scannerResult.classList.add("hidden");
  elements.scannerActions.classList.add("hidden");
  elements.actionBar.classList.add("hidden");
  document.body.classList.remove("has-action-bar");
  elements.entriesTableBody.innerHTML = '<tr><td colspan="7">No hay ingresos</td></tr>';
  elements.pendingEntries.textContent = "Sin ingresos pendientes para etiquetar";
  elements.adminSummary.innerHTML = "";
}

async function loadAdminUsers() {
  const response = await apiFetch("/api/admin/summary");
  const summary = await response.json();
  const entries = summary.ingresos_filtrados || [];
  const users = [...new Set(entries.map((entry) => entry.usuario_nombre).filter(Boolean))];
  const currentValue = elements.adminUserFilter.value;
  elements.adminUserFilter.innerHTML = '<option value="">Todos</option>';
  users.forEach((user) => {
    const option = document.createElement("option");
    option.value = user;
    option.textContent = user;
    if (currentValue === user) {
      option.selected = true;
    }
    elements.adminUserFilter.appendChild(option);
  });
}

function attachEvents() {
  elements.statusClose.addEventListener("click", clearStatus);
  elements.retryButton.addEventListener("click", retryConnection);
  elements.openReceptionButton.addEventListener("click", openReception);
  elements.exportButton.addEventListener("click", exportExcel);
  elements.startUnloadButton.addEventListener("click", startUnload);
  elements.closeReceptionButton.addEventListener("click", closeReception);
  window.addEventListener("offline", () => setOnline(false));
  window.addEventListener("online", checkServer);
  elements.scannerQty.addEventListener("input", () => updateConversion("scanner"));
  document.querySelectorAll("input, select, textarea").forEach((field) => {
    field.addEventListener("input", () => clearInvalid(field));
    field.addEventListener("change", () => clearInvalid(field));
  });
  elements.loginForm.addEventListener("submit", (event) => {
    event.preventDefault();
    login();
  });
  elements.logoutButton.addEventListener("click", logout);
  elements.searchBarcodeButton.addEventListener("click", searchByBarcode);
  // Escáner HID del EDA52: inyecta el código + Enter. Capturamos el Enter para procesar
  // sin recargar y re-enfocamos el campo para dejarlo listo para el siguiente escaneo.
  elements.barcodeInput.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    const term = elements.barcodeInput.value.trim();
    // Si se está buscando por nombre y hay resultados, Enter elige el primero.
    if (looksLikeName(term) && autocompleteResults.length) {
      selectAutocompleteItem(autocompleteResults[0]);
      return;
    }
    if (looksLikeName(term)) {
      runAutocomplete(term);
      return;
    }
    hideAutocomplete();
    searchByBarcode();
  });
  // Semáforo QC en vivo al cambiar el estado.
  qcEl("scanner", "EstadoQc").addEventListener("change", () => updateSemaforo("scanner"));
  // P04: estado de calidad con un toque.
  elements.scannerEstadoGroup.querySelectorAll(".seg").forEach((button) => {
    button.addEventListener("click", () => {
      const select = qcEl("scanner", "EstadoQc");
      select.value = button.dataset.estado;
      select.dispatchEvent(new Event("change"));
      clearInvalid(elements.scannerEstadoGroup);
      // P16: si pide motivo, se baja hasta el cuadro para que no quede tapado por la barra de Guardar.
      if (button.dataset.estado !== QC_ESTADO_CONFIRMABLE) {
        window.setTimeout(() => qcEl("scanner", "MotivoBox").scrollIntoView({ behavior: "smooth", block: "end" }), 50);
      }
    });
  });
  // Enter pasa al siguiente campo. Si el escáner dispara sobre cantidad o lote (el operador
  // escaneó el siguiente producto sin guardar), se trata como un escaneo y no como un dato.
  const pareceCodigo = (valor) => /^\(?\d{2}\)?\d{8,}/.test(valor) || /^\d{8,}$/.test(valor);
  [[elements.scannerQty, elements.scannerLote], [elements.scannerLote, elements.scannerCaducidad]].forEach(([field, next]) => {
    field.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      const valor = String(field.value).trim();
      if (pareceCodigo(valor)) {
        field.value = "";
        if (field === elements.scannerQty) updateConversion("scanner");
        elements.barcodeInput.value = valor;
        searchByBarcode().then(() => notify("Eso parecía un código de barras: se buscó como producto nuevo. El anterior no se guardó.", "warn"));
        return;
      }
      next.focus();
    });
  });
  elements.barcodeInput.addEventListener("input", onAutocompleteInput);
  elements.barcodeInput.addEventListener("blur", () => {
    // Delay para permitir el toque sobre un item antes de ocultar.
    window.setTimeout(hideAutocomplete, 150);
  });
  elements.saveScannerButton.addEventListener("click", () => saveEntry("scanner"));
  elements.confirmBarButton.addEventListener("click", bulkSave);
  elements.cancelEditButton.addEventListener("click", cancelEdit);
  elements.scannerCaducidad.addEventListener("input", updateCaducidadHint);
  [elements.scannerLote, elements.scannerCaducidad].forEach((f) => f.addEventListener("input", () => f.classList.remove("from-code")));
  elements.scannerCaducidad.addEventListener("change", updateCaducidadHint);
  elements.onlyNoBarcode.addEventListener("change", loadEntries);
  elements.filterLote.addEventListener("input", loadEntries);
  elements.filterCaducidad.addEventListener("change", loadEntries);
  elements.clearFiltersButton.addEventListener("click", () => {
    elements.filterLote.value = "";
    elements.filterCaducidad.value = "";
    elements.onlyNoBarcode.checked = false;
    loadEntries();
  });
  elements.printLabelsButton.addEventListener("click", openPrintView);
  elements.previewLabelsButton.addEventListener("click", renderPreview);
  elements.closePreviewButton.addEventListener("click", closePreview);
  elements.bulkButton.addEventListener("click", bulkSave);
  elements.adminUserFilter.addEventListener("change", loadAdminSummary);
  setupFieldHelp(); // P12
  elements.refreshAdminButton.addEventListener("click", refreshAdminData);
  // P16: los atajos de motivo llenan el campo (se puede seguir escribiendo).
  document.querySelectorAll("#scannerMotivoChips .chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const input = document.getElementById("scannerMotivoQc");
      input.value = chip.dataset.motivo;
      clearInvalid(input);
    });
  });
  elements.adminUserFilter.addEventListener("change", loadAdminSummary);
  document.querySelectorAll(".tab").forEach((button) => {
    // Al abrir la pantalla de escaneo, showTab enfoca el campo para el escáner HID.
    button.addEventListener("click", () => showTab(button.dataset.target));
  });
}

attachEvents();
window.addEventListener("popstate", onBackButton);
window.addEventListener("beforeunload", onBeforeUnload);

// Al recargar la página, se recupera la sesión de esta pestaña y sus pendientes.
(function restoreSession() {
  const saved = readSession();
  if (!saved || !saved.user || !saved.sessionId) return;
  state.user = saved.user;
  state.sessionId = saved.sessionId;
  enterApp({ restored: true });
})();
