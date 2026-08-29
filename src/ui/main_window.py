"""Interfaz principal de Campus Flow."""

from __future__ import annotations

import datetime as dt
import hashlib
import html
from urllib.parse import urlparse

from PyQt6.QtCore import QDate, Qt, QUrl
from PyQt6.QtGui import QBrush, QColor, QDesktopServices, QFont, QTextCharFormat
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QCalendarWidget, QCheckBox, QComboBox,
    QFileDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QProgressBar, QPushButton, QSplitter, QTabWidget, QTableWidget,
    QTableWidgetItem, QTextBrowser, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
    QWidget,
)

from src.services.calendar_export import (
    google_calendar_url, outlook_calendar_url, save_ics,
)
from src.services.notifications import NotificationManager
from src.services.storage import (
    CacheStore, ConfigStore, DiagnosticStore, LOG_FILE, SecureTokenStore, StateStore,
)
from src.services.sync_service import SyncWorker
from src.utils.utils_sys import UtilsSys
from src.version import __version__


DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
PALETA = [
    "#4fc3f7", "#81c784", "#ffb74d", "#e57373", "#ba68c8",
    "#4db6ac", "#f06292", "#a1887f", "#90a4ae", "#dce775",
]


class Ventana(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Campus Flow {__version__} — Moodle y Microsoft Teams")
        self.resize(1320, 850)
        self.setMinimumSize(1020, 680)
        self.entregas, self.reuniones = [], []
        self.calificaciones, self.cursos, self.diagnosticos = [], [], []
        self.colores = {}
        self.perfil = {}
        self._sincronizado = False
        self._token_guardado = None
        self._token_backend = "sin sesión"
        self._cache_date = None
        self._selected_delivery = None
        self.lunes_actual = self._lunes_de(dt.date.today())
        self.cfg = ConfigStore.load()
        self.state = StateStore.load()
        self._ui()
        self._estilos()
        self.notifier = NotificationManager(self)
        self._cargar_cache()
        self._cargar_guardado()

    # ---------------- Construcción de interfaz ----------------
    def _ui(self):
        raiz = QWidget(objectName="raiz")
        self.setCentralWidget(raiz)
        lay = QVBoxLayout(raiz)
        lay.setContentsMargins(18, 16, 18, 18)
        lay.setSpacing(10)

        cabecera = QFrame(objectName="cabecera")
        ch = QHBoxLayout(cabecera)
        textos = QVBoxLayout()
        titulo = QLabel("Campus Flow", objectName="tituloApp")
        self.lbl_bienvenida = QLabel(
            "Tu centro académico: tareas, clases y progreso", objectName="subtituloApp"
        )
        textos.addWidget(titulo)
        textos.addWidget(self.lbl_bienvenida)
        self.lbl_resumen = QLabel("Preparando tus datos…", objectName="resumen")
        self.lbl_resumen.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        ch.addLayout(textos)
        ch.addStretch()
        ch.addWidget(self.lbl_resumen)
        lay.addWidget(cabecera)

        barra = QFrame(objectName="barra")
        bl = QHBoxLayout(barra)
        self.in_url = QLineEdit()
        self.in_url.setPlaceholderText("URL del campus (https://campus.ibero.edu.co)")
        self.in_user = QLineEdit()
        self.in_user.setPlaceholderText("Usuario")
        self.in_pass = QLineEdit()
        self.in_pass.setPlaceholderText("Contraseña")
        self.in_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.in_pass.returnPressed.connect(self.sincronizar)
        self.btn_sync = QPushButton("↻  Sincronizar", objectName="principal")
        self.btn_sync.clicked.connect(self.sincronizar)
        self.btn_logout = QPushButton("Cerrar sesión")
        self.btn_logout.clicked.connect(self.cerrar_sesion)
        bl.addWidget(self.in_url, 3)
        bl.addWidget(self.in_user, 1)
        bl.addWidget(self.in_pass, 1)
        bl.addWidget(self.btn_sync)
        bl.addWidget(self.btn_logout)
        lay.addWidget(barra)

        estado = QHBoxLayout()
        self.lbl_estado = QLabel("Listo para conectar con Moodle.", objectName="estado")
        self.barra_prog = QProgressBar()
        self.barra_prog.setRange(0, 0)
        self.barra_prog.hide()
        estado.addWidget(self.lbl_estado)
        estado.addStretch()
        estado.addWidget(self.barra_prog)
        lay.addLayout(estado)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        lay.addWidget(self.tabs, 1)
        self._ui_hoy()
        self._ui_semana()
        self._ui_actividades()
        self._ui_mes()
        self._ui_reuniones()
        self._ui_academico()
        self._ui_preferencias()

    def _ui_hoy(self):
        widget = QWidget()
        root = QVBoxLayout(widget)
        root.setContentsMargins(14, 14, 14, 14)
        self.lbl_hoy_titulo = QLabel("Bienvenido a Campus Flow", objectName="tituloVista")
        self.lbl_hoy_sub = QLabel(
            "Sincroniza Moodle para construir tu agenda.", objectName="ayuda"
        )
        root.addWidget(self.lbl_hoy_titulo)
        root.addWidget(self.lbl_hoy_sub)
        cards = QHBoxLayout()
        card_pairs = [
            self._card("Vencen hoy"), self._card("Próxima entrega"),
            self._card("Pendientes vencidas"), self._card("Próxima reunión"),
        ]
        (self.card_hoy, self.card_proxima,
         self.card_vencidas, self.card_reunion) = [value for _, value in card_pairs]
        for frame, _ in card_pairs:
            cards.addWidget(frame)
        root.addLayout(cards)
        root.addWidget(QLabel("Próximas actividades", objectName="tituloPanel"))
        self.lista_hoy = QListWidget()
        self.lista_hoy.itemDoubleClicked.connect(self._abrir_actividad_hoy)
        root.addWidget(self.lista_hoy, 1)
        self.tabs.addTab(widget, "  Hoy  ")

    @staticmethod
    def _card(title):
        frame = QFrame(objectName="card")
        layout = QVBoxLayout(frame)
        label_title = QLabel(title, objectName="cardTitle")
        value = QLabel("—", objectName="cardValue")
        value.setWordWrap(True)
        layout.addWidget(label_title)
        layout.addWidget(value, 1)
        return frame, value

    def _ui_semana(self):
        widget = QWidget()
        root = QVBoxLayout(widget)
        nav = QHBoxLayout()
        prev = QPushButton("‹ Semana anterior")
        today = QPushButton("Hoy", objectName="secundario")
        nxt = QPushButton("Semana siguiente ›")
        prev.clicked.connect(lambda: self._mover_semana(-1))
        today.clicked.connect(self._ir_hoy)
        nxt.clicked.connect(lambda: self._mover_semana(1))
        self.lbl_semana = QLabel(objectName="titSemana")
        for item in [prev, today, nxt]:
            nav.addWidget(item)
        nav.addStretch()
        nav.addWidget(self.lbl_semana)
        root.addLayout(nav)
        self.tabla = QTableWidget(0, 7)
        self.tabla.setHorizontalHeaderLabels(DIAS)
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabla.verticalHeader().hide()
        self.tabla.verticalHeader().setDefaultSectionSize(82)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.setWordWrap(True)
        self.tabla.cellClicked.connect(self._detalle_celda)
        root.addWidget(self.tabla)
        self.tabs.addTab(widget, "  Semana  ")

    def _ui_actividades(self):
        widget = QWidget()
        root = QVBoxLayout(widget)
        filters = QHBoxLayout()
        self.in_buscar = QLineEdit()
        self.in_buscar.setPlaceholderText("Buscar actividad o materia…")
        self.combo_curso = QComboBox()
        self.combo_tipo = QComboBox()
        self.combo_estado = QComboBox()
        self.combo_estado.addItems(["Todas", "Pendientes", "Completadas", "Vencidas"])
        self.chk_ocultar = QCheckBox("Ocultar completadas")
        self.chk_ocultar.setChecked(bool(self.cfg.get("ocultar_completadas")))
        for control in [self.in_buscar, self.combo_curso, self.combo_tipo, self.combo_estado]:
            if isinstance(control, QLineEdit):
                control.textChanged.connect(self._pintar_lista)
            else:
                control.currentTextChanged.connect(self._pintar_lista)
        self.chk_ocultar.toggled.connect(self._pintar_lista)
        filters.addWidget(self.in_buscar, 2)
        filters.addWidget(self.combo_curso)
        filters.addWidget(self.combo_tipo)
        filters.addWidget(self.combo_estado)
        filters.addWidget(self.chk_ocultar)
        root.addLayout(filters)

        nav = QHBoxLayout()
        prev = QPushButton("‹ Semana anterior")
        today = QPushButton("Semana actual", objectName="secundario")
        nxt = QPushButton("Semana siguiente ›")
        prev.clicked.connect(lambda: self._mover_semana(-1))
        today.clicked.connect(self._ir_hoy)
        nxt.clicked.connect(lambda: self._mover_semana(1))
        self.lbl_semana_lista = QLabel(objectName="titSemana")
        nav.addWidget(prev); nav.addWidget(today); nav.addWidget(nxt); nav.addStretch()
        nav.addWidget(self.lbl_semana_lista)
        root.addLayout(nav)

        split = QSplitter()
        self.lista = QListWidget()
        self.lista.currentRowChanged.connect(self._detalle_lista)
        self.detalle = QTextBrowser()
        split.addWidget(self.lista); split.addWidget(self.detalle)
        split.setSizes([500, 650])
        root.addWidget(split, 1)
        actions = QHBoxLayout()
        self.btn_completar = QPushButton("Marcar como completada")
        self.btn_google = QPushButton("Google Calendar ↗")
        self.btn_outlook = QPushButton("Outlook ↗")
        self.btn_exportar = QPushButton("Exportar calendario .ics")
        self.btn_completar.clicked.connect(self._toggle_completada)
        self.btn_google.clicked.connect(lambda: self._abrir_calendario("google"))
        self.btn_outlook.clicked.connect(lambda: self._abrir_calendario("outlook"))
        self.btn_exportar.clicked.connect(self._exportar_ics)
        for button in [self.btn_completar, self.btn_google, self.btn_outlook]:
            button.setEnabled(False)
        actions.addWidget(self.btn_completar)
        actions.addStretch()
        actions.addWidget(self.btn_google); actions.addWidget(self.btn_outlook)
        actions.addWidget(self.btn_exportar)
        root.addLayout(actions)
        self.tabs.addTab(widget, "  Actividades  ")

    def _ui_mes(self):
        widget = QWidget()
        root = QHBoxLayout(widget)
        self.calendario = QCalendarWidget()
        self.calendario.setGridVisible(True)
        self.calendario.selectionChanged.connect(self._pintar_dia_mes)
        self.lista_mes = QListWidget()
        self.lista_mes.itemDoubleClicked.connect(self._abrir_actividad_mes)
        root.addWidget(self.calendario, 2)
        panel = QFrame(objectName="panel")
        panel_lay = QVBoxLayout(panel)
        self.lbl_dia_mes = QLabel("Actividades del día", objectName="tituloPanel")
        panel_lay.addWidget(self.lbl_dia_mes)
        panel_lay.addWidget(self.lista_mes, 1)
        root.addWidget(panel, 1)
        self.tabs.addTab(widget, "  Mes  ")

    def _ui_reuniones(self):
        widget = QWidget()
        root = QVBoxLayout(widget)
        root.addWidget(QLabel(
            "Salas de Microsoft Teams encontradas en calendario, recursos y cursos.",
            objectName="ayuda",
        ))
        split = QSplitter()
        self.arbol_reuniones = QTreeWidget()
        self.arbol_reuniones.setHeaderLabels(["Materia / reunión", "Fecha"])
        self.arbol_reuniones.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.arbol_reuniones.currentItemChanged.connect(self._detalle_reunion)
        self.arbol_reuniones.itemDoubleClicked.connect(self._abrir_reunion)
        panel = QWidget()
        panel_lay = QVBoxLayout(panel)
        self.detalle_reunion = QTextBrowser()
        botones = QHBoxLayout()
        self.btn_copiar_teams = QPushButton("Copiar enlace")
        self.btn_abrir_teams = QPushButton("Abrir en Teams ↗", objectName="teams")
        self.btn_copiar_teams.clicked.connect(self._copiar_teams)
        self.btn_abrir_teams.clicked.connect(self._abrir_reunion_seleccionada)
        botones.addWidget(self.btn_copiar_teams); botones.addWidget(self.btn_abrir_teams)
        panel_lay.addWidget(self.detalle_reunion, 1); panel_lay.addLayout(botones)
        split.addWidget(self.arbol_reuniones); split.addWidget(panel)
        split.setSizes([560, 620])
        root.addWidget(split, 1)
        self.tabs.addTab(widget, "  Teams  ")

    def _ui_academico(self):
        widget = QWidget()
        root = QVBoxLayout(widget)
        self.arbol_cursos = QTreeWidget()
        self.arbol_cursos.setHeaderLabels(["Materia", "Progreso", "Estado"])
        self.arbol_cursos.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        root.addWidget(QLabel("Progreso por materia", objectName="tituloPanel"))
        root.addWidget(self.arbol_cursos, 1)
        root.addWidget(QLabel("Calificaciones disponibles", objectName="tituloPanel"))
        self.tabla_notas = QTableWidget(0, 4)
        self.tabla_notas.setHorizontalHeaderLabels(["Materia", "Actividad", "Nota", "Porcentaje"])
        self.tabla_notas.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tabla_notas.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tabla_notas.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        root.addWidget(self.tabla_notas, 2)
        self.tabs.addTab(widget, "  Progreso  ")

    def _ui_preferencias(self):
        widget = QWidget()
        root = QVBoxLayout(widget)
        panel = QFrame(objectName="panel")
        grid = QGridLayout(panel)
        self.chk_notificaciones = QCheckBox("Activar recordatorios de escritorio")
        self.chk_notificaciones.setChecked(bool(self.cfg.get("notificaciones", True)))
        self.in_avisos = QLineEdit(
            ", ".join(str(value) for value in self.cfg.get("avisos_minutos", [1440, 120, 15]))
        )
        self.in_avisos.setPlaceholderText("Minutos antes: 1440, 120, 15")
        self.chk_cursos_finalizados = QCheckBox("Ocultar cursos finalizados")
        self.chk_cursos_finalizados.setChecked(bool(self.cfg.get("ocultar_cursos_finalizados", True)))
        self.btn_guardar_prefs = QPushButton("Guardar preferencias", objectName="principal")
        self.btn_guardar_prefs.clicked.connect(self._guardar_preferencias)
        grid.addWidget(self.chk_notificaciones, 0, 0, 1, 2)
        grid.addWidget(QLabel("Avisar estos minutos antes:"), 1, 0)
        grid.addWidget(self.in_avisos, 1, 1)
        grid.addWidget(self.chk_cursos_finalizados, 2, 0, 1, 2)
        grid.addWidget(self.btn_guardar_prefs, 3, 1)
        root.addWidget(panel)
        session = QFrame(objectName="panel")
        sl = QHBoxLayout(session)
        self.lbl_seguridad = QLabel("Sesión: sin configurar", objectName="ayuda")
        self.btn_olvidar = QPushButton("Olvidar cuenta y datos locales")
        self.btn_olvidar.clicked.connect(self.olvidar_cuenta)
        sl.addWidget(self.lbl_seguridad); sl.addStretch(); sl.addWidget(self.btn_olvidar)
        root.addWidget(session)
        root.addWidget(QLabel("Diagnóstico de sincronización", objectName="tituloPanel"))
        self.txt_diagnostico = QTextBrowser()
        root.addWidget(self.txt_diagnostico, 1)
        self.tabs.addTab(widget, "  Ajustes  ")

    # ---------------- Seguridad, caché y sincronización ----------------
    def _cargar_cache(self):
        result, saved_at = CacheStore.load()
        if result:
            self._cache_date = saved_at
            self._aplicar_resultado(result, desde_cache=True)

    def _cargar_guardado(self):
        self.cfg = ConfigStore.load()
        self.in_url.setText(self.cfg.get("url", ""))
        self.in_user.setText(self.cfg.get("usuario", ""))
        if self.cfg.get("url") and self.cfg.get("usuario"):
            self._token_guardado, self._token_backend = SecureTokenStore.get(
                self.cfg["url"], self.cfg["usuario"]
            )
        self.lbl_seguridad.setText(f"Sesión protegida mediante: {self._token_backend}")
        self.notifier.configure(
            self.cfg.get("notificaciones", True),
            self.cfg.get("avisos_minutos", [1440, 120, 15]),
        )
        if self._token_guardado:
            self.lbl_estado.setText("Sesión segura encontrada. Sincronizando…")
            self.sincronizar(auto=True)
        elif self._cache_date:
            self.lbl_estado.setText(f"Modo sin conexión · datos guardados {self._fecha_cache()}")

    def sincronizar(self, auto=False):
        url = UtilsSys.normalizar_url(self.in_url.text())
        usuario = self.in_user.text().strip()
        clave = self.in_pass.text()
        if not url or not usuario:
            if not auto:
                QMessageBox.warning(self, "Datos incompletos", "Escribe la URL y el usuario del campus.")
            return
        if not UtilsSys.url_es_segura(url):
            QMessageBox.warning(
                self, "Conexión insegura",
                "Campus Flow solo permite Moodle mediante HTTPS para proteger tus credenciales.",
            )
            return
        self.in_url.setText(url)
        token = self._token_guardado if not clave else None
        if not token and not clave:
            if not auto:
                QMessageBox.warning(self, "Falta la contraseña", "Escribe tu contraseña de Moodle.")
            return
        self.btn_sync.setEnabled(False)
        self.barra_prog.show()
        self.worker = SyncWorker(url, usuario, clave, token)
        self.worker.progreso.connect(self.lbl_estado.setText)
        self.worker.listo.connect(self._sync_ok)
        self.worker.error.connect(self._sync_error)
        self.worker.start()

    def _sync_ok(self, result):
        token = result.pop("token", None)
        cuenta = result.get("cuenta", {})
        if token:
            self._token_backend = SecureTokenStore.set(
                cuenta.get("url", ""), cuenta.get("usuario", ""), token
            )
            self._token_guardado = token
        self.cfg.update(cuenta)
        ConfigStore.save(self.cfg)
        fechas_anteriores = {item.get("id"): item.get("fecha") for item in self.entregas}
        CacheStore.save(result)
        self._cache_date = dt.datetime.now().astimezone()
        self._aplicar_resultado(result)
        nuevos = [item for item in self.entregas if item.get("id") not in fechas_anteriores]
        cambios = [
            item for item in self.entregas
            if item.get("id") in fechas_anteriores
            and item.get("fecha") != fechas_anteriores[item.get("id")]
        ]
        if fechas_anteriores and nuevos:
            self.notifier.announce("Campus Flow", f"Se encontraron {len(nuevos)} actividades nuevas.")
        if cambios:
            self.notifier.announce("Campus Flow", f"Cambió la fecha de {len(cambios)} actividades.")
        DiagnosticStore.append(self.diagnosticos)
        self.in_pass.clear()
        self.barra_prog.hide()
        self.btn_sync.setEnabled(True)
        extras = f" · {len(self.diagnosticos)} avisos" if self.diagnosticos else ""
        self.lbl_estado.setText(
            f"Sincronizado · {len(self.entregas)} actividades · {len(self.reuniones)} reuniones{extras}"
        )
        self.lbl_seguridad.setText(f"Sesión protegida mediante: {self._token_backend}")

    def _sync_error(self, message):
        self.barra_prog.hide()
        self.btn_sync.setEnabled(True)
        suffix = " Los datos guardados siguen disponibles." if self.entregas or self.reuniones else ""
        self.lbl_estado.setText("No se pudo sincronizar." + suffix)
        QMessageBox.critical(self, "Error de sincronización", message + suffix)

    def _aplicar_resultado(self, result, desde_cache=False):
        self.entregas = result.get("entregas", [])
        self.reuniones = result.get("reuniones", [])
        self.calificaciones = result.get("calificaciones", [])
        self.cursos = result.get("cursos", [])
        self.diagnosticos = result.get("diagnosticos", [])
        self.perfil = result.get("perfil", {})
        completadas = set(self.state.get("completadas", []))
        for entrega in self.entregas:
            entrega["completada"] = entrega.get("id") in completadas
        self._sincronizado = not desde_cache
        self._asignar_colores()
        self._actualizar_filtros()
        self._actualizar_todo()
        self.notifier.set_deliveries([e for e in self.entregas if not e.get("completada")])

    def cerrar_sesion(self):
        url, usuario = self.in_url.text().strip(), self.in_user.text().strip()
        if url and usuario:
            SecureTokenStore.delete(url, usuario)
        self._token_guardado = None
        self.in_pass.clear()
        self.lbl_seguridad.setText("Sesión cerrada; los datos offline permanecen disponibles.")
        self.lbl_estado.setText("Sesión cerrada.")

    def olvidar_cuenta(self):
        answer = QMessageBox.question(
            self, "Olvidar cuenta",
            "Se eliminarán la sesión y la caché local. El repositorio y Moodle no se modificarán.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.cerrar_sesion()
        CacheStore.clear()
        self.cfg.update({"url": "", "usuario": "", "bienvenida_mostrada": False})
        ConfigStore.save(self.cfg)
        self.in_url.clear(); self.in_user.clear()
        self.entregas, self.reuniones, self.cursos, self.calificaciones = [], [], [], []
        self._actualizar_todo()

    def _fecha_cache(self):
        return self._cache_date.strftime("%d/%m/%Y %I:%M %p") if self._cache_date else ""

    # ---------------- Actualización de vistas ----------------
    def _actualizar_todo(self):
        self._pintar_hoy(); self._pintar_semana(); self._pintar_lista()
        self._pintar_mes(); self._pintar_reuniones(); self._pintar_academico()
        self._pintar_diagnostico()

    def _cursos_finalizados(self):
        return {c["nombre"] for c in self.cursos if c.get("finalizado")}

    def _entregas_visibles(self):
        items = self.entregas
        if self.cfg.get("ocultar_cursos_finalizados", True):
            finalizados = self._cursos_finalizados()
            items = [item for item in items if item.get("curso") not in finalizados]
        return items

    def _asignar_colores(self):
        cursos = sorted({e["curso"] for e in self.entregas} | {r["curso"] for r in self.reuniones})
        self.colores = {
            curso: PALETA[int(hashlib.sha256(curso.encode("utf-8")).hexdigest()[:8], 16) % len(PALETA)]
            for curso in cursos
        }

    def _actualizar_filtros(self):
        curso_actual, tipo_actual = self.combo_curso.currentText(), self.combo_tipo.currentText()
        self.combo_curso.blockSignals(True); self.combo_tipo.blockSignals(True)
        self.combo_curso.clear(); self.combo_tipo.clear()
        self.combo_curso.addItems(["Todas las materias"] + sorted({e["curso"] for e in self._entregas_visibles()}))
        self.combo_tipo.addItems(["Todos los tipos"] + sorted({e["tipo"] for e in self._entregas_visibles()}))
        if curso_actual in [self.combo_curso.itemText(i) for i in range(self.combo_curso.count())]:
            self.combo_curso.setCurrentText(curso_actual)
        if tipo_actual in [self.combo_tipo.itemText(i) for i in range(self.combo_tipo.count())]:
            self.combo_tipo.setCurrentText(tipo_actual)
        self.combo_curso.blockSignals(False); self.combo_tipo.blockSignals(False)

    def _pintar_hoy(self):
        now, today = dt.datetime.now(), dt.date.today()
        visibles = self._entregas_visibles()
        pendientes = [e for e in visibles if not e.get("completada")]
        futuras = sorted([e for e in pendientes if e["fecha"] >= now], key=lambda e: e["fecha"])
        vencidas = [e for e in pendientes if e["fecha"] < now]
        hoy = [e for e in pendientes if e["fecha"].date() == today and e["fecha"] >= now]
        nombre = self.perfil.get("nombre")
        self.lbl_hoy_titulo.setText(f"Hola, {nombre}" if nombre else "Bienvenido a Campus Flow")
        self.lbl_hoy_sub.setText(
            f"Últimos datos guardados: {self._fecha_cache()}" if self._cache_date
            else "Sincroniza Moodle para construir tu agenda."
        )
        self.card_hoy.setText(str(len(hoy)))
        self.card_vencidas.setText(str(len(vencidas)))
        self.card_proxima.setText(
            f"{futuras[0]['titulo']}\n{self._texto_proximidad(futuras[0]['fecha'])}" if futuras else "Sin pendientes"
        )
        reuniones = [r for r in self.reuniones if r.get("fecha") and r["fecha"] >= now]
        self.card_reunion.setText(
            f"{reuniones[0]['titulo']}\n{self._texto_proximidad(reuniones[0]['fecha'])}" if reuniones else "Sin reuniones"
        )
        self.lista_hoy.clear()
        for entrega in futuras[:12]:
            item = QListWidgetItem(
                f"{entrega['fecha'].strftime('%a %d/%m · %I:%M %p')}  ·  {entrega['tipo']}\n"
                f"{entrega['titulo']} — {entrega['curso']}"
            )
            item.setData(Qt.ItemDataRole.UserRole, entrega.get("id"))
            item.setForeground(QBrush(QColor(self.colores.get(entrega["curso"], "#e8eaf0"))))
            self.lista_hoy.addItem(item)
        if not futuras:
            self.lista_hoy.addItem(QListWidgetItem("No tienes actividades pendientes próximas."))
        self.lbl_resumen.setText(f"{len(pendientes)} pendientes · {len(self.cursos)} materias")

    @staticmethod
    def _lunes_de(fecha):
        return fecha - dt.timedelta(days=fecha.weekday())

    def _mover_semana(self, delta):
        self.lunes_actual += dt.timedelta(weeks=delta)
        self._pintar_semana(); self._pintar_lista()

    def _ir_hoy(self):
        self.lunes_actual = self._lunes_de(dt.date.today())
        self._pintar_semana(); self._pintar_lista()

    def _entregas_semana(self):
        fin = self.lunes_actual + dt.timedelta(days=7)
        columns = {index: [] for index in range(7)}
        for entrega in self._entregas_visibles():
            fecha = entrega["fecha"].date()
            if self.lunes_actual <= fecha < fin:
                columns[fecha.weekday()].append(entrega)
        return columns

    def _pintar_semana(self):
        fin = self.lunes_actual + dt.timedelta(days=6)
        self.lbl_semana.setText(f"{self.lunes_actual:%d/%m/%Y} — {fin:%d/%m/%Y}")
        columns = self._entregas_semana()
        self.tabla.setRowCount(max([len(value) for value in columns.values()] + [1]))
        self.tabla.clearContents(); self._celdas = {}
        for day in range(7):
            date = self.lunes_actual + dt.timedelta(days=day)
            self.tabla.setHorizontalHeaderItem(day, QTableWidgetItem(f"{DIAS[day]} {date:%d/%m}"))
            for row, entrega in enumerate(columns[day]):
                mark = "✓ " if entrega.get("completada") else ""
                item = QTableWidgetItem(
                    f"{mark}{entrega['fecha']:%I:%M %p}\n{entrega['tipo']}: {entrega['titulo']}\n{entrega['curso']}"
                )
                color = QColor(self.colores.get(entrega["curso"], "#4fc3f7")); color.setAlpha(45)
                item.setBackground(QBrush(color))
                if entrega.get("completada"):
                    item.setForeground(QBrush(QColor("#7b8498")))
                self.tabla.setItem(row, day, item); self._celdas[(row, day)] = entrega

    def _detalle_celda(self, row, column):
        entrega = self._celdas.get((row, column))
        if entrega:
            self.tabs.setCurrentIndex(2)
            self._seleccionar_entrega(entrega)

    def _filtrar_entregas(self):
        query = self.in_buscar.text().strip().lower()
        curso, tipo, estado = self.combo_curso.currentText(), self.combo_tipo.currentText(), self.combo_estado.currentText()
        now = dt.datetime.now()
        result = []
        for entrega in self._entregas_visibles():
            if query and query not in f"{entrega['titulo']} {entrega['curso']} {entrega['tipo']}".lower():
                continue
            if curso and curso != "Todas las materias" and entrega["curso"] != curso:
                continue
            if tipo and tipo != "Todos los tipos" and entrega["tipo"] != tipo:
                continue
            completed = bool(entrega.get("completada"))
            if self.chk_ocultar.isChecked() and completed:
                continue
            if estado == "Pendientes" and completed:
                continue
            if estado == "Completadas" and not completed:
                continue
            if estado == "Vencidas" and (completed or entrega["fecha"] >= now):
                continue
            result.append(entrega)
        return result

    def _pintar_lista(self):
        self.lista.clear(); self._selected_delivery = None
        fin = self.lunes_actual + dt.timedelta(days=7)
        self.lbl_semana_lista.setText(f"Semana {self.lunes_actual.isocalendar().week} · {self.lunes_actual:%d/%m} — {(fin-dt.timedelta(days=1)):%d/%m/%Y}")
        self._orden_lista = [e for e in self._filtrar_entregas() if self.lunes_actual <= e["fecha"].date() < fin]
        now = dt.datetime.now()
        for entrega in self._orden_lista:
            if entrega.get("completada"):
                estado = "✓ COMPLETADA"
            elif entrega["fecha"] < now:
                estado = "VENCIDA"
            elif entrega["fecha"].date() == now.date():
                estado = "HOY"
            else:
                estado = "PENDIENTE"
            item = QListWidgetItem(
                f"{estado} · {entrega['fecha']:%d/%m/%Y · %I:%M %p}\n"
                f"{entrega['tipo']}: {entrega['titulo']} — {entrega['curso']}"
            )
            item.setForeground(QBrush(QColor(self.colores.get(entrega["curso"], "#e8eaf0"))))
            self.lista.addItem(item)
        if self._orden_lista:
            self.lista.setCurrentRow(0)
        else:
            empty = QListWidgetItem("No hay actividades que coincidan en esta semana.")
            empty.setFlags(Qt.ItemFlag.NoItemFlags); self.lista.addItem(empty)
            self.detalle.setHtml("<h2>Sin resultados</h2><p>Cambia la semana o los filtros.</p>")
            for button in [self.btn_completar, self.btn_google, self.btn_outlook]:
                button.setEnabled(False)

    def _detalle_lista(self, row):
        if 0 <= row < len(getattr(self, "_orden_lista", [])):
            self._mostrar_detalle(self._orden_lista[row])

    def _mostrar_detalle(self, entrega):
        self._selected_delivery = entrega
        status = "Completada" if entrega.get("completada") else "Pendiente"
        self.detalle.setHtml(
            f"<h2 style='color:{self.colores.get(entrega['curso'], '#8fa9ff')}'>{html.escape(str(entrega['titulo']))}</h2>"
            f"<p>{html.escape(str(entrega['tipo']))} · {html.escape(str(entrega['curso']))}</p>"
            f"<p><b>Estado:</b> {status}<br><b>Cierre:</b> {DIAS[entrega['fecha'].weekday()]} {entrega['fecha']:%d/%m/%Y a las %I:%M %p}</p>"
            f"<hr><p>{html.escape(str(entrega.get('descripcion', 'Sin descripción.')))}</p>"
        )
        self.btn_completar.setText("Marcar como pendiente" if entrega.get("completada") else "Marcar como completada")
        for button in [self.btn_completar, self.btn_google, self.btn_outlook]:
            button.setEnabled(True)

    def _seleccionar_entrega(self, entrega):
        self.lunes_actual = self._lunes_de(entrega["fecha"].date())
        self._pintar_lista()
        for row, current in enumerate(self._orden_lista):
            if current.get("id") == entrega.get("id"):
                self.lista.setCurrentRow(row); break

    def _toggle_completada(self):
        entrega = self._selected_delivery
        if not entrega:
            return
        completed = set(self.state.get("completadas", []))
        if entrega.get("id") in completed:
            completed.remove(entrega["id"]); entrega["completada"] = False
        else:
            completed.add(entrega["id"]); entrega["completada"] = True
        self.state["completadas"] = sorted(completed); StateStore.save(self.state)
        self._actualizar_todo()

    def _abrir_actividad_hoy(self, item):
        entrega = self._buscar_entrega(item.data(Qt.ItemDataRole.UserRole))
        if entrega:
            self.tabs.setCurrentIndex(2); self._seleccionar_entrega(entrega)

    def _abrir_actividad_mes(self, item):
        entrega = self._buscar_entrega(item.data(Qt.ItemDataRole.UserRole))
        if entrega:
            self.tabs.setCurrentIndex(2); self._seleccionar_entrega(entrega)

    def _buscar_entrega(self, identity):
        return next((e for e in self.entregas if e.get("id") == identity), None)

    def _pintar_mes(self):
        old = getattr(self, "_calendar_dates", set())
        blank = QTextCharFormat()
        for date in old:
            self.calendario.setDateTextFormat(QDate(date.year, date.month, date.day), blank)
        self._calendar_dates = {e["fecha"].date() for e in self._entregas_visibles()}
        marked = QTextCharFormat(); marked.setBackground(QBrush(QColor("#526fec"))); marked.setForeground(QBrush(QColor("white")))
        for date in self._calendar_dates:
            self.calendario.setDateTextFormat(QDate(date.year, date.month, date.day), marked)
        self._pintar_dia_mes()

    def _pintar_dia_mes(self):
        selected = self.calendario.selectedDate().toPyDate()
        self.lbl_dia_mes.setText(f"Actividades · {selected:%d/%m/%Y}")
        self.lista_mes.clear()
        items = [e for e in self._entregas_visibles() if e["fecha"].date() == selected]
        for entrega in items:
            item = QListWidgetItem(f"{entrega['fecha']:%I:%M %p} · {entrega['tipo']}\n{entrega['titulo']} — {entrega['curso']}")
            item.setData(Qt.ItemDataRole.UserRole, entrega.get("id")); self.lista_mes.addItem(item)
        if not items:
            empty = QListWidgetItem("No hay actividades este día."); empty.setFlags(Qt.ItemFlag.NoItemFlags); self.lista_mes.addItem(empty)

    # ---------------- Teams, progreso y preferencias ----------------
    @staticmethod
    def _texto_proximidad(fecha):
        if fecha is None:
            return "Enlace permanente"
        seconds = (fecha - dt.datetime.now()).total_seconds()
        if seconds < 0:
            return "Ya inició"
        if seconds < 3600:
            return f"En {max(1, int(seconds // 60))} min"
        if seconds < 86400:
            return f"En {int(seconds // 3600)} h"
        return f"En {int(seconds // 86400)} días"

    def _pintar_reuniones(self):
        self.arbol_reuniones.clear(); self._selected_meeting = None
        visibles = [r for r in self.reuniones if r["fecha"] is None or r["fecha"] >= dt.datetime.now() - dt.timedelta(hours=4)]
        grouped = {}
        for meeting in visibles:
            grouped.setdefault(meeting["curso"], []).append(meeting)
        for course in sorted(grouped, key=str.lower):
            group = QTreeWidgetItem([f"{course} ({len(grouped[course])})", ""])
            group.setData(0, Qt.ItemDataRole.UserRole, None)
            font = group.font(0); font.setBold(True); group.setFont(0, font)
            self.arbol_reuniones.addTopLevelItem(group)
            for meeting in grouped[course]:
                date = meeting["fecha"].strftime("%d/%m · %I:%M %p") if meeting["fecha"] else "Permanente"
                item = QTreeWidgetItem([meeting["titulo"], date])
                item.setData(0, Qt.ItemDataRole.UserRole, meeting.get("id")); group.addChild(item)
            group.setExpanded(True)
        if not visibles:
            self.detalle_reunion.setHtml("<h2>Sin reuniones</h2><p>No se encontraron enlaces directos de Teams.</p>")
        self.btn_copiar_teams.setEnabled(False); self.btn_abrir_teams.setEnabled(False)

    def _detalle_reunion(self, item, _previous):
        if not item:
            return
        identity = item.data(0, Qt.ItemDataRole.UserRole)
        meeting = next((r for r in self.reuniones if r.get("id") == identity), None)
        if not meeting:
            return
        self._selected_meeting = meeting
        host = html.escape(urlparse(meeting["url"]).hostname or "Microsoft Teams")
        date = meeting["fecha"].strftime("%d/%m/%Y a las %I:%M %p") if meeting["fecha"] else "Enlace permanente"
        self.detalle_reunion.setHtml(
            f"<h2>{html.escape(str(meeting['titulo']))}</h2><p>{html.escape(str(meeting['curso']))}</p>"
            f"<p><b>Cuándo:</b> {date}<br><b>Destino:</b> {host}</p>"
            f"<p>{html.escape(str(meeting.get('descripcion', '')))}</p>"
        )
        self.btn_copiar_teams.setEnabled(True); self.btn_abrir_teams.setEnabled(True)

    def _abrir_reunion(self, item, _column):
        self._detalle_reunion(item, None); self._abrir_reunion_seleccionada()

    def _abrir_reunion_seleccionada(self):
        if self._selected_meeting:
            self._abrir_url(self._selected_meeting["url"])

    def _copiar_teams(self):
        if self._selected_meeting:
            QApplication.clipboard().setText(self._selected_meeting["url"])
            self.lbl_estado.setText("Enlace de Teams copiado al portapapeles.")

    def _pintar_academico(self):
        self.arbol_cursos.clear()
        for course in sorted(self.cursos, key=lambda c: c["nombre"].lower()):
            progress = f"{course['progreso']:.0f}%" if isinstance(course.get("progreso"), (int, float)) else "No disponible"
            status = "Finalizado" if course.get("finalizado") or course.get("completado") else "Activo"
            self.arbol_cursos.addTopLevelItem(QTreeWidgetItem([course["nombre"], progress, status]))
        self.tabla_notas.setRowCount(len(self.calificaciones))
        for row, grade in enumerate(self.calificaciones):
            for column, value in enumerate([grade["curso"], grade["actividad"], grade["nota"], grade["porcentaje"]]):
                self.tabla_notas.setItem(row, column, QTableWidgetItem(str(value or "—")))

    def _pintar_diagnostico(self):
        if not self.diagnosticos:
            self.txt_diagnostico.setHtml("<h3>Todo disponible</h3><p>No se registraron fallos parciales.</p>")
            return
        rows = "".join(
            f"<li><b>{html.escape(item['etapa'])}:</b> {html.escape(item['mensaje'])}</li>"
            for item in self.diagnosticos
        )
        self.txt_diagnostico.setHtml(
            f"<h3>Sincronización parcial</h3><ul>{rows}</ul>"
            f"<p>Registro privado: {html.escape(str(LOG_FILE))}</p>"
        )

    def _guardar_preferencias(self):
        try:
            thresholds = sorted({int(value.strip()) for value in self.in_avisos.text().split(",") if value.strip()}, reverse=True)
            if not thresholds or any(value <= 0 for value in thresholds):
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, "Avisos inválidos", "Escribe minutos positivos separados por comas.")
            return
        self.cfg.update({
            "notificaciones": self.chk_notificaciones.isChecked(),
            "avisos_minutos": thresholds,
            "ocultar_completadas": self.chk_ocultar.isChecked(),
            "ocultar_cursos_finalizados": self.chk_cursos_finalizados.isChecked(),
        })
        ConfigStore.save(self.cfg); self.notifier.configure(self.cfg["notificaciones"], thresholds)
        self._actualizar_filtros(); self._actualizar_todo()
        self.lbl_estado.setText("Preferencias guardadas.")

    # ---------------- Integraciones ----------------
    def _exportar_ics(self):
        path, _ = QFileDialog.getSaveFileName(self, "Exportar calendario", "campus-flow.ics", "Calendario iCalendar (*.ics)")
        if not path:
            return
        if not path.lower().endswith(".ics"):
            path += ".ics"
        try:
            save_ics(path, self._entregas_visibles())
            self.lbl_estado.setText(f"Calendario exportado: {path}")
        except OSError as exc:
            QMessageBox.critical(self, "No se pudo exportar", str(exc))

    def _abrir_calendario(self, provider):
        if not self._selected_delivery:
            return
        url = google_calendar_url(self._selected_delivery) if provider == "google" else outlook_calendar_url(self._selected_delivery)
        self._abrir_url(url)

    @staticmethod
    def _abrir_url(url):
        if url:
            QDesktopServices.openUrl(QUrl(url))

    # ---------------- Estilos ----------------
    def _estilos(self):
        self.setStyleSheet("""
            QMainWindow, QWidget#raiz { background:#0b0e16; color:#edf1fa;
                font-family:'Inter','Segoe UI',sans-serif; font-size:13px; }
            QWidget { color:#edf1fa; }
            #cabecera { background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #202c55, stop:1 #16294b); border:1px solid #314774; border-radius:14px; }
            #tituloApp { font-size:24px; font-weight:800; color:white; }
            #tituloVista { font-size:22px; font-weight:750; color:white; }
            #subtituloApp, #ayuda, #estado { color:#aeb9d3; }
            #resumen { color:#c9d7ff; font-weight:600; padding:7px 11px; background:rgba(255,255,255,18); border-radius:8px; }
            #barra, #panel, #card { background:#131824; border:1px solid #252d42; border-radius:12px; }
            #card { min-height:95px; }
            #cardTitle { color:#9eabc7; font-weight:650; }
            #cardValue { color:white; font-size:17px; font-weight:750; }
            #tituloPanel, #titSemana { font-size:15px; font-weight:700; color:#8fa9ff; }
            QLineEdit, QComboBox { background:#0f1420; border:1px solid #2c354c; border-radius:8px; padding:8px 10px; color:#f2f5fb; }
            QLineEdit:focus, QComboBox:focus { border:1px solid #6c8dff; }
            QPushButton { background:#29344e; border:1px solid #3a4664; border-radius:8px; padding:8px 13px; color:#e9efff; font-weight:650; }
            QPushButton:hover { background:#354360; border-color:#526487; }
            QPushButton#principal { background:#526fec; border-color:#6f88f6; }
            QPushButton#secundario { background:#192136; color:#9fb5ff; }
            QPushButton#teams { background:#5865d8; border-color:#7782ec; }
            QPushButton:disabled { background:#242b3b; color:#68728b; }
            QTabWidget::pane { background:#101521; border:1px solid #252d42; border-radius:10px; }
            QTabBar::tab { background:#121724; color:#8f9bb5; padding:9px 13px; margin-right:2px; border:1px solid #252d42; }
            QTabBar::tab:selected { color:white; background:#526fec; }
            QTableWidget, QListWidget, QTreeWidget, QTextBrowser, QCalendarWidget {
                background:#0e131e; border:1px solid #252d42; border-radius:9px; color:#e7ecf7; outline:0; }
            QHeaderView::section { background:#171d2b; padding:8px; border:none; color:#8fa9ff; font-weight:700; }
            QListWidget::item, QTreeWidget::item { padding:8px; margin:2px 3px; border-radius:6px; }
            QListWidget::item:selected, QTreeWidget::item:selected { background:#334b99; color:white; }
            QProgressBar { max-width:180px; background:#1a2132; border:none; height:8px; }
            QProgressBar::chunk { background:#6683f4; }
        """)
        for button in self.findChildren(QPushButton):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
