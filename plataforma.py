# -*- coding: utf-8 -*-
"""
============================================================
  HORARIO DE ENTREGAS - MOODLE  |  v1.1
  ----------------------------------------------------------
  v1.1: - Limpia automaticamente la URL (puedes pegar el
          link de login o de cualquier pagina del campus)
        - Mensajes de error claros cuando el servidor no
          responde JSON o el servicio movil esta apagado
  ----------------------------------------------------------
  Conecta con la plataforma Moodle de tu universidad usando
  la API oficial (la misma de la app movil), revisa TODAS
  tus materias y arma un horario semanal con:
    - Que trabajos hay
    - Que dia y a que hora se entregan
    - Descripcion resumida de cada uno

  Requisitos:
      pip install PyQt6 requests

  Uso:
      python horario_entregas_v1.0.py
      1. Pega la URL de tu plataforma (ej: https://campus.ibero.edu.co)
      2. Usuario y contrasena (los mismos del campus virtual)
      3. Clic en "Conectar y sincronizar"
============================================================
"""

import sys
import os
import json
import re
import html
import datetime as dt

import requests
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QDate
from PyQt6.QtGui import QColor, QFont, QBrush
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QTabWidget, QListWidget, QListWidgetItem, QTextBrowser, QSplitter,
    QMessageBox, QHeaderView, QFrame, QProgressBar, QAbstractItemView
)

CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".horario_moodle.json")

DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

PALETA = ["#4fc3f7", "#81c784", "#ffb74d", "#e57373", "#ba68c8",
          "#4db6ac", "#f06292", "#a1887f", "#90a4ae", "#dce775"]


# ------------------------------------------------------------------
#  Utilidades
# ------------------------------------------------------------------
def normalizar_url(url):
    """Acepta cualquier link del campus y devuelve la raiz de Moodle.
    Ej: https://campusvirtual.ibero.edu.co/login/index.php
        -> https://campusvirtual.ibero.edu.co
    Soporta Moodle instalado en subcarpeta (…/moodle/login/index.php)."""
    url = url.strip()
    if not url.startswith("http"):
        url = "https://" + url
    url = url.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    # recortar rutas conocidas de Moodle al final
    patrones = [
        r"/login/(index|token|forgot_password)\.php$", r"/login$",
        r"/my(/.*)?$", r"/course(/.*)?$", r"/mod(/.*)?$",
        r"/calendar(/.*)?$", r"/user(/.*)?$", r"/index\.php$",
    ]
    cambio = True
    while cambio:
        cambio = False
        for p in patrones:
            nuevo = re.sub(p, "", url)
            if nuevo != url:
                url = nuevo.rstrip("/")
                cambio = True
    return url


def limpiar_html(texto, max_len=220):
    """Convierte HTML de Moodle a texto plano resumido."""
    if not texto:
        return "Sin descripción."
    t = re.sub(r"<br\s*/?>", " ", texto)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    t = re.sub(r"\s+", " ", t).strip()
    if not t:
        return "Sin descripción."
    if len(t) > max_len:
        corte = t[:max_len].rsplit(" ", 1)[0]
        t = corte + "…"
    return t


def cargar_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def guardar_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
    except Exception:
        pass


# ------------------------------------------------------------------
#  Cliente Moodle (API oficial de la app movil)
# ------------------------------------------------------------------
class MoodleClient:
    def __init__(self, base_url, token=None):
        self.base = base_url.rstrip("/")
        self.token = token
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": "MoodleMobile 4.3 (HorarioEntregas)"})

    def login(self, usuario, clave):
        """Obtiene token con usuario/contrasena (servicio de la app movil)."""
        r = self.s.get(
            f"{self.base}/login/token.php",
            params={"username": usuario, "password": clave,
                    "service": "moodle_mobile_app"},
            timeout=30,
        )
        try:
            data = r.json()
        except ValueError:
            raise RuntimeError(
                "El servidor no respondió como Moodle en:\n"
                f"{self.base}/login/token.php\n\n"
                "Posibles causas:\n"
                "• La URL no es la raíz del campus (revisa que quede solo el dominio)\n"
                "• La plataforma no es Moodle\n"
                f"(HTTP {r.status_code})")
        if "token" in data:
            self.token = data["token"]
            return self.token
        err = data.get("errorcode", "")
        if err == "enablewsdescription" or "web service" in str(data.get("error", "")).lower():
            raise RuntimeError(
                "Tu universidad tiene deshabilitados los servicios web de la "
                "app móvil, así que no se puede usar la API. Avísame y armamos "
                "la versión con inicio de sesión web.")
        if err == "invalidlogin":
            raise RuntimeError("Usuario o contraseña incorrectos. "
                               "Usa los mismos datos del campus virtual.")
        raise RuntimeError(data.get("error", "No se pudo obtener el token. "
                           "Verifica URL, usuario y contraseña."))

    def ws(self, funcion, **params):
        payload = {
            "wstoken": self.token,
            "wsfunction": funcion,
            "moodlewsrestformat": "json",
        }
        payload.update(params)
        r = self.s.post(f"{self.base}/webservice/rest/server.php",
                        data=payload, timeout=45)
        try:
            data = r.json()
        except ValueError:
            raise RuntimeError(
                f"{funcion}: el servidor no devolvió JSON (HTTP {r.status_code}). "
                "Vuelve a sincronizar; si persiste, la sesión pudo vencer.")
        if isinstance(data, dict) and data.get("exception"):
            raise RuntimeError(f"{funcion}: {data.get('message')}")
        return data

    def info_sitio(self):
        return self.ws("core_webservice_get_site_info")

    def mis_cursos(self, userid):
        return self.ws("core_enrol_get_users_courses", userid=userid)

    def tareas_de_cursos(self, ids):
        params = {}
        for i, cid in enumerate(ids):
            params[f"courseids[{i}]"] = cid
        return self.ws("mod_assign_get_assignments", **params)

    def eventos_calendario(self, dias_adelante=60):
        ahora = int(dt.datetime.now().timestamp())
        return self.ws(
            "core_calendar_get_action_events_by_timesort",
            timesortfrom=ahora - 86400,
            timesortto=ahora + dias_adelante * 86400,
            limitnum=50,
        )


# ------------------------------------------------------------------
#  Hilo de sincronizacion
# ------------------------------------------------------------------
class SyncWorker(QThread):
    progreso = pyqtSignal(str)
    listo = pyqtSignal(list, dict)      # entregas, cfg
    error = pyqtSignal(str)

    def __init__(self, url, usuario, clave, token=None):
        super().__init__()
        self.url, self.usuario, self.clave, self.token = url, usuario, clave, token

    def run(self):
        try:
            cli = MoodleClient(self.url, self.token)
            if not cli.token:
                self.progreso.emit("Iniciando sesión…")
                cli.login(self.usuario, self.clave)

            self.progreso.emit("Obteniendo perfil…")
            try:
                info = cli.info_sitio()
            except Exception:
                # token viejo invalido -> reintentar login
                cli.token = None
                cli.login(self.usuario, self.clave)
                info = cli.info_sitio()
            userid = info["userid"]

            self.progreso.emit("Buscando tus materias…")
            cursos = cli.mis_cursos(userid)
            mapa_cursos = {c["id"]: c.get("fullname", c.get("shortname", "?"))
                           for c in cursos}

            entregas = []
            vistos = set()

            # --- Tareas (mod_assign) ---
            self.progreso.emit(f"Revisando tareas en {len(cursos)} materias…")
            if cursos:
                data = cli.tareas_de_cursos(list(mapa_cursos.keys()))
                for curso in data.get("courses", []):
                    nombre_curso = mapa_cursos.get(curso["id"], curso.get("fullname", "?"))
                    for a in curso.get("assignments", []):
                        due = a.get("duedate", 0)
                        if not due:
                            continue
                        clave = ("assign", a["id"])
                        vistos.add(clave)
                        entregas.append({
                            "curso": nombre_curso,
                            "titulo": a.get("name", "Tarea"),
                            "tipo": "Tarea",
                            "fecha": dt.datetime.fromtimestamp(due),
                            "descripcion": limpiar_html(a.get("intro", "")),
                        })

            # --- Eventos del calendario (quices, foros, etc.) ---
            self.progreso.emit("Revisando calendario (quices, foros)…")
            try:
                eventos = cli.eventos_calendario()
                for e in eventos.get("events", []):
                    mod = e.get("modulename", "") or "evento"
                    inst = e.get("instance", 0)
                    if ("assign", inst) in vistos and mod == "assign":
                        continue
                    ts = e.get("timesort") or e.get("timestart", 0)
                    if not ts:
                        continue
                    tipo = {"assign": "Tarea", "quiz": "Quiz",
                            "forum": "Foro", "workshop": "Taller",
                            "lesson": "Lección"}.get(mod, mod.capitalize())
                    curso_nombre = (e.get("course") or {}).get("fullname", "General")
                    entregas.append({
                        "curso": curso_nombre,
                        "titulo": e.get("name", "Actividad"),
                        "tipo": tipo,
                        "fecha": dt.datetime.fromtimestamp(ts),
                        "descripcion": limpiar_html(e.get("description", "")),
                    })
            except Exception:
                pass  # si el sitio no expone calendario, seguimos con las tareas

            entregas.sort(key=lambda x: x["fecha"])
            cfg = {"url": self.url, "usuario": self.usuario, "token": cli.token}
            self.listo.emit(entregas, cfg)

        except Exception as ex:
            self.error.emit(str(ex))


# ------------------------------------------------------------------
#  Ventana principal
# ------------------------------------------------------------------
class Ventana(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("📚 Horario de Entregas — Moodle v1.1")
        self.resize(1150, 700)
        self.entregas = []
        self.colores = {}
        self.lunes_actual = self._lunes_de(dt.date.today())
        self._ui()
        self._estilos()
        self._cargar_guardado()

    # ---------------- UI ----------------
    def _ui(self):
        raiz = QWidget()
        self.setCentralWidget(raiz)
        lay = QVBoxLayout(raiz)

        # --- Barra de conexion ---
        barra = QFrame(); barra.setObjectName("barra")
        bl = QHBoxLayout(barra)
        self.in_url = QLineEdit(); self.in_url.setPlaceholderText("URL de la plataforma (ej: https://campus.ibero.edu.co)")
        self.in_user = QLineEdit(); self.in_user.setPlaceholderText("Usuario")
        self.in_pass = QLineEdit(); self.in_pass.setPlaceholderText("Contraseña")
        self.in_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.btn_sync = QPushButton("🔄 Conectar y sincronizar")
        self.btn_sync.clicked.connect(self.sincronizar)
        bl.addWidget(self.in_url, 3)
        bl.addWidget(self.in_user, 1)
        bl.addWidget(self.in_pass, 1)
        bl.addWidget(self.btn_sync)
        lay.addWidget(barra)

        self.lbl_estado = QLabel("Listo. Ingresa tus datos y sincroniza.")
        self.barra_prog = QProgressBar(); self.barra_prog.setRange(0, 0)
        self.barra_prog.hide()
        fila_est = QHBoxLayout()
        fila_est.addWidget(self.lbl_estado); fila_est.addWidget(self.barra_prog)
        lay.addLayout(fila_est)

        # --- Pestañas ---
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs, 1)

        # Pestaña 1: horario semanal
        w_sem = QWidget(); vsem = QVBoxLayout(w_sem)
        nav = QHBoxLayout()
        self.btn_prev = QPushButton("◀ Semana anterior")
        self.btn_hoy = QPushButton("Hoy")
        self.btn_next = QPushButton("Semana siguiente ▶")
        self.lbl_semana = QLabel(); self.lbl_semana.setObjectName("titSemana")
        self.btn_prev.clicked.connect(lambda: self._mover_semana(-1))
        self.btn_next.clicked.connect(lambda: self._mover_semana(1))
        self.btn_hoy.clicked.connect(self._ir_hoy)
        nav.addWidget(self.btn_prev); nav.addWidget(self.btn_hoy)
        nav.addWidget(self.btn_next); nav.addStretch()
        nav.addWidget(self.lbl_semana)
        vsem.addLayout(nav)

        self.tabla = QTableWidget(0, 7)
        self.tabla.setHorizontalHeaderLabels(DIAS)
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabla.verticalHeader().hide()
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setWordWrap(True)
        self.tabla.cellClicked.connect(self._detalle_celda)
        vsem.addWidget(self.tabla)
        self.tabs.addTab(w_sem, "🗓️  Horario semanal")

        # Pestaña 2: proximas entregas + detalle
        split = QSplitter()
        self.lista = QListWidget()
        self.lista.currentRowChanged.connect(self._detalle_lista)
        self.detalle = QTextBrowser()
        split.addWidget(self.lista); split.addWidget(self.detalle)
        split.setSizes([480, 620])
        self.tabs.addTab(split, "⏰  Próximas entregas")

    def _estilos(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background:#12141c; color:#e8eaf0;
                font-family:'Segoe UI'; font-size:13px; }
            #barra { background:#1b1e2b; border-radius:8px; padding:6px; }
            QLineEdit { background:#232738; border:1px solid #2f3450;
                border-radius:6px; padding:7px; color:#e8eaf0; }
            QLineEdit:focus { border:1px solid #4fc3f7; }
            QPushButton { background:#2b5cff; border:none; border-radius:6px;
                padding:8px 14px; color:white; font-weight:bold; }
            QPushButton:hover { background:#3d6bff; }
            QPushButton:disabled { background:#39405c; }
            QTabWidget::pane { border:1px solid #2f3450; border-radius:6px; }
            QTabBar::tab { background:#1b1e2b; padding:9px 18px;
                border-top-left-radius:6px; border-top-right-radius:6px; }
            QTabBar::tab:selected { background:#2b5cff; }
            QTableWidget { background:#161927; gridline-color:#2a2f45; }
            QHeaderView::section { background:#1b1e2b; padding:6px;
                border:none; font-weight:bold; color:#4fc3f7; }
            QListWidget { background:#161927; border:1px solid #2f3450;
                border-radius:6px; }
            QListWidget::item { padding:8px; border-bottom:1px solid #22263a; }
            QListWidget::item:selected { background:#2b5cff; }
            QTextBrowser { background:#161927; border:1px solid #2f3450;
                border-radius:6px; padding:10px; }
            #titSemana { font-size:15px; font-weight:bold; color:#4fc3f7; }
            QProgressBar { max-width:160px; background:#232738;
                border-radius:4px; height:10px; }
            QProgressBar::chunk { background:#2b5cff; border-radius:4px; }
        """)

    # ---------------- Sincronizacion ----------------
    def _cargar_guardado(self):
        cfg = cargar_config()
        self.in_url.setText(cfg.get("url", ""))
        self.in_user.setText(cfg.get("usuario", ""))
        self._token_guardado = cfg.get("token")
        if cfg.get("url") and self._token_guardado:
            self.lbl_estado.setText("Sesión guardada encontrada. Sincronizando…")
            self.sincronizar(auto=True)

    def sincronizar(self, auto=False):
        url = self.in_url.text().strip()
        if not url:
            QMessageBox.warning(self, "Falta la URL",
                                "Pega la URL de tu plataforma Moodle.")
            return
        url = normalizar_url(url)
        self.in_url.setText(url)   # muestra la URL ya limpia
        token = self._token_guardado if auto else None
        if not token and (not self.in_user.text() or not self.in_pass.text()):
            QMessageBox.warning(self, "Faltan datos",
                                "Escribe tu usuario y contraseña del campus.")
            return

        self.btn_sync.setEnabled(False)
        self.barra_prog.show()
        self.worker = SyncWorker(url, self.in_user.text().strip(),
                                 self.in_pass.text(), token)
        self.worker.progreso.connect(self.lbl_estado.setText)
        self.worker.listo.connect(self._sync_ok)
        self.worker.error.connect(self._sync_error)
        self.worker.start()

    def _sync_ok(self, entregas, cfg):
        self.entregas = entregas
        self._token_guardado = cfg["token"]
        guardar_config(cfg)          # guarda URL, usuario y token (NO la contraseña)
        self.barra_prog.hide()
        self.btn_sync.setEnabled(True)
        self.lbl_estado.setText(
            f"✅ Sincronizado: {len(entregas)} actividades con fecha encontradas.")
        self._asignar_colores()
        self._pintar_semana()
        self._pintar_lista()

    def _sync_error(self, msg):
        self.barra_prog.hide()
        self.btn_sync.setEnabled(True)
        self.lbl_estado.setText("❌ Error al sincronizar.")
        QMessageBox.critical(self, "Error", msg)

    # ---------------- Horario semanal ----------------
    @staticmethod
    def _lunes_de(fecha):
        return fecha - dt.timedelta(days=fecha.weekday())

    def _mover_semana(self, delta):
        self.lunes_actual += dt.timedelta(weeks=delta)
        self._pintar_semana()

    def _ir_hoy(self):
        self.lunes_actual = self._lunes_de(dt.date.today())
        self._pintar_semana()

    def _asignar_colores(self):
        cursos = sorted({e["curso"] for e in self.entregas})
        self.colores = {c: PALETA[i % len(PALETA)] for i, c in enumerate(cursos)}

    def _entregas_semana(self):
        fin = self.lunes_actual + dt.timedelta(days=7)
        cols = {i: [] for i in range(7)}
        for e in self.entregas:
            f = e["fecha"].date()
            if self.lunes_actual <= f < fin:
                cols[f.weekday()].append(e)
        return cols

    def _pintar_semana(self):
        fin = self.lunes_actual + dt.timedelta(days=6)
        self.lbl_semana.setText(
            f"{self.lunes_actual.strftime('%d/%m/%Y')} — {fin.strftime('%d/%m/%Y')}")
        cols = self._entregas_semana()
        filas = max([len(v) for v in cols.values()] + [1])
        self.tabla.setRowCount(filas)
        self.tabla.clearContents()
        self._celdas = {}

        hoy = dt.date.today()
        for d in range(7):
            # resaltar encabezado del dia actual
            hdr = QTableWidgetItem(DIAS[d] + " " +
                    (self.lunes_actual + dt.timedelta(days=d)).strftime("%d/%m"))
            self.tabla.setHorizontalHeaderItem(d, hdr)
            for fila, e in enumerate(cols[d]):
                txt = f"⏰ {e['fecha'].strftime('%I:%M %p')}\n{e['tipo']}: {e['titulo']}\n📘 {e['curso']}"
                item = QTableWidgetItem(txt)
                color = QColor(self.colores.get(e["curso"], "#4fc3f7"))
                color.setAlpha(45)
                item.setBackground(QBrush(color))
                item.setForeground(QBrush(QColor("#e8eaf0")))
                if e["fecha"].date() == hoy:
                    f2 = QFont(); f2.setBold(True); item.setFont(f2)
                self.tabla.setItem(fila, d, item)
                self._celdas[(fila, d)] = e
        self.tabla.resizeRowsToContents()

    def _detalle_celda(self, fila, col):
        e = self._celdas.get((fila, col))
        if e:
            self._mostrar_detalle(e)
            self.tabs.setCurrentIndex(1)

    # ---------------- Lista de proximas ----------------
    def _pintar_lista(self):
        self.lista.clear()
        ahora = dt.datetime.now()
        self._orden_lista = []
        for e in self.entregas:
            if e["fecha"] < ahora - dt.timedelta(days=1):
                continue
            delta = e["fecha"] - ahora
            if delta.total_seconds() < 0:
                cuenta = "⚠️ VENCE HOY"
            elif delta.days == 0:
                cuenta = f"🔥 en {delta.seconds // 3600} h"
            else:
                cuenta = f"en {delta.days} día(s)"
            it = QListWidgetItem(
                f"{e['fecha'].strftime('%a %d/%m %I:%M %p')}  ·  {cuenta}\n"
                f"{e['tipo']}: {e['titulo']}  —  {e['curso']}")
            it.setForeground(QBrush(QColor(self.colores.get(e["curso"], "#e8eaf0"))))
            self.lista.addItem(it)
            self._orden_lista.append(e)
        if not self._orden_lista:
            self.lista.addItem("🎉 No hay entregas pendientes próximas.")

    def _detalle_lista(self, fila):
        if 0 <= fila < len(getattr(self, "_orden_lista", [])):
            self._mostrar_detalle(self._orden_lista[fila])

    def _mostrar_detalle(self, e):
        color = self.colores.get(e["curso"], "#4fc3f7")
        self.detalle.setHtml(f"""
            <h2 style='color:{color};margin-bottom:2px'>{e['titulo']}</h2>
            <p style='color:#9aa3c0'>{e['tipo']} · {e['curso']}</p>
            <p><b>📅 Se entrega:</b> {DIAS[e['fecha'].weekday()]}
               {e['fecha'].strftime('%d/%m/%Y a las %I:%M %p')}</p>
            <hr style='border-color:#2f3450'>
            <p><b>📝 Descripción resumida:</b><br>{e['descripcion']}</p>
        """)


# ------------------------------------------------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    v = Ventana()
    v.show()
    sys.exit(app.exec())