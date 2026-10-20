# Hermes Cron Job Manager

Read-only CLI tool for managing and inspecting Hermes cron jobs.

## Purpose

This tool was created during an audit to investigate potential links between Hermes and Life_mean backends. It provides read-only access to cron job configurations and execution history.

**Note:** This is a read-only implementation. Actual job modifications require separate authorization.

## Installation

```bash
cd hermes_cronjob_manager
pip install -r requirements.txt
```

## Usage

### List all jobs

```bash
python cli.py list
```

### Get job details

```bash
python cli.py get <job_id>
```

### Get execution status

```bash
python cli.py status <job_id>
```

### JSON output

Add `--json` flag to any command for JSON output:

```bash
python cli.py list --json
python cli.py get <job_id> --json
python cli.py status <job_id> --json
```

### Custom database path

```bash
python cli.py --db-path /path/to/executions.db list
```

## Commands

| Command | Description |
|---------|-------------|
| `list` | List all cron jobs with basic info |
| `get <job_id>` | Get detailed information about a specific job |
| `status <job_id>` | Get execution statistics and recent history |

## Project Structure

```
hermes_cronjob_manager/
├── cli.py              # Command-line interface
├── config.py           # Database access layer
├── models.py           # Data models
├── tests/
│   └── test_cli.py     # Unit tests
└── requirements.txt    # Python dependencies
```

## Testing

Run tests with pytest:

```bash
pytest tests/test_cli.py -v
```

## Security Notes

- This tool is **read-only** by design
- No write operations are performed
- Database access requires appropriate permissions
- Do not use in production without authorization

## License

Internal use only. Part of the Hermes audit infrastructure.
