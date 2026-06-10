
import os

import requests

from scripts._auth import login


def apply():
    base_url = "http://localhost:8000"
    job_id = "cdf2aa70-56a6-4b84-94ab-569a9e7e0e66"
    resume_path = "scripts/john_doe_resume.txt"

    headers = login(base_url)

    # 1. Upload the resume
    print(f"Uploading {resume_path}...")
    with open(resume_path, "rb") as f:
        files = {"file": (os.path.basename(resume_path), f, "text/plain")}
        resp = requests.post(f"{base_url}/files/upload", headers=headers, files=files)
    
    if resp.status_code != 200:
        print(f"Upload failed: {resp.status_code} {resp.text}")
        return

    file_id = resp.json()["file_id"]
    print(f"Uploaded successfully. File ID: {file_id}")

    # 2. Create the application
    print(f"Creating application for job {job_id}...")
    payload = {
        "file_id": file_id
    }
    resp = requests.post(f"{base_url}/jobs/{job_id}/applications", headers=headers, json=payload)
    
    if resp.status_code not in (200, 201, 202):
        print(f"Application failed: {resp.status_code} {resp.text}")
        return

    app_data = resp.json()
    print(f"Application created successfully! Application ID: {app_data['id']}")

if __name__ == "__main__":
    apply()
