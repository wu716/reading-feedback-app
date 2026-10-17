"""Production startup must not depend on retired AI credentials."""

import os
from unittest import TestCase
from unittest.mock import patch

from start_aliyun import check_environment


class ProductionEnvironmentTests(TestCase):
    def test_required_service_configuration_without_ai_key(self):
        with patch.dict(os.environ, {
            "SECRET_KEY": "test-signing-key",
            "DATABASE_URL": "postgresql://localhost/shuran",
        }, clear=True):
            self.assertTrue(check_environment())

    def test_missing_database_or_signing_key_still_fails(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(check_environment())
