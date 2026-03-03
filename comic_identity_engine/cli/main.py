"""CLI main module for Comic Identity Engine.

This module provides the command-line interface for interacting with
the Comic Identity Engine API, including identity resolution from URLs.

USAGE:
    cie-find <url> [options]
    cie-find https://www.comics.org/issue/12345/
    cie-find https://leagueofcomicgeeks.com/comic/12345678/x-men-1 -v

ENTRY POINTS:
    - cli_find: Main entry point for cie-find command
"""

import json
import sys
import time
from typing import Any

import click
import httpx
from rich.console import Console
from rich.table import Table


def _extract_operation_id(name: str) -> str:
    """Extract UUID from operation name format 'operations/{uuid}'.

    Args:
        name: Operation name in format 'operations/{uuid}'

    Returns:
        The UUID portion of the operation name

    Raises:
        ValueError: If the name format is invalid
    """
    if not name.startswith("operations/"):
        raise ValueError(f"Invalid operation name format: {name}")
    return name.split("/", 1)[1]


def _poll_operation(
    client: httpx.Client,
    api_url: str,
    operation_id: str,
    timeout: int,
    verbose: bool,
    console: Console,
) -> dict[str, Any]:
    """Poll for operation completion.

    Args:
        client: HTTP client for making requests
        api_url: Base API URL
        operation_id: UUID of the operation to poll
        timeout: Maximum time to wait in seconds
        verbose: Whether to show verbose output
        console: Rich console for output

    Returns:
        The completed operation response data

    Raises:
        TimeoutError: If operation doesn't complete within timeout
        RuntimeError: If operation fails or returns an error
    """
    start_time = time.time()
    poll_interval = 1.0

    if verbose:
        console.print(f"[dim]Polling operation {operation_id}...[/dim]")

    while time.time() - start_time < timeout:
        response = client.get(f"{api_url}/api/v1/identity/resolve/{operation_id}")
        response.raise_for_status()
        data = response.json()

        if data.get("done"):
            if data.get("error"):
                error = data["error"]
                raise RuntimeError(
                    f"Operation failed: {error.get('message', 'Unknown error')}"
                )
            return data

        if verbose:
            metadata = data.get("metadata", {})
            status = metadata.get("status", "unknown")
            console.print(f"[dim]  Status: {status}...[/dim]")

        time.sleep(poll_interval)

    raise TimeoutError(f"Operation did not complete within {timeout} seconds")


def _display_json(data: dict[str, Any]) -> None:
    """Display results in JSON format.

    Args:
        data: The operation response data containing the result
    """
    click.echo(json.dumps(data, indent=2))


def _display_table(data: dict[str, Any], console: Console) -> None:
    """Display results in a pretty table format.

    Args:
        data: The operation response data containing the result
        console: Rich console for output
    """
    result = data.get("response", {})

    if not result:
        console.print("[red]No results found[/red]")
        return

    canonical_uuid = result.get("canonical_uuid", "N/A")
    confidence = result.get("confidence", 0.0)
    explanation = result.get("explanation", "N/A")
    platform_urls = result.get("platform_urls", {})

    table = Table(title="Identity Resolution Results")
    table.add_column("Field", style="cyan", no_wrap=True)
    table.add_column("Value", style="green")

    table.add_row("Canonical UUID", str(canonical_uuid))
    table.add_row("Confidence", f"{confidence:.2%}")
    table.add_row("Explanation", explanation)

    if platform_urls:
        urls_table = Table(show_header=False, box=None)
        urls_table.add_column("Platform", style="yellow")
        urls_table.add_column("URL", style="blue")
        for platform, url in sorted(platform_urls.items()):
            urls_table.add_row(platform, url)
        table.add_row("Platform URLs", urls_table)

    console.print(table)


def _display_urls(data: dict[str, Any]) -> None:
    """Display just the URLs, one per line.

    Args:
        data: The operation response data containing the result
    """
    result = data.get("response", {})
    platform_urls = result.get("platform_urls", {})

    for url in platform_urls.values():
        click.echo(url)


@click.command(name="cie-find")
@click.argument("url", required=True)
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
    default=60,
    type=int,
    help="Timeout in seconds for waiting",
    show_default=True,
)
@click.option(
    "--output",
    "-o",
    default="table",
    type=click.Choice(["json", "table", "urls"], case_sensitive=False),
    help="Output format",
    show_default=True,
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose output",
)
def cli_find(
    url: str,
    api_url: str,
    wait: bool,
    timeout: int,
    output: str,
    verbose: bool,
) -> None:
    """Resolve a comic identity from a URL.

    This command submits a URL to the Comic Identity Engine API for identity
    resolution and displays the results. The URL can be from any supported
    platform (GCD, LoCG, CCL, CLZ, AA, CPG, HipComic).

    Examples:
        cie-find https://www.comics.org/issue/12345/
        cie-find https://leagueofcomicgeeks.com/comic/12345678/x-men-1 -v
        cie-find https://www.comics.org/issue/12345/ -o json
        cie-find https://www.comics.org/issue/12345/ --no-wait
    """
    console = Console(stderr=True if output == "json" else None)

    if verbose:
        console.print(f"[dim]Resolving URL: {url}[/dim]")
        console.print(f"[dim]API endpoint: {api_url}[/dim]")

    try:
        with httpx.Client(timeout=30.0) as client:
            if verbose:
                console.print("[dim]Submitting URL to API...[/dim]")

            response = client.post(
                f"{api_url}/api/v1/identity/resolve",
                json={"url": url},
            )
            response.raise_for_status()
            data = response.json()

            operation_name = data.get("name")
            if not operation_name:
                raise RuntimeError("API response missing operation name")

            operation_id = _extract_operation_id(operation_name)

            if verbose:
                console.print(f"[dim]Operation ID: {operation_id}[/dim]")

            if not wait:
                click.echo(f"Operation submitted: {operation_id}")
                return

            final_data = _poll_operation(
                client=client,
                api_url=api_url,
                operation_id=operation_id,
                timeout=timeout,
                verbose=verbose,
                console=console,
            )

            if output == "json":
                _display_json(final_data)
            elif output == "table":
                _display_table(final_data, console)
            elif output == "urls":
                _display_urls(final_data)

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
        sys.exit(1)
    except httpx.RequestError as e:
        console.print(f"[red]Request error: {e}[/red]")
        sys.exit(1)
    except TimeoutError as e:
        console.print(f"[red]Timeout: {e}[/red]")
        sys.exit(1)
    except RuntimeError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    cli_find()
