"""One narrow function grant; no access to business tables or ledger mutations."""
import os
import psycopg


def reserve_request(nonce: str, body_hash: str, expiry: int) -> bool:
    # IAM tokens are signed locally. The worker has no database password secret.
    import boto3
    host = os.environ['AI_LEDGER_HOST']
    port = int(os.getenv('AI_LEDGER_PORT', '5432'))
    token = boto3.client('rds', region_name=os.environ['AWS_REGION']).generate_db_auth_token(
        DBHostname=host, Port=port, DBUsername='cf_inference')
    with psycopg.connect(host=host, port=port, dbname=os.environ['AI_LEDGER_DATABASE'],
                         user='cf_inference', password=token, sslmode='verify-full',
                         sslrootcert=os.environ['PGSSLROOTCERT'], connect_timeout=2,
                         options='-c statement_timeout=2000 -c lock_timeout=1500') as db:
        row = db.execute('SELECT public.cloudforge_reserve_inference(%s,%s,%s)',
                         (nonce, body_hash, expiry)).fetchone()
        return row is not None and row[0] is True
