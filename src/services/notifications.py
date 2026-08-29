"""Recordatorios de escritorio para entregas próximas."""

from __future__ import annotations

import datetime as dt

from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon

from src.services.storage import StateStore


def due_notifications(entregas, thresholds, sent, now=None):
    """Devuelve avisos pendientes sin repetirlos; es independiente de Qt y testeable."""
    now = now or dt.datetime.now()
    thresholds = sorted({int(value) for value in thresholds if int(value) > 0})
    pending = []
    for entrega in sorted(entregas, key=lambda item: item["fecha"]):
        minutes = (entrega["fecha"] - now).total_seconds() / 60
        if minutes < 0:
            continue
        eligible = [limit for limit in thresholds if minutes <= limit]
        if not eligible:
            continue
        threshold = min(eligible)
        key = f"{entrega.get('id')}:{threshold}"
        if key in sent:
            continue
        pending.append((key, threshold, entrega))
    return pending


class NotificationManager(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.entregas = []
        self.enabled = True
        self.thresholds = [1440, 120, 15]
        self.state = StateStore.load()
        self.tray = QSystemTrayIcon(QApplication.windowIcon(), parent)
        self.tray.setToolTip("Campus Flow")
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        self.timer = QTimer(self)
        self.timer.setInterval(60_000)
        self.timer.timeout.connect(self.check)
        self.timer.start()

    def configure(self, enabled, thresholds):
        self.enabled = bool(enabled)
        self.thresholds = thresholds
        self.check()

    def set_deliveries(self, entregas):
        self.entregas = entregas
        self.check()

    def check(self):
        if not self.enabled:
            return
        sent = self.state.setdefault("notificaciones_enviadas", {})
        pending = due_notifications(self.entregas, self.thresholds, sent)
        for key, threshold, entrega in pending[:3]:
            if threshold >= 1440:
                plazo = "en menos de 24 horas"
            elif threshold >= 60:
                plazo = f"en menos de {threshold // 60} horas"
            else:
                plazo = f"en menos de {threshold} minutos"
            self.tray.showMessage(
                "Campus Flow · Próxima entrega",
                f"{entrega['titulo']} ({entrega['curso']}) vence {plazo}.",
                QSystemTrayIcon.MessageIcon.Information,
                8000,
            )
            sent[key] = dt.datetime.now().isoformat()
        if pending:
            # Evita crecimiento indefinido del historial.
            if len(sent) > 500:
                sent = dict(list(sent.items())[-300:])
                self.state["notificaciones_enviadas"] = sent
            StateStore.save(self.state)

    def announce(self, title, message):
        if self.enabled:
            self.tray.showMessage(
                title, message, QSystemTrayIcon.MessageIcon.Information, 6000
            )
