"""CLI for Hermes Cron Job Manager.

Usage:
    hermes_cronjob list          # List all jobs
    hermes_cronjob get <id>      # Get details of a job
    hermes_cronjob status <id>   # Get execution status
"""

import click
from datetime import datetime
from typing import Optional

from config import CronJobManager, CronConfigError


@click.group()
@click.option('--db-path', help='Path to executions.db')
@click.pass_context
def cli(ctx, db_path):
    """Hermes Cron Job Manager - Read-only CLI tool."""
    ctx.ensure_object(dict)
    ctx.obj['manager'] = CronJobManager(db_path)


@cli.command()
@click.option('--json', is_flag=True, help='Output as JSON')
def list(**kwargs):
    """List all cron jobs."""
    manager = kwargs.get('ctx').obj['manager']
    
    try:
        jobs = manager.list_jobs()
        
        if not jobs:
            click.echo("No jobs found.")
            return
        
        if kwargs.get('json'):
            click.echo(json.dumps(jobs, indent=2))
            return
        
        # Table output
        click.echo(f"\n{'ID':<35} {'Name':<30} {'State':<12} {'Enabled':<8} {'Last Run':<20}")
        click.echo("-" * 100)
        
        for job in jobs:
            job_id = job.get('job_id', 'N/A')[:34]
            name = job.get('name', 'N/A')[:29]
            state = job.get('state', 'unknown')
            enabled = "Yes" if job.get('enabled', False) else "No"
            
            # Format last run
            last_run = job.get('last_run_at')
            if last_run:
                try:
                    dt = datetime.fromisoformat(last_run.replace('Z', '+00:00'))
                    last_run_str = dt.strftime('%Y-%m-%d %H:%M')
                except:
                    last_run_str = str(last_run)[:19]
            else:
                last_run_str = "Never"
            
            click.echo(f"{job_id:<35} {name:<30} {state:<12} {enabled:<8} {last_run_str:<20}")
        
        click.echo(f"\nTotal: {len(jobs)} jobs\n")
        
    except CronConfigError as e:
        click.echo(f"Error: {e}", err=True)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)


@cli.command()
@click.argument('job_id')
@click.option('--json', is_flag=True, help='Output as JSON')
def get(job_id, json_output=False):
    """Get details of a specific job."""
    manager = kwargs.get('ctx').obj['manager']
    
    try:
        job = manager.get_job(job_id)
        
        if not job:
            click.echo(f"Job not found: {job_id}", err=True)
            return
        
        if json_output:
            click.echo(json.dumps(job, indent=2, default=str))
            return
        
        # Detailed output
        click.echo(f"\nJob Details: {job.get('name', 'N/A')}")
        click.echo("=" * 50)
        click.echo(f"  ID:      {job.get('job_id', 'N/A')}")
        click.echo(f"  State:   {job.get('state', 'unknown')}")
        click.echo(f"  Enabled: {'Yes' if job.get('enabled') else 'No'}")
        click.echo(f"  Schedule: {job.get('schedule', 'N/A')}")
        
        last_run = job.get('last_run_at')
        if last_run:
            try:
                dt = datetime.fromisoformat(last_run.replace('Z', '+00:00'))
                click.echo(f"  Last Run: {dt.strftime('%Y-%m-%d %H:%M:%S')}")
            except:
                click.echo(f"  Last Run: {last_run}")
        
        last_status = job.get('last_status')
        if last_status:
            status_icon = "✓" if last_status == "ok" else "✗"
            click.echo(f"  Status:  {status_icon} {last_status}")
        
        last_error = job.get('last_error')
        if last_error:
            click.echo(f"  Error:   {last_error[:200]}...")
        
        click.echo()
        
    except CronConfigError as e:
        click.echo(f"Error: {e}", err=True)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)


@cli.command()
@click.argument('job_id')
@click.option('--json', is_flag=True, help='Output as JSON')
def status(job_id, json_output=False):
    """Get execution status and statistics for a job."""
    manager = kwargs.get('ctx').obj['manager']
    
    try:
        # Get job details
        job = manager.get_job(job_id)
        if not job:
            click.echo(f"Job not found: {job_id}", err=True)
            return
        
        # Get stats
        stats = manager.get_job_stats(job_id)
        
        # Get recent executions
        executions = manager.get_last_executions(job_id, limit=5)
        
        if json_output:
            output = {
                'job': job,
                'stats': stats,
                'recent_executions': executions
            }
            click.echo(json.dumps(output, indent=2, default=str))
            return
        
        # Display status
        click.echo(f"\nStatus: {job.get('name', 'N/A')}")
        click.echo("=" * 50)
        
        if stats:
            click.echo(f"  Total Executions: {stats.get('total', 0)}")
            click.echo(f"  Completed:        {stats.get('completed', 0)}")
            click.echo(f"  Errors:           {stats.get('errors', 0)}")
            if stats.get('avg_duration'):
                click.echo(f"  Avg Duration:     {stats.get('avg_duration'):.1f}s")
        
        if executions:
            click.echo(f"\n  Recent Executions:")
            for exec_record in executions:
                started = exec_record.get('started_at', 'N/A')
                status = exec_record.get('status', 'unknown')
                duration = exec_record.get('duration_seconds')
                
                status_icon = "✓" if status == "completed" else "✗"
                duration_str = f"{duration:.1f}s" if duration else "N/A"
                
                click.echo(f"    {status_icon} {started} ({duration_str})")
        
        click.echo()
        
    except CronConfigError as e:
        click.echo(f"Error: {e}", err=True)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)


def main():
    """Entry point for CLI."""
    cli()


if __name__ == '__main__':
    main()
