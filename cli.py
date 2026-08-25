#!/usr/bin/env python3
"""
CLI TUI Interface
"""

from __future__ import annotations

import argparse
import json
import sys
import typing
from pathlib import Path

# Compatibility shims for Python 3.10 and older Linux sqlite3
try:
    __import__("pysqlite3")
    sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")
except ImportError:
    pass

try:
    import typing_extensions
    if not hasattr(typing, "NotRequired"):
        typing.NotRequired = getattr(typing_extensions, "NotRequired", None)
    if not hasattr(typing, "Required"):
        typing.Required = getattr(typing_extensions, "Required", None)
except ImportError:
    pass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from app.config import config
from app.evaluation.evaluator import RAGEvaluator
from app.pipeline.events import PipelineEvent
from app.pipeline.rag_pipeline import IngestionResult, QueryResult, RAGPipeline

console = Console()


# Centralized CLI Theme and Glyphs
_THEME_PATH = Path(__file__).resolve().parent / "assets" / "configs" / "cli_theme.json"


def _load_cli_theme() -> dict[str, dict[str, str]]:
    """Load CLI theme asset with built-in resilient fallback."""
    if _THEME_PATH.is_file():
        try:
            with open(_THEME_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "icons": {
            "status_waiting": "⏳",
            "status_running": "⚡",
            "status_completed": "✔",
            "status_failed": "✖",
            "status_default": "•",
            "test_passed": "✔",
            "test_failed": "✖",
            "bullet": "•",
            "prompt_arrow": "›",
        },
        "colors": {
            "status_waiting": "yellow",
            "status_running": "cyan",
            "status_completed": "green",
            "status_failed": "red",
            "status_default": "white",
            "banner_border": "green",
            "table_primary_border": "green",
            "table_accent_border": "cyan",
            "warning_border": "yellow",
            "error_color": "bold red",
            "success_color": "bold green",
            "info_color": "bold cyan",
        },
    }


UI_THEME = _load_cli_theme()


def print_banner():
    """Print the Doc-QA Assistant CLI header banner."""
    banner_text = Text()
    banner_text.append(f"(v{config.version})\n", style=UI_THEME["colors"]["success_color"])
    banner_text.append("Educational, transparent RAG system with persistent ChromaDB & LiteLLM", style="dim")
    console.print(Panel(banner_text, border_style=UI_THEME["colors"]["banner_border"], expand=False))


def cli_event_listener(event: PipelineEvent):
    """Real-time event printer for truthful CLI observability."""
    status_key = f"status_{event.status.value.lower()}"
    status_icon = UI_THEME["icons"].get(status_key, UI_THEME["icons"]["status_default"])
    stage_color = UI_THEME["colors"].get(status_key, UI_THEME["colors"]["status_default"])

    console.print(f"  {status_icon} [{stage_color}]{event.stage.value:<20}[/{stage_color}] {event.message}")


def handle_ingest(pipeline: RAGPipeline, file_path: str, chunk_size: int = None, chunk_overlap: int = None):
    """Ingest a single document file."""
    path = Path(file_path)
    if not path.exists():
        console.print(f"[{UI_THEME['colors']['error_color']}]Error:[/{UI_THEME['colors']['error_color']}] File not found: {file_path}")
        sys.exit(1)

    console.print(f"\n[{UI_THEME['colors']['success_color']}=== Ingesting Document: {path.name} ===[/{UI_THEME['colors']['success_color']}]")
    try:
        res: IngestionResult = pipeline.ingest_document(
            file_path=path,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            event_callback=cli_event_listener,
        )

        table = Table(title="Ingestion Summary", border_style=UI_THEME["colors"]["table_primary_border"])
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="bold white")
        table.add_row("Document ID", res.doc_id[:12] + "...")
        table.add_row("Filename", res.filename)
        table.add_row("File Type", res.file_type.upper())
        table.add_row("Total Characters", str(res.total_chars))
        table.add_row("Page Count", str(res.page_count))
        table.add_row("Chunks Created", str(res.chunk_count))
        table.add_row("Est. Token Count", str(res.total_tokens_estimate))
        table.add_row("Duration", f"{res.duration_ms:.1f} ms")
        console.print(table)

    except Exception as err:
        console.print(f"\n[{UI_THEME['colors']['error_color']}]Ingestion Failed:[/{UI_THEME['colors']['error_color']}] {err}")
        sys.exit(1)


def handle_ingest_samples(pipeline: RAGPipeline):
    """Ingest all sample documents from data/sample_documents/."""
    samples_dir = Path(config.storage.samples_dir)
    if not samples_dir.exists():
        console.print(f"[{UI_THEME['colors']['error_color']}]Error:[/{UI_THEME['colors']['error_color']}] Sample documents directory not found: {samples_dir}")
        return

    files = sorted(list(samples_dir.glob("*.txt")) + list(samples_dir.glob("*.pdf")))
    if not files:
        console.print(f"[yellow]No sample documents found in {samples_dir}[/yellow]")
        return

    console.print(f"\n[{UI_THEME['colors']['success_color']}=== Ingesting {len(files)} Sample Documents ===[/{UI_THEME['colors']['success_color']}]")
    for f in files:
        handle_ingest(pipeline, str(f))


def handle_ask(pipeline: RAGPipeline, question: str, inspect_prompt: bool = False, top_k: int = None):
    """Submit a question to the RAG pipeline and display transparent results."""
    console.print(f"\n[{UI_THEME['colors']['success_color']}=== Processing Question ===[/{UI_THEME['colors']['success_color']}]")
    console.print(f"[{UI_THEME['colors']['info_color']}]Question:[/{UI_THEME['colors']['info_color']}] {question}\n")

    try:
        res: QueryResult = pipeline.answer_query(
            query=question,
            top_k=top_k,
            event_callback=cli_event_listener,
        )

        # 1. Retrieved Context Table
        if res.retrieved_chunks:
            ret_table = Table(title="Retrieved Context Chunks (ChromaDB)", border_style=UI_THEME["colors"]["table_accent_border"])
            ret_table.add_column("Rank", justify="center", style="bold")
            ret_table.add_column("Source", style="cyan")
            ret_table.add_column("Page", justify="center")
            ret_table.add_column("Distance", justify="right")
            ret_table.add_column("Similarity", justify="right", style="green")
            ret_table.add_column("Snippet Preview", style="dim")

            for c in res.retrieved_chunks:
                snippet = c.content[:80].replace("\n", " ") + "..."
                ret_table.add_row(
                    str(c.rank),
                    c.source_filename,
                    str(c.page_number),
                    f"{c.distance:.3f}",
                    f"{c.similarity:.3f}",
                    snippet,
                )
            console.print(ret_table)

        # 2. Inspect Augmented Prompt if requested
        if inspect_prompt:
            console.print(f"\n[{UI_THEME['colors']['warning_border']}]=== Inspecting Augmented Prompt ===[/{UI_THEME['colors']['warning_border']}]")
            console.print(Panel(res.prompt.full_prompt_text, title="Augmented Prompt", border_style=UI_THEME["colors"]["warning_border"]))

        # 3. Grounded Answer Panel
        ans_color = UI_THEME["colors"]["warning_border"] if res.is_refusal else UI_THEME["colors"]["banner_border"]
        ans_title = "Guardrail Refusal (No Grounding Context)" if res.is_refusal else "Grounded Answer"

        console.print(f"\n[bold {ans_color}]=== {ans_title} ===[/bold {ans_color}]")
        console.print(Panel(res.answer, border_style=ans_color, padding=(1, 2)))

        # 4. Citations
        if res.citations and not res.is_refusal:
            cit_table = Table(title="Source Citations", border_style=UI_THEME["colors"]["table_primary_border"])
            cit_table.add_column("Ref", justify="center", style="bold green")
            cit_table.add_column("Document", style="cyan")
            cit_table.add_column("Page", justify="center")
            cit_table.add_column("Relevance", justify="right")
            for cit in res.citations:
                cit_table.add_row(
                    f"[Source {cit.source_index}]",
                    cit.filename,
                    f"Page {cit.page_number}",
                    f"{cit.similarity:.3f}",
                )
            console.print(cit_table)

        # 5. Metadata summary
        console.print(
            f"[dim]Model: {res.generation.model} | Latency: {res.duration_ms:.1f}ms | Tokens: {res.generation.total_tokens} (prompt: {res.generation.prompt_tokens}, comp: {res.generation.completion_tokens})[/dim]\n"
        )

    except Exception as err:
        console.print(f"\n[{UI_THEME['colors']['error_color']}]Query Failed:[/{UI_THEME['colors']['error_color']}] {err}")


def handle_status(pipeline: RAGPipeline):
    """Display vector store statistics and indexed documents."""
    stats = pipeline.vector_store.get_collection_stats()

    table = Table(title="Vector Database Status (ChromaDB)", border_style=UI_THEME["colors"]["table_primary_border"])
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="bold white")
    table.add_row("Collection Name", stats["collection_name"])
    table.add_row("Persistence Path", stats["persist_directory"])
    table.add_row("Total Indexed Chunks", str(stats["total_chunks"]))
    table.add_row("Unique Documents", str(stats["total_documents"]))
    console.print(table)

    if stats["documents"]:
        doc_table = Table(title="Indexed Documents", border_style=UI_THEME["colors"]["table_accent_border"])
        doc_table.add_column("Filename", style="bold white")
        doc_table.add_column("Type", style="cyan")
        doc_table.add_column("Chunks", justify="center")
        doc_table.add_column("Pages", justify="center")
        doc_table.add_column("Est. Tokens", justify="right")
        doc_table.add_column("Doc ID", style="dim")

        for d in stats["documents"]:
            doc_table.add_row(
                d["filename"],
                d["file_type"].upper(),
                str(d["chunk_count"]),
                str(d["page_count"]),
                str(d["total_tokens_estimate"]),
                d["doc_id"][:12] + "...",
            )
        console.print(doc_table)


def handle_evaluate(pipeline: RAGPipeline):
    """Run the 8-10 benchmark test cases and display formatted results."""
    console.print(f"\n[{UI_THEME['colors']['success_color']}]=== Running Automated RAG Evaluation Benchmark ===[/{UI_THEME['colors']['success_color']}]")
    evaluator = RAGEvaluator(pipeline)
    report = evaluator.run_benchmark()

    # Results Table
    table = Table(title="Benchmark Test Case Results", border_style=UI_THEME["colors"]["table_primary_border"])
    table.add_column("ID", style="bold")
    table.add_column("Category", style="cyan")
    table.add_column("Question Preview", style="white")
    table.add_column("Retrieval", justify="center")
    table.add_column("Grounding", justify="center")
    table.add_column("Refusal", justify="center")
    table.add_column("Status", justify="center", style="bold")
    table.add_column("Latency", justify="right")

    pass_icon = UI_THEME["icons"]["test_passed"]
    fail_icon = UI_THEME["icons"]["test_failed"]

    for r in report.results:
        ret_icon = pass_icon if r.retrieval_passed else fail_icon
        grd_icon = pass_icon if r.grounding_passed else fail_icon
        ref_icon = pass_icon if r.refusal_passed else fail_icon
        status_text = "[green]PASS[/green]" if r.passed else "[red]FAIL[/red]"

        table.add_row(
            r.test_id,
            r.category,
            r.question[:45] + "...",
            ret_icon,
            grd_icon,
            ref_icon,
            status_text,
            f"{r.latency_ms:.0f}ms",
        )

    console.print(table)

    # Summary Metrics Panel
    summary_text = Text()
    summary_text.append(f"Total Tests: {report.total_tests}  |  ", style="bold")
    summary_text.append(f"Passed: {report.passed_tests}  |  ", style=UI_THEME["colors"]["success_color"])
    summary_text.append(f"Failed: {report.failed_tests}  |  ", style=UI_THEME["colors"]["error_color"] if report.failed_tests > 0 else UI_THEME["colors"]["success_color"])
    summary_text.append(f"Pass Rate: {report.pass_rate_pct:.1f}%\n", style=UI_THEME["colors"]["info_color"])
    summary_text.append(f"Retrieval Accuracy: {report.retrieval_accuracy_pct:.1f}%  |  ", style="white")
    summary_text.append(f"Grounding Accuracy: {report.grounding_accuracy_pct:.1f}%  |  ", style="white")
    summary_text.append(f"Refusal Accuracy: {report.refusal_accuracy_pct:.1f}%  |  ", style="white")
    summary_text.append(f"Avg Latency: {report.avg_latency_ms:.1f}ms", style="white")

    console.print(Panel(summary_text, title="Evaluation Benchmark Summary", border_style=UI_THEME["colors"]["banner_border"]))


def handle_interactive(pipeline: RAGPipeline):
    """Launch interactive REPL mode for submitting questions."""
    print_banner()
    bullet = UI_THEME["icons"]["bullet"]
    arrow = UI_THEME["icons"]["prompt_arrow"]

    console.print(f"\n[{UI_THEME['colors']['info_color']}]Interactive Doc-QA Shell.[/{UI_THEME['colors']['info_color']}] Type your question, or commands:")
    console.print(f"  [dim]{bullet} ':status'    - View vector store status[/dim]")
    console.print(f"  [dim]{bullet} ':eval'      - Run benchmark evaluation[/dim]")
    console.print(f"  [dim]{bullet} ':samples'   - Ingest sample documents[/dim]")
    console.print(f"  [dim]{bullet} ':prompt'    - Toggle prompt inspection[/dim]")
    console.print(f"  [dim]{bullet} ':exit'      - Exit interactive mode[/dim]\n")

    inspect_prompt = False
    while True:
        try:
            query = console.input(f"[bold green]doc-qa {arrow} [/bold green]").strip()
            if not query:
                continue

            if query.lower() in [":exit", ":quit", "exit", "quit"]:
                console.print("[dim]Goodbye![/dim]")
                break
            elif query.lower() == ":status":
                handle_status(pipeline)
            elif query.lower() == ":eval":
                handle_evaluate(pipeline)
            elif query.lower() == ":samples":
                handle_ingest_samples(pipeline)
            elif query.lower() == ":prompt":
                inspect_prompt = not inspect_prompt
                console.print(f"[yellow]Prompt inspection set to: {inspect_prompt}[/yellow]")
            else:
                handle_ask(pipeline, query, inspect_prompt=inspect_prompt)

        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Exiting...[/dim]")
            break


def main():
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Doc-QA Assistant CLI - Full GenAI Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-v", "--version", action="version", version=f"Doc-QA Assistant v{config.version}")
    subparsers = parser.add_subparsers(dest="command", help="Available CLI commands")

    # Ingest command
    ingest_parser = subparsers.add_parser("ingest", help="Ingest a document (.txt or .pdf)")
    ingest_parser.add_argument("file_path", type=str, help="Path to document")
    ingest_parser.add_argument("--chunk-size", type=int, default=None, help="Chunk size in characters")
    ingest_parser.add_argument("--chunk-overlap", type=int, default=None, help="Chunk overlap in characters")

    # Ingest samples command
    subparsers.add_parser("ingest-samples", help="Ingest all built-in sample documents")

    # Ask command
    ask_parser = subparsers.add_parser("ask", help="Ask a question against indexed documents")
    ask_parser.add_argument("question", type=str, help="Question string")
    ask_parser.add_argument("--inspect-prompt", action="store_true", help="Display augmented prompt")
    ask_parser.add_argument("--top-k", type=int, default=None, help="Number of chunks to retrieve")

    # Status command
    subparsers.add_parser("status", help="Show vector store status and indexed documents")

    # Evaluate command
    subparsers.add_parser("evaluate", help="Run 8-10 benchmark evaluation questions")

    # Reset command
    subparsers.add_parser("reset", help="Clear all documents from the vector database")

    # Interactive command
    subparsers.add_parser("interactive", help="Start interactive Q&A session")

    args = parser.parse_args()

    # Initialize RAG Pipeline
    pipeline = RAGPipeline()

    if args.command == "ingest":
        print_banner()
        handle_ingest(pipeline, args.file_path, args.chunk_size, args.chunk_overlap)
    elif args.command == "ingest-samples":
        print_banner()
        handle_ingest_samples(pipeline)
    elif args.command == "ask":
        print_banner()
        handle_ask(pipeline, args.question, inspect_prompt=args.inspect_prompt, top_k=args.top_k)
    elif args.command == "status":
        print_banner()
        handle_status(pipeline)
    elif args.command == "evaluate":
        print_banner()
        handle_evaluate(pipeline)
    elif args.command == "reset":
        print_banner()
        pipeline.vector_store.reset_collection()
        console.print(f"[{UI_THEME['colors']['success_color']}]Vector database collection reset successfully.[/{UI_THEME['colors']['success_color']}]")
    elif args.command == "interactive" or args.command is None:
        handle_interactive(pipeline)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
