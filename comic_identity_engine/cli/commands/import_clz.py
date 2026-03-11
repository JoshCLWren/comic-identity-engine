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
    TimeRemainingColumn,
    MofNCompleteColumn,
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
    "--retry-failed-only/--no-retry-failed-only",
    default=True,
    help="Requeue failed rows for a same-file import without reposting resolved rows",
    show_default=True,
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

                if verbose or debug:
                    console.print(
                        "[dim]Searching for missing platform mappings...[/dim]"
                    )

                refresh_response = client.post(
                    f"{api_url}/api/v1/import/clz/{normalized_operation_id}/refresh-mappings",
                )
                refresh_response.raise_for_status()
                refresh_data = refresh_response.json()

                refresh_operation_name = refresh_data.get("name")
                if refresh_operation_name:
                    normalized_operation_id = _normalize_operation_id(
                        refresh_operation_name
                    )
                    if verbose or debug:
                        console.print(
                            f"[dim]Refresh operation ID: {normalized_operation_id}[/dim]"
                        )

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
    last_processed = 0
    last_update_time = start_time

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        MofNCompleteColumn(),
        TimeRemainingColumn(),
        console=console,
        refresh_per_second=4,
    ) as progress:
        task = progress.add_task(
            f"[cyan]Importing {display_name}[/cyan]",
            total=None,  # Will be set when we know total_rows
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
            resolved = response_obj.get("resolved", 0)
            failed = response_obj.get("failed", 0)

            if total_rows > 0:
                # Calculate progress stats
                current_time = time.time()
                elapsed_since_last_update = current_time - last_update_time
                rows_since_last_update = processed - last_processed

                # Calculate rows per second
                if elapsed_since_last_update > 0 and rows_since_last_update > 0:
                    rows_per_sec = rows_since_last_update / elapsed_since_last_update
                elif processed > 0 and (current_time - start_time) > 0:
                    rows_per_sec = processed / (current_time - start_time)
                else:
                    rows_per_sec = 0

                # Calculate average time per row
                if processed > 0:
                    avg_time_per_row = (current_time - start_time) / processed
                else:
                    avg_time_per_row = 0

                # Calculate remaining rows
                remaining_rows = total_rows - processed

                # Calculate ETA
                if rows_per_sec > 0 and remaining_rows > 0:
                    eta_seconds = remaining_rows / rows_per_sec
                else:
                    eta_seconds = None

                # Update task with new total if not set
                if (
                    progress.tasks[0].total is None
                    or progress.tasks[0].total != total_rows
                ):
                    progress.update(task, total=total_rows)

                # Build description with stats
                stats_parts = []
                if verbose:
                    stats_parts.append(f"{processed}/{total_rows} rows")
                    stats_parts.append(f"{resolved} ✓")
                    if failed > 0:
                        stats_parts.append(f"{failed} ✗")
                    if rows_per_sec > 0:
                        stats_parts.append(f"{rows_per_sec:.1f}/s")
                    if avg_time_per_row > 0:
                        stats_parts.append(f"{avg_time_per_row * 1000:.0f}ms/row")
                else:
                    stats_parts.append(f"{processed}/{total_rows}")
                    if rows_per_sec > 0:
                        stats_parts.append(f"{rows_per_sec:.1f}/s")

                description = f"[cyan]Importing {display_name}[/cyan] " + ", ".join(
                    stats_parts
                )

                progress.update(
                    task,
                    completed=processed,
                    description=description,
                )

                last_processed = processed
                last_update_time = current_time

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

    # Get row_results for successful entries with platform mappings
    row_results = result.get("row_results", {})
    successful_results = []
    for row_key, row_result in row_results.items():
        if row_result.get("resolved") and not row_result.get("error"):
            platform_mappings = row_result.get("platform_mappings", [])
            if platform_mappings and len(platform_mappings) > 0:
                successful_results.append(row_result)

    # Sort by row_index
    successful_results.sort(key=lambda x: x.get("row_index", 0))

    # Add successful results section with navigation
    if successful_results:
        html_content += (
            """
        <style>
            .success-nav {{
                background: #f0f9f0;
                border: 1px solid #27ae60;
                border-radius: 8px;
                padding: 15px 20px;
                margin-bottom: 20px;
            }}
            .success-nav-title {{
                font-size: 18px;
                font-weight: bold;
                color: #27ae60;
                margin-bottom: 10px;
            }}
            .success-nav-controls {{
                display: flex;
                align-items: center;
                gap: 10px;
            }}
            .success-nav button {{
                background: #27ae60;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 14px;
            }}
            .success-nav button:hover {{
                background: #219a52;
            }}
            .success-nav button:disabled {{
                background: #95a5a6;
                cursor: not-allowed;
            }}
            .success-nav-info {{
                color: #555;
                font-size: 14px;
            }}
            .success-card {{
                display: none;
                border: 1px solid #27ae60: 8px;
                border-radius;
                margin-bottom: 20px;
                background: white;
                overflow: hidden;
            }}
            .success-card.active {{
                display: block;
            }}
            .success-header {{
                background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
                color: white;
                padding: 15px 20px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}
            .success-title {{
                font-size: 18px;
                font-weight: bold;
            }}
            .success-subtitle {{
                font-size: 14px;
                opacity: 0.9;
            }}
            .success-body {{
                padding: 20px;
            }}
            .data-section {{
                margin-bottom: 20px;
            }}
            .data-section h3 {{
                color: #2c3e50;
                font-size: 16px;
                margin-bottom: 10px;
                padding-bottom: 5px;
                border-bottom: 2px solid #3498db;
            }}
            .platform-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
                gap: 15px;
                margin-top: 10px;
            }}
            .platform-card {{
                background: #f8f9fa;
                border: 1px solid #ddd;
                border-radius: 6px;
                padding: 12px;
            }}
            .platform-card-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 8px;
            }}
            .platform-name {{
                font-weight: bold;
                color: #2c3e50;
                text-transform: uppercase;
                font-size: 12px;
            }}
            .platform-id {{
                font-family: 'Courier New', monospace;
                font-size: 13px;
                color: #555;
            }}
            .match-explanation {{
                background: #e8f5e9;
                border-left: 4px solid #27ae60;
                padding: 12px 15px;
                margin: 15px 0;
                border-radius: 4px;
            }}
            .match-explanation strong {{
                color: #1e7e34;
                display: block;
                margin-bottom: 5px;
            }}
        </style>

        <h2>✅ Successful Imports (with platform mappings)</h2>
        <div class="success-nav">
            <div class="success-nav-title">Navigate Results</div>
            <div class="success-nav-controls">
                <button id="prev-btn" onclick="navigateResult(-1)" disabled>← Previous</button>
                <span class="success-nav-info">Result <span id="current-index">1</span> of """
            + str(len(successful_results))
            + """</span>
                <button id="next-btn" onclick="navigateResult(1)">Next →</button>
            </div>
        </div>
"""
        )
        # Add each success card
        for idx, sr in enumerate(successful_results):
            row_index = sr.get("row_index", "?")
            source_issue_id = sr.get("source_issue_id", "")
            issue_id = sr.get("issue_id", "")
            row_data = sr.get("row_data", {})
            platform_mappings = sr.get("platform_mappings", [])
            explanation = sr.get("match_explanation", "")
            existing = sr.get("existing_mapping", False)

            # Build CLZ row data HTML
            clz_data_html = ""
            for key, value in sorted(row_data.items()):
                if value:
                    clz_data_html += f"""
                        <tr>
                            <td class="key-column">{key}</td>
                            <td>{value}</td>
                        </tr>"""

            # Build platform mappings HTML
            platform_html = ""
            all_platforms = ["gcd", "locg", "ccl", "aa", "cpg", "hip"]
            platforms_found = {pm["platform"] for pm in platform_mappings}

            for plat in all_platforms:
                plat_data = next(
                    (pm for pm in platform_mappings if pm["platform"] == plat), None
                )
                if plat_data:
                    platform_html += f"""
                    <div class="platform-card">
                        <div class="platform-card-header">
                            <span class="platform-name">{plat}</span>
                        </div>
                        <div class="platform-id">{plat_data.get("external_id", "N/A")}</div>
                    </div>"""
                else:
                    platform_html += f"""
                    <div class="platform-card" style="opacity: 0.5;">
                        <div class="platform-card-header">
                            <span class="platform-name">{plat}</span>
                        </div>
                        <div class="platform-id">Not found</div>
                    </div>"""

            html_content += f"""
        <div class="success-card" data-index="{idx}">
            <div class="success-header">
                <div>
                    <div class="success-title">Row {row_index}</div>
                    <div class="success-subtitle">CLZ ID: {source_issue_id} | Issue UUID: {issue_id[:8]}...</div>
                </div>
                <span class="category-badge" style="background: #27ae60; color: white;">{"Reused" if existing else "Resolved"}</span>
            </div>
            <div class="success-body">
                <div class="data-section">
                    <h3>📄 CLZ Row Data</h3>
                    <table class="row-data-table">
                        <tbody>
                            {clz_data_html}
                        </tbody>
                    </table>
                </div>
                
                <div class="match-explanation">
                    <strong>Match Explanation</strong>
                    {explanation}
                </div>
                
                <div class="data-section">
                    <h3>🔗 Platform Mappings ({len(platform_mappings)}/6 found)</h3>
                    <div class="platform-grid">
                        {platform_html}
                    </div>
                </div>
            </div>
        </div>
"""

        html_content += """
        <script>
            let currentIndex = 0;
            const cards = document.querySelectorAll('.success-card');
            const totalCards = cards.length;
            
            function showCard(index) {
                cards.forEach((card, i) => {
                    card.classList.toggle('active', i === index);
                });
                document.getElementById('current-index').textContent = index + 1;
                document.getElementById('prev-btn').disabled = index === 0;
                document.getElementById('next-btn').disabled = index === totalCards - 1;
            }
            
            function navigateResult(direction) {
                currentIndex = Math.max(0, Math.min(totalCards - 1, currentIndex + direction));
                showCard(currentIndex);
            }
            
            // Show first card initially
            if (totalCards > 0) {
                showCard(0);
            }
        </script>
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
        <style>
            .error-card {
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                margin-bottom: 20px;
                background: white;
                overflow: hidden;
            }
            .error-header {
                background: #f8f9fa;
                padding: 15px 20px;
                border-bottom: 1px solid #e0e0e0;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .error-title {
                display: flex;
                align-items: center;
                gap: 15px;
            }
            .error-row-num {
                font-size: 24px;
                font-weight: bold;
                color: #2c3e50;
                min-width: 60px;
            }
            .copy-button {
                background: #3498db;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 13px;
                font-weight: 600;
                transition: background 0.2s;
            }
            .copy-button:hover {
                background: #2980b9;
            }
            .copy-button.copied {
                background: #27ae60;
            }
            .error-body {
                padding: 20px;
            }
            .error-message-box {
                background: #fee;
                border-left: 4px solid #e74c3c;
                padding: 12px 15px;
                margin-bottom: 15px;
                border-radius: 4px;
            }
            .error-message-box strong {
                color: #c0392b;
                display: block;
                margin-bottom: 5px;
                font-size: 12px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            .row-data-table {
                width: 100%;
                border-collapse: collapse;
                margin-top: 15px;
            }
            .row-data-table th {
                background: #ecf0f1;
                color: #2c3e50;
                padding: 8px 12px;
                text-align: left;
                font-weight: 600;
                font-size: 12px;
                text-transform: uppercase;
                border: 1px solid #ddd;
            }
            .row-data-table td {
                padding: 10px 12px;
                border: 1px solid #ddd;
                font-size: 13px;
                font-family: 'Courier New', monospace;
            }
            .row-data-table tr:nth-child(even) {
                background: #f8f9fa;
            }
            .key-column {
                font-weight: 600;
                color: #2c3e50;
                width: 30%;
            }
        </style>
"""
        row_num = 0
        for error in errors:
            row_num += 1
            row_idx = error.get("row", "Unknown")
            msg = error.get("error", "Unknown error")
            category = _get_error_category(msg)
            row_data = error.get("row_data", {})
            source_issue_id = error.get("source_issue_id", "")

            # Build copy prompt data
            row_data_str = "\n".join(
                [f"  {k}: {v}" for k, v in sorted(row_data.items()) if v]
            )
            copy_data = f"""Row {row_idx} - CLZ Import Error

Error:
  {msg}

Row Data:
{row_data_str}

Investigation Request:
Please analyze this CLZ import error and suggest fixes. Consider:
1. Is the error due to missing or invalid data?
2. Can this be resolved with better matching logic?
3. Should this row be manually reviewed?
4. What specific changes would fix this?"""

            # Build row data HTML table
            row_data_html = ""
            for key, value in sorted(row_data.items()):
                if value:  # Only show non-empty values
                    row_data_html += f"""
                    <tr>
                        <td class="key-column">{key}</td>
                        <td>{value}</td>
                    </tr>"""

            html_content += f"""
        <div class="error-card">
            <div class="error-header">
                <div class="error-title">
                    <div class="error-row-num">#{row_idx}</div>
                    <span class="category-badge category-{category}">{category}</span>
                </div>
                <button class="copy-button" onclick="copyToClipboard(this, `{copy_data.replace("`", "\\`")}`)">
                    📋 Copy for LLM
                </button>
            </div>
            <div class="error-body">
                <div class="error-message-box">
                    <strong>Error Message</strong>
                    {msg}
                </div>
                <table class="row-data-table">
                    <thead>
                        <tr>
                            <th class="key-column">Field</th>
                            <th>Value</th>
                        </tr>
                    </thead>
                    <tbody>
                        {row_data_html}
                    </tbody>
                </table>
            </div>
        </div>
"""
        html_content += """
        <script>
            function copyToClipboard(button, text) {
                navigator.clipboard.writeText(text).then(() => {
                    const originalText = button.innerHTML;
                    button.innerHTML = "✓ Copied!";
                    button.classList.add("copied");
                    setTimeout(() => {
                        button.innerHTML = originalText;
                        button.classList.remove("copied");
                    }, 2000);
                }).catch(err => {
                    console.error("Failed to copy:", err);
                    button.innerHTML = "❌ Failed";
                    setTimeout(() => {
                        button.innerHTML = "📋 Copy for LLM";
                    }, 2000);
                });
            }
        </script>
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

    report_url = f"file://{report_path.resolve()}"
    console.print()
    console.print(
        f"[green]✓[/green] Detailed HTML report generated: [link={report_url}][cyan]{report_path}[/cyan][/link]"
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
