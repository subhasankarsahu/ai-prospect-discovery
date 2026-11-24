"""Controlled recording script for real API search fixtures.

Executes the discovery pipeline against the 5 assessment queries and stores raw responses
under .cache/fixtures/.

SAFETY REQUIREMENTS:
- Requires explicit --confirm-live flag to prevent accidental live API requests.
- Validates that TAVILY_API_KEY and GEMINI_API_KEY are configured.
- Never prints or leaks API keys.
- Tracks exact Tavily and Gemini request counts.
- Raw fixtures are saved under .cache/fixtures/ which is gitignored.
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure project root is in python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from fastapi import HTTPException

from app.config import get_settings
from app.schemas import DiscoveryRequest, QueryIntent
from app.schemas_internal import (
    CandidateClassification,
    RawCandidate,
    TavilySearchResult,
)
from app.services.discovery_service import discover_prospects
from app.services.llm_service import (
    BaseLLMService,
    GeminiLLMService,
    LLMServiceError,
)
from app.services.search_service import SearchServiceError, TavilySearchService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("record_fixtures")

ASSESSMENT_QUERIES = [
    {
        "query": "Football lovers in Washington DC in USA",
        "slug": "football_lovers_washington_dc",
    },
    {
        "query": "Digital marketing agency owners in New York USA",
        "slug": "digital_marketing_owners_new_york",
    },
    {
        "query": "Startup founders in London UK",
        "slug": "startup_founders_london",
    },
    {
        "query": "Cricket lovers in Ahmedabad India",
        "slug": "cricket_lovers_ahmedabad",
    },
    {
        "query": "Restaurant owners in Dubai UAE",
        "slug": "restaurant_owners_dubai",
    },
]


class RecordingSearchService(TavilySearchService):
    """Proxy around TavilySearchService capturing all raw search requests and responses."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.recorded_calls: list[dict[str, Any]] = []
        self.request_count: int = 0

    async def search(
        self,
        query: str,
        include_domains: list[str] | None = None,
    ) -> list[TavilySearchResult]:
        self.request_count += 1
        call_record: dict[str, Any] = {
            "call_index": self.request_count,
            "query": query,
            "include_domains": list(include_domains) if include_domains else None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            results = await super().search(query=query, include_domains=include_domains)
            call_record["status"] = "success"
            call_record["results"] = [r.model_dump() for r in results]
            self.recorded_calls.append(call_record)
            return results
        except (SearchServiceError, httpx.HTTPError) as exc:
            call_record["status"] = "error"
            call_record["error_type"] = type(exc).__name__
            call_record["error_message"] = str(exc)
            self.recorded_calls.append(call_record)
            raise


class RecordingLLMService:
    """Proxy around GeminiLLMService capturing all raw LLM prompts, inputs, and responses."""

    def __init__(self, base_service: BaseLLMService) -> None:
        self.base_service = base_service
        self.intent_calls: list[dict[str, Any]] = []
        self.classification_calls: list[dict[str, Any]] = []
        self.request_count: int = 0

    async def extract_query_intent(self, query: str) -> QueryIntent:
        self.request_count += 1
        record: dict[str, Any] = {
            "call_index": self.request_count,
            "query": query,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        try:
            intent = await self.base_service.extract_query_intent(query)
            record["status"] = "success"
            record["intent"] = intent.model_dump()
            self.intent_calls.append(record)
            return intent
        except (LLMServiceError, httpx.HTTPError) as exc:
            record["status"] = "error"
            record["error_type"] = type(exc).__name__
            record["error_message"] = str(exc)
            self.intent_calls.append(record)
            raise

    async def classify_candidates(
        self,
        intent: QueryIntent,
        candidates: list[RawCandidate],
    ) -> list[CandidateClassification]:
        self.request_count += 1
        record: dict[str, Any] = {
            "call_index": self.request_count,
            "intent": intent.model_dump(),
            "candidate_count": len(candidates),
            "candidates": [c.model_dump() for c in candidates],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        try:
            classifications = await self.base_service.classify_candidates(intent, candidates)
            record["status"] = "success"
            record["classifications"] = [c.model_dump() for c in classifications]
            self.classification_calls.append(record)
            return classifications
        except (LLMServiceError, httpx.HTTPError) as exc:
            record["status"] = "error"
            record["error_type"] = type(exc).__name__
            record["error_message"] = str(exc)
            self.classification_calls.append(record)
            raise


async def record_single_query(
    query_item: dict[str, str],
    output_dir: Path,
) -> dict[str, Any]:
    """Execute pipeline once for a single query and persist raw recording."""
    query_text = query_item["query"]
    slug = query_item["slug"]
    logger.info("Starting recording for query: %r (%s)", query_text, slug)

    # Initialize instrumented recording proxies
    search_service = RecordingSearchService()
    # Disable cache reading to guarantee live recording captures fresh responses
    search_service.cache = None  # type: ignore[assignment]
    raw_llm = GeminiLLMService()
    recording_llm = RecordingLLMService(raw_llm)

    start_time = datetime.now(timezone.utc)
    recording_status = "success"
    error_info = None
    response_data = None

    try:
        request = DiscoveryRequest(query=query_text)
        response = await discover_prospects(
            request=request,
            llm_service=recording_llm,  # type: ignore[arg-type]
            search_service=search_service,
        )
        response_data = response.model_dump()
        logger.info(
            "Query %r completed successfully: %d prospects resolved.",
            query_text,
            response.total_prospects,
        )
    except (
        HTTPException,
        LLMServiceError,
        SearchServiceError,
        httpx.HTTPError,
        ValueError,
        RuntimeError,
        OSError,
    ) as exc:
        recording_status = "failed"
        error_info = {
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
        logger.error("Query %r failed: %s (%s)", query_text, type(exc).__name__, exc)

    end_time = datetime.now(timezone.utc)
    duration_seconds = (end_time - start_time).total_seconds()

    record_payload = {
        "query": query_text,
        "slug": slug,
        "recorded_at": start_time.isoformat(),
        "duration_seconds": duration_seconds,
        "status": recording_status,
        "error": error_info,
        "metrics": {
            "tavily_requests": search_service.request_count,
            "gemini_intent_requests": len(recording_llm.intent_calls),
            "gemini_classification_requests": len(recording_llm.classification_calls),
            "total_gemini_requests": recording_llm.request_count,
            "prospects_count": response_data.get("total_prospects", 0) if response_data else 0,
        },
        "search_calls": search_service.recorded_calls,
        "gemini_intent_calls": recording_llm.intent_calls,
        "gemini_classification_calls": recording_llm.classification_calls,
        "final_response": response_data,
    }

    output_path = output_dir / f"{slug}.raw.json"
    output_path.write_text(
        json.dumps(record_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info("Saved raw fixture to: %s", output_path)

    return {
        "query": query_text,
        "slug": slug,
        "status": recording_status,
        "tavily_requests": search_service.request_count,
        "gemini_requests": recording_llm.request_count,
        "prospects": response_data.get("total_prospects", 0) if response_data else 0,
        "duration_seconds": duration_seconds,
        "file": str(output_path),
    }


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Record live API responses for the 5 assessment queries into .cache/fixtures/"
    )
    parser.add_argument(
        "--confirm-live",
        action="store_true",
        help="Explicit confirmation authorizing live Tavily and Gemini requests",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".cache/fixtures"),
        help="Directory to save raw recordings (default: .cache/fixtures)",
    )
    args = parser.parse_args()

    # CRITICAL SAFETY CHECK: Refuse execution without --confirm-live
    if not args.confirm_live:
        logger.error(
            "REFUSING EXECUTION: Live API requests require the explicit '--confirm-live' flag."
        )
        sys.exit(1)

    settings = get_settings()
    if not settings.tavily_api_key.strip():
        logger.error("MISSING CREDENTIAL: TAVILY_API_KEY is not configured.")
        sys.exit(1)
    if not settings.gemini_api_key.strip():
        logger.error("MISSING CREDENTIAL: GEMINI_API_KEY is not configured.")
        sys.exit(1)

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=== STARTING CONTROLLED LIVE FIXTURE RECORDING ===")
    logger.info("Target directory: %s", output_dir.resolve())
    logger.info("Total assessment queries to execute: %d", len(ASSESSMENT_QUERIES))

    manifest_entries: list[dict[str, Any]] = []
    total_tavily = 0
    total_gemini = 0

    for query_item in ASSESSMENT_QUERIES:
        entry = await record_single_query(query_item, output_dir)
        manifest_entries.append(entry)
        total_tavily += entry["tavily_requests"]
        total_gemini += entry["gemini_requests"]

    manifest = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "total_queries": len(manifest_entries),
        "total_tavily_requests": total_tavily,
        "total_gemini_requests": total_gemini,
        "entries": manifest_entries,
    }

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    logger.info("=== RECORDING COMPLETE ===")
    logger.info("Manifest saved to: %s", manifest_path)
    logger.info(
        "Total external consumption: Tavily requests=%d, Gemini requests=%d",
        total_tavily,
        total_gemini,
    )


if __name__ == "__main__":
    asyncio.run(main())
