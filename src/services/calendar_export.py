"""Exportación e integración de actividades con calendarios externos."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from urllib.parse import urlencode


def _ics_escape(value) -> str:
    return (str(value or "").replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\n", "\\n"))


def _utc_stamp(value: dt.datetime) -> str:
    if value.tzinfo is None:
        value = value.astimezone()
    return value.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_ics(entregas: list[dict]) -> str:
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Campus Flow//ES",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        "X-WR-CALNAME:Campus Flow",
    ]
    generado = _utc_stamp(dt.datetime.now().astimezone())
    for entrega in entregas:
        fecha = entrega.get("fecha")
        if not isinstance(fecha, dt.datetime):
            continue
        inicio = fecha - dt.timedelta(minutes=30)
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{_ics_escape(entrega.get('id'))}@campus-flow",
            f"DTSTAMP:{generado}",
            f"DTSTART:{_utc_stamp(inicio)}",
            f"DTEND:{_utc_stamp(fecha)}",
            f"SUMMARY:{_ics_escape(entrega.get('tipo'))}: {_ics_escape(entrega.get('titulo'))}",
            f"DESCRIPTION:{_ics_escape(entrega.get('descripcion'))}",
            f"LOCATION:{_ics_escape(entrega.get('curso'))}",
        ])
        if entrega.get("url"):
            lines.append(f"URL:{_ics_escape(entrega['url'])}")
        lines.extend([
            "BEGIN:VALARM", "TRIGGER:-PT2H", "ACTION:DISPLAY",
            f"DESCRIPTION:Próxima entrega: {_ics_escape(entrega.get('titulo'))}",
            "END:VALARM", "END:VEVENT",
        ])
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def save_ics(path: str | Path, entregas: list[dict]) -> None:
    Path(path).write_text(build_ics(entregas), encoding="utf-8", newline="")


def google_calendar_url(entrega: dict) -> str:
    fecha = entrega["fecha"]
    inicio = fecha - dt.timedelta(minutes=30)
    params = {
        "action": "TEMPLATE",
        "text": f"{entrega.get('tipo', 'Actividad')}: {entrega.get('titulo', '')}",
        "dates": f"{_utc_stamp(inicio)}/{_utc_stamp(fecha)}",
        "details": entrega.get("descripcion", ""),
        "location": entrega.get("curso", ""),
    }
    return "https://calendar.google.com/calendar/render?" + urlencode(params)


def outlook_calendar_url(entrega: dict) -> str:
    fecha = entrega["fecha"]
    inicio = fecha - dt.timedelta(minutes=30)
    if inicio.tzinfo is None:
        inicio = inicio.astimezone()
        fecha = fecha.astimezone()
    params = {
        "path": "/calendar/action/compose",
        "rru": "addevent",
        "subject": f"{entrega.get('tipo', 'Actividad')}: {entrega.get('titulo', '')}",
        "startdt": inicio.isoformat(),
        "enddt": fecha.isoformat(),
        "body": entrega.get("descripcion", ""),
        "location": entrega.get("curso", ""),
    }
    return "https://outlook.live.com/calendar/0/deeplink/compose?" + urlencode(params)
