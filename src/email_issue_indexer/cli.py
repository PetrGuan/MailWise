"""CLI interface for MailWise."""
from pathlib import Path

import click
import yaml

from .embeddings import EmbeddingEngine
from .indexer import index_directory
from .search import find_similar, format_results
from .store import Store

DEFAULT_CONFIG = Path(__file__).parent.parent.parent / "config.yaml"

BANNER = """
  __  __       _ ___        ___
 |  \\/  | __ _(_) \\ \\      / (_)___  ___
 | |\\/| |/ _` | | |\\ \\ /\\ / /| / __|/ _ \\
 | |  | | (_| | | | \\ V  V / | \\__ \\  __/
 |_|  |_|\\__,_|_|_|  \\_/\\_/  |_|___/\\___|
"""


def load_config(config_path: Path) -> dict:
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
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
    """MailWise - Turn email threads into a searchable knowledge base.

    Parse EML files, index with embeddings, and use RAG to learn how
    your best engineers analyze issues.

    \b
    Quick start:
      1. Put .eml files in the emails/ directory
      2. Run: mailwise index
      3. Run: mailwise search "your issue description"
      4. Run: mailwise analyze "your issue description"  (deep RAG analysis)

    \b
    Tip: For best results with 'analyze', paste the full bug report
    content rather than just a short title. More context = better matches.
    """
    ctx.ensure_object(dict)
    config = load_config(Path(config_path))
    ctx.obj["config"] = config
    ctx.obj["config_path"] = config_path

    if not config and not Path(config_path).exists():
        click.echo("Warning: No config.yaml found. Copy config.example.yaml "
                    "to config.yaml and edit it.", err=True)
        click.echo("  cp config.example.yaml config.yaml\n", err=True)


@cli.command()
@click.option("--dir", "eml_dir", type=click.Path(exists=True),
              help="Directory containing EML files (overrides config)")
@click.option("--batch-size", default=200, help="Emails per batch")
@click.pass_context
def index(ctx, eml_dir, batch_size):
    """Index EML files into the searchable database.

    \b
    Scans the configured eml_directory for .eml files, parses email
    threads, generates embeddings, and stores everything in SQLite.
    Also writes structured markdown files to the markdown/ directory.

    \b
    Features:
      - Incremental: only processes new or changed files
      - Parallel: parses EML files using multiple CPU cores
      - Resumable: safe to interrupt and re-run

    \b
    Examples:
      mailwise index                    # Index from configured directory
      mailwise index --dir ~/emails     # Index from a specific directory
    """
    config = ctx.obj["config"]
    eml_path = Path(eml_dir) if eml_dir else Path(config.get("eml_directory", "."))

    if not eml_path.exists():
        click.echo(f"Error: directory '{eml_path}' does not exist.", err=True)
        click.echo("Set 'eml_directory' in config.yaml or use --dir.", err=True)
        raise SystemExit(1)

    md_dir = Path(config.get("markdown_directory",
                  str(Path(__file__).parent.parent.parent / "markdown")))

    store = get_store(config)
    engine = get_engine(config)

    # Sync experts from config
    experts_synced = 0
    for expert in config.get("experts", []):
        if isinstance(expert, dict) and "email" in expert:
            store.add_expert(expert["email"], expert.get("name", ""))
            experts_synced += 1

    try:
        stats = index_directory(eml_path, store, engine, md_dir=md_dir,
                                batch_size=batch_size)

        click.echo(f"\nIndex complete: {stats['processed']} new, "
                    f"{stats['skipped']} unchanged, {stats['errors']} errors")

        if stats['processed'] > 0:
            s = store.get_stats()
            click.echo(f"\nDatabase summary:")
            click.echo(f"  Total emails:     {s['emails']}")
            click.echo(f"  Thread messages:  {s['thread_messages']}")
            click.echo(f"  Expert messages:  {s['expert_messages']}")
            click.echo(f"  Experts tracked:  {s['experts']}")
            click.echo(f"\nNext steps:")
            click.echo(f"  mailwise search \"describe your issue here\"")
            click.echo(f"  mailwise analyze \"paste full bug report here\"")

        if stats['processed'] > 0 and store.get_stats()['experts'] == 0:
            click.echo(f"\nTip: No expert engineers configured yet. "
                        f"Add your best engineers to boost their replies:")
            click.echo(f"  mailwise experts add engineer@company.com --name \"Jane Doe\"")
    finally:
        store.close()


@cli.command()
@click.argument("query")
@click.option("-k", "--top-k", default=10, help="Number of results to show")
@click.option("--expert-only", is_flag=True,
              help="Only show replies from expert engineers")
@click.option("--show-body", is_flag=True,
              help="Show a preview of each matching message")
@click.pass_context
def search(ctx, query, top_k, expert_only, show_body):
    """Find similar past issues using semantic search.

    \b
    Uses embeddings to find issues with similar meaning, not just
    keyword matching. Expert engineers' replies are boosted in results.

    \b
    Tips:
      - Use natural language: "email disappears after sync"
      - Be specific for better results: include error codes, API names,
        platform details (Mac/Windows/iOS)
      - Use --show-body to preview matching messages
      - Use --expert-only to see only what your best engineers said
      - Use 'mailwise show <ID>' to read the full thread

    \b
    Examples:
      mailwise search "calendar sync failure"
      mailwise search "attachment crashes on iOS" --show-body
      mailwise search "deleted items reappear" --expert-only -k 5
    """
    config = ctx.obj["config"]
    store = get_store(config)
    engine = get_engine(config)
    boost = config.get("expert_boost", 1.5)

    try:
        s = store.get_stats()
        if s['emails'] == 0:
            click.echo("No emails indexed yet. Run 'mailwise index' first.")
            return

        results = find_similar(query, store, engine, top_k=top_k,
                               expert_boost=boost, expert_only=expert_only)
        output = format_results(results, show_body=show_body)
        click.echo(output)

        if results and not show_body:
            click.echo("Tip: Add --show-body to preview matching messages, "
                        "or run 'mailwise show <Email ID>' for the full thread.")

        if not results and expert_only:
            click.echo("Tip: No expert matches found. Try without --expert-only "
                        "to search all messages.")
    finally:
        store.close()


@cli.command()
@click.argument("query")
@click.option("-k", "--top-k", default=5,
              help="Number of similar issues to feed to Claude")
@click.pass_context
def analyze(ctx, query, top_k):
    """Deep analysis of an issue using RAG with expert knowledge.

    \b
    Finds similar past issues, then asks Claude to analyze patterns
    in how your expert engineers investigated and resolved them.
    Claude will suggest root causes, debugging approaches, and next steps.

    \b
    This command requires Claude Code to be installed and authenticated.
    It uses your existing Claude Code auth — no separate API key needed.

    \b
    Tips:
      - Paste the FULL bug report for best results, not just a title.
        More context (error codes, logs, environment) = better matches.
      - Increase -k for broader analysis across more past issues.
      - Expert engineers' replies are highlighted and weighted heavily.

    \b
    Examples:
      mailwise analyze "user reports calendar not syncing on Mac"
      mailwise analyze "$(cat bug_report.txt)"
      mailwise analyze "emails moved to local folder reappear after 30 min" -k 10
    """
    config = ctx.obj["config"]
    store = get_store(config)
    engine = get_engine(config)
    boost = config.get("expert_boost", 2.0)

    from .rag import analyze as rag_analyze

    try:
        s = store.get_stats()
        if s['emails'] == 0:
            click.echo("No emails indexed yet. Run 'mailwise index' first.")
            return

        click.echo(f"Searching {s['emails']} indexed emails for similar issues...",
                    err=True)
        click.echo(f"Feeding top {top_k} matches to Claude for analysis...\n",
                    err=True)

        result = rag_analyze(query, store, engine, top_k=top_k,
                             expert_boost=boost,
                             system_prompt=config.get("system_prompt"))

        if result and result != "No similar issues found in the index. Try indexing more emails first.":
            click.echo("\n---")
            click.echo("Tip: Run 'mailwise search \"same query\" --show-body' "
                        "to see the raw source threads.", err=True)
    finally:
        store.close()


@cli.command()
@click.argument("email_id", type=int)
@click.pass_context
def show(ctx, email_id):
    """Display the full markdown for an indexed email thread.

    \b
    Shows the complete parsed thread with all replies, timestamps,
    and [Expert] tags. Use this to read the full context after finding
    an issue via 'mailwise search'.

    \b
    Example:
      mailwise show 42
    """
    config = ctx.obj["config"]
    store = get_store(config)
    try:
        email_record = store.get_email(email_id)
        if email_record:
            click.echo(email_record.markdown)
        else:
            click.echo(f"Email ID {email_id} not found.", err=True)
            click.echo("Run 'mailwise search' to find valid email IDs.", err=True)
    finally:
        store.close()


@cli.group()
def experts():
    """Manage the expert engineers list.

    \b
    Expert engineers get special treatment:
      - Their replies are tagged with [Expert] in markdown output
      - Their messages get a score boost in search results
      - Claude pays extra attention to their analysis in 'analyze' mode

    \b
    You can also configure experts in config.yaml under the 'experts' key.
    """
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
            click.echo("No experts configured yet.\n")
            click.echo("Add your team's best engineers so their replies get "
                        "boosted in search and highlighted in output:")
            click.echo("  mailwise experts add engineer@company.com --name \"Jane Doe\"\n")
            click.echo("Or add them in config.yaml under the 'experts' key.")
            return
        click.echo(f"Expert engineers ({len(expert_list)}):\n")
        for email_addr, name in expert_list:
            click.echo(f"  {name or '(no name)'} <{email_addr}>")
        click.echo(f"\nTheir replies get a score boost in search "
                    f"and [Expert] tags in markdown output.")
    finally:
        store.close()


@experts.command("add")
@click.argument("email_addr")
@click.option("--name", default="", help="Engineer's display name")
@click.pass_context
def experts_add(ctx, email_addr, name):
    """Add an expert engineer by email address.

    \b
    Examples:
      mailwise experts add senior.dev@company.com --name "Jane Doe"
      mailwise experts add tech.lead@company.com
    """
    config = ctx.obj["config"]
    store = get_store(config)
    try:
        store.add_expert(email_addr, name)
        click.echo(f"Added expert: {name or email_addr} <{email_addr}>")
        click.echo("\nTip: Re-run 'mailwise index' to re-tag existing "
                    "messages from this expert.")
    finally:
        store.close()


@experts.command("remove")
@click.argument("email_addr")
@click.pass_context
def experts_remove(ctx, email_addr):
    """Remove an expert engineer by email address."""
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
    """Show index statistics and health summary.

    \b
    Displays the current state of your MailWise index including
    email count, message count, and expert coverage.
    """
    config = ctx.obj["config"]
    store = get_store(config)
    try:
        s = store.get_stats()

        click.echo(BANNER.strip())
        click.echo("")
        click.echo(f"  Indexed emails:     {s['emails']:,}")
        click.echo(f"  Thread messages:    {s['thread_messages']:,}")
        click.echo(f"  Expert messages:    {s['expert_messages']:,}")
        click.echo(f"  Configured experts: {s['experts']}")

        if s['emails'] > 0 and s['thread_messages'] > 0:
            avg = s['thread_messages'] / s['emails']
            coverage = (s['expert_messages'] / s['thread_messages'] * 100
                        if s['thread_messages'] > 0 else 0)
            click.echo(f"\n  Avg replies/thread: {avg:.1f}")
            click.echo(f"  Expert coverage:    {coverage:.1f}% of messages")

        if s['emails'] == 0:
            click.echo(f"\n  No emails indexed yet. Get started:")
            click.echo(f"    1. Put .eml files in the emails/ directory")
            click.echo(f"    2. Run: mailwise index")
        elif s['experts'] == 0:
            click.echo(f"\n  Tip: Add expert engineers to boost their replies:")
            click.echo(f"    mailwise experts add engineer@company.com --name \"Name\"")
        else:
            click.echo(f"\n  Ready to use:")
            click.echo(f"    mailwise search \"describe your issue\"")
            click.echo(f"    mailwise analyze \"paste full bug report\"")
    finally:
        store.close()


if __name__ == "__main__":
    cli()
