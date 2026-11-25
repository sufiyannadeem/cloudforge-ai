#!/usr/bin/env python3
"""Synthetic bootstrap for this workflow's ephemeral hosted PostgreSQL only."""
import os
import hmac
import re
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

DATABASES=('cloudforge_inference_test','cloudforge_remediation_test','cloudforge_release_test')
ROLES=('cf_migrator','cf_project','cf_infrastructure','cf_deployment','cf_aiops',
       'cf_finops_project','cf_finops_audit','cf_drift','cf_inference')


def synthetic_config(dsn,password):
    if not re.fullmatch('[a-f0-9]{64}',password):
        raise RuntimeError('A dedicated random 64-hex-character synthetic CI secret is required')
    config=conninfo_to_dict(dsn)
    if (config.get('host')!='127.0.0.1' or config.get('dbname')!='postgres' or config.get('user')!='postgres'
        or not hmac.compare_digest(config.get('password',''),password) or config.get('sslmode')!='disable'):
        raise RuntimeError('Only synthetic service-container credentials accepted')
    return config


def main():
    if (os.getenv('GITHUB_ACTIONS')!='true' or os.getenv('RUNNER_ENVIRONMENT')!='github-hosted'
        or os.getenv('CI_EPHEMERAL_POSTGRES')!='synthetic-service-only'):
        raise RuntimeError('Hosted ephemeral-service bootstrap only; no local/shared database use')
    dsn=os.environ['CI_POSTGRES_ADMIN_DSN']
    config=synthetic_config(dsn,os.environ.get('CI_SYNTHETIC_POSTGRES_PASSWORD',''))
    with psycopg.connect(dsn,connect_timeout=3,autocommit=True) as db:
        if db.execute('SHOW server_version_num').fetchone()[0][:2]!='16':raise RuntimeError('Expected PostgreSQL 16')
        if db.execute('SELECT 1 FROM pg_database WHERE datname=ANY(%s)',(list(DATABASES),)).fetchone():
            raise RuntimeError('Test databases must not preexist; no reset/reuse allowed')
        if db.execute('SELECT 1 FROM pg_roles WHERE rolname=ANY(%s)',(list(ROLES),)).fetchone():
            raise RuntimeError('Service roles must not preexist on synthetic cluster')
        for role in ROLES:
            db.execute(sql.SQL('CREATE ROLE {} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT').format(sql.Identifier(role)))
        for database in DATABASES:db.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
    release={**config,'dbname':'cloudforge_release_test'}
    with psycopg.connect(**release,connect_timeout=3) as db:db.execute('CREATE EXTENSION pgcrypto')
    # No production identities/data, grants, historical ledgers or evidence are imported.
    print('Prepared three new disposable synthetic test databases and unprivileged NOLOGIN roles')


if __name__=='__main__':main()
