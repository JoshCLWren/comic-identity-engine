#!/usr/bin/env python3
"""Add row_data to existing CLZ import errors.

This script reads the original CSV and updates existing operation errors
to include the full row data that was missing.
"""

import asyncio
import sys
from pathlib import Path

from comic_identity_engine.adapters.clz import CLZAdapter
from comic_identity_engine.database import AsyncSessionLocal
from comic_identity_engine.database.models import Operation
from comic_identity_engine.services.imports import apply_clz_import_visibility


async def migrate_operation_with_row_data(csv_path: str, operation_id: str):
    """Add row_data to an existing operation's errors."""

    # Load CSV rows
    csv_file = Path(csv_path)
    adapter = CLZAdapter()

    print(f"Loading CSV: {csv_file}")
    with open(csv_file, "r") as f:
        rows = adapter.load_csv_from_string(f.read())

    print(f"Loaded {len(rows)} rows from CSV")

    # Load operation
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select

        result = await session.execute(
            select(Operation).where(Operation.id == operation_id)
        )
        op = result.scalar_one_or_none()

        if not op:
            print(f"❌ Operation not found: {operation_id}")
            return False

        print(f"Found operation: {op.id}")
        print(f"Status: {op.status}")

        result_data = dict(op.result or {})
        row_results = dict(result_data.get("row_results", {}))

        print(f"Total row_results: {len(row_results)}")
        print(
            f"Errors without row_data: {sum(1 for r in row_results.values() if 'error' in r and 'row_data' not in r)}"
        )

        # Update row_results with row_data
        updated_count = 0
        for row_index, row in enumerate(rows, start=1):
            # Find matching row_result
            for row_key, row_result in row_results.items():
                if row_result.get("row_index") == row_index:
                    if "error" in row_result and "row_data" not in row_result:
                        row_result["row_data"] = dict(row)
                        updated_count += 1
                    break

        print(f"✓ Updated {updated_count} error results with row_data")

        # Re-apply visibility to rebuild errors array with row_data
        result_data["row_results"] = row_results
        updated_result = apply_clz_import_visibility(result_data)

        # Save back to database
        op.result = updated_result
        await session.commit()

        print("✓ Saved updated operation")
        print("\nOperation now has:")
        errors = updated_result.get("errors", [])
        print(f"  - {len(errors)} errors")
        print(f"  - {sum(1 for e in errors if e.get('row_data'))} errors with row_data")

        return True


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <csv_path> <operation_id>")
        print("\nExample:")
        print(
            f"  {sys.argv[0]} /mnt/extra/josh/code/clz_export_all_columns.csv 19cb376e-e0d5-4aac-8305-edf96a3a8f38"
        )
        sys.exit(1)

    csv_path = sys.argv[1]
    operation_id = sys.argv[2]

    # Normalize operation ID if needed
    if "/" in operation_id:
        operation_id = operation_id.split("/")[-1]

    success = asyncio.run(migrate_operation_with_row_data(csv_path, operation_id))
    sys.exit(0 if success else 1)
