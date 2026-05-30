"""Command-line interface for the AI editorial agent.

The CLI supports two modes of work:

1. `run` performs the full end-to-end workflow.
2. Stage commands (`scout`, `research`, `brief`, `draft`, `review`, `image`) let
   a human debug or regenerate one part without rerunning everything.

Publishing actions are intentionally separated into `prepare-publish` and
`publish-draft`. The run command can never publish. The publish command refuses
to contact WordPress unless a human-edited approval file is supplied and
`--human-approved` is passed.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional convenience only
    load_dotenv = None


from .agent import EditorialAgent, SYSTEM_PROMPT, build_image_prompt, suggested_image_filename
from .cache import CachedHttpClient, FileCache
from .claim_ledger import write_claim_artifacts
from .duplicate_body import compare_body_to_existing, write_duplicate_report
from .editorial_memory import EditorialMemoryStore
from .events import EventBus, JsonlEventLogger, console_event_hook
from .hf_models import (
    HuggingFaceImageGenerator,
    HuggingFaceTextGenerator,
    OfflineEditorialGenerator,
    create_placeholder_featured_image,
)
from .image_files import first_featured_image
from .image_validation import validate_featured_image
from .model_routing import default_routing_file, parse_route_overrides, resolve_model_routes, routes_to_dict
from .io_utils import write_json, write_text
from .prompts import (
    PromptLibrary,
    assemble_article_prompt,
    assemble_topic_details_prompt,
    build_topic_user_input,
)
from .research import ResearchAgent
from .review import EditorialPackageReviewer
from .schemas import AgentConfig, CandidateTopic, ResearchEvidence, SiteArticle, SourceItem, utc_now_iso
from .scoring import CandidateSelector
from .scrapers import HttpClient, SiteArchiveScraper, TopicScout
from .validation import validate_article_package
from .site_profile import DEFAULT_AUTHOR_NAME, DEFAULT_SITE_BASE_URL, DEFAULT_SITE_CATEGORY_URL, DEFAULT_SITE_NAME
from .wordpress import create_approval_request, create_wordpress_draft_with_gate


def build_parser() -> argparse.ArgumentParser:
    """Build the command parser used by `python -m editorial_agent.cli`."""

    parser = argparse.ArgumentParser(
        prog="ai-editorial-agent",
        description="Scout recent AI topics and generate a human-gated WordPress-ready editorial package.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common_run_args(cmd):
        cmd.add_argument("--offline", action="store_true", help="Use deterministic offline fixtures and no HF calls.")
        cmd.add_argument("--output-dir", default="outputs", help="Directory where run artifacts are written.")
        cmd.add_argument("--site-url", default=os.getenv("SITE_CATEGORY_URL", DEFAULT_SITE_CATEGORY_URL), help="AI archive/category URL for duplicate checks and internal links.")
        cmd.add_argument("--site-base-url", default=os.getenv("SITE_BASE_URL", DEFAULT_SITE_BASE_URL), help="Base URL for the target WordPress site.")
        cmd.add_argument("--site-name", default=os.getenv("SITE_NAME", DEFAULT_SITE_NAME), help="Publication/site name.")
        cmd.add_argument("--author-name", default=os.getenv("AUTHOR_NAME", DEFAULT_AUTHOR_NAME), help="Required article author name.")
        cmd.add_argument("--lookback-days", type=int, default=21, help="Recent topic lookback window.")
        cmd.add_argument("--max-candidates", type=int, default=25, help="Maximum candidate topics to collect.")
        cmd.add_argument("--show-events", action="store_true", help="Print hook events while the agent runs.")
        cmd.add_argument("--cache-dir", default=None, help="Optional file-cache directory.")
        cmd.add_argument("--no-cache", action="store_true", help="Disable web/source caching.")
        cmd.add_argument("--editorial-memory-dir", default=None, help="Optional persistent editorial-memory directory.")

    run = sub.add_parser("run", help="Run the full editorial agent once.")
    add_common_run_args(run)
    run.add_argument("--text-model", default=os.getenv("HF_TEXT_MODEL", "openai/gpt-oss-120b"))
    run.add_argument("--text-provider", default=os.getenv("HF_TEXT_PROVIDER", "cerebras"))
    run.add_argument("--small-text-model", default=os.getenv("HF_SMALL_TEXT_MODEL", "Qwen/Qwen3.6-35B-A3B"))
    run.add_argument("--small-text-provider", default=os.getenv("HF_SMALL_TEXT_PROVIDER", "deepinfra"))
    run.add_argument(
        "--model-routing-file",
        default=os.getenv("MODEL_ROUTING_FILE", str(default_routing_file())),
        help="YAML/JSON file that maps each agent stage to a Hugging Face model/provider.",
    )
    run.add_argument(
        "--route",
        action="append",
        default=[],
        help="Override one route value, e.g. --route editorial_review.model=deepseek-ai/DeepSeek-V4-Pro.",
    )
    run.add_argument("--print-model-routing", action="store_true", help="Print resolved per-stage model routing before running.")
    run.add_argument("--image-model", default=os.getenv("HF_IMAGE_MODEL", "black-forest-labs/FLUX.1-Krea-dev"))
    run.add_argument("--image-provider", default=os.getenv("HF_IMAGE_PROVIDER", "fal-ai"))
    run.add_argument("--no-image", action="store_true", help="Skip featured image generation.")
    run.add_argument("--strict", action="store_true", help="Do not fall back to offline placeholder/image on HF errors.")
    run.add_argument("--quality-mode", choices=["balanced"], default="balanced", help="Model-call strategy. balanced uses selector, synthesis, review, conditional revision/polish, and image.")
    run.add_argument("--research-min-sources", type=int, default=5, help="Minimum usable sources before drafting.")
    run.add_argument("--research-min-authoritative", type=int, default=2, help="Minimum authoritative/primary sources.")
    run.add_argument("--research-min-chars", type=int, default=4500, help="Minimum cleaned source characters.")
    run.add_argument("--research-max-rounds", type=int, default=3, help="Maximum research expansion rounds.")
    run.add_argument("--max-research-prompt-chars", type=int, default=9000, help="Max compact research chars injected into article prompt.")
    run.add_argument("--max-revision-passes", type=int, default=2, help="Maximum final review repair passes.")
    run.add_argument("--no-final-review", action="store_true", help="Skip truthfulness/clarity/purpose review.")
    run.add_argument("--no-full-body-duplicate-check", action="store_true", help="Skip full-body duplicate check.")
    run.add_argument("--no-claim-ledger", action="store_true", help="Skip claim ledger artifacts.")

    scout = sub.add_parser("scout", help="Run only site verification, topic scouting, and candidate scoring.")
    add_common_run_args(scout)

    research = sub.add_parser("research", help="Run the research sufficiency stage.")
    add_common_run_args(research)
    research.add_argument("--candidate-json", default=None, help="Path to selected_candidate.json from scout. If omitted, scout runs first.")
    research.add_argument("--research-min-sources", type=int, default=5)
    research.add_argument("--research-min-authoritative", type=int, default=2)
    research.add_argument("--research-min-chars", type=int, default=4500)
    research.add_argument("--research-max-rounds", type=int, default=3)

    brief = sub.add_parser("brief", help="Generate only the topic brief from research artifacts.")
    brief.add_argument("--research-json", required=True)
    brief.add_argument("--output-dir", default=None)
    brief.add_argument("--offline", action="store_true")
    brief.add_argument("--text-model", default=os.getenv("HF_TEXT_MODEL", "openai/gpt-oss-120b"))
    brief.add_argument("--text-provider", default=os.getenv("HF_TEXT_PROVIDER", "cerebras"))

    draft = sub.add_parser("draft", help="Generate only the article package from a topic brief and research artifacts.")
    draft.add_argument("--research-json", required=True)
    draft.add_argument("--topic-brief", required=True)
    draft.add_argument("--output-dir", default=None)
    draft.add_argument("--offline", action="store_true")
    draft.add_argument("--text-model", default=os.getenv("HF_TEXT_MODEL", "openai/gpt-oss-120b"))
    draft.add_argument("--text-provider", default=os.getenv("HF_TEXT_PROVIDER", "cerebras"))

    review = sub.add_parser("review", help="Review an existing run's article package and write review artifacts.")
    review.add_argument("--run-dir", required=True)

    image = sub.add_parser("image", help="Generate or validate the featured image for an existing run.")
    image.add_argument("--run-dir", required=True)
    image.add_argument("--offline", action="store_true")
    image.add_argument("--image-model", default=os.getenv("HF_IMAGE_MODEL", "black-forest-labs/FLUX.1-Krea-dev"))
    image.add_argument("--image-provider", default=os.getenv("HF_IMAGE_PROVIDER", "fal-ai"))

    prep = sub.add_parser("prepare-publish", help="Create a human approval request for WordPress draft creation.")
    prep.add_argument("--run-dir", required=True)

    pub = sub.add_parser("publish-draft", help="Create a WordPress draft after explicit human approval.")
    pub.add_argument("--run-dir", required=True)
    pub.add_argument("--approval-file", required=True)
    pub.add_argument("--human-approved", action="store_true", help="Required explicit confirmation. Without this, no remote write occurs.")
    pub.add_argument("--dry-run", action="store_true", help="Validate approval and show draft payload without contacting WordPress.")
    pub.add_argument("--editorial-memory-dir", default=None)

    return parser


def prompt_dir() -> Path:
    """Return bundled prompt directory."""

    return Path(__file__).resolve().parent / "prompts"


def make_http(args) -> HttpClient:
    """Build a cache-wrapped HTTP client for staged commands."""

    http = HttpClient()
    if getattr(args, "no_cache", False):
        return http
    cache_root = Path(args.cache_dir) if getattr(args, "cache_dir", None) else Path(args.output_dir) / "_cache"
    return CachedHttpClient(http, FileCache(cache_root, enabled=True))


def generator_for(args):
    """Create either the deterministic offline generator or HF text generator."""

    if getattr(args, "offline", False):
        return OfflineEditorialGenerator()
    return HuggingFaceTextGenerator(model=args.text_model, provider=args.text_provider)


def candidate_from_dict(data: dict) -> CandidateTopic:
    """Deserialize CandidateTopic from JSON artifacts."""

    allowed = {field for field in CandidateTopic.__dataclass_fields__}
    return CandidateTopic(**{k: v for k, v in data.items() if k in allowed})


def evidence_from_dict(data: dict) -> ResearchEvidence:
    """Deserialize ResearchEvidence from JSON artifacts."""

    allowed = {field for field in ResearchEvidence.__dataclass_fields__}
    return ResearchEvidence(**{k: v for k, v in data.items() if k in allowed})


def site_article_from_dict(data: dict) -> SiteArticle:
    """Deserialize SiteArticle from JSON artifacts."""

    allowed = {field for field in SiteArticle.__dataclass_fields__}
    return SiteArticle(**{k: v for k, v in data.items() if k in allowed})


def stage_scout(args) -> Path:
    """Run discovery/scoring and return the stage directory."""

    run_dir = Path(args.output_dir) / f"scout-{utc_now_iso().replace(':','').replace('+','Z')}"
    run_dir.mkdir(parents=True, exist_ok=True)
    http = make_http(args)

    site_articles = offline_site_articles_for_cli() if args.offline else SiteArchiveScraper(http).scrape(args.site_url)
    source_items = offline_source_items_for_cli() if args.offline else TopicScout(http).collect(args.lookback_days, args.max_candidates)
    candidates = CandidateSelector().build_candidates(source_items, site_articles)

    memory = EditorialMemoryStore(Path(args.editorial_memory_dir) if args.editorial_memory_dir else Path(args.output_dir) / "_editorial_memory")
    for cand in candidates:
        memory_risk, memory_reason = memory.prior_topic_risk(cand)
        if memory_risk >= 0.45:
            cand.duplicate_risk = max(cand.duplicate_risk, memory_risk)
            cand.duplicate_reason = f"{cand.duplicate_reason}; {memory_reason}".strip("; ")
            cand.selected = False

    selected = next((c for c in candidates if c.selected and c.duplicate_risk < 0.70), None) or next((c for c in candidates if c.duplicate_risk < 0.70), None)
    if selected:
        selected.selected = True

    write_json(run_dir / "site_articles.json", [a.to_dict() for a in site_articles])
    write_json(run_dir / "source_items.json", [s.to_dict() for s in source_items])
    write_json(run_dir / "candidate_scores.json", [c.to_dict() for c in candidates])
    if selected:
        write_json(run_dir / "selected_candidate.json", selected.to_dict())
    print(f"Scout artifacts: {run_dir}")
    return run_dir


def stage_research(args) -> Path:
    """Run research sufficiency, either from a selected candidate or a fresh scout."""

    if args.candidate_json:
        candidate_path = Path(args.candidate_json)
        run_dir = Path(args.output_dir) / f"research-{utc_now_iso().replace(':','').replace('+','Z')}"
        run_dir.mkdir(parents=True, exist_ok=True)
        selected = candidate_from_dict(json.loads(candidate_path.read_text(encoding="utf-8")))
        source_items = [SourceItem(selected.title, selected.url, selected.source_name, selected.published, selected.summary)]
    else:
        scout_dir = stage_scout(args)
        run_dir = scout_dir
        selected = candidate_from_dict(json.loads((scout_dir / "selected_candidate.json").read_text(encoding="utf-8")))
        source_items = [SourceItem(**x) for x in json.loads((scout_dir / "source_items.json").read_text(encoding="utf-8"))]

    cfg = AgentConfig(
        output_dir=Path(args.output_dir),
        offline=args.offline,
        research_min_sources=args.research_min_sources,
        research_min_authoritative_sources=args.research_min_authoritative,
        research_min_total_chars=args.research_min_chars,
        research_max_rounds=args.research_max_rounds,
    )
    logger = JsonlEventLogger(run_dir / "research_events.jsonl")
    emit = lambda event_type, payload=None: logger.emit(event_type, payload or {})
    evidence, sufficiency = ResearchAgent(cfg, make_http(args), emit).gather(selected, source_items)
    write_json(
        run_dir / "research.json",
        {
            "selected_candidate": selected.to_dict(),
            "research_sufficiency": sufficiency.to_dict(),
            "evidence": [ev.to_dict() for ev in evidence],
        },
    )
    print(f"Research artifacts: {run_dir / 'research.json'}")
    return run_dir


def stage_brief(args) -> Path:
    """Generate a topic brief from research artifacts."""

    research_path = Path(args.research_json)
    run_dir = Path(args.output_dir) if args.output_dir else research_path.parent
    data = json.loads(research_path.read_text(encoding="utf-8"))
    selected = candidate_from_dict(data["selected_candidate"])
    evidence = [evidence_from_dict(x) for x in data["evidence"]]
    # Site articles are optional for staged brief generation; use an empty list if
    # the stage was run from a standalone candidate.
    site_path = research_path.parent / "site_articles.json"
    site_articles = [site_article_from_dict(x) for x in json.loads(site_path.read_text(encoding="utf-8"))] if site_path.exists() else []

    prompt_library = PromptLibrary(prompt_dir())
    user_input = build_topic_user_input(selected, site_articles, evidence, data.get("research_sufficiency_as_obj", _sufficiency_obj(data["research_sufficiency"])))
    rendered = assemble_topic_details_prompt(prompt_library.read("topic_details_prompt.md"), user_input)
    write_text(run_dir / "topic_prompt_rendered.md", rendered)
    brief_md = generator_for(args).generate(SYSTEM_PROMPT, rendered, max_tokens=4500)
    write_text(run_dir / "topic_brief.md", brief_md)
    print(f"Topic brief: {run_dir / 'topic_brief.md'}")
    return run_dir


def _sufficiency_obj(data: dict):
    """Create a tiny object with attributes expected by build_topic_user_input."""

    class Obj:
        pass

    obj = Obj()
    for key, value in data.items():
        setattr(obj, key, value)
    return obj


def stage_draft(args) -> Path:
    """Generate a full article package from a topic brief and research artifacts."""

    research_path = Path(args.research_json)
    run_dir = Path(args.output_dir) if args.output_dir else research_path.parent
    data = json.loads(research_path.read_text(encoding="utf-8"))
    selected = candidate_from_dict(data["selected_candidate"])
    evidence = [evidence_from_dict(x) for x in data["evidence"]]
    prompt_library = PromptLibrary(prompt_dir())
    article_prompt = assemble_article_prompt(
        prompt_library.read("article_generation_prompt.md"),
        Path(args.topic_brief).read_text(encoding="utf-8"),
        evidence,
        candidate=selected,
    )
    write_text(run_dir / "article_prompt_rendered.md", article_prompt)
    article_md = generator_for(args).generate(SYSTEM_PROMPT, article_prompt, max_tokens=10500)
    write_text(run_dir / "article.md", article_md)
    print(f"Article package: {run_dir / 'article.md'}")
    return run_dir


def stage_review(args) -> int:
    """Review an existing run's article, write report, claim ledger, and duplicate report."""

    run_dir = Path(args.run_dir)
    article_md = (run_dir / "article.md").read_text(encoding="utf-8")
    research = json.loads((run_dir / "research.json").read_text(encoding="utf-8"))
    selected = candidate_from_dict(research["selected_candidate"])
    evidence = [evidence_from_dict(x) for x in research["evidence"]]
    site_path = run_dir / "site_articles.json"
    site_articles = [site_article_from_dict(x) for x in json.loads(site_path.read_text(encoding="utf-8"))] if site_path.exists() else []

    validation = validate_article_package(article_md, min_word_count=1500)
    review = EditorialPackageReviewer().review(article_md, selected=selected, evidence=evidence, site_articles=site_articles, validation=validation)
    claim_json, fact_md = write_claim_artifacts(article_md, evidence, run_dir)
    dup = compare_body_to_existing(article_md, site_articles, None, offline=True)
    write_duplicate_report(dup, run_dir / "duplicate_body_report.json")
    image_report = validate_featured_image(first_featured_image(run_dir), article_md, validation.focus_keyword)

    write_json(
        run_dir / "review_report.json",
        {
            "validation": validation.__dict__,
            "editorial_review": review.to_dict(),
            "claim_ledger_json": str(claim_json),
            "fact_analysis_boundary_md": str(fact_md),
            "duplicate_body_report": dup.to_dict(),
            "image_validation": image_report.to_dict(),
        },
    )
    print(f"Review report: {run_dir / 'review_report.json'}")
    return 0 if validation.ok and review.ok and dup.ok and image_report.ok else 1


def stage_image(args) -> int:
    """Generate and validate a featured image for an existing run."""

    run_dir = Path(args.run_dir)
    article_md = (run_dir / "article.md").read_text(encoding="utf-8")
    research = json.loads((run_dir / "research.json").read_text(encoding="utf-8"))
    selected = candidate_from_dict(research["selected_candidate"])
    prompt = build_image_prompt(article_md, selected)
    path = run_dir / suggested_image_filename(article_md)
    if args.offline:
        create_placeholder_featured_image(path, selected.title)
    else:
        HuggingFaceImageGenerator(model=args.image_model, provider=args.image_provider).generate_image(prompt, path)
    validation = validate_featured_image(path, article_md, validate_article_package(article_md, min_word_count=1500).focus_keyword)
    write_json(run_dir / "image_validation.json", validation.to_dict())
    print(f"Featured image: {path}")
    return 0 if validation.ok else 1


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""

    if load_dotenv is not None:
        load_dotenv()
    args = build_parser().parse_args(argv)

    if args.command == "run":
        event_bus = EventBus()
        if args.show_events:
            event_bus.register(console_event_hook)

        routing_file = Path(args.model_routing_file) if args.model_routing_file else None
        model_routes = resolve_model_routes(
            routing_file=routing_file,
            heavy_model=args.text_model,
            heavy_provider=args.text_provider,
            small_model=args.small_text_model,
            small_provider=args.small_text_provider,
            image_model=args.image_model,
            image_provider=args.image_provider,
            cli_overrides=parse_route_overrides(args.route),
        )
        if args.print_model_routing:
            print(json.dumps(routes_to_dict(model_routes), indent=2))

        cfg = AgentConfig(
            site_category_url=args.site_url,
            site_base_url=args.site_base_url,
            site_name=args.site_name,
            author_name=args.author_name,
            output_dir=Path(args.output_dir),
            lookback_days=args.lookback_days,
            max_candidates=args.max_candidates,
            hf_text_model=args.text_model,
            hf_text_provider=args.text_provider,
            hf_small_text_model=args.small_text_model,
            hf_small_text_provider=args.small_text_provider,
            hf_image_model=args.image_model,
            hf_image_provider=args.image_provider,
            model_routes={stage: route.to_dict() for stage, route in model_routes.items()},
            model_routing_file=routing_file,
            offline=args.offline,
            allow_offline_fallback=not args.strict,
            generate_image=not args.no_image,
            quality_mode=args.quality_mode,
            research_min_sources=args.research_min_sources,
            research_min_authoritative_sources=args.research_min_authoritative,
            research_min_total_chars=args.research_min_chars,
            research_max_rounds=args.research_max_rounds,
            max_research_chars_for_article_prompt=args.max_research_prompt_chars,
            enable_final_review=not args.no_final_review,
            max_revision_passes=args.max_revision_passes,
            cache_dir=Path(args.cache_dir) if args.cache_dir else None,
            cache_enabled=not args.no_cache,
            editorial_memory_dir=Path(args.editorial_memory_dir) if args.editorial_memory_dir else None,
            enable_full_body_duplicate_check=not args.no_full_body_duplicate_check,
            enable_claim_ledger=not args.no_claim_ledger,
        )

        outputs = EditorialAgent(cfg, prompt_dir=prompt_dir(), event_bus=event_bus).run()

        print("\nRun complete.")
        print(f"Article Markdown: {outputs.article_md}")
        print(f"Featured image:   {outputs.featured_image}")
        print(f"Topic brief:      {outputs.topic_brief}")
        print(f"Events JSONL:     {outputs.events_jsonl}")
        print(f"Run report:       {outputs.run_report_json}")
        print(f"Publish request:  {outputs.publish_request_json}  (approval required before any WordPress draft action)")
        return 0

    if args.command == "scout":
        stage_scout(args)
        return 0
    if args.command == "research":
        stage_research(args)
        return 0
    if args.command == "brief":
        stage_brief(args)
        return 0
    if args.command == "draft":
        stage_draft(args)
        return 0
    if args.command == "review":
        return stage_review(args)
    if args.command == "image":
        return stage_image(args)
    if args.command == "prepare-publish":
        path = create_approval_request(Path(args.run_dir))
        print(f"Approval request created: {path}")
        print("Review the article and image, then edit approved=true, approved_by, and approved_at before running publish-draft.")
        return 0
    if args.command == "publish-draft":
        if not args.human_approved:
            print("Refusing remote write: --human-approved is required in addition to a valid approval file.")
            return 3
        result = create_wordpress_draft_with_gate(Path(args.run_dir), Path(args.approval_file), dry_run=args.dry_run)
        write_json(Path(args.run_dir) / "wordpress_draft_result.json", result)
        if not args.dry_run:
            memory = EditorialMemoryStore(Path(args.editorial_memory_dir) if args.editorial_memory_dir else Path(args.run_dir).parent / "_editorial_memory")
            memory.record_accepted_draft(result.get("approval", {}), result.get("post", {}))
        print(f"WordPress draft result: {Path(args.run_dir) / 'wordpress_draft_result.json'}")
        return 0

    return 2


def offline_site_articles_for_cli() -> list[SiteArticle]:
    """Small offline fixture mirroring the agent's offline mode."""

    from .agent import offline_site_articles

    return offline_site_articles()


def offline_source_items_for_cli() -> list[SourceItem]:
    """Small offline fixture mirroring the agent's offline mode."""

    from .agent import offline_source_items

    return offline_source_items()


if __name__ == "__main__":
    raise SystemExit(main())
