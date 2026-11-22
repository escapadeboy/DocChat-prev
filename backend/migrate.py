#!/usr/bin/env python3
"""
Simple migration script to run Alembic migrations.
Usage: python migrate.py
"""
import subprocess
import sys
import os

def run_migrations():
    """Run Alembic migrations to upgrade database to head."""
    try:
        # Change to backend directory if not already there
        backend_dir = os.path.dirname(os.path.abspath(__file__))
        os.chdir(backend_dir)
        
        print("Running database migrations...")
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            check=True,
            capture_output=False
        )
        print("\n✓ Migrations completed successfully!")
        return 0
    except subprocess.CalledProcessError as e:
        print(f"\n✗ Migration failed with error code {e.returncode}", file=sys.stderr)
        return e.returncode
    except FileNotFoundError:
        print("\n✗ Alembic not found. Make sure it's installed: pip install alembic", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(run_migrations())

