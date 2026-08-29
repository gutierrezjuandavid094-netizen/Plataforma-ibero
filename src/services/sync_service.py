"""Sincronización en segundo plano entre Moodle y Campus Flow."""

from __future__ import annotations

import datetime as dt
import hashlib
import json

from PyQt6.QtCore import QThread, pyqtSignal

from src.services.moodle_client import MoodleClient
from src.utils.utils_sys import UtilsSys


TIPOS = {
    "assign": "Tarea", "quiz": "Quiz", "forum": "Foro",
    "workshop": "Taller", "lesson": "Lección",
}


def _id_estable(*partes) -> str:
    texto = "|".join(str(parte or "") for parte in partes)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:20]


class SyncWorker(QThread):
    progreso = pyqtSignal(str)
    listo = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, url, usuario, clave, token=None):
        super().__init__()
        self.url, self.usuario, self.clave, self.token = url, usuario, clave, token

    def run(self):
        diagnosticos = []

        def aviso(etapa, error):
            registro = {
                "etapa": etapa,
                "mensaje": str(error).replace("\n", " ").strip()[:300],
            }
            if registro not in diagnosticos:
                diagnosticos.append(registro)

        try:
            cli = MoodleClient(self.url, self.token)
            if not cli.token:
                self.progreso.emit("Iniciando sesión…")
                cli.login(self.usuario, self.clave)

            self.progreso.emit("Obteniendo perfil…")
            try:
                info = cli.info_sitio()
            except Exception:
                if not self.clave:
                    raise RuntimeError(
                        "La sesión guardada venció. Escribe nuevamente tu contraseña."
                    )
                cli.token = None
                cli.login(self.usuario, self.clave)
                info = cli.info_sitio()
            userid = info["userid"]

            self.progreso.emit("Buscando tus materias…")
            cursos_moodle = cli.mis_cursos(userid)
            mapa_cursos = {
                curso["id"]: curso.get("fullname", curso.get("shortname", "?"))
                for curso in cursos_moodle
            }
            ids_cursos = list(mapa_cursos)
            ahora_ts = int(dt.datetime.now().timestamp())
            cursos = [{
                "id": curso["id"],
                "nombre": mapa_cursos[curso["id"]],
                "inicio": curso.get("startdate") or None,
                "fin": curso.get("enddate") or None,
                "progreso": curso.get("progress"),
                "finalizado": bool(curso.get("enddate") and curso["enddate"] < ahora_ts),
            } for curso in cursos_moodle]

            entregas, reuniones, calificaciones = [], [], []
            vistos, reuniones_vistas = set(), set()

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
                    clave = (curso, enlace.lower(), marca_fecha)
                    if clave in reuniones_vistas:
                        continue
                    reuniones_vistas.add(clave)
                    reuniones.append({
                        "id": _id_estable("teams", curso, enlace, marca_fecha),
                        "curso": curso or "General",
                        "titulo": titulo or "Reunión de Teams",
                        "fecha": fecha,
                        "url": enlace,
                        "descripcion": UtilsSys.limpiar_html(descripcion, 360),
                        "origen": origen,
                    })

            self.progreso.emit(f"Revisando tareas en {len(cursos)} materias…")
            if cursos:
                try:
                    data = cli.tareas_de_cursos(ids_cursos)
                    for curso in data.get("courses", []):
                        nombre = mapa_cursos.get(curso["id"], curso.get("fullname", "?"))
                        for tarea in curso.get("assignments", []):
                            due = tarea.get("duedate", 0)
                            if not due:
                                continue
                            vistos.add(("assign", tarea["id"]))
                            entregas.append({
                                "id": f"assign:{tarea['id']}",
                                "curso": nombre,
                                "titulo": tarea.get("name", "Tarea"),
                                "tipo": "Tarea",
                                "fecha": dt.datetime.fromtimestamp(due),
                                "descripcion": UtilsSys.limpiar_html(tarea.get("intro", "")),
                                "url": "",
                            })
                except Exception as exc:
                    aviso("Tareas", exc)

            self.progreso.emit("Revisando calendario y reuniones próximas…")
            try:
                for evento in cli.eventos_calendario().get("events", []):
                    modulo = evento.get("modulename", "") or "evento"
                    instancia = evento.get("instance", 0)
                    marca = evento.get("timesort") or evento.get("timestart", 0)
                    if not marca:
                        continue
                    fecha = dt.datetime.fromtimestamp(marca)
                    nombre_curso = curso_de(evento)
                    accion = evento.get("action") or {}
                    agregar_reuniones(
                        nombre_curso, evento.get("name"), fecha,
                        evento.get("description", ""), "Calendario",
                        evento.get("url", ""), accion.get("url", ""),
                        json.dumps(evento, ensure_ascii=False),
                    )
                    if ("assign", instancia) in vistos and modulo == "assign":
                        continue
                    entregas.append({
                        "id": f"event:{evento.get('id') or _id_estable(nombre_curso, evento.get('name'), marca)}",
                        "curso": nombre_curso,
                        "titulo": evento.get("name", "Actividad"),
                        "tipo": TIPOS.get(modulo, modulo.capitalize()),
                        "fecha": fecha,
                        "descripcion": UtilsSys.limpiar_html(evento.get("description", "")),
                        "url": accion.get("url") or evento.get("url", ""),
                    })
            except Exception as exc:
                aviso("Calendario de actividades", exc)

            try:
                completos = cli.eventos_calendario_completos(ids_cursos)
                for evento in completos.get("events", []):
                    marca = evento.get("timestart") or evento.get("timesort", 0)
                    fecha = dt.datetime.fromtimestamp(marca) if marca else None
                    agregar_reuniones(
                        curso_de(evento), evento.get("name"), fecha,
                        evento.get("description", ""), "Calendario",
                        evento.get("url", ""), evento.get("eventtype", ""),
                        json.dumps(evento, ensure_ascii=False),
                    )
            except Exception as exc:
                aviso("Calendario general", exc)

            self.progreso.emit("Buscando enlaces de Microsoft Teams por materia…")
            fuentes = [
                (cli.recursos_url, "urls", "Recursos del curso"),
                (cli.paginas, "pages", "Páginas del curso"),
                (cli.etiquetas, "labels", "Etiquetas del curso"),
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
                            json.dumps(recurso, ensure_ascii=False),
                        )
                except Exception as exc:
                    aviso(origen, exc)

            errores_contenido = 0
            for indice, cid in enumerate(ids_cursos, start=1):
                if indice == 1 or indice % 5 == 0:
                    self.progreso.emit(
                        f"Revisando recursos de Teams ({indice}/{len(ids_cursos)})…"
                    )
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
                                json.dumps(modulo, ensure_ascii=False),
                            )
                except Exception:
                    errores_contenido += 1
            if errores_contenido:
                aviso("Contenido de cursos", f"Fallaron {errores_contenido} de {len(ids_cursos)} cursos.")

            for curso in cursos_moodle:
                agregar_reuniones(
                    mapa_cursos.get(curso["id"], "General"),
                    "Sala principal de Teams", None, curso.get("summary", ""),
                    "Resumen de la materia", curso.get("viewurl", ""),
                )

            self.progreso.emit("Consultando calificaciones y progreso…")
            soporta_notas = soporta_progreso = True
            for curso in cursos:
                cid = curso["id"]
                if soporta_notas:
                    try:
                        reporte = cli.calificaciones_curso(cid, userid)
                        usuarios = reporte.get("usergrades", [])
                        items = usuarios[0].get("gradeitems", []) if usuarios else []
                        for item in items:
                            if item.get("itemtype") == "course" or item.get("graderaw") is not None:
                                calificaciones.append({
                                    "id": _id_estable("grade", cid, item.get("id")),
                                    "curso": curso["nombre"],
                                    "actividad": item.get("itemname") or "Calificación final",
                                    "nota": item.get("gradeformatted", "—"),
                                    "maxima": item.get("grademax"),
                                    "porcentaje": item.get("percentageformatted", ""),
                                })
                    except Exception as exc:
                        soporta_notas = False
                        aviso("Calificaciones", exc)
                if soporta_progreso:
                    try:
                        progreso = cli.progreso_curso(cid, userid).get("completionstatus", {})
                        completados = progreso.get("completions", [])
                        if completados:
                            hechos = sum(1 for item in completados if item.get("state") in {1, 2, 3})
                            curso["progreso"] = round(hechos * 100 / len(completados))
                        curso["completado"] = progreso.get("completed", False)
                    except Exception as exc:
                        soporta_progreso = False
                        aviso("Progreso de cursos", exc)

            entregas.sort(key=lambda item: item["fecha"])
            limite = dt.datetime.now() - dt.timedelta(hours=4)
            con_fecha = {
                (reunion["curso"], reunion["url"].lower())
                for reunion in reuniones
                if reunion["fecha"] and reunion["fecha"] >= limite
            }
            reuniones = [
                reunion for reunion in reuniones
                if reunion["fecha"] or (reunion["curso"], reunion["url"].lower()) not in con_fecha
            ]
            reuniones.sort(key=lambda item: (
                item["fecha"] is None, item["fecha"] or dt.datetime.max,
                item["curso"].lower(), item["titulo"].lower(),
            ))

            self.listo.emit({
                "entregas": entregas,
                "reuniones": reuniones,
                "calificaciones": calificaciones,
                "cursos": cursos,
                "diagnosticos": diagnosticos,
                "perfil": {
                    "nombre": info.get("fullname") or info.get("username") or self.usuario,
                    "userid": userid,
                },
                "cuenta": {"url": self.url, "usuario": self.usuario},
                "token": cli.token,
            })
        except Exception as exc:
            self.error.emit(str(exc))
