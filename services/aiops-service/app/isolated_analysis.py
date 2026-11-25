"""Translate aggregate-only diagnosis into existing API contracts; never changes telemetry."""
import json
from datetime import datetime, timezone
from .ai_provider import AIProvider
from .inference_security import validate_diagnosis
from .knowledge_config import knowledge_references
from .models import AIAnalysis, AnalysisConfidence
from .project_evidence import aggregate_evidence


def analyze_project(project_id: str) -> AIAnalysis:
    evidence=aggregate_evidence(project_id)
    references=knowledge_references(' '.join(e['signal'].replace('_',' ') for e in evidence if e['state']=='degraded'),project_id)
    degraded={e['signal'] for e in evidence if e['state']=='degraded'}
    related=degraded.intersection({s for r in references['references'] for s in r.get('signals',[])})
    base=dict(root_cause_hints=[f'Local runbook context supports investigating {s}; causality is unproven.' for s in sorted(related)],diagnosis_project_id=project_id,provider='gemini',model='gemini-2.5-flash',confidence=AnalysisConfidence.LOW,
              evidence_findings=[f"{e['signal']}: {e['state']}" for e in evidence],
              retrieval_status=references['retrieval_status'],knowledge_references=references['references'],
              generated_at=datetime.now(timezone.utc))
    provider=AIProvider()
    provider.provider='gemini'
    if all(e['state']=='unknown' for e in evidence):
        return AIAnalysis(**base,status='blocked',summary='Project telemetry is unavailable.',
                          assessment='insufficient_evidence',error='No verified project aggregates; no inference requested')
    result=provider.analyze('',json.dumps({'evidence':evidence}))
    if result.status!='success':
        return AIAnalysis(**base,status='blocked',summary='AI diagnosis is unavailable; review project telemetry.',
                          assessment='insufficient_evidence',error=result.error)
    try:
        diagnosis=validate_diagnosis(result.content or '',evidence)
        cited=[evidence[i] for i in diagnosis.citations]
        return AIAnalysis(**{**base,'confidence':AnalysisConfidence(diagnosis.confidence)},status='success',
                          summary={'healthy':'Supplied project signals are healthy.',
                                   'degraded':'Supplied project signals indicate degradation.',
                                   'insufficient_evidence':'The supplied evidence is insufficient for diagnosis.'}[diagnosis.assessment],
                          probable_cause='Causality is not established by aggregate signals.',
                          assessment='alert_supported' if diagnosis.assessment=='degraded' else 'insufficient_evidence' if diagnosis.assessment=='insufficient_evidence' else 'alert_not_currently_observed',
                          citations=[f"aggregate:{e['signal']}:{e['state']}" for e in cited])
    except Exception:
        return AIAnalysis(**base,status='blocked',summary='AI diagnosis was rejected.',
                          assessment='insufficient_evidence',error='Invalid or contradictory diagnosis')
