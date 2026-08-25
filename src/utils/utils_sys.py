import re
import html
import os
import json

from urllib.parse import unquote, urlparse


CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".horario_moodle.json")

DOMINIOS_TEAMS = {
    "teams.microsoft.com", "team.live.com", "msteams.link"
}

# ------------------------------------------------------------------
#  Utilidades
# ------------------------------------------------------------------

class UtilsSys():
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