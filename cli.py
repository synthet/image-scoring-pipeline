"""
Optional CLI for image-scoring.

Usage:
    python cli.py --help
    python cli.py score <path>
    python cli.py tag <path>
    python cli.py config get <key>
    ...
"""

import json
import signal
import time
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

app = typer.Typer(
    name="image-scoring",
    help="AI image scoring, tagging, and clustering CLI.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
config_app = typer.Typer(help="Manage configuration.", no_args_is_help=True)
app.add_typer(config_app, name="config")

console = Console()
err_console = Console(stderr=True)

# ---------------------------------------------------------------------------
# Lazy initialization
# ---------------------------------------------------------------------------

_db_initialized = False


def _ensure_db():
    """Initialize DB + config once (cheap, no GPU)."""
    global _db_initialized
    if _db_initialized:
        return
    from modules import db, config as cfg
    db.init_db()
    cfg.load_config()
    _db_initialized = True


class _Runners:
    """Lazy runner holder — avoids loading ML models until needed."""

    _scoring = None
    _tagging = None
    _clustering = None
    _selection = None
    _orchestrator = None

    @property
    def scoring(self):
        if self._scoring is None:
            _ensure_db()
            from modules.scoring import ScoringRunner
            self._scoring = ScoringRunner()
        return self._scoring

    @property
    def tagging(self):
        if self._tagging is None:
            _ensure_db()
            from modules.tagging import TaggingRunner
            self._tagging = TaggingRunner()
        return self._tagging

    @property
    def clustering(self):
        if self._clustering is None:
            _ensure_db()
            from modules.clustering import ClusteringRunner
            self._clustering = ClusteringRunner()
        return self._clustering

    @property
    def selection(self):
        if self._selection is None:
            _ensure_db()
            from modules.selection_runner import SelectionRunner
            self._selection = SelectionRunner()
        return self._selection

    @property
    def orchestrator(self):
        if self._orchestrator is None:
            from modules.pipeline_orchestrator import PipelineOrchestrator
            self._orchestrator = PipelineOrchestrator(
                scoring_runner=self.scoring,
                tagging_runner=self.tagging,
                selection_runner=self.selection,
                enable_background_tick=True,
            )
        return self._orchestrator


runners = _Runners()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_original_sigint = signal.getsignal(signal.SIGINT)


def _poll_runner(runner, label: str = "Processing"):
    """Poll a runner's get_status() and render Rich progress until done."""
    # Install Ctrl+C handler to stop the runner gracefully
    def _handler(sig, frame):
        err_console.print("\n[yellow]Stopping...[/yellow]")
        runner.stop()

    signal.signal(signal.SIGINT, _handler)

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(label, total=0)
            while True:
                status = runner.get_status()
                # All runners return 5-tuple: (is_running, log_text, status_msg, current, total)
                # ClusteringEngine returns 4-tuple — but we use ClusteringRunner which is 5-tuple
                is_running = status[0]
                status_msg = status[2] if len(status) > 2 else str(status[1])
                current = status[3] if len(status) > 3 else 0
                total = status[4] if len(status) > 4 else 0

                if total and total > 0:
                    progress.update(task, completed=current, total=total, description=status_msg or label)
                else:
                    progress.update(task, description=status_msg or label)

                if not is_running:
                    break
                time.sleep(0.5)
    finally:
        signal.signal(signal.SIGINT, _original_sigint)


def _print_json(data):
    """Pretty-print JSON to stdout."""
    console.print_json(json.dumps(data, default=str))


# ---------------------------------------------------------------------------
# Config commands
# ---------------------------------------------------------------------------

@config_app.command("get")
def config_get(
    key: str = typer.Argument(..., help="Config key (supports dot notation, e.g. 'scoring.force_rescore_default')"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Read a configuration value."""
    from modules import config as cfg
    value = cfg.get_config_value(key)
    if value is None:
        # Try as section
        section = cfg.get_config_section(key)
        if section:
            value = section
        else:
            err_console.print(f"[red]Key not found:[/red] {key}")
            raise typer.Exit(1)
    if as_json:
        _print_json(value)
    elif isinstance(value, dict):
        _print_json(value)
    else:
        console.print(value)


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Config key (supports dot notation, e.g. scoring.force_rescore_default)"),
    value: str = typer.Argument(..., help="Value to set (JSON-parsed if possible)"),
):
    """Write a configuration value."""
    from modules import config as cfg
    # Try to parse as JSON (for booleans, numbers, lists)
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, ValueError):
        parsed = value
    cfg.save_config_value(key, parsed)
    console.print(f"[green]Set[/green] {key} = {parsed!r}")


@config_app.command("show")
def config_show():
    """Show the full configuration."""
    from modules import config as cfg
    data = cfg.load_config()
    _print_json(data)


# ---------------------------------------------------------------------------
# Status command
# ---------------------------------------------------------------------------

@app.command()
def status(
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show runner and pipeline status."""
    _ensure_db()
    from modules import scoring, tagging, clustering

    statuses = {}
    # Check each runner type — only if already instantiated
    for name, cls in [("scoring", scoring.ScoringRunner), ("tagging", tagging.TaggingRunner), ("clustering", clustering.ClusteringRunner)]:
        runner_inst = getattr(runners, f"_{name}", None)
        if runner_inst is not None:
            s = runner_inst.get_status()
            statuses[name] = {
                "running": s[0],
                "message": s[2] if len(s) > 2 else str(s[1]),
                "current": s[3] if len(s) > 3 else 0,
                "total": s[4] if len(s) > 4 else 0,
            }
        else:
            statuses[name] = {"running": False, "message": "Not initialized"}

    if as_json:
        _print_json(statuses)
        return

    table = Table(title="Runner Status")
    table.add_column("Runner", style="bold")
    table.add_column("Running")
    table.add_column("Message")
    table.add_column("Progress")

    for name, s in statuses.items():
        running = "[green]Yes[/green]" if s["running"] else "[dim]No[/dim]"
        progress_str = f"{s.get('current', 0)}/{s.get('total', 0)}" if s.get('total') else "-"
        table.add_row(name, running, s.get("message", "-"), progress_str)

    console.print(table)


# ---------------------------------------------------------------------------
# Jobs command
# ---------------------------------------------------------------------------

@app.command()
def jobs(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of recent jobs to show"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List recent jobs."""
    _ensure_db()
    from modules import db

    rows = db.get_jobs(limit=limit)
    if as_json:
        _print_json([dict(r) for r in rows])
        return

    if not rows:
        console.print("[dim]No jobs found.[/dim]")
        return

    table = Table(title=f"Recent Jobs (limit {limit})")
    table.add_column("ID", style="bold")
    table.add_column("Type")
    table.add_column("Status")
    table.add_column("Input Path")
    table.add_column("Created")

    for row in rows:
        r = dict(row)
        status_style = {
            "completed": "green",
            "running": "yellow",
            "failed": "red",
            "queued": "cyan",
            "cancelled": "dim",
        }.get(str(r.get("status", "")).lower(), "")
        status_text = f"[{status_style}]{r.get('status', '')}[/{status_style}]" if status_style else str(r.get("status", ""))
        table.add_row(
            str(r.get("id", "")),
            str(r.get("job_type", "") or r.get("phase_code", "") or ""),
            status_text,
            str(r.get("input_path", "") or "")[:60],
            str(r.get("created_at", "") or "")[:19],
        )

    console.print(table)


# ---------------------------------------------------------------------------
# Query command
# ---------------------------------------------------------------------------

@app.command()
def query(
    folder: Optional[str] = typer.Option(None, "--folder", "-f", help="Filter by folder path"),
    keyword: Optional[str] = typer.Option(None, "--keyword", "-k", help="Filter by keyword"),
    sort: str = typer.Option("score", "--sort", "-s", help="Sort column"),
    order: str = typer.Option("desc", "--order", "-o", help="Sort order (asc/desc)"),
    rating: Optional[List[int]] = typer.Option(None, "--rating", "-r", help="Filter by rating (repeatable)"),
    limit: int = typer.Option(25, "--limit", "-n", help="Page size"),
    page: int = typer.Option(1, "--page", "-p", help="Page number"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Query images from the database."""
    _ensure_db()
    from modules import db

    rows, total = db.get_images_paginated_with_count(
        page=page,
        page_size=limit,
        sort_by=sort,
        order=order,
        rating_filter=rating,
        keyword_filter=keyword,
        folder_path=folder,
    )

    if as_json:
        _print_json({"total": total, "page": page, "page_size": limit, "results": [dict(r) for r in rows]})
        return

    total_pages = max(1, (total + limit - 1) // limit)
    console.print(f"[dim]Page {page}/{total_pages} ({total} total)[/dim]\n")

    if not rows:
        console.print("[dim]No images found.[/dim]")
        return

    table = Table()
    table.add_column("File", max_width=50)
    table.add_column("Score", justify="right")
    table.add_column("Rating", justify="center")
    table.add_column("Label", justify="center")
    table.add_column("Keywords", max_width=40)

    for row in rows:
        r = dict(row)
        fp = str(r.get("file_path", ""))
        name = Path(fp).name if fp else ""
        score = r.get("score", r.get("score_general", ""))
        score_str = f"{float(score):.2f}" if score is not None and score != "" else "-"
        rating_val = str(r.get("rating", "") or "-")
        label = str(r.get("label", "") or "-")
        kw = str(r.get("keywords", "") or "-")[:40]
        table.add_row(name, score_str, rating_val, label, kw)

    console.print(table)


# ---------------------------------------------------------------------------
# Export command
# ---------------------------------------------------------------------------

@app.command()
def export(
    output: str = typer.Argument(..., help="Output file path (.csv, .json, or .xlsx)"),
    folder: Optional[str] = typer.Option(None, "--folder", help="Filter by folder path"),
    keyword: Optional[str] = typer.Option(None, "--keyword", help="Filter by keyword"),
):
    """Export database to CSV, JSON, or Excel."""
    _ensure_db()
    from modules import db

    ext = Path(output).suffix.lower()
    kwargs = {}
    if folder:
        kwargs["folder_path"] = folder
    if keyword:
        kwargs["keyword_filter"] = keyword

    try:
        if ext == ".csv":
            ok, msg = db.export_db_to_csv(output, **kwargs)
        elif ext == ".json":
            ok, msg = db.export_db_to_json(output, **kwargs)
        elif ext in (".xlsx", ".xls"):
            ok, msg = db.export_db_to_excel(output, **kwargs)
        else:
            err_console.print(f"[red]Unsupported format:[/red] {ext}  (use .csv, .json, or .xlsx)")
            raise typer.Exit(1)
        if not ok:
            err_console.print(f"[red]Export failed:[/red] {msg}")
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        err_console.print(f"[red]Export failed:[/red] {e}")
        raise typer.Exit(1)

    console.print(f"[green]Exported to[/green] {output}")


# ---------------------------------------------------------------------------
# Score command
# ---------------------------------------------------------------------------

@app.command()
def score(
    path: str = typer.Argument(..., help="Folder path containing images to score"),
    skip_existing: bool = typer.Option(True, "--skip-existing/--no-skip-existing", help="Skip already-scored images"),
):
    """Batch score images in a folder."""
    _ensure_db()
    from modules import db

    folder = Path(path)
    if not folder.exists():
        err_console.print(f"[red]Path not found:[/red] {path}")
        raise typer.Exit(1)

    job_id = db.create_job(input_path=str(folder), phase_code="scoring", status="running")
    console.print(f"[bold]Starting scoring job #{job_id}[/bold] on {folder}")

    result = runners.scoring.start_batch(
        input_path=str(folder),
        job_id=job_id,
        skip_existing=skip_existing,
    )
    if result and "Error" in str(result):
        err_console.print(f"[red]{result}[/red]")
        raise typer.Exit(1)

    _poll_runner(runners.scoring, label="Scoring")
    console.print("[green]Scoring complete.[/green]")


# ---------------------------------------------------------------------------
# Tag command
# ---------------------------------------------------------------------------

@app.command()
def tag(
    path: str = typer.Argument(..., help="Folder path containing images to tag"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing keywords"),
    captions: bool = typer.Option(False, "--captions", help="Generate BLIP captions"),
    keywords: Optional[List[str]] = typer.Option(None, "--keyword", "-k", help="Custom keywords (repeatable)"),
):
    """Batch tag images in a folder."""
    _ensure_db()
    from modules import db

    folder = Path(path)
    if not folder.exists():
        err_console.print(f"[red]Path not found:[/red] {path}")
        raise typer.Exit(1)

    job_id = db.create_job(input_path=str(folder), phase_code="keywords", status="running")
    console.print(f"[bold]Starting tagging job #{job_id}[/bold] on {folder}")

    result = runners.tagging.start_batch(
        input_path=str(folder),
        job_id=job_id,
        custom_keywords=keywords or None,
        overwrite=overwrite,
        generate_captions=captions,
    )
    if result and "Error" in str(result):
        err_console.print(f"[red]{result}[/red]")
        raise typer.Exit(1)

    _poll_runner(runners.tagging, label="Tagging")
    console.print("[green]Tagging complete.[/green]")


# ---------------------------------------------------------------------------
# Cluster command
# ---------------------------------------------------------------------------

@app.command()
def cluster(
    path: str = typer.Argument(..., help="Folder path containing images to cluster"),
    threshold: Optional[float] = typer.Option(None, "--threshold", "-t", help="Similarity threshold"),
    time_gap: Optional[int] = typer.Option(None, "--time-gap", help="Time gap in seconds"),
    force: bool = typer.Option(False, "--force", "-f", help="Force rescan"),
):
    """Cluster images into stacks."""
    _ensure_db()
    from modules import db

    folder = Path(path)
    if not folder.exists():
        err_console.print(f"[red]Path not found:[/red] {path}")
        raise typer.Exit(1)

    job_id = db.create_job(input_path=str(folder), phase_code="culling", status="running")
    console.print(f"[bold]Starting clustering job #{job_id}[/bold] on {folder}")

    result = runners.clustering.start_batch(
        input_path=str(folder),
        job_id=job_id,
        threshold=threshold,
        time_gap=time_gap,
        force_rescan=force,
    )
    if result and "Error" in str(result):
        err_console.print(f"[red]{result}[/red]")
        raise typer.Exit(1)

    _poll_runner(runners.clustering, label="Clustering")
    console.print("[green]Clustering complete.[/green]")


# ---------------------------------------------------------------------------
# Propagate-tags command
# ---------------------------------------------------------------------------

@app.command(name="propagate-tags")
def propagate_tags_cmd(
    path: Optional[str] = typer.Argument(None, help="Folder path (omit for all images)"),
    dry_run: bool = typer.Option(True, "--dry-run/--apply", help="Preview changes vs apply them"),
    k: Optional[int] = typer.Option(None, "--k", help="Number of neighbors"),
    min_similarity: Optional[float] = typer.Option(None, "--min-similarity", help="Minimum cosine similarity"),
):
    """Propagate tags from tagged images to untagged neighbors."""
    _ensure_db()
    from modules.tagging import propagate_tags

    kwargs = {"folder_path": path, "dry_run": dry_run}
    if k is not None:
        kwargs["k"] = k
    if min_similarity is not None:
        kwargs["min_similarity"] = min_similarity

    mode_label = "[yellow]DRY RUN[/yellow]" if dry_run else "[green]APPLY[/green]"
    console.print(f"[bold]Propagating tags[/bold] {mode_label}")

    with console.status("Propagating tags..."):
        result = propagate_tags(**kwargs)

    if isinstance(result, dict):
        _print_json(result)
    else:
        console.print(result)


# ---------------------------------------------------------------------------
# Pipeline command
# ---------------------------------------------------------------------------

@app.command()
def pipeline(
    path: str = typer.Argument(..., help="Folder path to run the full pipeline on"),
):
    """Run the full processing pipeline (score + tag + cluster + select) on a folder."""
    _ensure_db()
    from modules import phase_executors

    # Register phase executors like the WebUI does
    phase_executors.register_all(
        scoring_runner=runners.scoring,
        tagging_runner=runners.tagging,
        selection_runner=runners.selection,
    )

    folder = Path(path)
    if not folder.exists():
        err_console.print(f"[red]Path not found:[/red] {path}")
        raise typer.Exit(1)

    console.print(f"[bold]Starting pipeline[/bold] on {folder}")
    result = runners.orchestrator.start(str(folder))
    if result and "already running" in str(result).lower():
        err_console.print(f"[red]{result}[/red]")
        raise typer.Exit(1)

    # Poll orchestrator status
    def _handler(sig, frame):
        err_console.print("\n[yellow]Stopping pipeline...[/yellow]")
        runners.orchestrator.stop()

    signal.signal(signal.SIGINT, _handler)

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Pipeline", total=0)
            while True:
                s = runners.orchestrator.get_status()
                is_active = s.get("active", False)
                phase = s.get("current_phase", "")
                phase_label = f"Pipeline: {phase}" if phase else "Pipeline"

                # Try to get current runner progress
                current, total = 0, 0
                for runner_name in ["scoring", "tagging", "clustering", "selection"]:
                    inst = getattr(runners, f"_{runner_name}", None)
                    if inst is not None:
                        rs = inst.get_status()
                        if rs[0]:  # is_running
                            current = rs[3] if len(rs) > 3 else 0
                            total = rs[4] if len(rs) > 4 else 0
                            break

                if total and total > 0:
                    progress.update(task, completed=current, total=total, description=phase_label)
                else:
                    progress.update(task, description=phase_label)

                if not is_active:
                    break
                time.sleep(0.5)
    finally:
        signal.signal(signal.SIGINT, _original_sigint)

    console.print("[green]Pipeline complete.[/green]")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()
