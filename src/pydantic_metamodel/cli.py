"""Command line interface for :mod:`pydantic_metamodel`."""

import click

__all__ = [
    "main",
]


@click.command()
def main() -> None:
    """CLI for pydantic_metamodel."""


if __name__ == "__main__":
    main()
