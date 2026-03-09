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

    if errors:
        console.print()
        error_table = Table(show_header=True, header_style="bold red")
        error_table.add_column("Row", style="dim")
        error_table.add_column("Error")

        # Show all errors
        for error in errors:
            row_num = error.get("row", "N/A")
            error_msg = error.get("error", "")
            error_table.add_row(str(row_num), error_msg[:200])

        console.print(error_table)

    if verbose:
        console.print()
        console.print("[dim]Raw response data:[/dim]")
        console.print(result)


if __name__ == "__main__":
    cli_import_clz()
