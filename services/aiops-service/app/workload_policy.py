"""Reject accidental credential co-location before any AWS/database access."""
import os


def validate_workload():
    forbidden=('DATABASE_URL','AI_API_KEY','AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY',
               'AWS_SESSION_TOKEN','AWS_PROFILE','AWS_SHARED_CREDENTIALS_FILE','KUBECONFIG',
               'AWS_CONFIG_FILE','AWS_DEFAULT_PROFILE','AWS_CREDENTIAL_FILE','BOTO_CONFIG',
               'GOOGLE_APPLICATION_CREDENTIALS',
               'AWS_CONTAINER_CREDENTIALS_FULL_URI','AWS_CONTAINER_CREDENTIALS_RELATIVE_URI')
    if (os.getenv('AI_WORKLOAD')!='inference' or any(os.getenv(k) for k in forbidden)
        or any(k.startswith('CLOUDFORGE_') and v for k,v in os.environ.items())
        or not os.getenv('AWS_ROLE_ARN') or not os.getenv('AWS_WEB_IDENTITY_TOKEN_FILE')
        or os.getenv('AWS_EC2_METADATA_DISABLED')!='true'):
        raise ValueError('Dedicated workload identity and credential boundary required')
