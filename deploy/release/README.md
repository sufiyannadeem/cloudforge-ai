# Unbound release inputs

Supply an independently approved clean source revision, hosted run/attempt and
actual seven-image registry references only after separate release authorization.
Templates deliberately contain nulls and publish=false. Local image IDs, tags,
fixtures and prior release identities are not current release evidence.

../security/retired-release-denylist.json is a deny-only security policy. It cannot
select images or authorize a release. Production Cosign signature/attestation,
issuer/identity/ref/event/predicate/subject checks remain mandatory through the
existing release-images.py verification path. The source-only check is not
publication or deployment authorization. No workflow is dispatched here.
