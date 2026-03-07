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
import re
import sys
import time
from typing import Any

import click
import httpx
from rich.console import Console
from rich.live import Live
from rich.table import Table


ALL_PLATFORMS = ["gcd", "locg", "aa", "ccl", "cpg", "hip"]
PLATFORM_NAMES = {
    "gcd": "Grand Comics Database",
    "locg": "League of Comic Geeks",
    "aa": "Atomic Avenue",
    "ccl": "Comic Collector Live",
    "cpg": "ComicPriceGuide",
    "hip": "HipComic",
}


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


def _build_progress_table(
    platform_status: dict[str, Any],
    found_count: int,
    total_platforms: int,
    elapsed_time: float,
) -> Table:
    """Build a progress table showing platform search status.

    Args:
        platform_status: Dictionary mapping platform -> status info
        found_count: Number of platforms found so far
        total_platforms: Total number of platforms being searched
        elapsed_time: Time elapsed since search started

    Returns:
        Rich Table displaying current progress
    """
    table = Table(
        title=f"Cross-Platform Search Progress ({found_count}/{total_platforms} found)",
        show_header=True,
    )
    table.add_column("Platform", style="cyan", no_wrap=True)
    table.add_column("Status", style="white")
    table.add_column("Details", style="dim")

    status_colors = {
        "found": "green",
        "not_found": "yellow",
        "failed": "red",
        "searching": "blue",
        "searching_retry_1": "cyan",
        "searching_retry_2": "magenta",
        "searching_retry_3": "bright_magenta",
    }

    status_labels = {
        "searching": "Searching...",
        "searching_exact": "Exact match",
        "searching_no_year": "No year filter",
        "searching_normalized_title": "Normalized title",
        "searching_fuzzy_title": "Fuzzy title match",
        "searching_simplified_tokens": "Simplified tokens",
        "searching_alt_issue_format": "Alt issue format",
        "searching_retry_1": "Retry 1",
        "searching_retry_2": "Retry 2",
        "searching_retry_3": "Retry 3",
        "found": "[green]✓[/green] Found",
        "not_found": "[yellow]✗[/yellow] Not found",
        "failed": "[red]✗[/red] Failed",
    }

    sorted_platforms = sorted(platform_status.keys())
    for platform in sorted_platforms:
        info = platform_status[platform]

        if isinstance(info, dict):
            status = info.get("status", "unknown")
            strategy = info.get("strategy")
            retry = info.get("retry")
        else:
            status = info
            strategy = None
            retry = None

        display_name = PLATFORM_NAMES.get(platform, platform.upper())
        status_display = status_labels.get(status, status)

        details = []
        if strategy and strategy != "exact":
            strategy_label = status_labels.get(f"searching_{strategy}", strategy)
            details.append(strategy_label)
        if retry:
            details.append(f"Attempt {retry}")

        detail_text = " | ".join(details) if details else ""

        color = status_colors.get(status, "white")
        table.add_row(
            display_name,
            f"[{color}]{status_display}[/{color}]",
            detail_text,
        )

    table.add_row("", "", "")
    table.add_row("", f"[dim]Elapsed: {elapsed_time:.1f}s[/dim]", "")

    return table


def _build_status_message(status: str, elapsed_time: float) -> str:
    """Build a compact single-line status message for pre-progress polling."""
    return f"[dim]Status: {status} | elapsed={elapsed_time:.1f}s[/dim]"


def _normalize_platform_entry(entry: Any) -> tuple[str, str]:
    """Normalize a platform status entry into status and detail text."""
    if isinstance(entry, dict):
        status = entry.get("status", "unknown")
        detail_parts = []
        strategy = entry.get("strategy")
        retry = entry.get("retry")
        reason = entry.get("reason")
        detail = entry.get("detail")
        if strategy and strategy != "exact":
            detail_parts.append(strategy)
        if retry:
            detail_parts.append(f"attempt={retry}")
        if reason:
            detail_parts.append(f"reason={reason}")
        if detail:
            detail_parts.append(str(detail))
        return status, ", ".join(detail_parts)

    return str(entry), ""


def _summarize_platform_status(platform_status: dict[str, Any]) -> str:
    """Render compact platform status text for errors and timeouts."""
    parts = []
    for platform in sorted(platform_status):
        status, detail = _normalize_platform_entry(platform_status[platform])
        if detail:
            parts.append(f"{platform}={status} ({detail})")
        else:
            parts.append(f"{platform}={status}")
    return ", ".join(parts)


def _extract_duplicate_mapping_hint(
    error_message: str,
    response_context: dict[str, Any],
    url: str | None,
) -> str | None:
    """Build a remediation hint for duplicate mapping failures."""
    source = response_context.get("source")
    source_issue_id = response_context.get("source_issue_id")

    if not source or not source_issue_id:
        match = re.search(
            r"source=(?P<source>[a-z0-9_]+)\s+and\s+source_issue_id=(?P<source_issue_id>[^\s]+)",
            error_message,
            flags=re.IGNORECASE,
        )
        if match:
            source = match.group("source")
            source_issue_id = match.group("source_issue_id")

    if not source_issue_id:
        return None

    hint_parts = [f"retry with `--clear-mappings {source_issue_id}`"]
    if url:
        hint_parts.append(f"`cie-find {url} --force --clear-mappings {source_issue_id} --verbose`")

    if "DuplicateEntityError" in error_message:
        hint_parts.append("if you already patched the code, restart the API and worker so they stop running stale task code")

    return "; ".join(hint_parts)


def _format_failure_message(
    error: dict[str, Any],
    response_context: dict[str, Any],
    request_url: str | None = None,
) -> str:
    """Format a concise but actionable operation failure message."""
    failure_parts = [f"Operation failed: {error.get('message', 'Unknown error')}"]
    error_type = response_context.get("error_type")
    exception_type = response_context.get("exception_type")
    if error_type:
        failure_parts.append(f"type={error_type}")
    if exception_type:
        failure_parts.append(f"exception={exception_type}")

    platform_status = response_context.get("platform_status")
    if platform_status:
        failure_parts.append(f"platforms={_summarize_platform_status(platform_status)}")

    hint = _extract_duplicate_mapping_hint(
        error_message=error.get("message", ""),
        response_context=response_context,
        url=request_url,
    )
    if hint:
        failure_parts.append(f"hint={hint}")

    return " | ".join(failure_parts)


def _poll_operation(
    client: httpx.Client,
    api_url: str,
    operation_id: str,
    timeout: int,
    verbose: bool,
    console: Console,
    request_url: str | None = None,
) -> dict[str, Any]:
    """Poll for operation completion with real-time progress display.

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
    poll_interval = 0.1

    total_platforms = len(ALL_PLATFORMS)

    if verbose:
        console.print(f"[dim]Polling operation {operation_id}...[/dim]")
        console.print(
            "[dim]Cross-platform fan-out: gcd, locg, aa, ccl, cpg, hip[/dim]"
        )

    last_metadata: dict[str, Any] = {}
    last_platform_status: dict[str, Any] = {}

    with Live(console=console, refresh_per_second=10, transient=False) as live:
        while time.time() - start_time < timeout:
            response = client.get(f"{api_url}/api/v1/identity/resolve/{operation_id}")
            response.raise_for_status()
            data = response.json()
            last_metadata = data.get("metadata", {}) or {}
            elapsed = time.time() - start_time

            response_obj = data.get("response") or {}
            platform_status = (
                response_obj.get("platform_status", {}) if response_obj else {}
            )
            if platform_status:
                last_platform_status = platform_status

            if verbose and platform_status:
                found_count = sum(
                    1
                    for p in platform_status.values()
                    if (p.get("status") if isinstance(p, dict) else p) == "found"
                )

                progress_table = _build_progress_table(
                    platform_status=platform_status,
                    found_count=found_count,
                    total_platforms=total_platforms,
                    elapsed_time=elapsed,
                )

                live.update(progress_table)
            elif verbose:
                if not data.get("done"):
                    status = last_metadata.get("status", "unknown")
                else:
                    status = "completed"
                live.update(_build_status_message(status, elapsed))

            if data.get("done"):
                if data.get("error"):
                    raise RuntimeError(
                        _format_failure_message(
                            error=data["error"],
                            response_context=data.get("response") or {},
                            request_url=request_url,
                        )
                    )
                return data

            time.sleep(poll_interval)

    timeout_parts = [f"Operation did not complete within {timeout} seconds"]
    if last_metadata.get("status"):
        timeout_parts.append(f"last_status={last_metadata['status']}")
    if last_platform_status:
        timeout_parts.append(
            f"platforms={_summarize_platform_status(last_platform_status)}"
        )
    raise TimeoutError(" | ".join(timeout_parts))


def _display_json(data: dict[str, Any]) -> None:
    """Display results in JSON format.

    Args:
        data: The operation response data containing the result
    """
    click.echo(json.dumps(data, indent=2))


def _display_table(data: dict[str, Any], console: Console, *, verbose: bool = False) -> None:
    """Display results in a pretty table format.

    Args:
        data: The operation response data containing the result
        console: Rich console for output
    """
    result = data.get("response") or {}

    if not result:
        console.print("[red]No results found[/red]")
        return

    canonical_uuid = result.get("canonical_uuid", "N/A")
    confidence = result.get("confidence", 0.0)
    explanation = result.get("explanation", "N/A")
    platform_urls = {
        platform: url
        for platform, url in (result.get("platform_urls", {}) or {}).items()
        if url
    }
    platform_status = result.get("platform_status", {})
    found_count = 0
    not_found_count = 0
    failed_count = 0
    searching_count = 0
    if platform_status:
        for raw_status in platform_status.values():
            status, _ = _normalize_platform_entry(raw_status)
            if status == "found":
                found_count += 1
            elif status == "not_found":
                not_found_count += 1
            elif status == "failed":
                failed_count += 1
            elif status.startswith("searching"):
                searching_count += 1

    table = Table(title="Identity Resolution Results")
    table.add_column("Field", style="cyan", no_wrap=True)
    table.add_column("Value", style="green")

    table.add_row("Canonical UUID", str(canonical_uuid))
    table.add_row("Confidence", f"{confidence:.2%}")
    table.add_row("Explanation", explanation)
    if platform_status and not verbose:
        table.add_row(
            "Cross-Platform Search",
            (
                f"checked={len(platform_status)} in parallel | "
                f"found={found_count} | not_found={not_found_count} | "
                f"failed={failed_count} | in_progress={searching_count}"
            ),
        )

    if platform_urls:
        url_lines = "\n".join(
            f"{platform}: {url}" for platform, url in sorted(platform_urls.items())
        )
        table.add_row("Platform URLs", url_lines)

    if platform_status and not verbose:
        status_colors = {
            "found": "green",
            "not_found": "yellow",
            "failed": "red",
            "searching": "blue",
        }
        status_lines = []
        for platform, raw_status in sorted(platform_status.items()):
            status, detail = _normalize_platform_entry(raw_status)
            color = status_colors.get(status, "white")
            line = f"[{color}]{platform}: {status}[/{color}]"
            if detail:
                line = f"{line} ({detail})"
            status_lines.append(line)
        table.add_row("Platform Status", "\n".join(status_lines))

    console.print(table)


def _display_urls(data: dict[str, Any]) -> None:
    """Display just the URLs, one per line.

    Args:
        data: The operation response data containing the result
    """
    result = data.get("response") or {}
    platform_urls = {
        platform: url
        for platform, url in (result.get("platform_urls", {}) or {}).items()
        if url
    }

    for url in platform_urls.values():
        click.echo(url)


def _build_platform_timeline(
    data: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build a per-platform timeline from persisted platform events."""
    result = data.get("response") or {}
    events = result.get("platform_events", [])
    platform_status = result.get("platform_status", {}) or {}
    platform_urls = result.get("platform_urls", {}) or {}
    if not events and not platform_status:
        return []

    base_time = min(
        (
            float(event["timestamp"])
            for event in events
            if isinstance(event, dict) and event.get("timestamp") is not None
        ),
        default=0.0,
    )
    timeline: list[dict[str, Any]] = []
    for platform in ALL_PLATFORMS:
        matching_events = [
            event
            for event in events
            if isinstance(event, dict) and event.get("platform") == platform
        ]
        started_at = None
        finished_at = None
        final_status = None
        strategies: list[str] = []
        retries: list[str] = []
        final_reason = None
        final_detail = None
        final_strategy = None
        final_retry = None

        for event in matching_events:
            timestamp = event.get("timestamp")
            if timestamp is not None and started_at is None:
                started_at = float(timestamp)
            status = str(event.get("status", "unknown"))
            final_status = status
            if event.get("strategy"):
                final_strategy = str(event["strategy"])
            if event.get("retry") is not None:
                final_retry = int(event["retry"])
            if event.get("reason"):
                final_reason = str(event["reason"])
            if event.get("detail"):
                final_detail = str(event["detail"])
            if status in {"found", "not_found", "failed"} and timestamp is not None:
                finished_at = float(timestamp)
            strategy = event.get("strategy")
            if strategy and strategy not in strategies and strategy != "exact":
                strategies.append(str(strategy))
            retry = event.get("retry")
            if retry is not None:
                retry_label = str(retry)
                if retry_label not in retries:
                    retries.append(retry_label)

        raw_status = platform_status.get(platform)
        if raw_status:
            if isinstance(raw_status, dict):
                final_status = raw_status.get("status", "unknown")
                if raw_status.get("strategy"):
                    final_strategy = str(raw_status["strategy"])
                if raw_status.get("retry") is not None:
                    final_retry = int(raw_status["retry"])
                if raw_status.get("reason"):
                    final_reason = str(raw_status["reason"])
                if raw_status.get("detail"):
                    final_detail = str(raw_status["detail"])
            else:
                final_status = str(raw_status)

        started_delta = (
            f"+{started_at - base_time:.1f}s" if started_at is not None and base_time else "-"
        )
        finished_delta = (
            f"+{finished_at - base_time:.1f}s"
            if finished_at is not None and base_time
            else "-"
        )
        duration = (
            f"{finished_at - started_at:.1f}s"
            if started_at is not None and finished_at is not None
            else "-"
        )

        detail_parts = []
        if final_reason == "source_mapping":
            detail_parts.append("source mapping")
        elif final_reason == "match_found":
            match_parts = []
            if final_retry is not None:
                match_parts.append(f"attempt {final_retry}")
            if final_strategy:
                match_parts.append(f"via {final_strategy}")
            detail_parts.append(" ".join(match_parts) or "match found")
        elif final_reason == "timeout":
            detail_parts.append(final_detail or "timed out")
        elif final_reason in {"no_match", "no_match_after_errors"}:
            detail_parts.append(final_detail or "no match")
        elif final_reason == "network_error":
            detail_parts.append(final_detail or "network error")
        elif final_reason == "task_crashed":
            detail_parts.append(final_detail or "task crashed")
        elif final_detail:
            detail_parts.append(final_detail)

        if (
            strategies
            and final_reason not in {"match_found", "source_mapping"}
            and "attempts across" not in (final_detail or "")
        ):
            detail_parts.append("strategies=" + ",".join(strategies))

        timeline.append(
            {
                "platform": platform,
                "name": PLATFORM_NAMES.get(platform, platform.upper()),
                "started_at": started_delta,
                "finished_at": finished_delta,
                "duration": duration,
                "status": final_status or "not_started",
                "details": " | ".join(detail_parts),
                "url": platform_urls.get(platform, ""),
            }
        )

    return timeline


def _display_platform_timeline(data: dict[str, Any], console: Console) -> None:
    """Display a durable per-platform timeline for verbose troubleshooting."""
    timeline = _build_platform_timeline(data)
    if not timeline:
        return

    table = Table(title="Cross-Platform Timeline (all searches launched at +0.0s)")
    table.add_column("Platform", style="cyan", no_wrap=True)
    table.add_column("Started", style="dim", no_wrap=True)
    table.add_column("Finished", style="dim", no_wrap=True)
    table.add_column("Duration", style="dim", no_wrap=True)
    table.add_column("Outcome", style="white", no_wrap=True)
    table.add_column("Details", style="dim")

    status_colors = {
        "found": "green",
        "not_found": "yellow",
        "failed": "red",
        "searching": "blue",
        "not_started": "dim",
    }

    for entry in timeline:
        color = status_colors.get(entry["status"], "white")
        table.add_row(
            entry["name"],
            entry["started_at"],
            entry["finished_at"],
            entry["duration"],
            f"[{color}]{entry['status']}[/{color}]",
            entry["details"] or "-",
        )

    console.print(table)


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
    default=180,
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
    help="Enable verbose output (INFO level logging)",
)
@click.option(
    "--debug",
    is_flag=True,
    help="Enable DEBUG level logging with full stack traces",
)
@click.option(
    "--force",
    is_flag=True,
    help="Skip idempotency check and re-search even if mapping exists",
)
@click.option(
    "--clear-mappings",
    type=str,
    metavar="SOURCE_ISSUE_ID",
    help="Delete all external mappings for this source_issue_id before searching",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would happen without executing the search",
)
def cli_find(
    url: str,
    api_url: str,
    wait: bool,
    timeout: int,
    output: str,
    verbose: bool,
    debug: bool,
    force: bool,
    clear_mappings: str | None,
    dry_run: bool,
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
        cie-find https://www.comics.org/issue/12345/ --force
        cie-find https://www.comics.org/issue/12345/ --debug
        cie-find https://www.comics.org/issue/12345/ --clear-mappings 12345
        cie-find https://www.comics.org/issue/12345/ --dry-run
    """
    console = Console(stderr=True if output == "json" else False)

    if verbose or debug:
        console.print(f"[dim]Resolving URL: {url}[/dim]")
        console.print(f"[dim]API endpoint: {api_url}[/dim]")

    if dry_run:
        console.print(
            "[yellow]DRY RUN MODE - No actual search will be performed[/yellow]"
        )
        console.print(f"[dim]Would resolve: {url}[/dim]")
        if force:
            console.print("[dim]Would skip idempotency check (--force)[/dim]")
        if clear_mappings:
            console.print(f"[dim]Would clear mappings for: {clear_mappings}[/dim]")
        return

    try:
        with httpx.Client(timeout=30.0) as client:
            if verbose or debug:
                console.print("[dim]Submitting URL to API...[/dim]")

            request_body: dict[str, Any] = {"url": url}
            if force:
                request_body["force"] = True
            if clear_mappings:
                request_body["clear_mappings"] = clear_mappings

            response = client.post(
                f"{api_url}/api/v1/identity/resolve",
                json=request_body,
            )
            response.raise_for_status()
            data = response.json()

            operation_name = data.get("name")
            if not operation_name:
                raise RuntimeError("API response missing operation name")

            operation_id = _extract_operation_id(operation_name)

            if verbose or debug:
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
                request_url=url,
            )

            if output == "json":
                _display_json(final_data)
            elif output == "table":
                _display_table(final_data, console, verbose=verbose)
                if verbose:
                    _display_platform_timeline(final_data, console)
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


if __name__ == "__main__":
    cli_find()
