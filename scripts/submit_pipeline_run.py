"""Upload fd-gitops-pipeline and create a run against THIS demo's DSPA."""
import json
import os
import ssl
import time
import urllib.error
import urllib.request
import urllib.parse

PIPELINE_FILE = os.environ.get("PIPELINE_FILE", "/pipeline/pipeline.yaml")
API = os.environ.get(
    "DSPA_API",
    "https://ds-pipeline-fd-gitops-dspa.fd-gitops.svc.cluster.local:8443",
).rstrip("/")
NAMESPACE = os.environ.get("NAMESPACE", "fd-gitops")
EXPERIMENT_NAME = os.environ.get("EXPERIMENT_NAME", "fd-gitops-training")
RUN_NAME = os.environ.get("RUN_NAME", "fd-gitops-e2e")
PIPELINE_DISPLAY = os.environ.get("PIPELINE_DISPLAY_NAME", "fd-gitops-pipeline")


def _token() -> str:
    path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ca = "/var/run/secrets/kubernetes.io/serviceaccount/service-ca.crt"
    if os.path.exists(ca):
        ctx.load_verify_locations(ca)
    else:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    ctx.check_hostname = False
    return ctx


def _request(method: str, path: str, data: bytes | None = None, content_type: str | None = None):
    headers = {"Authorization": f"Bearer {_token()}"}
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(f"{API}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, context=_ssl_context(), timeout=120) as resp:
            body = resp.read()
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} -> HTTP {e.code}: {err[:500]}") from e


def ensure_experiment() -> str:
    status, body = _request("GET", f"/apis/v2beta1/experiments?namespace={NAMESPACE}&page_size=100")
    for exp in body.get("experiments") or []:
        if exp.get("display_name") == EXPERIMENT_NAME:
            print("experiment_id", exp["experiment_id"])
            return exp["experiment_id"]
    payload = json.dumps(
        {
            "display_name": EXPERIMENT_NAME,
            "description": "fd-gitops independent demo",
            "namespace": NAMESPACE,
        }
    ).encode()
    status, body = _request("POST", "/apis/v2beta1/experiments", payload, "application/json")
    print("created_experiment", body.get("experiment_id"))
    return body["experiment_id"]


def _pipeline_ids(obj: dict) -> tuple:
    pid = obj.get("pipeline_id")
    vid = obj.get("pipeline_version_id")
    if not pid and isinstance(obj.get("pipeline"), dict):
        pid = obj["pipeline"].get("pipeline_id")
    if not vid and isinstance(obj.get("pipeline_version"), dict):
        vid = obj["pipeline_version"].get("pipeline_version_id")
        pid = pid or obj["pipeline_version"].get("pipeline_id")
    return pid, vid


def _multipart(yaml_bytes: bytes) -> tuple:
    boundary = "----FdGitopsBoundary7MA4YWxkTrZu0gW"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="uploadfile"; filename="pipeline.yaml"\r\n'
        f"Content-Type: application/x-yaml\r\n\r\n"
    ).encode() + yaml_bytes + f"\r\n--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def ensure_pipeline() -> tuple:
    force_new = os.environ.get("UPLOAD_NEW_VERSION", "true").lower() in ("1", "true", "yes")
    status, body = _request("GET", f"/apis/v2beta1/pipelines?namespace={NAMESPACE}&page_size=100")
    existing = None
    for p in body.get("pipelines") or []:
        if p.get("display_name") == PIPELINE_DISPLAY:
            existing = p
            break

    with open(PIPELINE_FILE, "rb") as f:
        yaml_bytes = f.read()
    body_bytes, headers_ct = _multipart(yaml_bytes)

    def _latest_version(pid: str) -> str | None:
        _, vers = _request(
            "GET",
            f"/apis/v2beta1/pipelines/{pid}/versions?page_size=5&sort_by=created_at%20desc",
        )
        versions = vers.get("pipeline_versions") or []
        return versions[0]["pipeline_version_id"] if versions else None

    if existing and force_new:
        pid = existing["pipeline_id"]
        ver_name = urllib.parse.quote(
            f"{PIPELINE_DISPLAY}-{os.environ.get('RUN_NAME', 'v')}-{int(time.time())}"
        )
        path = f"/apis/v2beta1/pipelines/upload_version?pipelineid={pid}&name={ver_name}"
        req = urllib.request.Request(
            f"{API}{path}",
            data=body_bytes,
            headers={"Authorization": f"Bearer {_token()}", "Content-Type": headers_ct},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, context=_ssl_context(), timeout=180) as resp:
                uploaded = json.loads(resp.read())
            print("upload_version_response", json.dumps(uploaded)[:500])
            _, vid = _pipeline_ids(uploaded)
            vid = vid or uploaded.get("pipeline_version_id")
            if not vid:
                raise RuntimeError(f"upload_version missing id: {uploaded}")
            print("uploaded_version", pid, vid)
            return pid, vid
        except urllib.error.HTTPError as e:
            # 409 = version name clash — reuse latest and still create a run
            err = e.read().decode("utf-8", errors="replace")
            print(f"upload_version HTTP {e.code}: {err[:200]} — falling back to latest version")
            vid = _latest_version(pid)
            if not vid:
                raise RuntimeError(f"upload_version failed HTTP {e.code}: {err[:800]}") from e
            print("reuse_pipeline_after_conflict", pid, vid)
            return pid, vid

    if existing and not force_new:
        pid = existing["pipeline_id"]
        vid = _latest_version(pid)
        if vid:
            print("reuse_pipeline", pid, vid)
            return pid, vid

    path = f"/apis/v2beta1/pipelines/upload?namespace={NAMESPACE}&name={PIPELINE_DISPLAY}"
    req = urllib.request.Request(
        f"{API}{path}",
        data=body_bytes,
        headers={"Authorization": f"Bearer {_token()}", "Content-Type": headers_ct},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, context=_ssl_context(), timeout=180) as resp:
            uploaded = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"upload failed HTTP {e.code}: {err[:800]}") from e
    print("upload_response", json.dumps(uploaded)[:500])
    pid, vid = _pipeline_ids(uploaded)
    if pid and not vid:
        _, vers = _request(
            "GET",
            f"/apis/v2beta1/pipelines/{pid}/versions?page_size=5&sort_by=created_at%20desc",
        )
        versions = vers.get("pipeline_versions") or []
        if versions:
            vid = versions[0]["pipeline_version_id"]
    if not pid or not vid:
        raise RuntimeError(f"upload response missing ids: {uploaded}")
    print("uploaded_pipeline", pid, vid)
    return pid, vid


def create_run(experiment_id: str, pipeline_id: str, pipeline_version_id: str) -> str:
    ns = NAMESPACE
    feast_name = os.environ.get("FEAST_NAME", "fd-gitops-fs")
    params = {
        "s3_endpoint": os.environ["AWS_S3_ENDPOINT"],
        "s3_bucket": os.environ["AWS_S3_BUCKET"],
        "aws_access_key_id": os.environ["AWS_ACCESS_KEY_ID"],
        "aws_secret_access_key": os.environ["AWS_SECRET_ACCESS_KEY"],
        "feast_online_server_url": os.environ.get(
            "FEAST_URL",
            f"https://feast-{feast_name}-online.{ns}.svc.cluster.local:443",
        ),
        "mlflow_tracking_uri": os.environ.get(
            "MLFLOW_TRACKING_URI",
            "https://mlflow.redhat-ods-applications.svc.cluster.local:8443/mlflow",
        ),
        "s3_key": os.environ.get("S3_KEY", "fd-gitops/raw/transactions.csv"),
        "mlflow_experiment": EXPERIMENT_NAME,
        "model_s3_key": os.environ.get("MODEL_S3_KEY", "fd-gitops/models/fraud-model.pkl"),
        "model_name": "fd-gitops-model",
    }
    payload = {
        "display_name": RUN_NAME,
        "description": "fd-gitops PostSync: S3 -> Feast -> MLflow",
        "experiment_id": experiment_id,
        "pipeline_version_reference": {
            "pipeline_id": pipeline_id,
            "pipeline_version_id": pipeline_version_id,
        },
        "runtime_config": {"parameters": params},
        "service_account": os.environ.get(
            "PIPELINE_SA", f"pipeline-runner-{os.environ.get('DSPA_NAME', 'fd-gitops-dspa')}"
        ),
    }
    status, body = _request("POST", "/apis/v2beta1/runs", json.dumps(payload).encode(), "application/json")
    rid = body.get("run_id") or body.get("run", {}).get("run_id")
    print("run_id", rid)
    print("run_state", body.get("state") or body.get("run", {}).get("state"))
    return rid


def main() -> None:
    exp = ensure_experiment()
    pid, vid = ensure_pipeline()
    create_run(exp, pid, vid)


if __name__ == "__main__":
    main()
