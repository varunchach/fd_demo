"""Local regressions; requires Helm 3, Python 3 and PyYAML. No cluster is used."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
HELM = os.environ.get("HELM", "helm")


class FeatureStoreUI(unittest.TestCase):
    def render(self, *extra):
        command = [
            HELM, "template", "fd-cust-trial", str(ROOT / "chart"),
            "--namespace", "fd-cust-trial",
            "--set", "featureStore.offlineS3Bucket=feature-store",
            "--set", "featureStore.offlineS3Prefix=fd-cust-trial/features",
            "--set", "pipelines.s3Host=s3.example.test",
            "--set", "pipelines.s3Bucket=pipelines",
            *extra,
        ]
        return subprocess.run(command, capture_output=True, text=True)

    def test_ui_toggle_changes_only_discovery_label(self):
        enabled = self.render("--set", "featureStore.uiEnabled=true")
        disabled = self.render("--set", "featureStore.uiEnabled=false")
        self.assertEqual(enabled.returncode, 0, enabled.stderr)
        self.assertEqual(disabled.returncode, 0, disabled.stderr)
        on = [d for d in yaml.safe_load_all(enabled.stdout) if d]
        off = [d for d in yaml.safe_load_all(disabled.stdout) if d]
        fs = next(d for d in on if d["kind"] == "FeatureStore")
        self.assertEqual(fs["metadata"].pop("labels"), {"feature-store-ui": "enabled"})
        self.assertEqual(on, off)  # Storage, services, pipelines and namespace do not change.
        self.assertTrue(fs["spec"]["services"]["registry"]["local"]["server"]["restAPI"])

    def test_boolean_string_is_rejected(self):
        result = self.render("--set-string", "featureStore.uiEnabled=false")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("uiEnabled", result.stderr)

    def setup_script(self, existing, ui=None, lookup_fails=False, namespace="fd-cust-trial", new=False):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            mock = work / "oc"
            mock.write_text("#!" + sys.executable + "\n" + '''
import json, os, sys
args = sys.argv[1:]
with open(os.environ["MOCK_LOG"], "a") as stream:
    stream.write(json.dumps(args) + "\\n")
if args[0] == "get":
    if os.environ.get("MOCK_LOOKUP_FAIL") == "1":
        sys.exit(1)
    print(os.environ["MOCK_APPLICATION"], end="")
''')
            mock.chmod(0o755)
            env = dict(os.environ)
            for key in ("APP_NAME", "FEAST_UI_ENABLED", "APP_NS", "S3_PREFIX", "S3_RAW_KEY"):
                env.pop(key, None)
            application = {
                "spec": {
                    "destination": {"namespace": namespace},
                    "source": {
                        "repoURL": "https://github.com/example/customer-fork.git",
                        "targetRevision": "customer-release", "path": "chart",
                        "helm": {"parameters": existing, "valueFiles": ["values.yaml", "customer.yaml"]},
                    },
                },
            }
            env.update(
                PATH=str(work) + os.pathsep + env["PATH"], TMPDIR=directory,
                NS="fd-cust-trial", AWS_S3_ENDPOINT="https://s3.example.test",
                PIPELINE_BUCKET="pipelines", FEAST_BUCKET="feature-store",
                MOCK_LOG=str(work / "calls"), MOCK_APPLICATION="" if new else json.dumps(application),
                MOCK_LOOKUP_FAIL="1" if lookup_fails else "0",
            )
            if ui is not None:
                env["FEAST_UI_ENABLED"] = ui
            result = subprocess.run(
                ["bash", str(ROOT / "scripts/configure_argo_site.sh")],
                env=env, capture_output=True, text=True,
            )
            log = work / "calls"
            calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
            return result, calls

    def parameters_from(self, calls):
        for args in calls:
            if args[0] == "patch":
                patch = json.loads(args[args.index("-p") + 1])
                if "spec" in patch:
                    return patch["spec"]["source"]["helm"]["parameters"]
        self.fail("No parameter patch")

    def test_rerun_preserves_ui_and_registry_overrides(self):
        existing = [
            {"name": "featureStore.uiEnabled", "value": "false"},
            {"name": "featureStore.enabled", "value": "false"},
            {"name": "featureStore.registryS3Path", "value": "s3://shared/custom/registry.db"},
            {"name": "git.repoURL", "value": "https://github.com/example/fork.git", "forceString": True},
        ]
        result, calls = self.setup_script(existing)
        self.assertEqual(result.returncode, 0, result.stderr)
        parameters = self.parameters_from(calls)
        self.assertFalse(any(args[0] == "apply" for args in calls))
        for args in calls:
            if args[0] == "patch":
                patch = json.loads(args[args.index("-p") + 1])
                if "spec" in patch:
                    self.assertEqual(set(patch["spec"]["source"]), {"helm"})
                if "operation" in patch:
                    self.assertNotIn("revision", patch["operation"]["sync"])
        for item in existing:
            self.assertIn(item, parameters)
        # NS alone selects that application, not the old fd-gitops application.
        self.assertTrue(all(args[2] == "fd-cust-trial" for args in calls if args[0] in ("get", "patch", "annotate")))
        again, calls = self.setup_script(parameters)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(self.parameters_from(calls), parameters)

    def test_explicit_selection_replaces_only_ui_override(self):
        existing = [{"name": "featureStore.uiEnabled", "value": "false"}]
        result, calls = self.setup_script(existing, ui="true")
        self.assertEqual(result.returncode, 0, result.stderr)
        selected = [p for p in self.parameters_from(calls) if p["name"] == "featureStore.uiEnabled"]
        self.assertEqual(selected, [{"name": "featureStore.uiEnabled", "value": "true"}])

    def test_lookup_failure_stops_before_mutation(self):
        result, calls = self.setup_script([], lookup_fails=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(calls)
        self.assertTrue(all(args[0] == "get" for args in calls))

    def test_wrong_application_namespace_stops_before_mutation(self):
        result, calls = self.setup_script([], namespace="old-stack")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(all(args[0] == "get" for args in calls))

    def test_new_application_is_bootstrapped(self):
        result, calls = self.setup_script([], ui="true", new=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sum(args[0] == "apply" for args in calls), 1)

    def test_invalid_selection_stops_before_cluster_calls(self):
        result, calls = self.setup_script([], ui="yes")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
