import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class DeploymentVaultConfigTests(unittest.TestCase):
    def test_compose_uses_vault_dir_variable(self):
        compose_text = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

        self.assertIn("${VAULT_DIR}:/vault", compose_text)

    def test_env_example_documents_vault_dir_and_nfs_remote(self):
        env_text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

        self.assertIn("VAULT_DIR=", env_text)
        self.assertIn("VAULT_NFS_REMOTE=", env_text)

    def test_install_script_supports_vault_dir_and_nfs_mount(self):
        script_text = (REPO_ROOT / "scripts" / "install-or-update.sh").read_text(encoding="utf-8")

        self.assertIn("VAULT_DIR=", script_text)
        self.assertIn("VAULT_NFS_REMOTE=", script_text)
        self.assertIn("nfs-common", script_text)

    def test_install_script_preserves_explicit_env_overrides(self):
        script_text = (REPO_ROOT / "scripts" / "install-or-update.sh").read_text(encoding="utf-8")

        self.assertIn("APP_DIR_OVERRIDE", script_text)
        self.assertIn("VAULT_DIR_OVERRIDE", script_text)
        self.assertIn("VAULT_NFS_REMOTE_OVERRIDE", script_text)

    def test_install_script_does_not_echo_live_api_token(self):
        script_text = (REPO_ROOT / "scripts" / "install-or-update.sh").read_text(encoding="utf-8")

        self.assertNotIn("grep '^CLASSIFIER_API_TOKEN='", script_text)

    def test_reset_script_uses_vault_dir_variable(self):
        script_text = (REPO_ROOT / "scripts" / "reset-vault-and-index.sh").read_text(encoding="utf-8")

        self.assertIn("VAULT_DIR=", script_text)
        self.assertIn("${VAULT_DIR}", script_text)


if __name__ == "__main__":
    unittest.main()
