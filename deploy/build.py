#!/usr/bin/env python3
import json
import os
import sys
import subprocess
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional

# Constants
REGISTRY_URL = "vmapi/hubcentral"

def run_command(cmd: List[str], cwd: str = None) -> Tuple[bool, str]:
    """Run a shell command and return success status and output."""
    try:
        print(f"Running command: {' '.join(cmd)}")
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

def load_config(config_path: str) -> List[Dict[str, Any]]:
    """Load configuration from JSON file."""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()
            return json.loads(content)
    except json.JSONDecodeError as e:
        print(f"JSON Error: {e}")
        print(f"JSON Error position: Line {e.lineno}, Column {e.colno}, Position {e.pos}")
        sys.exit(1)
    except Exception as e:
        print(f"Failed to read config file: {e}")
        sys.exit(1)

def save_config(config_path: str, config: List[Dict[str, Any]]) -> None:
    """Save configuration to JSON file."""
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"Failed to update config file: {e}")
        sys.exit(1)

def get_app_version(app_setting_path: str) -> Optional[str]:
    """Get application version from appsettings.json."""
    try:
        with open(app_setting_path, 'r', encoding='utf-8') as f:
            app_config = json.load(f)
            return app_config.get("Deployment", {}).get("Version")
    except Exception as e:
        print(f"Failed to read app config: {e}")
        return None

def build_activity_api(path: str, image_tag: str, version: str, build_mode: str) -> bool:
    """Build Activity API and create Docker image using dotnet commands directly."""
    os.chdir(path)
    print(f"Building Activity API at {os.getcwd()}")
    
    # Get project file name
    project_files = [f for f in os.listdir('.') if f.endswith('.csproj')]
    if not project_files:
        print("Error: No .csproj file found in the directory")
        return False
    
    project_file = project_files[0]
    project_name = os.path.splitext(project_file)[0]
    print(f"Project file: {project_file}, Project name: {project_name}")
    
    # Create release folders
    release_folder = f"bin/release/{project_name}"
    release_app_folder = f"{release_folder}/app"
    
    # Remove existing release folder if it exists
    if os.path.exists(release_folder):
        print(f"Removing existing release folder: {release_folder}")
        import shutil
        shutil.rmtree(release_folder)
    
    # Create release folders
    os.makedirs(release_app_folder, exist_ok=True)
    
    # Run dotnet publish
    print("Running dotnet publish...")
    dotnet_cmd = ['dotnet', 'publish', project_file, '-c', 'release', '-o', f'./{release_app_folder}']
    success, output = run_command(dotnet_cmd)
    
    if not success:
        print(f"Dotnet publish failed: {output}")
        return False
    
    # Check if build produced output
    if not os.path.exists(release_app_folder) or not os.listdir(release_app_folder):
        print(f"Build completed but no output found in {release_app_folder}")
        return False
    
    # Create Dockerfile
    print("Creating Dockerfile...")
    dockerfile_path = os.path.join(release_folder, "Dockerfile")
    dockerfile_content = f"""
FROM mcr.microsoft.com/dotnet/aspnet:8.0 AS runtime
WORKDIR /app
COPY /app ./
ENTRYPOINT ["dotnet", "{project_name}.dll"]
"""
    
    with open(dockerfile_path, 'w') as f:
        f.write(dockerfile_content)
    
    print(f"Created Dockerfile at {dockerfile_path}")
    
    # Convert image tag to lowercase for Docker
    lowercase_image_tag = image_tag.lower()
    
    # In CI mode, skip Docker build
    if build_mode == "CI":
        print(f"CI mode - skipping Docker build for {lowercase_image_tag}")
        return True
    
    # Build Docker image
    print(f"Building Docker image {lowercase_image_tag}.{version}...")
    docker_build_cmd = ['docker', 'build', '-f', dockerfile_path, '-t', f'{lowercase_image_tag}.{version}', f'{release_folder}/.']
    success, output = run_command(docker_build_cmd)
    
    if not success:
        print(f"Docker build failed: {output}")
        return False
    
    # Tag Docker image
    docker_tag_cmd = ['docker', 'tag', f'{lowercase_image_tag}.{version}', f'vmapi/hubcentral:{lowercase_image_tag}.{version}']
    success, output = run_command(docker_tag_cmd)
    
    if not success:
        print(f"Docker tag failed: {output}")
        return False
    
    # Push Docker image
    docker_push_cmd = ['docker', 'push', f'vmapi/hubcentral:{lowercase_image_tag}.{version}']
    success, output = run_command(docker_push_cmd)
    
    if not success:
        print(f"Docker push failed: {output}")
        return False
    
    print(f"Successfully built and pushed {lowercase_image_tag}:{version}")
    return True

def update_yaml_files(env: str, yaml_files: List[str], image_tag: str, version: str) -> bool:
    """Update the image version in yaml files using yq."""
    for yaml_file in yaml_files:
        yaml_file = yaml_file.strip()
        yaml_path = Path(f"app/activity/{env.lower()}/{yaml_file}")
        
        if not yaml_path.exists():
            print(f"Warning: YAML file {yaml_path} does not exist, skipping")
            continue
            
        image_value = f"{REGISTRY_URL}:{image_tag}.{version}"
        cmd = [
            "yq", "-i",
            f'(select(.kind == "Deployment") | .spec.template.spec.containers[] | .image) = "{image_value}"',
            str(yaml_path)
        ]
        
        success, output = run_command(cmd)
        if not success:
            print(f"Failed to update yaml file {yaml_file}: {output}")
            return False
            
    return True

def commit_changes(env: str, config: List[Dict[str, Any]]) -> bool:
    """Commit and push changes to Git."""
    commit_msg = " ".join([f"{item['app']}::{item.get('version', '1.0.0')}" for item in config])
    
    git_commands = [
        ['git', 'add', f'app/activity/{env.lower()}/build.config.json'],
        ['git', 'add', f'app/activity/{env.lower()}/*.yaml'],
        ['git', 'commit', '-m', f"Update activity {env} deployments: {commit_msg}"],
        ['git', 'push']
    ]

    for cmd in git_commands:
        success, output = run_command(cmd)
        if not success:
            print(f"Git operation failed: {output}")
            return False
    
    return True

def main():
    """Main function to build and deploy the Activity API."""
    if len(sys.argv) != 4:
        print("Usage: python build.py <ENV> <BUILD_MODE> <REPO>")
        sys.exit(1)

    env = sys.argv[1]  # dev, prod
    build_mode = sys.argv[2]  # CI, CICD
    repo = sys.argv[3]  # activity
    
    original_path = os.getcwd()
    print(f"Starting build process for {repo} in {env} environment with mode {build_mode}")
    print(f"Current directory: {original_path}")

    # Read configuration file
    config_path = Path(f"app/activity/{env.lower()}/build.config.json")
    if not config_path.exists():
        print(f"Error: Configuration file not found at {config_path.absolute()}")
        sys.exit(1)
    
    config = load_config(str(config_path))
    print(f"Successfully loaded config with {len(config)} items")

    build_results = []
    
    # Process each item in configuration
    for index, item in enumerate(config):
        print("\n" + "#" * 80)
        print(f"Building item {index+1}: {item['app']}")
        
        # Extract configuration values
        path = item['path']
        old_version = item.get('version', '1.0.0')
        yaml_files = item['yaml'].split('|') if '|' in item['yaml'] else [item['yaml']]
        image_tag = item['app']

        # Convert relative path to absolute
        if not os.path.isabs(path):
            path = os.path.normpath(os.path.join(original_path, path))
        
        # Verify path exists
        if not os.path.isdir(path):
            print(f"Error: Path {path} does not exist")
            continue

        # Get application version from appsettings
        app_setting_path = os.path.join(path, "appsettings.json")
        if env.lower() in ["staging", "dev"]:
            env_setting_path = os.path.join(path, f"appsettings.{env.title()}.json")
            if os.path.exists(env_setting_path):
                app_setting_path = env_setting_path

        print(f"Reading version from: {app_setting_path}")
        app_version = get_app_version(app_setting_path)
        if app_version is None:
            print(f"Warning: {image_tag} is missing deployment version config, using {old_version}")
            app_version = old_version
        else:
            print(f"Found application version: {app_version}")
            
        # Set new version
        version = str(app_version)
        
        # Skip build if version hasn't changed
        if old_version == version:
            print(f"Version {version} unchanged - skipping build for {image_tag}")
            build_results.append(True)
            continue
            
        print(f"Version changed from {old_version} to {version} - building {image_tag}")
        
        # Build the application
        if not build_activity_api(path, image_tag, version, build_mode):
            print(f"Failed to build {image_tag}")
            build_results.append(False)
            continue
        
        # Return to original directory
        os.chdir(original_path)
        
        # Update configuration with new version after successful build
        config[index]['version'] = version
        save_config(str(config_path), config)
        print(f"Updated build.config.json with new version {version} for {image_tag}")
        
        build_results.append(True)
        print(f"Successfully processed {image_tag}")
        print("#" * 80)

    # Check if any build failed
    if False in build_results:
        print("One or more builds failed")
        sys.exit(1)
        
    print("\nAll operations completed successfully")
    sys.exit(0)

if __name__ == "__main__":
    main()