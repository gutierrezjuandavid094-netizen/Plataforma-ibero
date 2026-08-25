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

from src.ui.main_window import Ventana, QApplication

if __name__ == "__main__":
    app = QApplication(sys.argv)
    v = Ventana()
    v.show()
    sys.exit(app.exec())