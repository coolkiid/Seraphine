import argparse
import os
import requests

parser = argparse.ArgumentParser(
    description="a script to sync GitHub Release to Gitee release."
)
parser.add_argument(
    "-t", "--tag", type=str, help="version tag of GitHub Release", required=True
)
args = parser.parse_args()

ACCESS_TOKEN = os.environ["ACCESS_TOKEN"]
TAG_NAME = args.tag
NAME = TAG_NAME
BODY = f"Seraphine {TAG_NAME}"
TARGET_COMMITISH = "main"
FILE_PATH = "Seraphine.zip"

HEADERS = {"Authorization": f"Bearer {ACCESS_TOKEN}"}


def create_new_release(owner, repo):
    url = f"https://gitee.com/api/v5/repos/{owner}/{repo}/releases"
    data = {
        "tag_name": TAG_NAME,
        "name": NAME,
        "body": BODY,
        "target_commitish": TARGET_COMMITISH,
    }
    response = requests.post(url, data=data, headers=HEADERS, timeout=30)
    if 200 <= response.status_code < 300:
        return response.json()["id"]
    raise requests.HTTPError("create release on gitee failed.")


def upload_file(release_id):
    url = f"https://gitee.com/api/v5/repos/coolkiid/Macast/releases/{release_id}/attach_files"
    files = {"file": open(FILE_PATH, "rb")}
    response = requests.post(url, files=files, headers=HEADERS, timeout=30)
    if 200 <= response.status_code < 300:
        return response.json()["browser_download_url"]
    raise requests.HTTPError("push release file to gitee failed.")


release_id = create_new_release("coolkiid", "Macast")
download_url = upload_file(release_id)
print(
    f"latest GitHub Release has been synced to Gitee Release, download url is {download_url}"
)
