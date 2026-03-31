"""Copy the fixture repository template into a target directory."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def copy_template(target_dir: Path, force: bool) -> None:
    template_dir = Path(__file__).resolve().parents[2] / "e2e" / "fixture_repo_template"
    target_dir.mkdir(parents=True, exist_ok=True)

    for source in template_dir.rglob("*"):
        relative_path = source.relative_to(template_dir)
        destination = target_dir / relative_path

        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue

        if destination.exists() and not force:
            raise FileExistsError(f"{destination} already exists. Re-run with --force to overwrite.")

        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap the dbt-governance fixture repository template.")
    parser.add_argument("target_dir", help="Directory to write the fixture repo template into.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files in the target directory.")
    args = parser.parse_args()

    copy_template(Path(args.target_dir).resolve(), force=args.force)
    print(f"Fixture repo template copied to {Path(args.target_dir).resolve()}")


if __name__ == "__main__":
    main()
