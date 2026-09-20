from threading import Lock

from .models import Incident


class IncidentStore:
    def __init__(self) -> None:
        self._incidents: dict[str, Incident] = {}
        self._lock = Lock()

    def upsert(self, incident: Incident) -> Incident:
        with self._lock:
            existing = self._incidents.get(incident.fingerprint)

            if existing:
                existing.status = incident.status
                existing.severity = incident.severity
                existing.summary = incident.summary
                existing.probable_cause = incident.probable_cause
                existing.recommended_actions = incident.recommended_actions
                existing.labels = incident.labels
                existing.annotations = incident.annotations
                existing.updated_at = incident.updated_at
                existing.alert_count += 1
                existing.raw_alerts.extend(incident.raw_alerts)

                self._incidents[incident.fingerprint] = existing
                return existing

            self._incidents[incident.fingerprint] = incident
            return incident

    def list_all(self) -> list[Incident]:
        with self._lock:
            return list(self._incidents.values())

    def get(self, incident_id: str) -> Incident | None:
        with self._lock:
            for incident in self._incidents.values():
                if incident.id == incident_id:
                    return incident

        return None

    def clear(self) -> None:
        with self._lock:
            self._incidents.clear()


incident_store = IncidentStore()
