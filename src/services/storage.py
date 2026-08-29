"""Persistencia local segura y caché sin conexión para Campus Flow."""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


APP_NAME = "campus-flow"
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_NAME
DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / APP_NAME
CONFIG_FILE = CONFIG_DIR / "config.json"
TOKEN_FILE = CONFIG_DIR / "tokens.json"
CACHE_FILE = DATA_DIR / "cache.json"
STATE_FILE = DATA_DIR / "state.json"
LOG_FILE = DATA_DIR / "campus-flow.log"
LEGACY_CONFIG_FILE = Path.home() / ".horario_moodle.json"
KEYRING_SERVICE = "Campus Flow Moodle"


def _read_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError, TypeError):
        return default


def _write_private_json(path: Path, data: Any) -> None:
    """Escribe JSON de forma atómica y limita su lectura al usuario actual."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    temporary.chmod(0o600)
    os.replace(temporary, path)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _account_key(url: str, usuario: str) -> str:
    host = (urlparse(url).hostname or url).lower()
    return f"{usuario.strip()}@{host}"


class SecureTokenStore:
    """Usa el llavero del sistema y cae a un archivo privado si no está disponible."""

    @staticmethod
    def _keyring():
        try:
            import keyring
            return keyring
        except Exception:
            return None

    @classmethod
    def get(cls, url: str, usuario: str) -> tuple[str | None, str]:
        account = _account_key(url, usuario)
        keyring = cls._keyring()
        if keyring:
            try:
                token = keyring.get_password(KEYRING_SERVICE, account)
                if token:
                    return token, "llavero del sistema"
            except Exception:
                pass
        fallback = _read_json(TOKEN_FILE, {})
        token = fallback.get(account) if isinstance(fallback, dict) else None
        return token, "archivo privado (600)" if token else "sin sesión"

    @classmethod
    def set(cls, url: str, usuario: str, token: str) -> str:
        account = _account_key(url, usuario)
        keyring = cls._keyring()
        if keyring:
            try:
                keyring.set_password(KEYRING_SERVICE, account, token)
                fallback = _read_json(TOKEN_FILE, {})
                if isinstance(fallback, dict) and fallback.pop(account, None):
                    _write_private_json(TOKEN_FILE, fallback)
                return "llavero del sistema"
            except Exception:
                pass
        fallback = _read_json(TOKEN_FILE, {})
        if not isinstance(fallback, dict):
            fallback = {}
        fallback[account] = token
        _write_private_json(TOKEN_FILE, fallback)
        return "archivo privado (600)"

    @classmethod
    def delete(cls, url: str, usuario: str) -> None:
        account = _account_key(url, usuario)
        keyring = cls._keyring()
        if keyring:
            try:
                keyring.delete_password(KEYRING_SERVICE, account)
            except Exception:
                pass
        fallback = _read_json(TOKEN_FILE, {})
        if isinstance(fallback, dict) and account in fallback:
            fallback.pop(account, None)
            _write_private_json(TOKEN_FILE, fallback)


class ConfigStore:
    DEFAULTS = {
        "url": "",
        "usuario": "",
        "notificaciones": True,
        "avisos_minutos": [1440, 120, 15],
        "ocultar_completadas": False,
        "ocultar_cursos_finalizados": True,
        "bienvenida_mostrada": False,
    }

    @classmethod
    def load(cls) -> dict:
        raw = _read_json(CONFIG_FILE, None)
        if not isinstance(raw, dict):
            raw = _read_json(LEGACY_CONFIG_FILE, {})
        if not isinstance(raw, dict):
            raw = {}

        token = raw.pop("token", None)
        cfg = {**cls.DEFAULTS, **raw}
        if token and cfg.get("url") and cfg.get("usuario"):
            SecureTokenStore.set(cfg["url"], cfg["usuario"], token)
        cls.save(cfg)

        # El archivo heredado podía contener el token en texto plano.
        if LEGACY_CONFIG_FILE.exists():
            try:
                _write_private_json(
                    LEGACY_CONFIG_FILE,
                    {"url": cfg.get("url", ""), "usuario": cfg.get("usuario", "")},
                )
            except OSError:
                # Un entorno restringido no debe impedir que la aplicación abra.
                pass
        return cfg

    @classmethod
    def save(cls, cfg: dict) -> None:
        safe = {**cls.DEFAULTS, **cfg}
        safe.pop("token", None)
        _write_private_json(CONFIG_FILE, safe)


def _encode_dates(value: Any) -> Any:
    if isinstance(value, dt.datetime):
        return {"__datetime__": value.isoformat()}
    if isinstance(value, dict):
        return {key: _encode_dates(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_encode_dates(item) for item in value]
    return value


def _decode_dates(value: Any) -> Any:
    if isinstance(value, dict):
        if set(value) == {"__datetime__"}:
            try:
                return dt.datetime.fromisoformat(value["__datetime__"])
            except (TypeError, ValueError):
                return None
        return {key: _decode_dates(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decode_dates(item) for item in value]
    return value


class CacheStore:
    @staticmethod
    def save(result: dict) -> None:
        payload = {
            "saved_at": dt.datetime.now().astimezone().isoformat(),
            "result": _encode_dates(result),
        }
        _write_private_json(CACHE_FILE, payload)

    @staticmethod
    def load() -> tuple[dict | None, dt.datetime | None]:
        payload = _read_json(CACHE_FILE, {})
        if not isinstance(payload, dict) or not isinstance(payload.get("result"), dict):
            return None, None
        try:
            saved_at = dt.datetime.fromisoformat(payload.get("saved_at", ""))
        except (TypeError, ValueError):
            saved_at = None
        return _decode_dates(payload["result"]), saved_at

    @staticmethod
    def clear() -> None:
        try:
            CACHE_FILE.unlink()
        except FileNotFoundError:
            pass


class StateStore:
    DEFAULTS = {"completadas": [], "notificaciones_enviadas": {}}

    @classmethod
    def load(cls) -> dict:
        data = _read_json(STATE_FILE, {})
        return {**cls.DEFAULTS, **(data if isinstance(data, dict) else {})}

    @classmethod
    def save(cls, data: dict) -> None:
        _write_private_json(STATE_FILE, {**cls.DEFAULTS, **data})


class DiagnosticStore:
    @staticmethod
    def append(items: list[dict]) -> None:
        if not items:
            return
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        timestamp = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            for item in items:
                stage = str(item.get("etapa", "Sincronización")).replace("\n", " ")
                message = str(item.get("mensaje", "")).replace("\n", " ")
                handle.write(f"{timestamp} | {stage} | {message}\n")
        try:
            LOG_FILE.chmod(0o600)
        except OSError:
            pass
