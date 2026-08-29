"""Genera una captura reproducible de la interfaz con datos ficticios."""

import datetime as dt
import os
import sys
import tempfile
from pathlib import Path


def main():
    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))
    temporary = tempfile.TemporaryDirectory()
    root = Path(temporary.name)
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["XDG_CONFIG_HOME"] = str(root / "config")
    os.environ["XDG_DATA_HOME"] = str(root / "data")

    from PyQt6.QtWidgets import QApplication
    import src.services.storage as storage
    from src.ui.main_window import Ventana

    storage.LEGACY_CONFIG_FILE = root / "legacy.json"
    app = QApplication([])
    window = Ventana()
    now = dt.datetime.now().replace(second=0, microsecond=0)
    window._aplicar_resultado({
        "entregas": [
            {"id": "demo:1", "curso": "Programación", "titulo": "Proyecto final",
             "tipo": "Tarea", "fecha": now + dt.timedelta(hours=5),
             "descripcion": "Entrega del proyecto integrador.", "url": ""},
            {"id": "demo:2", "curso": "Matemáticas", "titulo": "Quiz unidad 3",
             "tipo": "Quiz", "fecha": now + dt.timedelta(days=1, hours=2),
             "descripcion": "Evaluación de la tercera unidad.", "url": ""},
            {"id": "demo:3", "curso": "Investigación", "titulo": "Foro semanal",
             "tipo": "Foro", "fecha": now + dt.timedelta(days=3),
             "descripcion": "Participación argumentada en el foro.", "url": ""},
        ],
        "reuniones": [
            {"id": "meet:1", "curso": "Programación", "titulo": "Clase sincrónica",
             "fecha": now + dt.timedelta(hours=1),
             "url": "https://teams.microsoft.com/l/meetup-join/demo",
             "descripcion": "Revisión del proyecto.", "origen": "Calendario"},
        ],
        "calificaciones": [
            {"id": "grade:1", "curso": "Programación", "actividad": "Primer corte",
             "nota": "4.5", "porcentaje": "90%"},
        ],
        "cursos": [
            {"id": 1, "nombre": "Programación", "progreso": 72, "finalizado": False},
            {"id": 2, "nombre": "Matemáticas", "progreso": 58, "finalizado": False},
            {"id": 3, "nombre": "Investigación", "progreso": 43, "finalizado": False},
        ],
        "diagnosticos": [], "perfil": {"nombre": "Juan"},
    }, desde_cache=True)
    window.resize(1320, 850)
    window.show()
    app.processEvents()
    output = project_root / "docs" / "screenshot.png"
    if not window.grab().save(str(output), "PNG"):
        raise RuntimeError("No se pudo guardar la captura")
    window.close()
    temporary.cleanup()
    print(output)


if __name__ == "__main__":
    main()
