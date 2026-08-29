import datetime as dt
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import src.services.storage as storage


class StorageTests(unittest.TestCase):
    def assert_private_mode(self, path):
        if os.name != "nt":
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.patches = [
            patch.object(storage, "CONFIG_FILE", root / "config.json"),
            patch.object(storage, "TOKEN_FILE", root / "tokens.json"),
            patch.object(storage, "CACHE_FILE", root / "cache.json"),
            patch.object(storage, "STATE_FILE", root / "state.json"),
            patch.object(storage, "LOG_FILE", root / "campus-flow.log"),
            patch.object(storage, "LEGACY_CONFIG_FILE", root / "legacy.json"),
            patch.object(storage.SecureTokenStore, "_keyring", return_value=None),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def test_config_no_guarda_token(self):
        storage.ConfigStore.save({"url": "https://campus.test", "usuario": "juan", "token": "secret"})
        self.assertNotIn("secret", storage.CONFIG_FILE.read_text())
        self.assert_private_mode(storage.CONFIG_FILE)

    def test_token_fallback_privado(self):
        backend = storage.SecureTokenStore.set("https://campus.test", "juan", "secret")
        token, _ = storage.SecureTokenStore.get("https://campus.test", "juan")
        self.assertEqual(backend, "archivo privado (600)")
        self.assertEqual(token, "secret")
        self.assert_private_mode(storage.TOKEN_FILE)

    def test_cache_recupera_fechas(self):
        expected = dt.datetime(2026, 8, 29, 12, 0)
        storage.CacheStore.save({"entregas": [{"fecha": expected}]})
        result, saved_at = storage.CacheStore.load()
        self.assertEqual(result["entregas"][0]["fecha"], expected)
        self.assertIsNotNone(saved_at)

    def test_diagnostico_es_privado(self):
        storage.DiagnosticStore.append([{"etapa": "Calendario", "mensaje": "No disponible"}])
        self.assertIn("Calendario", storage.LOG_FILE.read_text())
        self.assert_private_mode(storage.LOG_FILE)


if __name__ == "__main__":
    unittest.main()
