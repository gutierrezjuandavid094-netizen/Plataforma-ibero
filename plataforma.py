# -*- coding: utf-8 -*-
"""
============================================================
  CAMPUS FLOW - MOODLE + MICROSOFT TEAMS  |  v2.0
  ----------------------------------------------------------
  v2.0: - Busca enlaces de Teams en el calendario y en los
          recursos, paginas y secciones de cada materia
        - Muestra las reuniones mas cercanas y una vista
          agrupada por materias
        - Incorpora una interfaz renovada y navegacion inmediata
  ----------------------------------------------------------
  Conecta con la plataforma Moodle de tu universidad usando
  la API oficial (la misma de la app movil), revisa TODAS
  tus materias y arma un horario semanal con:
    - Que trabajos hay
    - Que dia y a que hora se entregan
    - Descripcion resumida de cada uno
    - Acceso directo a las reuniones de Microsoft Teams

  Requisitos:
      pip install PyQt6 requests

  Uso:
      python plataforma.py
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
from urllib.parse import unquote, urlparse

import requests
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl
from PyQt6.QtGui import QColor, QFont, QBrush, QDesktopServices
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QTabWidget, QListWidget, QListWidgetItem, QTextBrowser, QSplitter,
    QMessageBox, QHeaderView, QFrame, QProgressBar, QAbstractItemView,
    QTreeWidget, QTreeWidgetItem
)

CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".horario_moodle.json")

DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

PALETA = ["#4fc3f7", "#81c784", "#ffb74d", "#e57373", "#ba68c8",
          "#4db6ac", "#f06292", "#a1887f", "#90a4ae", "#dce775"]

DOMINIOS_TEAMS = {
    "teams.microsoft.com", "teams.live.com", "msteams.link"
}


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


def extraer_links_teams(*textos):
    """Extrae y normaliza enlaces directos de Microsoft Teams."""
    encontrados = []
    vistos = set()
    patron = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

    for texto in textos:
        if not texto:
            continue
        original = html.unescape(str(texto))
        variantes = [original]
        # También encuentra Teams dentro de redirecciones con URL codificada.
        for _ in range(2):
            decodificada = unquote(variantes[-1])
            if decodificada == variantes[-1]:
                break
            variantes.append(decodificada)

        for variante in variantes:
            for candidato in patron.findall(variante):
                candidato = html.unescape(candidato).rstrip(".,;:!?)']}\"")
                try:
                    partes = urlparse(candidato)
                    host = (partes.hostname or "").lower()
                    ruta = partes.path.lower()
                except ValueError:
                    continue
                es_teams = host in DOMINIOS_TEAMS or host.endswith(".teams.microsoft.com")
                es_atajo = host == "aka.ms" and ("teams" in ruta or "join" in ruta)
                if not (es_teams or es_atajo):
                    continue
                clave = candidato.lower()
                if clave not in vistos:
                    vistos.add(clave)
                    encontrados.append(candidato)
    return encontrados


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

    def eventos_calendario_completos(self, ids, dias_adelante=120):
        """Incluye eventos sin acción, donde suelen publicarse las clases."""
        ahora = int(dt.datetime.now().timestamp())
        params = {
            "options[userevents]": 0,
            "options[siteevents]": 0,
            "options[timestart]": ahora - 86400,
            "options[timeend]": ahora + dias_adelante * 86400,
            "options[ignorehidden]": 1,
        }
        for i, cid in enumerate(ids):
            params[f"events[courseids][{i}]"] = cid
        return self.ws("core_calendar_get_calendar_events", **params)

    def recursos_url(self, ids):
        params = {f"courseids[{i}]": cid for i, cid in enumerate(ids)}
        return self.ws("mod_url_get_urls_by_courses", **params)

    def paginas(self, ids):
        params = {f"courseids[{i}]": cid for i, cid in enumerate(ids)}
        return self.ws("mod_page_get_pages_by_courses", **params)

    def etiquetas(self, ids):
        params = {f"courseids[{i}]": cid for i, cid in enumerate(ids)}
        return self.ws("mod_label_get_labels_by_courses", **params)

    def contenido_curso(self, courseid):
        return self.ws("core_course_get_contents", courseid=courseid)


# ------------------------------------------------------------------
#  Hilo de sincronizacion
# ------------------------------------------------------------------
class SyncWorker(QThread):
    progreso = pyqtSignal(str)
    listo = pyqtSignal(list, list, dict)      # entregas, reuniones, cfg
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
            ids_cursos = list(mapa_cursos.keys())

            entregas = []
            reuniones = []
            vistos = set()
            reuniones_vistas = set()

            def curso_de(objeto):
                curso = objeto.get("course")
                if isinstance(curso, dict):
                    return curso.get("fullname") or curso.get("shortname") or "General"
                cid = objeto.get("courseid", curso)
                try:
                    cid = int(cid)
                except (TypeError, ValueError):
                    pass
                return mapa_cursos.get(cid, objeto.get("coursefullname", "General"))

            def agregar_reuniones(curso, titulo, fecha, descripcion, origen, *campos):
                for enlace in extraer_links_teams(descripcion, *campos):
                    marca_fecha = int(fecha.timestamp()) if fecha else None
                    clave_reunion = (curso, enlace.lower(), marca_fecha)
                    if clave_reunion in reuniones_vistas:
                        continue
                    reuniones_vistas.add(clave_reunion)
                    reuniones.append({
                        "curso": curso or "General",
                        "titulo": titulo or "Reunión de Teams",
                        "fecha": fecha,
                        "url": enlace,
                        "descripcion": limpiar_html(descripcion, 360),
                        "origen": origen,
                    })

            # --- Tareas (mod_assign) ---
            self.progreso.emit(f"Revisando tareas en {len(cursos)} materias…")
            if cursos:
                data = cli.tareas_de_cursos(ids_cursos)
                for curso in data.get("courses", []):
                    curso_nombre = mapa_cursos.get(curso["id"], curso.get("fullname", "?"))
                    for a in curso.get("assignments", []):
                        due = a.get("duedate", 0)
                        if not due:
                            continue
                        clave = ("assign", a["id"])
                        vistos.add(clave)
                        entregas.append({
                            "curso": curso_nombre,
                            "titulo": a.get("name", "Tarea"),
                            "tipo": "Tarea",
                            "fecha": dt.datetime.fromtimestamp(due),
                            "descripcion": limpiar_html(a.get("intro", "")),
                        })

            # --- Eventos del calendario (quices, foros, etc.) ---
            self.progreso.emit("Revisando calendario y reuniones próximas…")
            eventos_accion = []
            try:
                eventos = cli.eventos_calendario()
                eventos_accion = eventos.get("events", [])
                for e in eventos_accion:
                    mod = e.get("modulename", "") or "evento"
                    inst = e.get("instance", 0)
                    ts = e.get("timesort") or e.get("timestart", 0)
                    if not ts:
                        continue
                    fecha_evento = dt.datetime.fromtimestamp(ts)
                    curso_nombre = curso_de(e)
                    agregar_reuniones(
                        curso_nombre, e.get("name"), fecha_evento,
                        e.get("description", ""), "Calendario",
                        e.get("url", ""), (e.get("action") or {}).get("url", ""),
                        json.dumps(e, ensure_ascii=False)
                    )
                    if ("assign", inst) in vistos and mod == "assign":
                        continue
                    tipo = {"assign": "Tarea", "quiz": "Quiz",
                            "forum": "Foro", "workshop": "Taller",
                            "lesson": "Lección"}.get(mod, mod.capitalize())
                    entregas.append({
                        "curso": curso_nombre,
                        "titulo": e.get("name", "Actividad"),
                        "tipo": tipo,
                        "fecha": fecha_evento,
                        "descripcion": limpiar_html(e.get("description", "")),
                    })
            except Exception:
                pass  # si el sitio no expone calendario, seguimos con las tareas

            # Los eventos normales no siempre aparecen como actividades pendientes.
            try:
                completos = cli.eventos_calendario_completos(ids_cursos)
                for e in completos.get("events", []):
                    ts = e.get("timestart") or e.get("timesort", 0)
                    fecha_evento = dt.datetime.fromtimestamp(ts) if ts else None
                    agregar_reuniones(
                        curso_de(e), e.get("name"), fecha_evento,
                        e.get("description", ""), "Calendario",
                        e.get("url", ""), e.get("eventtype", ""),
                        json.dumps(e, ensure_ascii=False)
                    )
            except Exception:
                pass

            # Enlaces permanentes publicados como recurso, página o etiqueta.
            self.progreso.emit("Buscando enlaces de Microsoft Teams por materia…")
            fuentes = [
                (cli.recursos_url, "urls", "Recurso del curso"),
                (cli.paginas, "pages", "Página del curso"),
                (cli.etiquetas, "labels", "Etiqueta del curso"),
            ]
            for obtener, llave, origen in fuentes:
                try:
                    data = obtener(ids_cursos)
                    for recurso in data.get(llave, []):
                        agregar_reuniones(
                            curso_de(recurso), recurso.get("name"), None,
                            recurso.get("intro", "") or recurso.get("content", ""),
                            origen, recurso.get("externalurl", ""),
                            recurso.get("url", ""), recurso.get("content", ""),
                            json.dumps(recurso, ensure_ascii=False)
                        )
                except Exception:
                    pass

            # Último respaldo: inspeccionar las secciones visibles de cada materia.
            for indice, cid in enumerate(ids_cursos, start=1):
                if indice == 1 or indice % 5 == 0:
                    self.progreso.emit(
                        f"Revisando recursos de Teams ({indice}/{len(ids_cursos)})…")
                try:
                    for seccion in cli.contenido_curso(cid):
                        for modulo in seccion.get("modules", []):
                            extras = [modulo.get("url", "")]
                            for contenido in modulo.get("contents", []):
                                extras.extend([
                                    contenido.get("fileurl", ""),
                                    contenido.get("externalurl", ""),
                                ])
                            agregar_reuniones(
                                mapa_cursos.get(cid, "General"), modulo.get("name"),
                                None, modulo.get("description", ""),
                                "Contenido del curso", *extras,
                                json.dumps(modulo, ensure_ascii=False)
                            )
                except Exception:
                    pass

            # También puede estar publicado en el resumen de la materia.
            for curso in cursos:
                agregar_reuniones(
                    mapa_cursos.get(curso["id"], "General"),
                    "Sala principal de Teams", None, curso.get("summary", ""),
                    "Resumen de la materia", curso.get("viewurl", "")
                )

            entregas.sort(key=lambda x: x["fecha"])
            # Si el calendario ya aporta fechas, se omite su copia sin fecha.
            limite_visible = dt.datetime.now() - dt.timedelta(hours=4)
            con_fecha = {
                (r["curso"], r["url"].lower()) for r in reuniones
                if r["fecha"] and r["fecha"] >= limite_visible
            }
            reuniones = [
                r for r in reuniones
                if r["fecha"] or (r["curso"], r["url"].lower()) not in con_fecha
            ]
            reuniones.sort(key=lambda r: (
                r["fecha"] is None,
                r["fecha"] or dt.datetime.max,
                r["curso"].lower(),
                r["titulo"].lower(),
            ))
            cfg = {"url": self.url, "usuario": self.usuario, "token": cli.token}
            self.listo.emit(entregas, reuniones, cfg)

        except Exception as ex:
            self.error.emit(str(ex))


# ------------------------------------------------------------------
#  Ventana principal
# ------------------------------------------------------------------
class Ventana(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Campus Flow — Moodle y Microsoft Teams")
        self.resize(1240, 790)
        self.setMinimumSize(980, 650)
        self.entregas = []
        self.reuniones = []
        self.colores = {}
        self._sincronizado = False
        self.lunes_actual = self._lunes_de(dt.date.today())
        self._ui()
        self._estilos()
        self._configurar_movimiento_suave()
        self._pintar_semana()
        self._pintar_lista()
        self._pintar_reuniones()
        self._cargar_guardado()

    # ---------------- UI ----------------
    def _ui(self):
        raiz = QWidget()
        raiz.setObjectName("raiz")
        self.setCentralWidget(raiz)
        lay = QVBoxLayout(raiz)
        lay.setContentsMargins(18, 16, 18, 18)
        lay.setSpacing(11)

        # --- Encabezado ---
        cabecera = QFrame(); cabecera.setObjectName("cabecera")
        ch = QHBoxLayout(cabecera); ch.setContentsMargins(18, 12, 18, 12)
        textos = QVBoxLayout(); textos.setSpacing(1)
        titulo = QLabel("Campus Flow"); titulo.setObjectName("tituloApp")
        subtitulo = QLabel("Tus entregas y reuniones de Teams, en un solo lugar")
        subtitulo.setObjectName("subtituloApp")
        textos.addWidget(titulo); textos.addWidget(subtitulo)
        self.lbl_resumen = QLabel("Aún no has sincronizado")
        self.lbl_resumen.setObjectName("resumen")
        self.lbl_resumen.setAlignment(Qt.AlignmentFlag.AlignRight |
                                      Qt.AlignmentFlag.AlignVCenter)
        ch.addLayout(textos); ch.addStretch(); ch.addWidget(self.lbl_resumen)
        lay.addWidget(cabecera)

        # --- Barra de conexion ---
        barra = QFrame(); barra.setObjectName("barra")
        bl = QHBoxLayout(barra); bl.setContentsMargins(12, 10, 12, 10)
        bl.setSpacing(9)
        self.in_url = QLineEdit(); self.in_url.setPlaceholderText("URL de la plataforma (ej: https://campus.ibero.edu.co)")
        self.in_user = QLineEdit(); self.in_user.setPlaceholderText("Usuario")
        self.in_pass = QLineEdit(); self.in_pass.setPlaceholderText("Contraseña")
        self.in_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.in_pass.returnPressed.connect(self.sincronizar)
        self.btn_sync = QPushButton("↻  Sincronizar")
        self.btn_sync.setObjectName("principal")
        self.btn_sync.setToolTip("Actualizar entregas y enlaces de Teams")
        self.btn_sync.clicked.connect(self.sincronizar)
        bl.addWidget(self.in_url, 3)
        bl.addWidget(self.in_user, 1)
        bl.addWidget(self.in_pass, 1)
        bl.addWidget(self.btn_sync)
        lay.addWidget(barra)

        self.lbl_estado = QLabel("Listo para conectar con Moodle.")
        self.lbl_estado.setObjectName("estado")
        self.barra_prog = QProgressBar(); self.barra_prog.setRange(0, 0)
        self.barra_prog.hide()
        fila_est = QHBoxLayout()
        fila_est.addWidget(self.lbl_estado); fila_est.addWidget(self.barra_prog)
        lay.addLayout(fila_est)

        # --- Pestañas ---
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        lay.addWidget(self.tabs, 1)

        # Pestaña 1: horario semanal
        w_sem = QWidget(); vsem = QVBoxLayout(w_sem); vsem.setContentsMargins(12, 12, 12, 12)
        nav = QHBoxLayout()
        self.btn_prev = QPushButton("‹  Semana anterior")
        self.btn_hoy = QPushButton("Hoy")
        self.btn_hoy.setObjectName("secundario")
        self.btn_next = QPushButton("Semana siguiente  ›")
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
        self.tabla.verticalHeader().setDefaultSectionSize(78)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.setWordWrap(True)
        self.tabla.cellClicked.connect(self._detalle_celda)
        vsem.addWidget(self.tabla)
        self.tabs.addTab(w_sem, "  Calendario semanal  ")

        # Pestaña 2: cierres de la semana seleccionada + detalle.
        w_cierres = QWidget()
        vc = QVBoxLayout(w_cierres); vc.setContentsMargins(12, 12, 12, 12)
        nav_cierres = QHBoxLayout()
        self.btn_prev_lista = QPushButton("‹  Semana anterior")
        self.btn_hoy_lista = QPushButton("Semana actual")
        self.btn_hoy_lista.setObjectName("secundario")
        self.btn_next_lista = QPushButton("Semana siguiente  ›")
        self.lbl_semana_lista = QLabel(); self.lbl_semana_lista.setObjectName("titSemana")
        self.btn_prev_lista.clicked.connect(lambda: self._mover_semana(-1))
        self.btn_hoy_lista.clicked.connect(self._ir_hoy)
        self.btn_next_lista.clicked.connect(lambda: self._mover_semana(1))
        nav_cierres.addWidget(self.btn_prev_lista)
        nav_cierres.addWidget(self.btn_hoy_lista)
        nav_cierres.addWidget(self.btn_next_lista)
        nav_cierres.addStretch()
        nav_cierres.addWidget(self.lbl_semana_lista)
        vc.addLayout(nav_cierres)

        split = QSplitter()
        self.lista = QListWidget()
        self.lista.setSpacing(3)
        self.lista.currentRowChanged.connect(self._detalle_lista)
        self.detalle = QTextBrowser()
        split.addWidget(self.lista); split.addWidget(self.detalle)
        split.setSizes([480, 620])
        vc.addWidget(split, 1)
        self.tabs.addTab(w_cierres, "  Cierres de la semana  ")

        # Pestaña 3: reuniones generales y agrupadas por materia.
        w_reuniones = QWidget()
        vr = QVBoxLayout(w_reuniones); vr.setContentsMargins(10, 10, 10, 10)
        aviso = QLabel(
            "Acceso rápido a las salas de Microsoft Teams encontradas en tus cursos")
        aviso.setObjectName("ayuda")
        vr.addWidget(aviso)
        self.tabs_reuniones = QTabWidget()
        self.tabs_reuniones.setObjectName("tabsReuniones")
        vr.addWidget(self.tabs_reuniones, 1)

        # Reuniones más cercanas de todas las materias.
        split_cercanas = QSplitter()
        panel_lista = QFrame(); panel_lista.setObjectName("panel")
        vl = QVBoxLayout(panel_lista); vl.setContentsMargins(10, 10, 10, 10)
        lbl_cercanas = QLabel("Lo más cercano"); lbl_cercanas.setObjectName("tituloPanel")
        self.lista_reuniones = QListWidget(); self.lista_reuniones.setSpacing(3)
        self.lista_reuniones.currentRowChanged.connect(self._detalle_reunion_general)
        self.lista_reuniones.itemDoubleClicked.connect(self._abrir_reunion_general)
        vl.addWidget(lbl_cercanas); vl.addWidget(self.lista_reuniones, 1)

        panel_detalle = QFrame(); panel_detalle.setObjectName("panel")
        vd = QVBoxLayout(panel_detalle); vd.setContentsMargins(10, 10, 10, 10)
        self.detalle_reunion = QTextBrowser()
        self.btn_abrir_general = QPushButton("Abrir reunión en Teams  ↗")
        self.btn_abrir_general.setObjectName("teams")
        self.btn_abrir_general.hide()
        self.btn_abrir_general.clicked.connect(
            lambda: self._abrir_desde_boton(self.btn_abrir_general))
        vd.addWidget(self.detalle_reunion, 1); vd.addWidget(self.btn_abrir_general)
        split_cercanas.addWidget(panel_lista); split_cercanas.addWidget(panel_detalle)
        split_cercanas.setSizes([500, 610])
        self.tabs_reuniones.addTab(split_cercanas, "  Más cercanas  ")

        # Árbol de reuniones separado por materias.
        split_materias = QSplitter()
        panel_arbol = QFrame(); panel_arbol.setObjectName("panel")
        va = QVBoxLayout(panel_arbol); va.setContentsMargins(10, 10, 10, 10)
        lbl_materias = QLabel("Reuniones por materia"); lbl_materias.setObjectName("tituloPanel")
        self.arbol_reuniones = QTreeWidget()
        self.arbol_reuniones.setHeaderLabels(["Materia / reunión", "Fecha"])
        self.arbol_reuniones.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.arbol_reuniones.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.arbol_reuniones.currentItemChanged.connect(self._detalle_reunion_materia)
        self.arbol_reuniones.itemDoubleClicked.connect(self._abrir_reunion_materia)
        va.addWidget(lbl_materias); va.addWidget(self.arbol_reuniones, 1)

        panel_detalle_m = QFrame(); panel_detalle_m.setObjectName("panel")
        vm = QVBoxLayout(panel_detalle_m); vm.setContentsMargins(10, 10, 10, 10)
        self.detalle_reunion_materia = QTextBrowser()
        self.btn_abrir_materia = QPushButton("Abrir reunión en Teams  ↗")
        self.btn_abrir_materia.setObjectName("teams")
        self.btn_abrir_materia.hide()
        self.btn_abrir_materia.clicked.connect(
            lambda: self._abrir_desde_boton(self.btn_abrir_materia))
        vm.addWidget(self.detalle_reunion_materia, 1); vm.addWidget(self.btn_abrir_materia)
        split_materias.addWidget(panel_arbol); split_materias.addWidget(panel_detalle_m)
        split_materias.setSizes([560, 550])
        self.tabs_reuniones.addTab(split_materias, "  Por materias  ")

        self.tabs.addTab(w_reuniones, "  Reuniones de Teams  ")

    def _estilos(self):
        self.setStyleSheet("""
            QMainWindow, QWidget#raiz { background:#0b0e16; color:#edf1fa;
                font-family:'Segoe UI','Inter',sans-serif; font-size:13px; }
            QWidget { color:#edf1fa; }
            #cabecera { background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #202c55, stop:1 #16294b); border:1px solid #314774;
                border-radius:14px; }
            #tituloApp { font-size:23px; font-weight:800; color:#ffffff; }
            #subtituloApp, #ayuda { color:#aeb9d3; }
            #resumen { color:#c9d7ff; font-weight:600; padding:6px 10px;
                background:rgba(255,255,255,18); border-radius:8px; }
            #barra, #panel { background:#131824; border:1px solid #252d42;
                border-radius:12px; }
            #estado { color:#9eabc7; padding-left:4px; }
            #tituloPanel { font-size:15px; font-weight:700; color:#dce6ff;
                padding:2px 3px 6px 3px; }
            QLineEdit { background:#0f1420; border:1px solid #2c354c;
                border-radius:8px; padding:9px 11px; color:#f2f5fb;
                selection-background-color:#4267dc; }
            QLineEdit:hover { border-color:#3a4765; }
            QLineEdit:focus { border:1px solid #6c8dff; background:#121a2a; }
            QPushButton { background:#29344e; border:1px solid #3a4664;
                border-radius:8px; padding:8px 14px; color:#e9efff;
                font-weight:650; }
            QPushButton:hover { background:#354360; border-color:#526487; }
            QPushButton:pressed { background:#202a40; border-color:#7e96c5; }
            QPushButton#principal { background:#526fec; border-color:#6f88f6; }
            QPushButton#principal:hover { background:#6380f5; }
            QPushButton#secundario { background:#192136; color:#9fb5ff; }
            QPushButton#teams { background:#5865d8; border-color:#7782ec;
                font-size:14px; padding:10px 18px; }
            QPushButton#teams:hover { background:#6976e8; }
            QPushButton:disabled { background:#242b3b; color:#68728b;
                border-color:#30384a; }
            QTabWidget::pane { background:#101521; border:1px solid #252d42;
                border-radius:11px; top:-1px; }
            QTabBar::tab { background:#121724; color:#8f9bb5;
                padding:10px 18px; margin-right:3px; border:1px solid #252d42;
                border-top-left-radius:9px; border-top-right-radius:9px; }
            QTabBar::tab:hover { color:#d9e3fa; background:#192137; }
            QTabBar::tab:selected { color:#ffffff; background:#526fec;
                border-color:#6d86f2; }
            QTabWidget#tabsReuniones QTabBar::tab { padding:8px 17px;
                border-radius:8px; margin:4px; }
            QTableWidget, QListWidget, QTreeWidget, QTextBrowser {
                background:#0e131e; border:1px solid #252d42;
                border-radius:9px; color:#e7ecf7; outline:0; }
            QTableWidget { gridline-color:#222a3d; }
            QHeaderView::section { background:#171d2b; padding:8px;
                border:none; border-right:1px solid #252d42;
                font-weight:700; color:#8fa9ff; }
            QListWidget::item, QTreeWidget::item { padding:9px 8px;
                margin:2px 4px; border-radius:7px; }
            QListWidget::item:hover, QTreeWidget::item:hover { background:#1b2438; }
            QListWidget::item:selected, QTreeWidget::item:selected {
                background:#334b99; color:#ffffff; }
            QTextBrowser { padding:13px; selection-background-color:#4267dc; }
            #titSemana { font-size:15px; font-weight:700; color:#8fa9ff; }
            QProgressBar { max-width:180px; background:#1a2132; border:none;
                border-radius:4px; height:8px; }
            QProgressBar::chunk { background:#6683f4; border-radius:4px; }
            QSplitter::handle { background:#20283a; width:2px; height:2px; }
            QScrollBar:vertical { background:transparent; width:10px; margin:3px; }
            QScrollBar::handle:vertical { background:#36425f; min-height:28px;
                border-radius:4px; }
            QScrollBar::handle:vertical:hover { background:#526487; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height:0px; }
            QToolTip { background:#20283a; color:white; border:1px solid #526487;
                padding:5px; }
        """)

        for boton in self.findChildren(QPushButton):
            boton.setCursor(Qt.CursorShape.PointingHandCursor)

    def _configurar_movimiento_suave(self):
        """Desplaza el contenido por píxeles para evitar saltos bruscos."""
        vistas = [
            self.tabla, self.lista, self.lista_reuniones, self.arbol_reuniones
        ]
        for vista in vistas:
            vista.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            vista.verticalScrollBar().setSingleStep(14)
        self.tabla.setHorizontalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel)
        for navegador in [
                self.detalle, self.detalle_reunion,
                self.detalle_reunion_materia]:
            navegador.verticalScrollBar().setSingleStep(14)

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

    def _sync_ok(self, entregas, reuniones, cfg):
        self.entregas = entregas
        self.reuniones = reuniones
        self._sincronizado = True
        self._token_guardado = cfg["token"]
        guardar_config(cfg)          # guarda URL, usuario y token (NO la contraseña)
        self.barra_prog.hide()
        self.btn_sync.setEnabled(True)
        self.lbl_estado.setText(
            f"Sincronizado correctamente · {len(entregas)} actividades · "
            f"{len(reuniones)} reuniones de Teams")
        self._asignar_colores()
        self._pintar_semana()
        self._pintar_lista()
        self._pintar_reuniones()

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
        self._actualizar_semana()

    def _ir_hoy(self):
        self.lunes_actual = self._lunes_de(dt.date.today())
        self._actualizar_semana()

    def _actualizar_semana(self):
        self._pintar_semana()
        self._pintar_lista()

    def _asignar_colores(self):
        cursos = sorted(
            {e["curso"] for e in self.entregas} |
            {r["curso"] for r in self.reuniones}
        )
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
                txt = (f"CIERRA {e['fecha'].strftime('%I:%M %p')}\n"
                       f"{e['tipo']}: {e['titulo']}\n{e['curso']}")
                item = QTableWidgetItem(txt)
                item.setToolTip(
                    f"Cierra el {DIAS[e['fecha'].weekday()]} "
                    f"{e['fecha'].strftime('%d/%m/%Y a las %I:%M %p')}")
                color = QColor(self.colores.get(e["curso"], "#4fc3f7"))
                color.setAlpha(45)
                item.setBackground(QBrush(color))
                item.setForeground(QBrush(QColor("#e8eaf0")))
                if e["fecha"].date() == hoy:
                    f2 = QFont(); f2.setBold(True); item.setFont(f2)
                self.tabla.setItem(fila, d, item)
                self._celdas[(fila, d)] = e

    def _detalle_celda(self, fila, col):
        e = self._celdas.get((fila, col))
        if e:
            self._mostrar_detalle(e)
            self.tabs.setCurrentIndex(1)

    # ---------------- Cierres de la semana ----------------
    def _pintar_lista(self):
        self.lista.clear()
        ahora = dt.datetime.now()
        fin = self.lunes_actual + dt.timedelta(days=7)
        fin_visible = fin - dt.timedelta(days=1)
        numero_semana = self.lunes_actual.isocalendar().week
        self.lbl_semana_lista.setText(
            f"Semana {numero_semana} · {self.lunes_actual.strftime('%d/%m')} — "
            f"{fin_visible.strftime('%d/%m/%Y')}")

        self._orden_lista = [
            e for e in self.entregas
            if self.lunes_actual <= e["fecha"].date() < fin
        ]
        if self._sincronizado:
            enlaces_unicos = len({r["url"].lower() for r in self.reuniones})
            self.lbl_resumen.setText(
                f"{len(self._orden_lista)} cierres en esta semana  ·  "
                f"{enlaces_unicos} salas de Teams")
        for e in self._orden_lista:
            if e["fecha"] < ahora:
                estado = "CERRÓ"
            elif e["fecha"].date() == ahora.date():
                estado = "CIERRA HOY"
            else:
                estado = "CIERRA"
            it = QListWidgetItem(
                f"{estado}: {DIAS[e['fecha'].weekday()].upper()} "
                f"{e['fecha'].strftime('%d/%m/%Y · %I:%M %p')}\n"
                f"{e['tipo']}: {e['titulo']}  —  {e['curso']}")
            it.setForeground(QBrush(QColor(
                self.colores.get(e["curso"], "#e8eaf0"))))
            self.lista.addItem(it)

        if not self._orden_lista:
            item = QListWidgetItem(
                "No hay actividades con cierre durante esta semana.")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.lista.addItem(item)
            self.detalle.setHtml(f"""
                <h2 style='color:#8fa9ff'>Semana sin cierres</h2>
                <p style='color:#aeb9d3'>No hay actividades que cierren entre el
                {self.lunes_actual.strftime('%d/%m/%Y')} y el
                {fin_visible.strftime('%d/%m/%Y')}.</p>
            """)
        else:
            self.lista.setCurrentRow(0)

    def _detalle_lista(self, fila):
        if 0 <= fila < len(getattr(self, "_orden_lista", [])):
            self._mostrar_detalle(self._orden_lista[fila])

    def _mostrar_detalle(self, e):
        color = self.colores.get(e["curso"], "#4fc3f7")
        titulo = html.escape(str(e["titulo"]))
        tipo = html.escape(str(e["tipo"]))
        curso = html.escape(str(e["curso"]))
        descripcion = html.escape(str(e["descripcion"]))
        self.detalle.setHtml(f"""
            <h2 style='color:{color};margin-bottom:2px'>{titulo}</h2>
            <p style='color:#9aa3c0'>{tipo} · {curso}</p>
            <p><b>Fecha y hora de cierre:</b> {DIAS[e['fecha'].weekday()]}
               {e['fecha'].strftime('%d/%m/%Y a las %I:%M %p')}</p>
            <hr style='border-color:#2f3450'>
            <p><b>Descripción resumida:</b><br>{descripcion}</p>
        """)

    # ---------------- Reuniones de Teams ----------------
    @staticmethod
    def _texto_proximidad(fecha):
        if fecha is None:
            return "Enlace permanente"
        segundos = (fecha - dt.datetime.now()).total_seconds()
        if segundos < 0:
            return "Ya inició o acaba de iniciar"
        if segundos < 3600:
            minutos = max(1, int(segundos // 60))
            return f"En {minutos} min"
        if segundos < 86400:
            horas = int(segundos // 3600)
            minutos = int((segundos % 3600) // 60)
            return f"En {horas} h {minutos} min"
        dias = int(segundos // 86400)
        return f"En {dias} día" if dias == 1 else f"En {dias} días"

    def _reuniones_visibles(self):
        # Conserva reuniones recién iniciadas y todos los enlaces permanentes.
        limite = dt.datetime.now() - dt.timedelta(hours=4)
        return [r for r in self.reuniones
                if r["fecha"] is None or r["fecha"] >= limite]

    def _pintar_reuniones(self):
        self.lista_reuniones.clear()
        self.arbol_reuniones.clear()
        self.btn_abrir_general.setProperty("url_reunion", "")
        self.btn_abrir_materia.setProperty("url_reunion", "")
        self.btn_abrir_general.hide()
        self.btn_abrir_materia.hide()
        self._reuniones_mostradas = self._reuniones_visibles()

        for indice, reunion in enumerate(self._reuniones_mostradas):
            if reunion["fecha"]:
                fecha = (f"{DIAS[reunion['fecha'].weekday()]} "
                         f"{reunion['fecha'].strftime('%d/%m · %I:%M %p')}")
            else:
                fecha = "Disponible siempre"
            item = QListWidgetItem(
                f"{fecha}  ·  {self._texto_proximidad(reunion['fecha'])}\n"
                f"{reunion['titulo']}  —  {reunion['curso']}")
            item.setData(Qt.ItemDataRole.UserRole, indice)
            item.setForeground(QBrush(QColor(
                self.colores.get(reunion["curso"], "#c8d4f0"))))
            self.lista_reuniones.addItem(item)

        agrupadas = {}
        for indice, reunion in enumerate(self._reuniones_mostradas):
            agrupadas.setdefault(reunion["curso"], []).append((indice, reunion))

        for curso in sorted(agrupadas, key=str.lower):
            reuniones_curso = agrupadas[curso]
            grupo = QTreeWidgetItem([
                f"{curso}  ({len(reuniones_curso)})", ""
            ])
            grupo.setData(0, Qt.ItemDataRole.UserRole, -1)
            grupo.setForeground(0, QBrush(QColor(
                self.colores.get(curso, "#8fa9ff"))))
            fuente = grupo.font(0); fuente.setBold(True); grupo.setFont(0, fuente)
            self.arbol_reuniones.addTopLevelItem(grupo)
            for indice, reunion in reuniones_curso:
                fecha = (reunion["fecha"].strftime("%d/%m · %I:%M %p")
                         if reunion["fecha"] else "Permanente")
                hijo = QTreeWidgetItem([reunion["titulo"], fecha])
                hijo.setData(0, Qt.ItemDataRole.UserRole, indice)
                hijo.setToolTip(0, "Doble clic para abrir en Microsoft Teams")
                grupo.addChild(hijo)
            grupo.setExpanded(True)

        if not self._reuniones_mostradas:
            vacio = QListWidgetItem(
                "No se encontraron enlaces de Teams. Sincroniza para volver a buscar.")
            vacio.setFlags(Qt.ItemFlag.NoItemFlags)
            self.lista_reuniones.addItem(vacio)
            grupo = QTreeWidgetItem(["Sin reuniones encontradas", ""])
            grupo.setFlags(Qt.ItemFlag.NoItemFlags)
            self.arbol_reuniones.addTopLevelItem(grupo)
            mensaje = """
                <h2 style='color:#8fa9ff'>Aún no hay enlaces de Teams</h2>
                <p style='color:#aeb9d3'>Al sincronizar se revisan el calendario,
                los recursos, las páginas, las etiquetas y las secciones de cada
                materia. Solo se muestran enlaces directos y seguros de Microsoft
                Teams.</p>
            """
            self.detalle_reunion.setHtml(mensaje)
            self.detalle_reunion_materia.setHtml(mensaje)
            self.btn_abrir_general.hide()
            self.btn_abrir_materia.hide()
            return

        self.lista_reuniones.setCurrentRow(0)
        primer_grupo = self.arbol_reuniones.topLevelItem(0)
        if primer_grupo and primer_grupo.childCount():
            self.arbol_reuniones.setCurrentItem(primer_grupo.child(0))

    def _detalle_reunion_general(self, fila):
        if not (0 <= fila < self.lista_reuniones.count()):
            return
        indice = self.lista_reuniones.item(fila).data(Qt.ItemDataRole.UserRole)
        if isinstance(indice, int) and 0 <= indice < len(self._reuniones_mostradas):
            self._mostrar_detalle_reunion(
                self._reuniones_mostradas[indice],
                self.detalle_reunion, self.btn_abrir_general)

    def _detalle_reunion_materia(self, actual, _anterior):
        if actual is None:
            return
        indice = actual.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(indice, int) and 0 <= indice < len(self._reuniones_mostradas):
            self._mostrar_detalle_reunion(
                self._reuniones_mostradas[indice],
                self.detalle_reunion_materia, self.btn_abrir_materia)
        elif indice == -1:
            self.btn_abrir_materia.hide()
            self.btn_abrir_materia.setProperty("url_reunion", "")
            curso = html.escape(actual.text(0))
            self.detalle_reunion_materia.setHtml(
                f"<h2 style='color:#8fa9ff'>{curso}</h2>"
                "<p style='color:#aeb9d3'>Selecciona una reunión para ver "
                "sus datos y abrirla.</p>")

    def _mostrar_detalle_reunion(self, reunion, navegador, boton):
        color = self.colores.get(reunion["curso"], "#8fa9ff")
        titulo = html.escape(str(reunion["titulo"]))
        curso = html.escape(str(reunion["curso"]))
        descripcion = html.escape(str(reunion["descripcion"]))
        origen = html.escape(str(reunion["origen"]))
        if reunion["fecha"]:
            cuando = (
                f"{DIAS[reunion['fecha'].weekday()]} "
                f"{reunion['fecha'].strftime('%d/%m/%Y a las %I:%M %p')}"
            )
        else:
            cuando = "Enlace permanente, sin fecha publicada"
        host = html.escape(urlparse(reunion["url"]).hostname or "Microsoft Teams")
        navegador.setHtml(f"""
            <h2 style='color:{color};margin-bottom:3px'>{titulo}</h2>
            <p style='color:#aeb9d3'>{curso}</p>
            <p><b>Cuándo:</b> {cuando}<br>
               <span style='color:#8fa9ff'>{self._texto_proximidad(reunion['fecha'])}</span></p>
            <hr style='border-color:#2f3450'>
            <p><b>Información:</b><br>{descripcion}</p>
            <p style='color:#7f8ba6'>Encontrado en: {origen}<br>Destino: {host}</p>
        """)
        boton.setProperty("url_reunion", reunion["url"])
        boton.setEnabled(True)
        boton.setText("Abrir reunión en Teams  ↗")
        boton.show()

    def _abrir_desde_boton(self, boton):
        enlace = str(boton.property("url_reunion") or "")
        self._abrir_enlace_teams(enlace)

    def _abrir_reunion_general(self, item):
        indice = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(indice, int) and 0 <= indice < len(self._reuniones_mostradas):
            self._abrir_enlace_teams(self._reuniones_mostradas[indice]["url"])

    def _abrir_reunion_materia(self, item, _columna):
        indice = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(indice, int) and 0 <= indice < len(self._reuniones_mostradas):
            self._abrir_enlace_teams(self._reuniones_mostradas[indice]["url"])

    def _abrir_enlace_teams(self, enlace):
        if not enlace or not extraer_links_teams(enlace):
            return
        abierto = QDesktopServices.openUrl(QUrl(enlace))
        if not abierto:
            QMessageBox.warning(
                self, "No se pudo abrir Teams",
                "No encontré una aplicación o navegador para abrir la reunión.")


# ------------------------------------------------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    v = Ventana()
    v.show()
    sys.exit(app.exec())
