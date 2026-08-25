import requests
import datetime as dt

# ------------------------------------------------------------------
#  Cliente Moodle (API oficial de la app movil)
# ------------------------------------------------------------------

class MoodleClient:
    def __init__(self, base_url, token=None):
        self.base = base_url.rstrip("/")
        self.token = token
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": "MoodleMobile 4.3 (HorarioEntregas)"
        })

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