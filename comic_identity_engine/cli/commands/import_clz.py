"""CLZ import command for Comic Identity Engine CLI.

This module provides the command-line interface for importing
CLZ CSV collections into the Comic Identity Engine.

USAGE:
    cie-import-clz <csv_path> [options]
    cie-import-clz --operation-id <operation_id> [options]
    cie-import-clz collection.csv
    cie-import-clz collection.csv --limit 100
    cie-import-clz collection.csv --api-url http://localhost:8000
"""

import sys
from datetime import datetime
from pathlib import Path

import click
import httpx
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
)
from rich.table import Table


@click.command(name="cie-import-clz")
@click.argument("csv_path", type=click.Path(exists=True), required=False)
@click.option(
    "--api-url",
    default="http://localhost:8000",
    help="API endpoint URL",
    show_default=True,
)
@click.option(
    "--wait/--no-wait",
    default=True,
    help="Wait for the operation to complete and show results",
    show_default=True,
)
@click.option(
    "--timeout",
    default=600,
    type=int,
    help="Timeout in seconds for waiting (default: 600, longer than cie-find)",
    show_default=True,
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose output",
)
@click.option(
    "--debug",
    is_flag=True,
    help="Enable DEBUG level logging with full stack traces",
)
@click.option(
    "--operation-id",
    "--attach",
    "operation_id",
    help="Attach to an existing CLZ import operation without submitting a file",
)
@click.option(
    "--retry-failed-only",
    is_flag=True,
    help="Requeue failed rows for a same-file import without reposting resolved rows",
)
def cli_import_clz(
    csv_path: str | None,
    api_url: str,
    wait: bool,
    timeout: int,
    verbose: bool,
    debug: bool,
    operation_id: str | None,
    retry_failed_only: bool,
) -> None:
    """Import comic data from a CLZ CSV export file.

    This command submits a CLZ CSV file to the Comic Identity Engine API
    for batch import and displays the results, or attaches to an existing
    import operation without creating a new one.

    \b
    Examples:
        cie-import-clz clz_export.csv
        cie-import-clz --operation-id 550e8400-e29b-41d4-a716-446655440000
        cie-import-clz clz_export.csv --no-wait
        cie-import-clz clz_export.csv --verbose
    """
    if csv_path and operation_id:
        raise click.UsageError(
            "Provide either a CSV path or --operation-id/--attach, not both."
        )
    if not csv_path and not operation_id:
        raise click.UsageError(
            "Provide a CSV path to submit or --operation-id/--attach to monitor."
        )
    if retry_failed_only and not csv_path:
        raise click.UsageError("--retry-failed-only requires a CSV path submission.")

    console = Console(stderr=True)

    csv_file: Path | None = None
    if csv_path:
        csv_file = Path(csv_path)
        if not csv_file.exists():
            console.print(f"[red]CSV file not found: {csv_path}[/red]")
            sys.exit(1)

        if not csv_file.suffix.lower() == ".csv":
            console.print(
                f"[yellow]Warning: File does not have .csv extension: {csv_path}[/yellow]"
            )

    normalized_operation_id = (
        _normalize_operation_id(operation_id) if operation_id else None
    )

    if verbose or debug:
        if csv_file is not None:
            console.print(f"[dim]Importing CLZ CSV: {csv_file}[/dim]")
            if retry_failed_only:
                console.print("[dim]Retry mode: failed rows only[/dim]")
        else:
            console.print(
                f"[dim]Attaching to CLZ import operation: {normalized_operation_id}[/dim]"
            )
        console.print(f"[dim]API endpoint: {api_url}[/dim]")

    try:
        with httpx.Client(timeout=30.0) as client:
            if normalized_operation_id is None:
                # csv_file is guaranteed to be set here since operation_id is None
                assert csv_file is not None, (
                    "csv_file must be set when operation_id is None"
                )

                if verbose or debug:
                    console.print("[dim]Submitting CSV to API...[/dim]")

                response = client.post(
                    f"{api_url}/api/v1/import/clz",
                    json={
                        "file_path": str(csv_file.absolute()),
                        "retry_failed_only": retry_failed_only,
                    },
                )
                response.raise_for_status()
                data = response.json()

                operation_name = data.get("name")
                if not operation_name:
                    raise RuntimeError("API response missing operation name")

                normalized_operation_id = _normalize_operation_id(operation_name)

                if verbose or debug:
                    console.print(f"[dim]Operation ID: {normalized_operation_id}[/dim]")
            elif verbose or debug:
                console.print(
                    "[dim]Skipping submission and polling existing operation[/dim]"
                )

            if not wait:
                action = "attached" if operation_id else "submitted"
                click.echo(f"Import operation {action}: {normalized_operation_id}")
                return

            final_data = _poll_import_operation(
                client=client,
                api_url=api_url,
                operation_id=normalized_operation_id,
                timeout=timeout,
                verbose=verbose,
                console=console,
                display_name=(
                    csv_file.name
                    if csv_file is not None
                    else f"operation {normalized_operation_id}"
                ),
            )

            _display_import_result(final_data, console, verbose=verbose)

    except httpx.HTTPStatusError as e:
        error_msg = f"API error: {e.response.status_code}"
        try:
            error_data = e.response.json()
            if "detail" in error_data:
                detail = error_data["detail"]
                if isinstance(detail, dict):
                    error_msg = f"{error_msg} - {detail.get('message', detail)}"
                else:
                    error_msg = f"{error_msg} - {detail}"
        except Exception:
            pass
        console.print(f"[red]{error_msg}[/red]")
        if debug:
            import traceback

            console.print("[red]Stack trace:[/red]")
            console.print(traceback.format_exc())
        sys.exit(1)
    except httpx.RequestError as e:
        console.print(f"[red]Request error: {e}[/red]")
        if debug:
            import traceback

            console.print("[red]Stack trace:[/red]")
            console.print(traceback.format_exc())
        sys.exit(1)
    except TimeoutError as e:
        console.print(f"[red]Timeout: {e}[/red]")
        sys.exit(1)
    except RuntimeError as e:
        console.print(f"[red]Error: {e}[/red]")
        if debug:
            import traceback

            console.print("[red]Stack trace:[/red]")
            console.print(traceback.format_exc())
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        if debug:
            import traceback

            console.print("[red]Stack trace:[/red]")
            console.print(traceback.format_exc())
        sys.exit(1)


def _normalize_operation_id(operation_ref: str) -> str:
    """Accept either a raw UUID or an AIP-151 operation resource name."""
    if operation_ref.startswith("operations/"):
        return operation_ref.split("/", 1)[1]
    return operation_ref


def _poll_import_operation(
    client: httpx.Client,
    api_url: str,
    operation_id: str,
    timeout: int,
    verbose: bool,
    console: Console,
    display_name: str,
) -> dict:
    """Poll for import operation completion with progress display.

    Args:
        client: HTTP client for making requests
        api_url: Base API URL
        operation_id: UUID of the operation to poll
        timeout: Maximum time to wait in seconds
        verbose: Whether to show verbose output
        console: Rich console for output
        display_name: Human-readable label for the operation

    Returns:
        The completed operation response data

    Raises:
        TimeoutError: If operation doesn't complete within timeout
        RuntimeError: If operation fails
    """
    import time

    start_time = time.time()
    poll_interval = 0.5

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            f"[cyan]Importing {display_name}[/cyan]",
            total=100,
        )

        last_metadata = {}

        while time.time() - start_time < timeout:
            response = client.get(f"{api_url}/api/v1/import/clz/{operation_id}")
            response.raise_for_status()
            data = response.json()

            last_metadata = data.get("metadata", {}) or {}

            response_obj = data.get("response") or {}

            total_rows = response_obj.get("total_rows", 0)
            processed = response_obj.get("processed", 0)

            if total_rows > 0:
                if verbose and processed > 0:
                    progress.update(
                        task,
                        completed=processed,
                        total=total_rows,
                        description=f"[cyan]Importing {display_name}[/cyan] ({processed}/{total_rows} rows processed)",
                    )
                else:
                    progress.update(
                        task,
                        completed=processed,
                        total=total_rows,
                    )

            if data.get("done"):
                if data.get("error"):
                    error = data["error"]
                    raise RuntimeError(
                        f"Import failed: {error.get('message', 'Unknown error')}"
                    )
                return data

            time.sleep(poll_interval)

    raise TimeoutError(
        f"Import operation did not complete within {timeout} seconds. "
        f"Last status: {last_metadata.get('status', 'unknown')}"
    )


def _generate_html_report(operation_id: str, result: dict) -> Path:
    """Generate an HTML report with full import details.

    Args:
        operation_id: Operation UUID for filename
        result: Result dictionary with all import data

    Returns:
        Path to the generated HTML report
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_filename = f"clz-import-report-{operation_id[:8]}-{timestamp}.html"
    report_path = Path.cwd() / report_filename

    total_rows = result.get("total_rows", 0)
    processed = result.get("processed", 0)
    resolved = result.get("resolved", 0)
    failed = result.get("failed", 0)
    errors = result.get("errors", [])
    error_summary = result.get("error_summary", [])

    success_rate = (resolved / processed * 100) if processed > 0 else 0

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CLZ Import Report - {operation_id[:8]}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
            padding: 20px;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}

        h1 {{
            color: #2c3e50;
            margin-bottom: 10px;
            font-size: 28px;
        }}

        .subtitle {{
            color: #7f8c8d;
            margin-bottom: 30px;
            font-size: 14px;
        }}

        h2 {{
            color: #2c3e50;
            margin-top: 30px;
            margin-bottom: 15px;
            font-size: 20px;
            border-bottom: 2px solid #3498db;
            padding-bottom: 10px;
        }}

        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}

        .metric-card {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }}

        .metric-card.success {{
            background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
        }}

        .metric-card.warning {{
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        }}

        .metric-card.error {{
            background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);
        }}

        .metric-label {{
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
            opacity: 0.9;
            margin-bottom: 5px;
        }}

        .metric-value {{
            font-size: 32px;
            font-weight: bold;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 20px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}

        th {{
            background: #34495e;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: 600;
        }}

        td {{
            padding: 12px;
            border-bottom: 1px solid #ecf0f1;
        }}

        tr:hover {{
            background: #f8f9fa;
        }}

        .error-summary-table tr:last-child td {{
            border-bottom: none;
        }}

        .category-badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
        }}

        .category-missing_year {{ background: #ffeaa7; color: #d35400; }}
        .category-duplicate {{ background: #fab1a0; color: #c0392b; }}
        .category-validation {{ background: #74b9ff; color: #0984e3; }}
        .category-resolution {{ background: #a29bfe; color: #6c5ce7; }}
        .category-network {{ background: #55efc4; color: #00b894; }}
        .category-timeout {{ background: #fdcb6e; color: #e17055; }}
        .category-other {{ background: #b2bec3; color: #636e72; }}

        .sample-rows {{
            font-family: 'Courier New', monospace;
            font-size: 11px;
            background: #f8f9fa;
            padding: 4px 8px;
            border-radius: 4px;
            color: #495057;
        }}

        .error-details-table td {{
            font-size: 13px;
        }}

        .error-message {{
            max-width: 600px;
            word-wrap: break-word;
        }}

        .footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #ecf0f1;
            text-align: center;
            color: #95a5a6;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 CLZ Import Report</h1>
        <p class="subtitle">Operation: {operation_id} | Generated: {timestamp}</p>

        <h2>📈 Summary Metrics</h2>
        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-label">Total Rows</div>
                <div class="metric-value">{total_rows:,}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Processed</div>
                <div class="metric-value">{processed:,}</div>
            </div>
            <div class="metric-card success">
                <div class="metric-label">Resolved</div>
                <div class="metric-value">{resolved:,}</div>
            </div>
            <div class="metric-card warning">
                <div class="metric-label">Failed</div>
                <div class="metric-value">{failed:,}</div>
            </div>
            <div class="metric-card error">
                <div class="metric-label">Errors</div>
                <div class="metric-value">{len(errors):,}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Success Rate</div>
                <div class="metric-value">{success_rate:.1f}%</div>
            </div>
        </div>
"""

    # Add error summary section if there are errors
    if error_summary:
        html_content += """
        <h2>📋 Error Summary by Category</h2>
        <table class="error-summary-table">
            <thead>
                <tr>
                    <th>Category</th>
                    <th>Count</th>
                    <th>Sample Row Numbers</th>
                    <th>Description</th>
                </tr>
            </thead>
            <tbody>
"""
        for category_data in error_summary:
            category = category_data["category"]
            count = category_data["count"]
            sample_rows = category_data.get("sample_rows", [])
            description = category_data.get("description", "")

            html_content += f"""
                <tr>
                    <td><span class="category-badge category-{category}">{category}</span></td>
                    <td>{count:,}</td>
                    <td><span class="sample-rows">{sample_rows[:10]}</span></td>
                    <td>{description}</td>
                </tr>
"""
        html_content += """
            </tbody>
        </table>
"""

    # Add detailed error table if there are errors
    if errors:
        html_content += """
        <h2>❌ Detailed Error List</h2>
        <table class="error-details-table">
            <thead>
                <tr>
                    <th style="width: 80px;">Row</th>
                    <th style="width: 150px;">Category</th>
                    <th>Error Message</th>
                </tr>
            </thead>
            <tbody>
"""
        for error in errors:
            row = error.get("row", "Unknown")
            msg = error.get("error", "Unknown error")
            category = _get_error_category(msg)

            html_content += f"""
                <tr>
                    <td><strong>{row}</strong></td>
                    <td><span class="category-badge category-{category}">{category}</span></td>
                    <td class="error-message">{msg}</td>
                </tr>
"""
        html_content += """
            </tbody>
        </table>
"""

    html_content += f"""
        <div class="footer">
            <p>Generated by Comic Identity Engine CLZ Import Tool</p>
            <p>Operation ID: {operation_id}</p>
        </div>
    </div>
</body>
</html>
"""

    report_path.write_text(html_content, encoding="utf-8")
    return report_path


def _display_import_result(
    data: dict, console: Console, *, verbose: bool = False
) -> None:
    """Display import results in a table format.

    Args:
        data: The operation response data containing the result
        console: Rich console for output
        verbose: Whether to show verbose output
    """
    result = data.get("response") or {}

    if not result:
        console.print("[red]No results found[/red]")
        return

    table = Table(title="CLZ Import Results")
    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Value", style="green")

    total_rows = result.get("total_rows", 0)
    processed = result.get("processed", 0)
    resolved = result.get("resolved", 0)
    failed = result.get("failed", 0)
    errors = result.get("errors", [])

    table.add_row("Total Rows", str(total_rows))
    table.add_row("Processed", str(processed))
    table.add_row("Resolved", str(resolved))
    table.add_row("Failed", str(failed))
    table.add_row("Errors", str(len(errors)))

    if processed > 0:
        success_rate = (resolved / processed) * 100
        table.add_row("Success Rate", f"{success_rate:.1f}%")

    console.print(table)

    # Generate HTML report with full details
    operation_id = data.get("name", "unknown")
    report_path = _generate_html_report(operation_id, result)

    console.print()
    console.print(
        f"[green]✓[/green] Detailed HTML report generated: [cyan]{report_path}[/cyan]"
    )
    console.print(
        "[dim]Open the report in your browser to view full details and error breakdowns.[/dim]"
    )


def _get_error_category(error_msg: str) -> str:
    """Categorize error message for display."""
    error_lower = error_msg.lower()

    if "source series start year" in error_lower or "year" in error_lower:
        return "missing_year"
    if "multiple rows were found" in error_lower:
        return "duplicate"
    if "validation error" in error_lower:
        return "validation"
    if "resolution error" in error_lower:
        return "resolution"
    if "network" in error_lower or "connection" in error_lower:
        return "network"
    if "timeout" in error_lower:
        return "timeout"

    return "other"


if __name__ == "__main__":
    cli_import_clz()
