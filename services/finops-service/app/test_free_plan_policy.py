from unittest.mock import patch

import pytest

from .aws_finops_client import AWSFinOpsClient, AWSFinOpsError


def test_disabled_billing_never_creates_sdk_clients(monkeypatch):
    monkeypatch.setenv('CLOUDFORGE_AWS_BILLING_ENABLED', 'false')
    with patch('app.aws_finops_client.boto3.client') as client:
        with pytest.raises(AWSFinOpsError, match='disabled by deployment policy'):
            AWSFinOpsClient()
        client.assert_not_called()
