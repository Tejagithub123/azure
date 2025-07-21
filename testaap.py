import requests
import json
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

awx_url = "https://192.168.56.19"
job_template_id = 14
username = "admin"
password = "redhat123"

payload = {
    "extra_vars": {
        "vmId": 7,
        "name": "MaherTurki",
        "flavor": "small",
        "image": "rhel",
        "network": "public",
        "keypair": "",
        "userData": ""
    },
    "inventory": 1
}

response = requests.post(
    f"{awx_url}/api/v2/job_templates/{job_template_id}/launch/",
    auth=(username, password),
    headers={"Content-Type": "application/json"},
    data=json.dumps(payload),
    verify=False
)

print("Status Code:", response.status_code)
print("Response:", json.dumps(response.json(), indent=2))
