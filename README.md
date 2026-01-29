# Standalone Scripts

A collection of standalone Python scripts for various utility and automation tasks.

## Scripts

### [Artifactory Sync Tool](artifactory_sync/artifactory_sync_README.md)

Recursively downloads artifacts from a source Artifactory server and uploads them to a destination Artifactory server.

**Features:**
- Recursive artifact transfer between Artifactory servers
- Environment variable-based credential management
- Command-line interface with Click
- Verbose logging with categorized output
- Dry-run mode for testing before actual sync
- Temporary file management

**Quick Start:**
```bash
cd artifactory_sync
pip install -r artifactory_requirements.txt

# Set credentials
export SOURCE_ARTIFACTORY_USERNAME="user1"
export SOURCE_ARTIFACTORY_PASSWORD="pass1"
export DEST_ARTIFACTORY_USERNAME="user2"
export DEST_ARTIFACTORY_PASSWORD="pass2"

# Run sync
python artifactory_sync.py \
    --source-url https://source.example.com/artifactory \
    --source-repo my-repo \
    --dest-url https://dest.example.com/artifactory \
    --dest-repo backup-repo \
    --verbose
```

See [Artifactory Sync README](artifactory_sync/artifactory_sync_README.md) for detailed documentation.

## Directory Structure

```
standalone-scripts/
├── README.md                             # This file
├── .gitignore                            # Git ignore file
└── artifactory_sync/                     # Artifactory Sync Tool
    ├── artifactory_sync.py               # Main Artifactory sync script
    ├── artifactory_sync_README.md        # Detailed documentation
    └── artifactory_requirements.txt      # Python dependencies
```

## Requirements

- Python 3.7+
- Individual scripts may have additional dependencies (see their respective README files)

## Contributing

Feel free to add more standalone scripts to this repository. Each script should:
- Have a clear purpose with documentation
- Include a README with usage examples
- Have a requirements.txt file for dependencies
- Be self-contained and runnable independently

## License

MIT
