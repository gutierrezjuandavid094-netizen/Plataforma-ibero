
import datetime as dt
import html

from src.services.sync_service import SyncWorker
from src.utils.utils_sys import UtilsSys

from urllib.parse import urlparse
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QColor, QFont, QBrush, QDesktopServices
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QTabWidget, QListWidget, QListWidgetItem, QTextBrowser, QSplitter,
    QMessageBox, QHeaderView, QFrame, QProgressBar, QAbstractItemView,
    QTreeWidget, QTreeWidgetItem
)

DIAS = [
    "Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"
]

PALETA = ["#4fc3f7", "#81c784", "#ffb74d", "#e57373", "#ba68c8",
          "#4db6ac", "#f06292", "#a1887f", "#90a4ae", "#dce775"]


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
        cfg = UtilsSys.cargar_config()
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
        url = UtilsSys.normalizar_url(url)
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
        UtilsSys.guardar_config(cfg)          # guarda URL, usuario y token (NO la contraseña)
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
        if not enlace or not UtilsSys.extraer_links_teams(enlace):
            return
        abierto = QDesktopServices.openUrl(QUrl(enlace))
        if not abierto:
            QMessageBox.warning(
                self, "No se pudo abrir Teams",
                "No encontré una aplicación o navegador para abrir la reunión.")