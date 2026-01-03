"""Standalone python script to generate Arknights FlatBuffers schemas by bruteforcing previously-known schemas.

Requires: python 3.9+, python's requests, .NET 6.0, flatc
"""

import argparse
import json
import os
import random
import re
import shutil
import stat
import subprocess
import tempfile
import typing
import zipfile
from pathlib import Path

import requests


def _rmtree_onerror(func: typing.Callable[[str], None], path: str, exc_info: object):
    # Make file writable and retry
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        raise


# parse arguments
parser = argparse.ArgumentParser()
parser.add_argument("--server", choices=["tw", "yostar"], required=True)
args = parser.parse_args()
server: str = args.server

# setup temporary directory
tmp_dir = Path(tempfile.gettempdir()) / f"fbs-{server}"
if tmp_dir.exists():
    shutil.rmtree(tmp_dir, onerror=_rmtree_onerror)  # pyright: ignore[reportDeprecated]
tmp_dir.mkdir(parents=True, exist_ok=True)

bundles_dir = tmp_dir / "bundles"
bundles_dir.mkdir(parents=True, exist_ok=True)


# prepare network config
# cannot use en for yostar because it updates later
network_config_url = (
    "https://ak-conf-tw.gryphline.com/config/prod/official/network_config" if server == "tw" else "https://ak-conf.arknights.jp/config/prod/official/network_config"
)
network_config = json.loads(requests.get(network_config_url).json()["content"])
network_urls = network_config["configs"][network_config["funcVer"]]["network"]
version_url = network_urls["hv"].replace("{0}", "Android")
res_version: str = requests.get(version_url).json()["resVersion"]
assets_url = network_urls["hu"] + "/Android/assets/" + res_version + "/"

# download gamedata files
print(f"downloading assets for {server}")
hot_update_list = requests.get(assets_url + "hot_update_list.json").json()
for item in hot_update_list["abInfos"]:
    name = item["name"]
    if "gamedata" not in name and "anon" not in name:
        continue

    print(name)
    formatted_name = name.replace("/", "_").replace("#", "__").rsplit(".", 1)[0] + ".dat"
    url = assets_url + formatted_name
    zip_file_path = tmp_dir / "akassets" / formatted_name
    zip_file_path.parent.mkdir(parents=True, exist_ok=True)

    with requests.get(url, stream=True) as response, open(zip_file_path, "wb") as file:
        for chunk in response.iter_content(chunk_size=None):
            file.write(chunk)

    with zipfile.ZipFile(zip_file_path, "r") as zip_ref:
        zip_ref.extractall(bundles_dir)

    os.remove(zip_file_path)

# download ArknightsStudioCLI
if os.name == "nt":
    url = "https://github.com/aelurum/AssetStudio/releases/download/ak-v1.2.1/ArknightsStudioCLI-net6-Portable.v1.2.1.zip"
    arknights_studio_path = tmp_dir / "ArknightsStudioCLI\\ArknightsStudioCLI.exe"
else:
    url = "https://github.com/thesadru/AssetStudio/releases/download/ak-v1.2.1/ArknightsStudioCLI-net6-linux64.v1.2.1.zip"
    arknights_studio_path = tmp_dir / "ArknightsStudioCLI/ArknightsStudioCLI"

if not arknights_studio_path.is_file():
    print("downloading ArknightsStudioCLI")
    with tempfile.TemporaryFile("wb+") as file:
        with requests.get(url, stream=True) as response:
            for chunk in response.iter_content(chunk_size=None):
                file.write(chunk)
        file.seek(0)
        with zipfile.ZipFile(file, "r") as zip_ref:
            zip_ref.extractall(tmp_dir / "ArknightsStudioCLI")

os.chmod(arknights_studio_path, 0o775)

# download flatc
if os.name == "nt":
    url = "https://github.com/google/flatbuffers/releases/download/v25.12.19/Windows.flatc.binary.zip"
    flatc_path = tmp_dir / "flatc.exe"
else:
    url = "https://github.com/google/flatbuffers/releases/download/v25.12.19/Linux.flatc.binary.g++-13.zip"
    flatc_path = tmp_dir / "flatc"

with tempfile.TemporaryFile("wb+") as file:
    print("downloading flatc")
    with requests.get(url, stream=True) as response:
        for chunk in response.iter_content(chunk_size=None):
            file.write(chunk)
    file.seek(0)
    with zipfile.ZipFile(file, "r") as zip_ref:
        zip_ref.extractall(tmp_dir)

os.chmod(flatc_path, 0o775)

# clone OpenArknightsFBS
print("cloning OpenArknightsFBS")
oafbs_dir = tmp_dir / "OpenArknightsFBS"
subprocess.run(["git", "clone", "https://github.com/MooncellWiki/OpenArknightsFBS", str(oafbs_dir)], check=True, stdout=subprocess.DEVNULL)

# extract TextAssets
print("extracting TextAssets")
extracted_dir = tmp_dir / "extracted"
subprocess.run([str(arknights_studio_path), str(bundles_dir), "-t", "TextAsset", "-o", str(extracted_dir)], check=True)

# setup output directories
export_dir = tmp_dir / "export"
extracted_cut_dir = tmp_dir / "extracted-cut"
output_dir = tmp_dir / "output" / server
schema_dir = Path(server)

export_dir.mkdir(parents=True, exist_ok=True)
extracted_cut_dir.mkdir(parents=True, exist_ok=True)
output_dir.mkdir(parents=True, exist_ok=True)
(output_dir / "levels").mkdir(parents=True, exist_ok=True)
schema_dir.mkdir(parents=True, exist_ok=True)

# prepare yostar-preferred if needed
yostar_preferred_dir = Path()
if server == "yostar":
    subprocess.run(["git", "-C", str(oafbs_dir), "checkout", "origin/YoStar"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    yostar_preferred_dir = tmp_dir / "yostar-preferred"
    if yostar_preferred_dir.exists():
        shutil.rmtree(yostar_preferred_dir, onerror=_rmtree_onerror)  # pyright: ignore[reportDeprecated]
    shutil.copytree(oafbs_dir / "FBS", yostar_preferred_dir)
    subprocess.run(["git", "-C", str(oafbs_dir), "checkout", "origin/main"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# process gamedata files
print("Processing gamedata files")
for path in extracted_dir.rglob("*.bytes"):
    cutpath = extracted_cut_dir / path.name
    with open(path, "rb") as infile, open(cutpath, "wb") as outfile:
        infile.seek(128)
        outfile.write(infile.read())

    match = re.search(r"gamedata[/\\](.+_(table|data|const|database))([0-9a-fA-F]{6})", str(path))
    if not match:
        continue
    name = Path(match[1]).name

    # for yostar, try preferred schema first
    if server == "yostar":
        preferred_schema = yostar_preferred_dir / f"{name}.fbs"
        if preferred_schema.exists():
            result = subprocess.run(
                [
                    str(flatc_path),
                    "-o",
                    str(output_dir),
                    str(preferred_schema),
                    "--",
                    str(cutpath),
                    "--no-warnings",
                    "--json",
                    "--strict-json",
                    "--natural-utf8",
                    "--defaults-json",
                    "--unknown-json",
                    "--raw-binary",
                    "--force-empty",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if result.returncode == 0:
                (output_dir / f"{cutpath.stem}.json").rename(output_dir / f"{name}.json")
                shutil.copy(preferred_schema, schema_dir / f"{name}.fbs")
                print(f"{name} - default")
                continue

    # bruteforce through git history
    git_result = subprocess.run(["git", "-C", str(oafbs_dir), "rev-list", "--all", "--objects", "--", f"FBS/{name}.fbs"], capture_output=True, text=True, check=True)

    for line in git_result.stdout.strip().split("\n"):
        if not line:
            continue
        commit_hash = line.split()[0]

        schema_content = subprocess.run(["git", "-C", str(oafbs_dir), "cat-file", "-p", f"{commit_hash}:FBS/{name}.fbs"], capture_output=True, text=True)
        if schema_content.returncode != 0:
            continue

        temp_schema = export_dir / f"{name}.{commit_hash}.fbs"
        temp_schema.write_text(schema_content.stdout)

        result = subprocess.run(
            [
                str(flatc_path),
                "-o",
                str(output_dir),
                str(temp_schema),
                "--",
                str(cutpath),
                "--no-warnings",
                "--json",
                "--strict-json",
                "--natural-utf8",
                "--defaults-json",
                "--unknown-json",
                "--raw-binary",
                "--force-empty",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        if result.returncode == 0:
            (output_dir / f"{cutpath.stem}.json").rename(output_dir / f"{name}.json")
            with open(schema_dir / f"{name}.fbs", "w") as outfile:
                outfile.write(f"// https://github.com/MooncellWiki/OpenArknightsFBS/commit/{commit_hash}\n")
                outfile.write(schema_content.stdout)
            print(f"{name} - {commit_hash}")
            break

# process levels
print("Processing levels")
name = "prts___levels"

levels_path = extracted_dir / "dyn" / "gamedata" / "levels" / "activities"

# for yostar, try preferred schema first
preferred_schema_for_levels_works = False
if server == "yostar":
    preferred_schema = yostar_preferred_dir / f"{name}.fbs"
    if preferred_schema.exists():
        success = True
        level_files = list(levels_path.rglob("*.bytes"))

        for path in random.choices(level_files, k=20):
            cutpath = extracted_cut_dir / path.name
            with open(path, "rb") as infile, open(cutpath, "wb") as outfile:
                infile.seek(128)
                outfile.write(infile.read())

            result = subprocess.run(
                [
                    str(flatc_path),
                    "-o",
                    str(output_dir / "levels"),
                    str(preferred_schema),
                    "--",
                    str(cutpath),
                    "--no-warnings",
                    "--json",
                    "--strict-json",
                    "--natural-utf8",
                    "--defaults-json",
                    "--unknown-json",
                    "--raw-binary",
                    "--force-empty",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            if result.returncode != 0:
                success = False
                break

        if success:
            shutil.copy(preferred_schema, schema_dir / f"{name}.fbs")
            preferred_schema_for_levels_works = True
            print(f"{name} - default")
        else:
            print(f"{name} - default schema failed, trying git history")

if not preferred_schema_for_levels_works:
    git_result = subprocess.run(["git", "-C", str(oafbs_dir), "rev-list", "--all", "--objects", "--", f"FBS/{name}.fbs"], capture_output=True, text=True, check=True)

    for line in git_result.stdout.strip().split("\n"):
        if not line:
            continue
        commit_hash = line.split()[0]

        schema_content = subprocess.run(["git", "-C", str(oafbs_dir), "cat-file", "-p", f"{commit_hash}:FBS/{name}.fbs"], capture_output=True, text=True)
        if schema_content.returncode != 0:
            continue

        temp_schema = export_dir / f"{name}.{commit_hash}.fbs"
        temp_schema.write_text(schema_content.stdout)

        success = True
        level_files = list(levels_path.rglob("*.bytes"))

        for path in random.choices(level_files, k=20):
            cutpath = extracted_cut_dir / path.name
            with open(path, "rb") as infile, open(cutpath, "wb") as outfile:
                infile.seek(128)
                outfile.write(infile.read())

            print(f"{commit_hash} {path}")
            result = subprocess.run(
                [
                    str(flatc_path),
                    "-o",
                    str(output_dir / "levels"),
                    str(temp_schema),
                    "--",
                    str(cutpath),
                    "--no-warnings",
                    "--json",
                    "--strict-json",
                    "--natural-utf8",
                    "--defaults-json",
                    "--unknown-json",
                    "--raw-binary",
                    "--force-empty",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            if result.returncode != 0:
                success = False
                break

        if success:
            with open(schema_dir / f"{name}.fbs", "w") as outfile:
                outfile.write(f"// https://github.com/MooncellWiki/OpenArknightsFBS/commit/{commit_hash}\n")
                outfile.write(schema_content.stdout)
            print(f"{name} - {commit_hash}")
            break

# copy cn and yostar schemas
print("Copying reference schemas")
subprocess.run(["git", "-C", str(oafbs_dir), "checkout", "origin/main"], check=True, stdout=subprocess.DEVNULL)
cn_dir = Path("cn")
if cn_dir.exists():
    shutil.rmtree(cn_dir, onerror=_rmtree_onerror)  # pyright: ignore[reportDeprecated]
shutil.copytree(oafbs_dir / "FBS", cn_dir)

print("Done!")
