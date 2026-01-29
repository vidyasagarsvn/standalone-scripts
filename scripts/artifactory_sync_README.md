# Artifactory Sync Tool

A standalone Python script that recursively downloads artifacts from a source Artifactory server and uploads them to a destination Artifactory server.

## Features

- **Recursive artifact transfer**: Downloads entire folder structures from source to destination
- **Credential management**: Credentials retrieved from environment variables (never hardcoded)
- **CLI parameters**: Command-line interface for flexible configuration
- **Verbose logging**: Optional verbose mode for detailed operation tracking
- **Error handling**: Robust error handling and reporting
- **Efficient**: Uses temporary directory for intermediate storage

## Requirements

- Python 3.7+
- `click` - Modern CLI framework
- `requests` - HTTP library for API calls

## Installation

1. Install dependencies:
```bash
pip install -r artifactory_requirements.txt
```

## Usage

### Set Environment Variables

Before running the script, set the required credentials:

```bash
export SOURCE_ARTIFACTORY_USERNAME="your_source_username"
export SOURCE_ARTIFACTORY_PASSWORD="your_source_password"
export DEST_ARTIFACTORY_USERNAME="your_dest_username"
export DEST_ARTIFACTORY_PASSWORD="your_dest_password"
```

### Basic Usage

```bash
python artifactory_sync.py \
    --source-url https://source-artifactory.example.com/artifactory \
    --source-repo my-repo \
    --source-path my/folder/path \
    --dest-url https://dest-artifactory.example.com/artifactory \
    --dest-repo destination-repo \
    --dest-path target/folder/path
```

### Command-Line Options

- `--source-url` (required): Source Artifactory base URL
- `--source-repo` (required): Source repository name
- `--source-path` (optional): Source path within repository (default: root)
- `--dest-url` (required): Destination Artifactory base URL
- `--dest-repo` (required): Destination repository name
- `--dest-path` (optional): Destination path within repository (default: root)
- `--verbose`: Enable verbose output with detailed logging for every operation
- `--dry-run`: Perform a dry run of the upload (download still happens, upload is simulated)
- `--keep-temp`: Keep temporary directory after sync (for debugging)
- `--help`: Show help message

### Examples

#### Sync entire repository
```bash
python artifactory_sync.py \
    --source-url https://artifactory.example.com/artifactory \
    --source-repo my-releases \
    --dest-url https://backup-artifactory.example.com/artifactory \
    --dest-repo my-releases-backup
```

#### Sync specific folder with verbose output
```bash
python artifactory_sync.py \
    --source-url https://artifactory.example.com/artifactory \
    --source-repo releases \
    --source-path apps/myapp/1.0 \
    --dest-url https://backup.example.com/artifactory \
    --dest-repo releases \
    --dest-path apps/myapp/1.0 \
    --verbose
```

#### Dry-run test before actual upload
```bash
python artifactory_sync.py \
    --source-url https://artifactory.example.com/artifactory \
    --source-repo my-repo \
    --dest-url https://backup.example.com/artifactory \
    --dest-repo my-repo-backup \
    --dry-run \
    --verbose
```

#### Keep temporary files for debugging
```bash
python artifactory_sync.py \
    --source-url https://artifactory.example.com/artifactory \
    --source-repo my-repo \
    --dest-url https://backup.example.com/artifactory \
    --dest-repo my-repo-backup \
    --keep-temp
```

## How It Works

1. **Initialization**: Creates temporary directory for intermediate storage
2. **Download**: Recursively downloads all artifacts from source repository
3. **Upload (or Dry-Run)**: Recursively uploads downloaded artifacts to destination repository (or simulates if `--dry-run` is used)
4. **Cleanup**: Removes temporary files (or keeps them if `--keep-temp` is used)

## Logging and Verbose Mode

When `--verbose` is enabled, the script provides detailed logging prefixed with categories:

- `[CONFIG]`: Configuration settings
- `[CLIENT]`: Client initialization
- `[TEMP]`: Temporary directory operations
- `[LIST]`: Repository listing operations
- `[DOWNLOAD]`: Individual file downloads
- `[UPLOAD]`: Individual file uploads
- `[DRY-RUN]`: Dry-run simulation details
- `[RECURSIVE]`: Recursive operation details
- `[FILE]`: File processing
- `[SUCCESS]`: Successful operations
- `[ERROR]`: Error messages
- `[PROGRESS]`: Upload progress tracking

## Dry-Run Mode

The `--dry-run` flag allows you to test the sync process without actually uploading files:

- **Download phase**: Still downloads all artifacts normally to a temporary directory
- **Upload phase**: Simulates uploads by reporting what would be uploaded
- **No data written**: No files are actually written to the destination server

This is useful for:
- Testing configuration and credentials
- Verifying folder structure and artifact count
- Identifying potential issues before actual sync
- Validating permissions and access

## Error Handling

- Validates environment variables before execution
- Handles network errors with informative messages
- Continues upload even if some downloads fail (reports count)
- Exits with proper error codes on failure

## Performance Considerations

- Downloads are streamed in 8KB chunks to minimize memory usage
- Temporary directory uses system default temp location
- Supports large folder structures
- Network timeouts depend on requests library defaults (can be configured)

## Security Notes

- Credentials are never stored or logged
- Uses HTTPS by default (explicitly set in URL)
- HTTP Basic Authentication is used for API access
- Temporary files are stored in secure system temp directory
- Consider using API tokens instead of passwords for better security

## Troubleshooting

### Authentication Failed
- Verify credentials in environment variables
- Check Artifactory URL format includes `/artifactory`
- Ensure user has permission to read/write specified repositories

### Connection Issues
- Verify Artifactory servers are accessible
- Check firewall rules and VPN connectivity
- Ensure URL format is correct (http:// or https://)

### No Artifacts Downloaded
- Verify source path exists in repository
- Check repository name is correct
- Ensure user has read permissions

## License

MIT
