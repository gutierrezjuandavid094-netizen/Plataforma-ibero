
import datetime as dt
import json

from PyQt6.QtCore import QThread, Qt, pyqtSignal, QUrl
from src.services.moodle_client import MoodleClient
from src.utils.utils_sys import UtilsSys



# ------------------------------------------------------------------
#  Hilo de sincronizacion
# ------------------------------------------------------------------

class SyncWorker(QThread):
    progreso = pyqtSignal(str)
    listo = pyqtSignal(list, list, dict)
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
                for enlace in UtilsSys.extraer_links_teams(descripcion, *campos):
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
                        "descripcion": UtilsSys.limpiar_html(descripcion, 360),
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
                            "descripcion": UtilsSys.limpiar_html(a.get("intro", "")),
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
                        "descripcion": UtilsSys.limpiar_html(e.get("description", "")),
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