from google.cloud import run_v2


def define_job_data() -> run_v2.Job:
    job = run_v2.Job(
        {
            "name": "",  # has to be empty
            "template": _get_execution_template(),
        }
    )
    return job


def _get_execution_template():
    return run_v2.ExecutionTemplate(
        {
            "parallelism": 1,
            "task_count": 1,
            "template": _get_task_template(),
        },
    )


def _get_task_template():
    return run_v2.TaskTemplate(
        {
            "max_retries": 3,
            # "service_account": can be added here (if needed)
            "containers": [_get_container()],
        }
    )


def _get_container():
    return run_v2.Container(
        {
            "image": "eu.gcr.io/acai-bolt-internal/argo-builder:cloud-run-locust-v1",
            "ports": [_get_port()],
        },
    )


def _get_port():
    return run_v2.ContainerPort(
        {"container_port": 5000}
    )
