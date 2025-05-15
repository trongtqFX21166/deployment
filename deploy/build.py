#!/usr/bin/env python3
import json
import os
import sys
import subprocess
from pathlib import Path
from typing import List, Tuple

def run_command(cmd: List[str], cwd: str = None) -> Tuple[bool, str]:
    """Run a shell command and return success status and output."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            check=True,
            text=True,
            capture_output=True
        )
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        return False, e.stderr

def update_yaml_files(repo: str, env: str, yaml_files: List[str], image_tag: str, version: str):
    """Update the image version in yaml files using yq."""
    for yaml_file in yaml_files:
        yaml_file = yaml_file.strip()
        yaml_path = f"../../{repo}/Deployment/{env}/k8s/{yaml_file}"
        image_value = f"vmapi/vml-s2:{image_tag}.{version}"
        cmd = [
            "yq", "-i",
            f'(select(.kind == "Deployment") | .spec.template.spec.containers[] | .image) |="{image_value}"',
            yaml_path
        ]
        success, output = run_command(cmd)
        if not success:
            print(f"Failed to update yaml file {yaml_file}: {output}")
            sys.exit(1)

def main():
    if len(sys.argv) != 4:
        print("Usage: python build.py <ENV> <BUILD_MODE> <REPO>")
        sys.exit(1)

    env = sys.argv[1]
    build_mode = sys.argv[2]
    repo = sys.argv[3]
    original_path = os.getcwd()

    print(f"Start build {env} {build_mode} {original_path}")

    # Read config
    config_file = f"../../{repo}/Deployment/{env}/build.config.json"
    try:
        with open(config_file) as f:
            config = json.load(f)
    except Exception as e:
        print(f"Failed to read config file: {e}")
        sys.exit(1)

    for index, item in enumerate(config):
        print("#" * 80)
        print(f"*************Start build at {index}")
        print("*************Read build config")

        path = item['path']
        version = item['version']
        yaml_files = item['yaml'].split('|')
        image_tag = item['app']

        print(f"{image_tag} {version} {yaml_files} {path}")

        print("*************valid config")
        if not os.path.isdir(path):
            print(f"{path} not existed")
            sys.exit(1)

        print("*************read app config")
        app_setting_path = os.path.join(path, "appsettings.json")
        if env in ["Staging", "Dev"]:
            app_setting_path = os.path.join(path, f"appsettings.{env}.json")

        try:
            with open(app_setting_path) as f:
                app_config = json.load(f)
                app_version = app_config.get("Deployment", {}).get("Version")
        except Exception as e:
            print(f"Failed to read app config: {e}")
            sys.exit(1)

        if app_version is None:
            print(f" {image_tag} missing config deployment version ")
            continue

        print(f"app version {app_version}")
        print("*************update config ver from app ver")
        version = str(app_version)
        config[index]['version'] = version

        try:
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            print(f"Failed to update config file: {e}")
            sys.exit(1)

        print(f"begin build {image_tag}")
        print("************* Run build")
        os.chdir(path)
        print(f"current path {os.getcwd()}")

        print(f"run command bash build.sh {image_tag} {version}")
        success, output = run_command(['bash', 'build.sh', image_tag, version, build_mode])
        if not success:
            print(f"Build failed: {output}")
            sys.exit(1)

        print(f"change original path {path}")
        os.chdir(original_path)
        print(f"current path {os.getcwd()}")

        if build_mode == "CI":
            continue

        print("************* Update version yaml file")
        update_yaml_files(repo, env, yaml_files, image_tag, version)

        print(f"end build {image_tag}")
        print("#" * 80)

    if build_mode == "CI":
        sys.exit(0)

    # Git operations
    commit_msg = " ".join([f"{item['app']}::{item['version']}" for item in config])
    
    git_commands = [
        ['git', 'add', f'{env}/build.config.json'],
        ['git', 'add', f'{env}/k8s/*.yaml'],
        ['git', 'commit', '-m', commit_msg],
        ['git', 'push']
    ]

    os.chdir(original_path)
    print(f"Git operations current path {os.getcwd()}")
    for cmd in git_commands:
        success, output = run_command(cmd)
        if not success:
            print(f"Git operation failed: {output}")
            sys.exit(1)

if __name__ == "__main__":
    main()