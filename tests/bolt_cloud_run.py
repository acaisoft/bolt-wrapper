import uuid

from google.cloud import run_v2

from bolt_utils.cloud_run.job_data import define_job_data


class CloudRunController:
    def __init__(self, workflow_data: dict):
        self.client = run_v2.JobsClient()
        self.workflow_data = workflow_data
        self.uuid = uuid.uuid4()

    def run_workflow(self):
        project_name = "acai-bolt-internal"
        location = "europe-central2"
        parent = f"projects/{project_name}/locations/{location}"
        job_id = f"bolt-auto-cloud-run-job-{self.uuid}"
        job_name = f"projects/{project_name}/locations/{location}/jobs/{job_id}"
        self.create_job(parent, job_id)
        self.run_job(job_name)

    def create_job(self, parent: str, job_id: str):
        job = define_job_data()
        request = run_v2.CreateJobRequest(
            {"parent": parent, "job": job, "job_id": job_id}
        )

        # Make the request
        operation = self.client.create_job(request=request)

        print("Waiting for job creation to complete...")

        response = operation.result()

        # Handle the response
        print(response)

    def run_job(self, job_name: str):
        request = run_v2.RunJobRequest({"name": job_name})

        # Make the request
        operation = self.client.run_job(request=request)

        print("Waiting for job execution to complete...")

        response = operation.result()

        # Handle the response
        print(response)


if __name__ == "__main__":
    cloud_run_controller = CloudRunController({})
    cloud_run_controller.run_workflow()
