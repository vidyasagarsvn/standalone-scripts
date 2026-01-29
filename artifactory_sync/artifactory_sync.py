#!/usr/bin/env python3
"""
Artifactory Artifact Sync Tool

Downloads artifacts (folders) recursively from a source Artifactory server
and uploads them to a destination Artifactory server.

Credentials are retrieved from environment variables:
- SOURCE_ARTIFACTORY_USERNAME
- SOURCE_ARTIFACTORY_PASSWORD
- DEST_ARTIFACTORY_USERNAME
- DEST_ARTIFACTORY_PASSWORD
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Dict, List
import click
import requests
from requests.auth import HTTPBasicAuth
from urllib.parse import urljoin, urlparse


class ArtifactoryClient:
    """Client for interacting with Artifactory API."""
    
    def __init__(self, base_url: str, username: str, password: str):
        """
        Initialize Artifactory client.
        
        Args:
            base_url: Base URL of Artifactory server (e.g., https://artifactory.example.com/artifactory)
            username: Artifactory username
            password: Artifactory password
        """
        self.base_url = base_url.rstrip('/')
        self.auth = HTTPBasicAuth(username, password)
        self.session = requests.Session()
        self.session.auth = self.auth
    
    def _ensure_url_format(self, url: str) -> str:
        """Ensure URL has proper format."""
        if not url.startswith(('http://', 'https://')):
            url = f'https://{url}'
        return url
    
    def list_artifacts(self, repo: str, path: str = '', verbose: bool = False) -> List[Dict]:
        """
        List artifacts in a repository path.
        
        Args:
            repo: Repository name
            path: Path within repository (optional)
            verbose: Enable verbose logging
            
        Returns:
            List of artifact metadata dictionaries
        """
        path = path.lstrip('/')
        url = f'{self.base_url}/api/repository/{repo}/{path}'
        
        try:
            if verbose:
                click.echo(f'[LIST] Querying repository: {url}')
            
            response = self.session.get(url, params={'list': '1', 'deep': '1', 'listFolders': '1'})
            response.raise_for_status()
            data = response.json()
            results = data.get('results', [])
            
            if verbose:
                click.echo(f'[LIST] Found {len(results)} items')
            
            return results
        except requests.exceptions.RequestException as e:
            click.echo(f'[ERROR] Error listing artifacts: {e}', err=True)
            raise
    
    def download_file(self, repo: str, artifact_path: str, local_path: Path, verbose: bool = False) -> bool:
        """
        Download a single artifact from Artifactory.
        
        Args:
            repo: Repository name
            artifact_path: Path to artifact in repository
            local_path: Local path to save file
            verbose: Enable verbose logging
            
        Returns:
            True if successful, False otherwise
        """
        artifact_path = artifact_path.lstrip('/')
        url = f'{self.base_url}/{repo}/{artifact_path}'
        
        try:
            if verbose:
                click.echo(f'[DOWNLOAD] Fetching from: {url}')
            
            response = self.session.get(url, stream=True)
            response.raise_for_status()
            
            # Create parent directories if needed
            local_path.parent.mkdir(parents=True, exist_ok=True)
            
            if verbose:
                content_length = response.headers.get('content-length', 'unknown')
                click.echo(f'[DOWNLOAD] File size: {content_length} bytes')
            
            # Download file
            bytes_written = 0
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        bytes_written += len(chunk)
            
            if verbose:
                click.echo(f'[DOWNLOAD] Successfully saved to: {local_path} ({bytes_written} bytes)')
            
            return True
        except requests.exceptions.RequestException as e:
            click.echo(f'[ERROR] Error downloading {artifact_path}: {e}', err=True)
            return False
    
    def upload_file(self, repo: str, artifact_path: str, local_path: Path, dry_run: bool = False, verbose: bool = False) -> bool:
        """
        Upload a file to Artifactory.
        
        Args:
            repo: Repository name
            artifact_path: Target path in repository
            local_path: Local file path to upload
            dry_run: If True, simulate upload without actually uploading
            verbose: Enable verbose logging
            
        Returns:
            True if successful (or would be successful in dry run), False otherwise
        """
        artifact_path = artifact_path.lstrip('/')
        url = f'{self.base_url}/{repo}/{artifact_path}'
        
        try:
            if dry_run:
                file_size = local_path.stat().st_size
                click.echo(f'[DRY-RUN] Would upload to: {url} ({file_size} bytes)')
                if verbose:
                    click.echo(f'[DRY-RUN] Source file: {local_path}')
                return True
            
            file_size = local_path.stat().st_size
            if verbose:
                click.echo(f'[UPLOAD] Uploading to: {url}')
                click.echo(f'[UPLOAD] File size: {file_size} bytes')
            
            with open(local_path, 'rb') as f:
                response = self.session.put(url, data=f)
            
            response.raise_for_status()
            
            if verbose:
                click.echo(f'[UPLOAD] Successfully uploaded: {artifact_path}')
            
            return True
        except requests.exceptions.RequestException as e:
            click.echo(f'[ERROR] Error uploading {artifact_path}: {e}', err=True)
            return False


def download_artifacts_recursively(
    client: ArtifactoryClient,
    repo: str,
    src_path: str,
    local_dir: Path,
    verbose: bool = False
) -> int:
    """
    Recursively download artifacts from Artifactory.
    
    Args:
        client: ArtifactoryClient instance
        repo: Repository name
        src_path: Source path in repository
        local_dir: Local directory to save artifacts
        verbose: Enable verbose output
        
    Returns:
        Number of files downloaded
    """
    count = 0
    
    try:
        if verbose:
            click.echo(f'[RECURSIVE] Starting download from: {repo}/{src_path}')
        
        artifacts = client.list_artifacts(repo, src_path, verbose)
        
        for artifact in artifacts:
            artifact_path = artifact.get('uri', '').lstrip('/')
            
            if artifact.get('folder', False):
                # Recursively download folder
                if verbose:
                    click.echo(f'[RECURSIVE] Entering folder: {artifact_path}')
                count += download_artifacts_recursively(
                    client, repo, artifact_path, local_dir, verbose
                )
            else:
                # Download file
                local_file = local_dir / artifact_path
                if verbose:
                    click.echo(f'[FILE] Processing file: {artifact_path}')
                
                if client.download_file(repo, artifact_path, local_file, verbose):
                    count += 1
                    if verbose:
                        click.echo(f'[SUCCESS] File downloaded: {artifact_path}')
    except Exception as e:
        click.echo(f'[ERROR] Error during recursive download: {e}', err=True)
        raise
    
    if verbose:
        click.echo(f'[RECURSIVE] Download complete from: {repo}/{src_path} (Total: {count} files)')
    
    return count


def upload_artifacts_recursively(
    client: ArtifactoryClient,
    repo: str,
    dest_path: str,
    local_dir: Path,
    dry_run: bool = False,
    verbose: bool = False
) -> int:
    """
    Recursively upload artifacts to Artifactory.
    
    Args:
        client: ArtifactoryClient instance
        repo: Repository name
        dest_path: Destination path in repository
        local_dir: Local directory containing artifacts
        dry_run: If True, simulate uploads without actually uploading
        verbose: Enable verbose output
        
    Returns:
        Number of files uploaded (or would be uploaded in dry run)
    """
    count = 0
    dest_path = dest_path.rstrip('/')
    
    if verbose:
        mode = "DRY-RUN" if dry_run else "UPLOAD"
        click.echo(f'[{mode}] Starting {mode.lower()} to: {repo}/{dest_path}')
    
    files_list = list(local_dir.rglob('*'))
    total_files = len([f for f in files_list if f.is_file()])
    
    if verbose:
        click.echo(f'[COUNT] Found {total_files} files to process')
    
    for idx, local_file in enumerate(local_dir.rglob('*'), 1):
        if local_file.is_file():
            # Calculate relative path and target artifact path
            rel_path = local_file.relative_to(local_dir)
            artifact_path = f'{dest_path}/{rel_path}'.replace('\\', '/')
            
            if verbose:
                click.echo(f'[PROGRESS] [{idx}/{total_files}] Processing: {artifact_path}')
            
            if client.upload_file(repo, artifact_path, local_file, dry_run, verbose):
                count += 1
                if verbose and not dry_run:
                    click.echo(f'[SUCCESS] File uploaded: {artifact_path}')
                elif verbose and dry_run:
                    click.echo(f'[DRY-RUN] Would upload: {artifact_path}')
    
    mode = "DRY-RUN" if dry_run else "UPLOAD"
    if verbose:
        click.echo(f'[{mode}] {mode} complete to: {repo}/{dest_path} (Total: {count} files)')
    
    return count


@click.command()
@click.option(
    '--source-url',
    required=True,
    help='Source Artifactory base URL (e.g., https://artifactory.example.com/artifactory)'
)
@click.option(
    '--source-repo',
    required=True,
    help='Source Artifactory repository name'
)
@click.option(
    '--source-path',
    default='',
    help='Source path within repository (default: root)'
)
@click.option(
    '--dest-url',
    required=True,
    help='Destination Artifactory base URL'
)
@click.option(
    '--dest-repo',
    required=True,
    help='Destination Artifactory repository name'
)
@click.option(
    '--dest-path',
    default='',
    help='Destination path within repository (default: root)'
)
@click.option(
    '--verbose',
    is_flag=True,
    help='Enable verbose output'
)
@click.option(
    '--dry-run',
    is_flag=True,
    help='Perform a dry run of the upload (download still happens, upload is simulated)'
)
@click.option(
    '--keep-temp',
    is_flag=True,
    help='Keep temporary directory after sync (for debugging)'
)
def sync_artifacts(
    source_url: str,
    source_repo: str,
    source_path: str,
    dest_url: str,
    dest_repo: str,
    dest_path: str,
    verbose: bool,
    dry_run: bool,
    keep_temp: bool
):
    """
    Sync artifacts from source Artifactory to destination Artifactory.
    
    Credentials are read from environment variables:
    - SOURCE_ARTIFACTORY_USERNAME
    - SOURCE_ARTIFACTORY_PASSWORD
    - DEST_ARTIFACTORY_USERNAME
    - DEST_ARTIFACTORY_PASSWORD
    """
    
    # Validate environment variables
    source_username = os.getenv('SOURCE_ARTIFACTORY_USERNAME')
    source_password = os.getenv('SOURCE_ARTIFACTORY_PASSWORD')
    dest_username = os.getenv('DEST_ARTIFACTORY_USERNAME')
    dest_password = os.getenv('DEST_ARTIFACTORY_PASSWORD')
    
    if not source_username or not source_password:
        click.echo(
            'Error: SOURCE_ARTIFACTORY_USERNAME and SOURCE_ARTIFACTORY_PASSWORD '
            'environment variables are required',
            err=True
        )
        sys.exit(1)
    
    if not dest_username or not dest_password:
        click.echo(
            'Error: DEST_ARTIFACTORY_USERNAME and DEST_ARTIFACTORY_PASSWORD '
            'environment variables are required',
            err=True
        )
        sys.exit(1)
    
    try:
        # Initialize clients
        click.echo('=' * 60)
        click.echo('Artifactory Sync Tool')
        click.echo('=' * 60)
        
        if verbose:
            click.echo(f'[CONFIG] Source: {source_url}/{source_repo}/{source_path}')
            click.echo(f'[CONFIG] Destination: {dest_url}/{dest_repo}/{dest_path}')
            click.echo(f'[CONFIG] Dry Run: {dry_run}')
        
        click.echo('Initializing Artifactory clients...')
        source_client = ArtifactoryClient(source_url, source_username, source_password)
        dest_client = ArtifactoryClient(dest_url, dest_username, dest_password)
        
        if verbose:
            click.echo('[CLIENT] Source client initialized')
            click.echo('[CLIENT] Destination client initialized')
        
        # Create temporary directory for downloads
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            if verbose:
                click.echo(f'[TEMP] Temporary directory created: {temp_path}')
            
            # Download from source
            click.echo('-' * 60)
            click.echo(f'Downloading artifacts from {source_repo}{source_path or "/"}...')
            click.echo('-' * 60)
            
            download_count = download_artifacts_recursively(
                source_client,
                source_repo,
                source_path,
                temp_path,
                verbose
            )
            click.echo(f'✓ Downloaded {download_count} artifacts')
            
            # Upload to destination
            click.echo('-' * 60)
            mode = "DRY-RUN: Simulating upload" if dry_run else f'Uploading artifacts to {dest_repo}{dest_path or "/"}'
            click.echo(mode + '...')
            click.echo('-' * 60)
            
            upload_count = upload_artifacts_recursively(
                dest_client,
                dest_repo,
                dest_path,
                temp_path,
                dry_run,
                verbose
            )
            
            if dry_run:
                click.echo(f'✓ DRY-RUN: Would upload {upload_count} artifacts')
            else:
                click.echo(f'✓ Uploaded {upload_count} artifacts')
            
            # Keep temp directory if requested
            if keep_temp:
                keep_dir = Path.cwd() / 'artifactory_temp'
                shutil.copytree(temp_path, keep_dir, dirs_exist_ok=True)
                click.echo(f'[TEMP] Temporary files kept in: {keep_dir}')
        
        click.echo('-' * 60)
        click.echo('✓ Sync completed successfully')
        click.echo('=' * 60)
    
    except Exception as e:
        click.echo(f'[ERROR] {e}', err=True)
        sys.exit(1)


if __name__ == '__main__':
    sync_artifacts()
