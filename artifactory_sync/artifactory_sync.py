#!/usr/bin/env python3
"""Artifactory Artifact Sync Tool.

Downloads artifacts (folders) recursively from a source Artifactory server
and uploads them to a destination Artifactory server.

Can use either the Artifactory REST API or JFrog CLI for operations.
If using JFrog CLI, ensure it is installed and configured.

Environment Variables
---------------------
SOURCE_ARTIFACTORY_USERNAME : str
    Username for source Artifactory server.
SOURCE_ARTIFACTORY_PASSWORD : str
    Password for source Artifactory server.
DEST_ARTIFACTORY_USERNAME : str
    Username for destination Artifactory server.
DEST_ARTIFACTORY_PASSWORD : str
    Password for destination Artifactory server.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

import click
import requests
from requests.auth import HTTPBasicAuth
from tqdm import tqdm


class ArtifactoryClient:
    """Client for interacting with Artifactory API."""
    
    def __init__(self, base_url: str, username: str, password: str, retries: int = 3):
        """Initialize Artifactory client.

        Parameters
        ----------
        base_url : str
            Base URL of Artifactory server.
            Example: https://artifactory.example.com/artifactory
        username : str
            Artifactory username.
        password : str
            Artifactory password.
        retries : int, optional
            Number of retry attempts for failed requests. Default is 3.
        """
        self._validate_url(base_url)
        self.base_url = base_url.rstrip('/')
        self.auth = HTTPBasicAuth(username, password)
        self.session = requests.Session()
        self.session.auth = self.auth
        self.timeout = 30  # Request timeout in seconds
        self.retries = retries
    
    @staticmethod
    def _validate_url(url: str) -> None:
        """Validate URL format.

        Parameters
        ----------
        url : str
            URL to validate.

        Raises
        ------
        ValueError
            If URL format is invalid.
        """
        try:
            result = urlparse(url)
            if not result.scheme or not result.netloc:
                raise ValueError()
        except Exception as e:
            raise ValueError(f"Invalid URL format: {url}") from e
    
    def _retry_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Execute request with exponential backoff retry.

        Parameters
        ----------
        method : str
            HTTP method (GET, PUT, etc.).
        url : str
            Request URL.
        **kwargs
            Additional arguments to pass to requests.

        Returns
        -------
        requests.Response
            Response object.

        Raises
        ------
        requests.exceptions.RequestException
            If all retries fail.
        """
        last_exception = None
        for attempt in range(self.retries):
            try:
                response = self.session.request(method, url, **kwargs)
                response.raise_for_status()
                return response
            except requests.exceptions.RequestException as e:
                last_exception = e
                if attempt < self.retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff: 1, 2, 4 seconds
                    time.sleep(wait_time)
        raise last_exception
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close session."""
        self.session.close()
        return False
    
    def list_artifacts(self, repo: str, path: str = '', verbose: bool = False) -> list[dict]:
        """List artifacts in a repository path.

        Parameters
        ----------
        repo : str
            Repository name.
        path : str, optional
            Path within repository. Defaults to root if empty.
        verbose : bool, optional
            Enable verbose logging. Default is False.

        Returns
        -------
        list[dict]
            List of artifact metadata dictionaries from Artifactory API.

        Raises
        ------
        requests.exceptions.RequestException
            If API request fails.
        """
        path = path.lstrip('/')
        url = f'{self.base_url}/api/repository/{repo}'
        if path:
            url = f'{url}/{path}'
        
        try:
            if verbose:
                click.echo(f'[LIST] Querying repository: {url}')
            
            response = self._retry_request(
                'GET',
                url,
                params={'list': '1', 'deep': '1', 'listFolders': '1'},
                timeout=self.timeout
            )
            data = response.json()
            results = data.get('results', [])
            
            if verbose:
                click.echo(f'[LIST] Found {len(results)} items')
            
            return results
        except requests.exceptions.RequestException as e:
            click.echo(f'[ERROR] Error listing artifacts: {e}', err=True)
            raise
    
    def download_file(self, repo: str, artifact_path: str, local_path: Path, verbose: bool = False) -> bool:
        """Download a single artifact from Artifactory.

        Parameters
        ----------
        repo : str
            Repository name.
        artifact_path : str
            Path to artifact in repository.
        local_path : Path
            Local path to save downloaded file.
        verbose : bool, optional
            Enable verbose logging. Default is False.

        Returns
        -------
        bool
            True if download successful, False otherwise.
        """
        artifact_path = artifact_path.lstrip('/')
        url = f'{self.base_url}/{repo}'
        if artifact_path:
            url = f'{url}/{artifact_path}'
        
        try:
            if verbose:
                click.echo(f'[DOWNLOAD] Fetching from: {url}')
            
            response = self._retry_request('GET', url, stream=True, timeout=self.timeout)
            
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
        """Upload a file to Artifactory.

        Parameters
        ----------
        repo : str
            Repository name.
        artifact_path : str
            Target path in repository.
        local_path : Path
            Local file path to upload.
        dry_run : bool, optional
            If True, simulate upload without actually uploading.
            Default is False.
        verbose : bool, optional
            Enable verbose logging. Default is False.

        Returns
        -------
        bool
            True if upload successful or would be successful in dry run,
            False otherwise.
        """
        artifact_path = artifact_path.lstrip('/')
        url = f'{self.base_url}/{repo}'
        if artifact_path:
            url = f'{url}/{artifact_path}'
        
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
                response = self._retry_request('PUT', url, data=f, timeout=self.timeout)
            
            if verbose:
                click.echo(f'[UPLOAD] Successfully uploaded: {artifact_path}')
            
            return True
        except requests.exceptions.RequestException as e:
            click.echo(f'[ERROR] Error uploading {artifact_path}: {e}', err=True)
            return False


class JFrogCLIClient:
    """Client for interacting with Artifactory using JFrog CLI."""
    
    def __init__(self, base_url: str, username: str, password: str):
        """Initialize JFrog CLI client.

        Parameters
        ----------
        base_url : str
            Base URL of Artifactory server.
        username : str
            Artifactory username.
        password : str
            Artifactory password.
        """
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
    
    def _run_command(self, command: list, verbose: bool = False, display_command: list = None) -> tuple[bool, str]:
        """Execute a jf CLI command.

        Parameters
        ----------
        command : list
            Command and arguments to execute.
        verbose : bool, optional
            Enable verbose logging. Default is False.
        display_command : list, optional
            Command to display in verbose output (e.g., without password).
            If not provided, command is used.

        Returns
        -------
        tuple[bool, str]
            Tuple of (success, output).
        """
        try:
            if verbose:
                cmd_to_display = display_command if display_command else command
                click.echo(f'[JFROG] Running: {" ".join(cmd_to_display)}')
            
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                return True, result.stdout
            else:
                error_msg = result.stderr or result.stdout
                if verbose:
                    click.echo(f'[JFROG] Error: {error_msg}', err=True)
                return False, error_msg
        except subprocess.TimeoutExpired:
            return False, "Command timed out"
        except Exception as e:
            return False, str(e)
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        return False
    
    def list_artifacts(self, repo: str, path: str = '', verbose: bool = False) -> list[dict]:
        """List artifacts in a repository path using jfrog CLI.

        Parameters
        ----------
        repo : str
            Repository name.
        path : str, optional
            Path within repository. Defaults to root if empty.
        verbose : bool, optional
            Enable verbose logging. Default is False.

        Returns
        -------
        list[dict]
            List of artifact metadata.

        Raises
        ------
        RuntimeError
            If command fails.
        """
        path = path.lstrip('/')
        pattern = f'{repo}/*' if not path else f'{repo}/{path}/*'
        
        command = [
            'jf',
            'rt',
            'search',
            pattern,
            f'--url={self.base_url}',
            f'--user={self.username}',
            f'--password={self.password}',
            '--format=json'
        ]
        
        display_command = [
            'jf',
            'rt',
            'search',
            pattern,
            f'--url={self.base_url}',
            f'--user={self.username}',
            '--password=***',
            '--format=json'
        ]
        
        success, output = self._run_command(command, verbose, display_command)
        if not success:
            raise RuntimeError(f"Failed to list artifacts: {output}")
        
        try:
            data = json.loads(output)
            results = data.get('results', [])
            
            if verbose:
                click.echo(f'[JFROG] Found {len(results)} items')
            
            return results
        except json.JSONDecodeError:
            if verbose:
                click.echo(f'[JFROG] No artifacts found or empty result')
            return []
    
    def download_file(self, repo: str, artifact_path: str, local_path: Path, verbose: bool = False) -> bool:
        """Download a single artifact using jfrog CLI.

        Parameters
        ----------
        repo : str
            Repository name.
        artifact_path : str
            Path to artifact in repository.
        local_path : Path
            Local path to save downloaded file.
        verbose : bool, optional
            Enable verbose logging. Default is False.

        Returns
        -------
        bool
            True if download successful, False otherwise.
        """
        artifact_path = artifact_path.lstrip('/')
        source_path = f'{repo}/{artifact_path}'
        
        # Create parent directories if needed
        local_path.parent.mkdir(parents=True, exist_ok=True)
        
        command = [
            'jf',
            'rt',
            'download',
            source_path,
            str(local_path),
            f'--url={self.base_url}',
            f'--user={self.username}',
            f'--password={self.password}'
        ]
        
        display_command = [
            'jf',
            'rt',
            'download',
            source_path,
            str(local_path),
            f'--url={self.base_url}',
            f'--user={self.username}',
            '--password=***'
        ]
        
        if verbose:
            click.echo(f'[JFROG] Downloading from: {source_path}')
        
        success, output = self._run_command(command, verbose, display_command)
        
        if success:
            if verbose:
                click.echo(f'[JFROG] Successfully saved to: {local_path}')
            return True
        else:
            click.echo(f'[ERROR] Error downloading {artifact_path}: {output}', err=True)
            return False
    
    def upload_file(self, repo: str, artifact_path: str, local_path: Path, dry_run: bool = False, verbose: bool = False) -> bool:
        """Upload a file using jfrog CLI.

        Parameters
        ----------
        repo : str
            Repository name.
        artifact_path : str
            Target path in repository.
        local_path : Path
            Local file path to upload.
        dry_run : bool, optional
            If True, simulate upload without actually uploading. Default is False.
        verbose : bool, optional
            Enable verbose logging. Default is False.

        Returns
        -------
        bool
            True if upload successful or would be successful in dry run, False otherwise.
        """
        artifact_path = artifact_path.lstrip('/')
        target_path = f'{repo}/{artifact_path}'
        
        try:
            file_size = local_path.stat().st_size
            
            if dry_run:
                click.echo(f'[DRY-RUN] Would upload to: {target_path} ({file_size} bytes)')
                if verbose:
                    click.echo(f'[DRY-RUN] Source file: {local_path}')
                return True
            
            if verbose:
                click.echo(f'[JFROG] Uploading to: {target_path}')
                click.echo(f'[JFROG] File size: {file_size} bytes')
            
            command = [
                'jf',
                'rt',
                'upload',
                str(local_path),
                target_path,
                f'--url={self.base_url}',
                f'--user={self.username}',
                f'--password={self.password}'
            ]
            
            display_command = [
                'jf',
                'rt',
                'upload',
                str(local_path),
                target_path,
                f'--url={self.base_url}',
                f'--user={self.username}',
                '--password=***'
            ]
            
            success, output = self._run_command(command, verbose, display_command)
            
            if success:
                if verbose:
                    click.echo(f'[JFROG] Successfully uploaded: {artifact_path}')
                return True
            else:
                click.echo(f'[ERROR] Error uploading {artifact_path}: {output}', err=True)
                return False
        except OSError as e:
            click.echo(f'[ERROR] Error uploading {artifact_path}: {e}', err=True)
            return False


def download_artifacts_recursively(
    client: ArtifactoryClient,
    repo: str,
    src_path: str,
    local_dir: Path,
    verbose: bool = False
) -> tuple[int, int]:
    """Recursively download artifacts from Artifactory.

    Parameters
    ----------
    client : ArtifactoryClient
        ArtifactoryClient instance.
    repo : str
        Repository name.
    src_path : str
        Source path in repository.
    local_dir : Path
        Local directory to save artifacts.
    verbose : bool, optional
        Enable verbose output. Default is False.

    Returns
    -------
    tuple[int, int]
        Tuple of (successful_downloads, failed_downloads).
    """
    success_count = 0
    fail_count = 0
    
    try:
        if verbose:
            src_display = src_path if src_path else '/'
            click.echo(f'[RECURSIVE] Starting download from: {repo}/{src_display}')
        
        artifacts = client.list_artifacts(repo, src_path, verbose)
        
        if not artifacts:
            if verbose:
                src_display = src_path if src_path else '/'
                click.echo(f'[RECURSIVE] No artifacts found at: {repo}/{src_display}')
            return success_count, fail_count
        
        for artifact in artifacts:
            artifact_path = artifact.get('uri', '').lstrip('/')
            
            if artifact.get('folder', False):
                # Recursively download folder
                if verbose:
                    click.echo(f'[RECURSIVE] Entering folder: {artifact_path}')
                sub_success, sub_fail = download_artifacts_recursively(
                    client, repo, artifact_path, local_dir, verbose
                )
                success_count += sub_success
                fail_count += sub_fail
            else:
                # Download file
                local_file = local_dir / artifact_path
                if verbose:
                    click.echo(f'[FILE] Processing file: {artifact_path}')
                
                if client.download_file(repo, artifact_path, local_file, verbose):
                    success_count += 1
                    if verbose:
                        click.echo(f'[SUCCESS] File downloaded: {artifact_path}')
                else:
                    fail_count += 1
    except (requests.exceptions.RequestException, OSError) as e:
        click.echo(f'[ERROR] Error during recursive download: {e}', err=True)
    
    if verbose:
        src_display = src_path if src_path else '/'
        click.echo(f'[RECURSIVE] Download complete from: {repo}/{src_display} (Success: {success_count}, Failed: {fail_count})')
    
    return success_count, fail_count


def upload_artifacts_recursively(
    client: ArtifactoryClient,
    repo: str,
    dest_path: str,
    local_dir: Path,
    dry_run: bool = False,
    verbose: bool = False,
    overwrite: bool = True
) -> tuple[int, int]:
    """Recursively upload artifacts to Artifactory.

    Parameters
    ----------
    client : ArtifactoryClient
        ArtifactoryClient instance.
    repo : str
        Repository name.
    dest_path : str
        Destination path in repository.
    local_dir : Path
        Local directory containing artifacts.
    dry_run : bool, optional
        If True, simulate uploads without actually uploading.
        Default is False.
    verbose : bool, optional
        Enable verbose output. Default is False.
    overwrite : bool, optional
        If True, overwrite existing files. Default is True.

    Returns
    -------
    tuple[int, int]
        Tuple of (successful_uploads, failed_uploads).
    """
    success_count = 0
    fail_count = 0
    dest_path = dest_path.rstrip('/')
    
    if verbose:
        mode = "DRY-RUN" if dry_run else "UPLOAD"
        dest_display = dest_path if dest_path else '/'
        click.echo(f'[{mode}] Starting {mode.lower()} to: {repo}/{dest_display}')
    
    # Use generator for memory efficiency with large repos
    def file_generator():
        """Generate all files in directory."""
        return (f for f in local_dir.rglob('*') if f.is_file())
    
    files_list = list(file_generator())
    total_files = len(files_list)
    
    if verbose:
        click.echo(f'[COUNT] Found {total_files} files to process')
    
    # Use tqdm for progress bar (always show unless very quiet mode)
    with tqdm(files_list, disable=dry_run or verbose, desc='Uploading', unit='file') as pbar:
        for local_file in pbar:
            # Calculate relative path and target artifact path
            rel_path = local_file.relative_to(local_dir)
            rel_path_str = str(rel_path).replace('\\', '/')
            
            # Construct artifact path, handling empty dest_path
            if dest_path:
                artifact_path = f'{dest_path}/{rel_path_str}'
            else:
                artifact_path = rel_path_str
            
            if verbose:
                click.echo(f'[PROGRESS] Processing: {artifact_path}')
            
            if client.upload_file(repo, artifact_path, local_file, dry_run, verbose):
                success_count += 1
                if verbose and not dry_run:
                    click.echo(f'[SUCCESS] File uploaded: {artifact_path}')
                elif verbose and dry_run:
                    click.echo(f'[DRY-RUN] Would upload: {artifact_path}')
            else:
                fail_count += 1
                click.echo(f'[FAILED] Could not upload: {artifact_path}', err=True)
    
    mode = "DRY-RUN" if dry_run else "UPLOAD"
    dest_display = dest_path if dest_path else '/'
    if verbose:
        click.echo(f'[{mode}] {mode} complete to: {repo}/{dest_display} (Success: {success_count}, Failed: {fail_count})')
    
    return success_count, fail_count


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
@click.option(
    '--overwrite',
    is_flag=True,
    default=True,
    help='Overwrite existing files in destination (default: True)'
)
@click.option(
    '--validate',
    is_flag=True,
    help='Validate connectivity to both Artifactory servers before syncing'
)
@click.option(
    '--use-jfrog-cli',
    is_flag=True,
    help='Use JFrog CLI for Artifactory operations instead of REST API'
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
    keep_temp: bool,
    overwrite: bool,
    validate: bool,
    use_jfrog_cli: bool
):
    """Sync artifacts from source Artifactory to destination Artifactory.

    Environment variables (required):
        SOURCE_ARTIFACTORY_USERNAME : str
            Username for source Artifactory server.
        SOURCE_ARTIFACTORY_PASSWORD : str
            Password for source Artifactory server.
        DEST_ARTIFACTORY_USERNAME : str
            Username for destination Artifactory server.
        DEST_ARTIFACTORY_PASSWORD : str
            Password for destination Artifactory server.
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
        
        client_type = 'JFrog CLI' if use_jfrog_cli else 'REST API'
        if verbose:
            click.echo(f'[CONFIG] Client type: {client_type}')
            click.echo(f'[CONFIG] Source: {source_url}/{source_repo}/{source_path}')
            click.echo(f'[CONFIG] Destination: {dest_url}/{dest_repo}/{dest_path}')
            click.echo(f'[CONFIG] Dry Run: {dry_run}')
            click.echo(f'[CONFIG] Overwrite: {overwrite}')
        
        click.echo(f'Initializing Artifactory clients ({client_type})...')
        
        # Create appropriate client type
        if use_jfrog_cli:
            source_client_obj = JFrogCLIClient(source_url, source_username, source_password)
            dest_client_obj = JFrogCLIClient(dest_url, dest_username, dest_password)
        else:
            source_client_obj = ArtifactoryClient(source_url, source_username, source_password)
            dest_client_obj = ArtifactoryClient(dest_url, dest_username, dest_password)
        
        with source_client_obj as source_client, dest_client_obj as dest_client:
            
            if verbose:
                click.echo('[CLIENT] Source client initialized')
                click.echo('[CLIENT] Destination client initialized')
            
            # Validate connectivity if requested
            if validate:
                click.echo('Validating connectivity to source...')
                try:
                    source_client.list_artifacts(source_repo, '', verbose=False)
                    click.echo('✓ Source connectivity validated')
                except Exception as e:
                    click.echo(f'✗ Source connection failed: {e}', err=True)
                    sys.exit(1)
                
                click.echo('Validating connectivity to destination...')
                try:
                    dest_client.list_artifacts(dest_repo, '', verbose=False)
                    click.echo('✓ Destination connectivity validated')
                except Exception as e:
                    click.echo(f'✗ Destination connection failed: {e}', err=True)
                    sys.exit(1)
            
            # Create temporary directory for downloads
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                
                if verbose:
                    click.echo(f'[TEMP] Temporary directory created: {temp_path}')
                
                # Download from source
                click.echo('-' * 60)
                src_display = source_path if source_path else '/'
                click.echo(f'Downloading artifacts from {source_repo}{src_display}...')
                click.echo('-' * 60)
                
                download_success, download_fail = download_artifacts_recursively(
                    source_client,
                    source_repo,
                    source_path,
                    temp_path,
                    verbose
                )
                total_downloaded = download_success + download_fail
                click.echo(f'✓ Downloaded {download_success}/{total_downloaded} artifacts')
                if download_fail > 0:
                    click.echo(f'⚠ {download_fail} downloads failed', err=True)
                
                # Upload to destination
                click.echo('-' * 60)
                dest_display = dest_path if dest_path else '/'
                mode = "DRY-RUN: Simulating upload" if dry_run else f'Uploading artifacts to {dest_repo}{dest_display}'
                click.echo(mode + '...')
                click.echo('-' * 60)
                
                upload_success, upload_fail = upload_artifacts_recursively(
                    dest_client,
                    dest_repo,
                    dest_path,
                    temp_path,
                    dry_run,
                    verbose,
                    overwrite
                )
                total_uploaded = upload_success + upload_fail
                
                if dry_run:
                    click.echo(f'✓ DRY-RUN: Would upload {upload_success}/{total_uploaded} artifacts')
                else:
                    click.echo(f'✓ Uploaded {upload_success}/{total_uploaded} artifacts')
                if upload_fail > 0:
                    click.echo(f'⚠ {upload_fail} uploads failed', err=True)
                
                # Keep temp directory if requested
                if keep_temp:
                    keep_dir = Path.cwd() / 'artifactory_temp'
                    shutil.copytree(temp_path, keep_dir, dirs_exist_ok=True)
                    click.echo(f'[TEMP] Temporary files kept in: {keep_dir}')
        
        click.echo('-' * 60)
        click.echo('✓ Sync completed successfully')
        click.echo('=' * 60)
    
    except (requests.exceptions.RequestException, OSError) as e:
        click.echo(f'[ERROR] {e}', err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo('\n[ERROR] Operation cancelled by user', err=True)
        sys.exit(1)


if __name__ == '__main__':
    sync_artifacts()
