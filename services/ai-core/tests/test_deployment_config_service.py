import unittest

from services.deployment_config_service import validate_deployment_config


def valid_environment() -> dict[str, str]:
    return {
        "ARK_API_KEY": "ark-secret",
        "ARK_ENDPOINT_ID": "ep-example",
        "VOLC_ACCESS_KEY": "volc-access",
        "VOLC_SECRET_KEY": "volc-secret",
        "VOLC_ACCOUNT_ID": "account-id",
        "KB_COLLECTION_NAME": "commerce",
        "API_AUTH_ENABLED": "true",
        "API_VIEWER_KEY": "viewer-key-123456",
        "API_SERVICE_KEY": "service-key-12345",
        "API_ADMIN_KEY": "admin-key-1234567",
        "SERVER_URL": "https://ai.example.com",
    }


class DeploymentConfigServiceTests(unittest.TestCase):
    def test_valid_production_configuration_passes(self) -> None:
        result = validate_deployment_config(
            valid_environment(),
            production=True,
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.errors, [])

    def test_production_requires_authentication(self) -> None:
        environment = valid_environment()
        environment["API_AUTH_ENABLED"] = "false"

        result = validate_deployment_config(environment, production=True)

        self.assertFalse(result.passed)
        self.assertIn(
            "生产模式必须设置 API_AUTH_ENABLED=true",
            result.errors,
        )

    def test_api_keys_must_be_long_and_distinct(self) -> None:
        environment = valid_environment()
        environment["API_VIEWER_KEY"] = "same"
        environment["API_SERVICE_KEY"] = "same"

        result = validate_deployment_config(environment, production=True)

        self.assertFalse(result.passed)
        self.assertTrue(any("至少需要16位" in error for error in result.errors))
        self.assertTrue(any("不同的 API Key" in error for error in result.errors))

    def test_missing_external_dependencies_are_reported_by_name(self) -> None:
        environment = valid_environment()
        environment["ARK_API_KEY"] = ""
        environment["VOLC_ACCOUNT_ID"] = ""

        result = validate_deployment_config(environment, production=True)

        self.assertFalse(result.passed)
        self.assertTrue(any("ARK_API_KEY" in error for error in result.errors))
        self.assertTrue(any("VOLC_ACCOUNT_ID" in error for error in result.errors))
