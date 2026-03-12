"""CLI interface for email-issue-indexer."""
from pathlib import Path

import click
import yaml

from .embeddings import EmbeddingEngine
from .indexer import index_directory
from .search import find_similar, format_results
from .store import Store

DEFAULT_CONFIG = Path(__file__).parent.parent.parent / "config.yaml"


def load_config(config_path: Path) -> dict:
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    # Check for config.local.yaml as alternative
    local_path = config_path.parent / "config.local.yaml"
    if local_path.exists():
        with open(local_path) as f:
            return yaml.safe_load(f) or {}
    return {}


def get_store(config: dict) -> Store:
    db_path = Path(config.get("database", "data/index.db"))
    return Store(db_path)


def get_engine(config: dict) -> EmbeddingEngine:
    model = config.get("embedding_model", "all-MiniLM-L6-v2")
    return EmbeddingEngine(model)


@click.group()
@click.option("--config", "config_path", type=click.Path(exists=False),
              default=str(DEFAULT_CONFIG), help="Path to config.yaml")
@click.pass_context
def cli(ctx, config_path):
    """Email Issue Indexer - parse, index, and search email issue threads."""
    ctx.ensure_object(dict)
    ctx.obj["config"] = load_config(Path(config_path))
    ctx.obj["config_path"] = config_path


@cli.command()
@click.option("--dir", "eml_dir", type=click.Path(exists=True),
              help="Directory containing EML files (overrides config)")
@click.option("--batch-size", default=100, help="Emails per batch")
@click.pass_context
def index(ctx, eml_dir, batch_size):
    """Index EML files into the searchable database."""
    config = ctx.obj["config"]
    eml_path = Path(eml_dir) if eml_dir else Path(config.get("eml_directory", "."))

    if not eml_path.exists():
        click.echo(f"Error: directory {eml_path} does not exist", err=True)
        raise SystemExit(1)

    # Markdown output directory
    md_dir = Path(config.get("markdown_directory",
                  str(Path(__file__).parent.parent.parent / "markdown")))

    store = get_store(config)
    engine = get_engine(config)

    # Sync experts from config
    for expert in config.get("experts", []):
        if isinstance(expert, dict) and "email" in expert:
            store.add_expert(expert["email"], expert.get("name", ""))

    try:
        stats = index_directory(eml_path, store, engine, md_dir=md_dir,
                                batch_size=batch_size)
        click.echo(f"\nIndex complete: {stats['processed']} new, "
                    f"{stats['skipped']} unchanged, {stats['errors']} errors")
    finally:
        store.close()


@cli.command()
@click.argument("query")
@click.option("-k", "--top-k", default=10, help="Number of results")
@click.option("--expert-only", is_flag=True, help="Only show expert replies")
@click.option("--show-body", is_flag=True, help="Show message preview")
@click.pass_context
def search(ctx, query, top_k, expert_only, show_body):
    """Search for similar issues by description."""
    config = ctx.obj["config"]
    store = get_store(config)
    engine = get_engine(config)
    boost = config.get("expert_boost", 1.5)

    try:
        results = find_similar(query, store, engine, top_k=top_k,
                               expert_boost=boost, expert_only=expert_only)
        click.echo(format_results(results, show_body=show_body))
    finally:
        store.close()


@cli.command()
@click.argument("query")
@click.option("-k", "--top-k", default=5, help="Number of similar issues to retrieve")
@click.pass_context
def analyze(ctx, query, top_k):
    """Analyze a new issue using expert knowledge from similar past issues (RAG).

    Uses your Claude Code auth - no separate API key needed.
    """
    config = ctx.obj["config"]
    store = get_store(config)
    engine = get_engine(config)
    boost = config.get("expert_boost", 2.0)

    from .rag import analyze as rag_analyze

    try:
        click.echo(f"Retrieving {top_k} similar issues...\n", err=True)
        rag_analyze(query, store, engine, top_k=top_k, expert_boost=boost,
                    system_prompt=config.get("system_prompt"))
    finally:
        store.close()


@cli.command()
@click.argument("email_id", type=int)
@click.pass_context
def show(ctx, email_id):
    """Show the full markdown for an indexed email."""
    config = ctx.obj["config"]
    store = get_store(config)
    try:
        email_record = store.get_email(email_id)
        if email_record:
            click.echo(email_record.markdown)
        else:
            click.echo(f"Email ID {email_id} not found.", err=True)
    finally:
        store.close()


@cli.group()
def experts():
    """Manage the expert engineers list."""
    pass


@experts.command("list")
@click.pass_context
def experts_list(ctx):
    """List all configured expert engineers."""
    config = ctx.obj["config"]
    store = get_store(config)
    try:
        expert_list = store.get_experts()
        if not expert_list:
            click.echo("No experts configured. Use 'eix experts add' to add some.")
            return
        for email_addr, name in expert_list:
            click.echo(f"  {name or '(no name)'} <{email_addr}>")
    finally:
        store.close()


@experts.command("add")
@click.argument("email_addr")
@click.option("--name", default="", help="Engineer's name")
@click.pass_context
def experts_add(ctx, email_addr, name):
    """Add an expert engineer."""
    config = ctx.obj["config"]
    store = get_store(config)
    try:
        store.add_expert(email_addr, name)
        click.echo(f"Added expert: {name or email_addr} <{email_addr}>")
    finally:
        store.close()


@experts.command("remove")
@click.argument("email_addr")
@click.pass_context
def experts_remove(ctx, email_addr):
    """Remove an expert engineer."""
    config = ctx.obj["config"]
    store = get_store(config)
    try:
        store.remove_expert(email_addr)
        click.echo(f"Removed expert: {email_addr}")
    finally:
        store.close()


@cli.command()
@click.pass_context
def stats(ctx):
    """Show index statistics."""
    config = ctx.obj["config"]
    store = get_store(config)
    try:
        s = store.get_stats()
        click.echo(f"Indexed emails:    {s['emails']}")
        click.echo(f"Thread messages:   {s['thread_messages']}")
        click.echo(f"Expert messages:   {s['expert_messages']}")
        click.echo(f"Configured experts: {s['experts']}")
    finally:
        store.close()


if __name__ == "__main__":
    cli()
