"""
Legal Document Template System
================================
FastAPI router providing a complete legal document management platform for:
  - Oregon state court (ORS) motions and documents
  - Federal District of Oregon documents

Features
--------
* Up to 2,000 named templates with structured content blocks
* Verbatim fact block storage
* Defendant / party information storage
* File upload & storage (copies of your documents)
* Hardcoded cover-page and caption formats for ORS and Federal courts
* Document package builder (cover page + caption + facts + law)
* Multi-model AI deep-research (OpenAI + Google queried in parallel)
* Full-featured web UI at /legal/ui
"""

from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

import legal_db as db

try:
    import ai_providers
    _ai_available = True
except Exception as _ai_err:
    import logging
    logging.getLogger("legal_templates").warning(
        "ai_providers not available — research endpoints will return errors: %s", _ai_err
    )
    ai_providers = None  # type: ignore[assignment]
    _ai_available = False

# ── Router ─────────────────────────────────────────────────────────────────────
router = APIRouter(prefix="/legal", tags=["Legal Templates"])

# ══════════════════════════════════════════════════════════════════════════════
# Pydantic Models
# ══════════════════════════════════════════════════════════════════════════════

class ContentBlock(BaseModel):
    type: str           # 'law' | 'fact' | 'argument' | 'proof' | 'conclusion' | 'custom'
    heading: str = ""
    content: str = ""
    citation: str = ""
    note: str = ""


class TemplateCreate(BaseModel):
    name: str
    category: str = "ORS"          # 'ORS' | 'Federal'
    court_type: str = ""
    description: str = ""
    content_blocks: List[Dict] = []
    tags: List[str] = []


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    court_type: Optional[str] = None
    description: Optional[str] = None
    content_blocks: Optional[List[Dict]] = None
    tags: Optional[List[str]] = None


class FactBlockCreate(BaseModel):
    title: str
    content: str
    category: str = ""
    tags: List[str] = []
    source: str = ""


class FactBlockUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    source: Optional[str] = None


class DefendantCreate(BaseModel):
    name: str
    case_number: str = ""
    court: str = ""
    charges: List[str] = []
    address: str = ""
    dob: str = ""
    phone: str = ""
    notes: str = ""
    extra_info: Dict[str, Any] = {}


class DefendantUpdate(BaseModel):
    name: Optional[str] = None
    case_number: Optional[str] = None
    court: Optional[str] = None
    charges: Optional[List[str]] = None
    address: Optional[str] = None
    dob: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    extra_info: Optional[Dict[str, Any]] = None


class BuildRequest(BaseModel):
    package_name: str
    template_id: Optional[int] = None
    defendant_id: Optional[int] = None
    fact_block_ids: List[int] = []
    motion_title: str = "MOTION"
    additional_law: str = ""
    additional_facts: str = ""
    include_research: bool = False
    research_query: str = ""


class ResearchRequest(BaseModel):
    query: str
    providers: List[str] = ["openai", "google"]
    depth: int = 2          # 1 = single query, 2 = follow-up queries, 3 = three rounds
    max_tokens: int = 2000


# ══════════════════════════════════════════════════════════════════════════════
# Cover-page / Caption helpers  (hardcoded court formats)
# ══════════════════════════════════════════════════════════════════════════════

def _ors_cover_page(defendant: Optional[Dict], court_type: str, motion_title: str) -> str:
    county = court_type or "MULTNOMAH"
    county_upper = county.upper()
    case_no = defendant.get("case_number", "_______________") if defendant else "_______________"
    def_name = defendant.get("name", "_______________") if defendant else "_______________"
    return f"""
{'=' * 70}
                IN THE CIRCUIT COURT OF THE STATE OF OREGON
                         FOR {county_upper} COUNTY

{'=' * 70}

STATE OF OREGON,                        )
                                        )  Case No.: {case_no}
        Plaintiff,                      )
                                        )  {motion_title}
   vs.                                  )
                                        )
{def_name.upper()},                     )
                                        )
        Defendant.                      )
{'_' * 70}
""".strip()


def _federal_cover_page(defendant: Optional[Dict], motion_title: str) -> str:
    case_no = defendant.get("case_number", "_______________") if defendant else "_______________"
    def_name = defendant.get("name", "_______________") if defendant else "_______________"
    return f"""
{'=' * 70}
           IN THE UNITED STATES DISTRICT COURT
                FOR THE DISTRICT OF OREGON
{'=' * 70}

UNITED STATES OF AMERICA,              )
                                        )  Case No.: {case_no}
        Plaintiff,                      )
                                        )  {motion_title}
   v.                                   )
                                        )
{def_name.upper()},                     )
                                        )
        Defendant.                      )
{'_' * 70}
""".strip()


def _defendant_info_block(defendant: Dict) -> str:
    charges = "\n".join(f"  • {c}" for c in defendant.get("charges", [])) or "  (none listed)"
    extra = defendant.get("extra_info", {})
    extra_lines = "\n".join(f"  {k}: {v}" for k, v in extra.items()) if extra else ""
    return (
        f"DEFENDANT INFORMATION\n"
        f"{'─' * 40}\n"
        f"Name:         {defendant.get('name', '')}\n"
        f"DOB:          {defendant.get('dob', '')}\n"
        f"Address:      {defendant.get('address', '')}\n"
        f"Phone:        {defendant.get('phone', '')}\n"
        f"Court:        {defendant.get('court', '')}\n"
        f"Case Number:  {defendant.get('case_number', '')}\n"
        f"Charges:\n{charges}\n"
        + (f"Notes:        {defendant.get('notes', '')}\n" if defendant.get("notes") else "")
        + (f"{extra_lines}\n" if extra_lines else "")
    )


def _build_document(
    template: Optional[Dict],
    defendant: Optional[Dict],
    fact_blocks: List[Dict],
    motion_title: str,
    additional_law: str,
    additional_facts: str,
    research_text: str = "",
) -> str:
    category = (template or {}).get("category", "ORS")
    court_type = (template or {}).get("court_type", "")

    # Cover page
    if category == "Federal":
        cover = _federal_cover_page(defendant, motion_title)
    else:
        cover = _ors_cover_page(defendant, court_type, motion_title)

    sections: List[str] = [cover, ""]

    # Defendant info
    if defendant:
        sections.append(_defendant_info_block(defendant))
        sections.append("")

    # Motion heading
    sections.append(f"\n{motion_title}\n{'═' * len(motion_title)}\n")

    # Template content blocks
    if template and template.get("content_blocks"):
        for block in template["content_blocks"]:
            heading = block.get("heading", "")
            content = block.get("content", "")
            citation = block.get("citation", "")
            note = block.get("note", "")
            if heading:
                sections.append(f"\n{heading}\n{'─' * len(heading)}")
            if content:
                sections.append(content)
            if citation:
                sections.append(f"  Citation: {citation}")
            if note:
                sections.append(f"  [Note: {note}]")
            sections.append("")

    # Facts section
    if fact_blocks or additional_facts:
        sections.append("\nSTATEMENT OF FACTS\n" + "─" * 20)
        for fb in fact_blocks:
            sections.append(f"\n{fb['title']}")
            sections.append(fb["content"])
            if fb.get("source"):
                sections.append(f"  Source: {fb['source']}")
        if additional_facts:
            sections.append("\nADDITIONAL FACTS")
            sections.append(additional_facts)
        sections.append("")

    # Additional law
    if additional_law:
        sections.append("\nAPPLICABLE LAW\n" + "─" * 14)
        sections.append(additional_law)
        sections.append("")

    # Research section
    if research_text:
        sections.append("\nLEGAL RESEARCH FINDINGS\n" + "─" * 24)
        sections.append(research_text)
        sections.append("")

    # Signature block
    sections.append("\nRespectfully submitted,\n")
    sections.append("_" * 40)
    sections.append("Defendant / Authorized Representative")
    sections.append("Date: _____________________\n")

    return "\n".join(sections)


# ══════════════════════════════════════════════════════════════════════════════
# Multi-model research helper
# ══════════════════════════════════════════════════════════════════════════════

def _research_prompt(query: str, round_num: int, previous: str = "") -> str:
    base = (
        f"You are a legal research assistant specializing in Oregon state law (ORS) and "
        f"Federal District of Oregon court procedures. "
        f"Provide thorough, specific, and citable legal research.\n\n"
    )
    if round_num == 1:
        return (
            base
            + f"Research the following legal question thoroughly. Cite specific ORS statutes, "
            f"Federal codes (28 USC, 42 USC, etc.), Constitutional provisions, and case law:\n\n"
            f"QUERY: {query}\n\n"
            f"Provide:\n"
            f"1. Relevant Oregon statutes (ORS citations)\n"
            f"2. Relevant Federal statutes and constitutional provisions\n"
            f"3. Key case law from the 9th Circuit and Oregon Supreme Court\n"
            f"4. How these authorities support the legal argument\n"
        )
    elif round_num == 2:
        return (
            base
            + f"Building on the following initial research, provide ADDITIONAL supporting authority "
            f"and counter-argument analysis. Find MORE statutes, cases, and constitutional provisions "
            f"that strengthen the argument. Look for anything missed in round 1.\n\n"
            f"Original query: {query}\n\n"
            f"Round 1 findings:\n{previous}\n\n"
            f"Provide additional authority and supporting analysis:"
        )
    else:
        return (
            base
            + f"You have done two rounds of research on: {query}\n\n"
            f"Previous findings:\n{previous}\n\n"
            f"Now synthesize everything into a final, organized legal argument section "
            f"with properly formatted citations suitable for filing. "
            f"Double-check all statutes and ensure accuracy."
        )


async def _query_provider_async(provider: str, prompt: str, max_tokens: int) -> str:
    """Run a single provider query in a thread pool to avoid blocking."""
    if not _ai_available or ai_providers is None:
        return f"[{provider} unavailable: ai_providers module not loaded]"
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: ai_providers.generate_text(
            prompt=prompt,
            provider=provider,
            max_tokens=max_tokens,
            temperature=0.3,
        ),
    )
    if "error" in result:
        return f"[{provider} error: {result['error']}]"
    return result.get("text", "")


async def run_multi_model_research(
    query: str,
    providers: List[str],
    depth: int = 2,
    max_tokens: int = 2000,
) -> Dict[str, Any]:
    """
    Query multiple AI providers across several rounds (depth) to gather
    comprehensive legal research. Returns combined text per provider and
    a merged summary.
    """
    provider_results: Dict[str, List[str]] = {p: [] for p in providers}

    previous_combined = ""
    for round_num in range(1, depth + 1):
        prompt = _research_prompt(query, round_num, previous_combined)

        # Fire all providers in parallel for this round
        tasks = {p: _query_provider_async(p, prompt, max_tokens) for p in providers}
        round_results = await asyncio.gather(*tasks.values())

        round_texts: Dict[str, str] = {}
        for provider, text in zip(tasks.keys(), round_results):
            provider_results[provider].append(text)
            round_texts[provider] = text

        # Combine this round's results for the next round's prompt
        previous_combined = "\n\n".join(
            f"[{p.upper()}]:\n{t}" for p, t in round_texts.items()
        )

    # Build final per-provider text and merged summary
    final_per_provider = {
        p: "\n\n--- Next Round ---\n\n".join(rounds)
        for p, rounds in provider_results.items()
    }

    merged = (
        "COMBINED MULTI-MODEL LEGAL RESEARCH\n"
        + "=" * 40 + "\n\n"
        + "\n\n" + "─" * 40 + "\n\n".join(
            f"[Source: {p.upper()}]\n{text}"
            for p, text in final_per_provider.items()
        )
    )

    return {"per_provider": final_per_provider, "merged": merged}


# ══════════════════════════════════════════════════════════════════════════════
# Template endpoints
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/templates")
async def list_templates(
    category: Optional[str] = Query(None, description="Filter by 'ORS' or 'Federal'"),
    search: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List templates, optionally filtered by category or search term."""
    templates = db.list_templates(category=category, search=search, limit=limit, offset=offset)
    return {"templates": templates, "total": len(templates), "limit": db.MAX_TEMPLATES}


@router.post("/templates", status_code=201)
async def create_template(body: TemplateCreate):
    """Create a new legal document template (max 2000 total)."""
    try:
        template = db.create_template(
            name=body.name,
            category=body.category,
            court_type=body.court_type,
            description=body.description,
            content_blocks=body.content_blocks,
            tags=body.tags,
        )
        return template
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/templates/{template_id}")
async def get_template(template_id: int):
    t = db.get_template(template_id)
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    return t


@router.put("/templates/{template_id}")
async def update_template(template_id: int, body: TemplateUpdate):
    t = db.update_template(template_id, **body.dict(exclude_none=True))
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    return t


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template(template_id: int):
    if not db.delete_template(template_id):
        raise HTTPException(status_code=404, detail="Template not found")


# ══════════════════════════════════════════════════════════════════════════════
# Fact block endpoints
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/facts")
async def list_fact_blocks(
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    facts = db.list_fact_blocks(category=category, search=search, limit=limit, offset=offset)
    return {"facts": facts, "total": len(facts)}


@router.post("/facts", status_code=201)
async def create_fact_block(body: FactBlockCreate):
    return db.create_fact_block(
        title=body.title,
        content=body.content,
        category=body.category,
        tags=body.tags,
        source=body.source,
    )


@router.get("/facts/{fact_id}")
async def get_fact_block(fact_id: int):
    f = db.get_fact_block(fact_id)
    if not f:
        raise HTTPException(status_code=404, detail="Fact block not found")
    return f


@router.put("/facts/{fact_id}")
async def update_fact_block(fact_id: int, body: FactBlockUpdate):
    f = db.update_fact_block(fact_id, **body.dict(exclude_none=True))
    if not f:
        raise HTTPException(status_code=404, detail="Fact block not found")
    return f


@router.delete("/facts/{fact_id}", status_code=204)
async def delete_fact_block(fact_id: int):
    if not db.delete_fact_block(fact_id):
        raise HTTPException(status_code=404, detail="Fact block not found")


# ══════════════════════════════════════════════════════════════════════════════
# Defendant endpoints
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/defendants")
async def list_defendants(
    search: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    return {"defendants": db.list_defendants(search=search, limit=limit, offset=offset)}


@router.post("/defendants", status_code=201)
async def create_defendant(body: DefendantCreate):
    return db.create_defendant(
        name=body.name,
        case_number=body.case_number,
        court=body.court,
        charges=body.charges,
        address=body.address,
        dob=body.dob,
        phone=body.phone,
        notes=body.notes,
        extra_info=body.extra_info,
    )


@router.get("/defendants/{def_id}")
async def get_defendant(def_id: int):
    d = db.get_defendant(def_id)
    if not d:
        raise HTTPException(status_code=404, detail="Defendant not found")
    return d


@router.put("/defendants/{def_id}")
async def update_defendant(def_id: int, body: DefendantUpdate):
    d = db.update_defendant(def_id, **body.dict(exclude_none=True))
    if not d:
        raise HTTPException(status_code=404, detail="Defendant not found")
    return d


@router.delete("/defendants/{def_id}", status_code=204)
async def delete_defendant(def_id: int):
    if not db.delete_defendant(def_id):
        raise HTTPException(status_code=404, detail="Defendant not found")


# ══════════════════════════════════════════════════════════════════════════════
# File storage endpoints
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/files")
async def list_files(
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    return {"files": db.list_stored_files(category=category, search=search, limit=limit, offset=offset)}


@router.post("/files/upload", status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    description: str = Form(""),
    category: str = Form(""),
):
    """Upload and store a copy of a document file."""
    content = await file.read()
    ext = os.path.splitext(file.filename or "")[1]
    stored_name = f"{uuid.uuid4().hex}{ext}"
    dest = os.path.join(db.FILES_DIR, stored_name)
    with open(dest, "wb") as fh:
        fh.write(content)
    mime = file.content_type or mimetypes.guess_type(file.filename or "")[0] or "application/octet-stream"
    record = db.create_stored_file(
        original_filename=file.filename or stored_name,
        stored_filename=stored_name,
        file_type=mime,
        description=description,
        category=category,
        file_size=len(content),
    )
    return record


@router.get("/files/{file_id}")
async def get_file_info(file_id: int):
    f = db.get_stored_file(file_id)
    if not f:
        raise HTTPException(status_code=404, detail="File not found")
    return f


@router.get("/files/{file_id}/download")
async def download_file(file_id: int):
    f = db.get_stored_file(file_id)
    if not f:
        raise HTTPException(status_code=404, detail="File not found")
    path = os.path.join(db.FILES_DIR, f["stored_filename"])
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Physical file not found")
    return FileResponse(
        path=path,
        media_type=f.get("file_type", "application/octet-stream"),
        filename=f["original_filename"],
    )


@router.delete("/files/{file_id}", status_code=204)
async def delete_file(file_id: int):
    ok, _ = db.delete_stored_file(file_id)
    if not ok:
        raise HTTPException(status_code=404, detail="File not found")


# ══════════════════════════════════════════════════════════════════════════════
# Document builder endpoint
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/build")
async def build_document(body: BuildRequest):
    """
    Assemble a complete legal document package from a template, defendant
    information, fact blocks, and optional multi-model research.
    """
    template = db.get_template(body.template_id) if body.template_id else None
    defendant = db.get_defendant(body.defendant_id) if body.defendant_id else None
    fact_blocks = [
        fb for fid in body.fact_block_ids
        if (fb := db.get_fact_block(fid)) is not None
    ]

    research_text = ""
    if body.include_research and body.research_query:
        research_data = await run_multi_model_research(
            query=body.research_query,
            providers=["openai", "google"],
            depth=2,
            max_tokens=2000,
        )
        research_text = research_data.get("merged", "")

    doc = _build_document(
        template=template,
        defendant=defendant,
        fact_blocks=fact_blocks,
        motion_title=body.motion_title,
        additional_law=body.additional_law,
        additional_facts=body.additional_facts,
        research_text=research_text,
    )

    package = db.create_document_package(
        name=body.package_name,
        output_content=doc,
        defendant_id=body.defendant_id,
        template_id=body.template_id,
        fact_block_ids=body.fact_block_ids,
    )

    return {
        "package_id": package["id"],
        "name": package["name"],
        "created_at": package["created_at"],
        "document": doc,
        "character_count": len(doc),
    }


@router.get("/packages")
async def list_packages(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    return {"packages": db.list_document_packages(limit=limit, offset=offset)}


@router.get("/packages/{pkg_id}")
async def get_package(pkg_id: int):
    p = db.get_document_package(pkg_id)
    if not p:
        raise HTTPException(status_code=404, detail="Package not found")
    return p


@router.delete("/packages/{pkg_id}", status_code=204)
async def delete_package(pkg_id: int):
    if not db.delete_document_package(pkg_id):
        raise HTTPException(status_code=404, detail="Package not found")


# ══════════════════════════════════════════════════════════════════════════════
# Research endpoint
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/research")
async def research(body: ResearchRequest):
    """
    Run a multi-model, multi-round legal research query against all
    configured AI providers and return consolidated findings.
    """
    depth = max(1, min(body.depth, 3))
    providers = [p for p in body.providers if p in ("openai", "google")]
    if not providers:
        raise HTTPException(status_code=400, detail="No valid providers specified (use 'openai' or 'google')")

    results = await run_multi_model_research(
        query=body.query,
        providers=providers,
        depth=depth,
        max_tokens=body.max_tokens,
    )

    record = db.save_research(
        query=body.query,
        providers=providers,
        results=results,
    )

    return {
        "research_id": record["id"],
        "query": body.query,
        "providers": providers,
        "depth": depth,
        "merged": results["merged"],
        "per_provider": results["per_provider"],
        "created_at": record["created_at"],
    }


@router.get("/research/history")
async def research_history(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    return {"history": db.list_research_history(limit=limit, offset=offset)}


@router.get("/research/history/{research_id}")
async def get_research(research_id: int):
    r = db.get_research(research_id)
    if not r:
        raise HTTPException(status_code=404, detail="Research record not found")
    return r


# ══════════════════════════════════════════════════════════════════════════════
# Web UI
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/ui", response_class=HTMLResponse)
async def legal_ui():
    """Full-featured web interface for the Legal Document Template System."""
    template_count = db.template_count()
    return HTMLResponse(content=_build_ui_html(template_count))


def _build_ui_html(template_count: int) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Legal Document Template System</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #1a1a2e; color: #e0e0e0; min-height: 100vh; }}
  header {{ background: #16213e; padding: 16px 24px; border-bottom: 2px solid #0f3460; display: flex; align-items: center; gap: 16px; }}
  header h1 {{ color: #e94560; font-size: 1.4em; }}
  header .badge {{ background: #0f3460; color: #53d8fb; padding: 4px 10px; border-radius: 12px; font-size: 0.8em; }}
  nav {{ background: #16213e; display: flex; gap: 0; border-bottom: 1px solid #0f3460; overflow-x: auto; }}
  nav button {{ background: none; border: none; color: #aaa; padding: 12px 20px; cursor: pointer; font-size: 0.95em; white-space: nowrap; border-bottom: 3px solid transparent; transition: all 0.2s; }}
  nav button:hover, nav button.active {{ color: #e94560; border-bottom-color: #e94560; background: rgba(233,69,96,0.08); }}
  .panel {{ display: none; padding: 20px; max-width: 1200px; margin: 0 auto; }}
  .panel.active {{ display: block; }}
  .card {{ background: #16213e; border: 1px solid #0f3460; border-radius: 8px; padding: 20px; margin-bottom: 16px; }}
  .card h3 {{ color: #53d8fb; margin-bottom: 12px; }}
  .form-row {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }}
  .form-group {{ display: flex; flex-direction: column; gap: 4px; flex: 1; min-width: 200px; }}
  label {{ font-size: 0.85em; color: #aaa; }}
  input, select, textarea {{ background: #0f3460; border: 1px solid #1a4a7a; color: #e0e0e0; padding: 8px 12px; border-radius: 6px; font-size: 0.9em; width: 100%; }}
  textarea {{ resize: vertical; font-family: 'Consolas', monospace; }}
  .btn {{ padding: 8px 18px; border: none; border-radius: 6px; cursor: pointer; font-size: 0.9em; transition: opacity 0.2s; }}
  .btn:hover {{ opacity: 0.85; }}
  .btn-primary {{ background: #e94560; color: white; }}
  .btn-secondary {{ background: #0f3460; color: #53d8fb; }}
  .btn-danger {{ background: #8b0000; color: white; }}
  .btn-success {{ background: #1a6b3c; color: white; }}
  .btn-sm {{ padding: 4px 10px; font-size: 0.8em; }}
  .list-container {{ margin-top: 16px; }}
  .list-item {{ background: #0f3460; border-radius: 6px; padding: 12px 16px; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }}
  .list-item-info {{ flex: 1; }}
  .list-item-info h4 {{ color: #e0e0e0; margin-bottom: 4px; }}
  .list-item-info small {{ color: #888; }}
  .tag {{ display: inline-block; background: #1a4a7a; color: #53d8fb; padding: 2px 8px; border-radius: 10px; font-size: 0.75em; margin: 2px; }}
  .cat-ors {{ background: #1a3a1a; color: #6fcf6f; }}
  .cat-federal {{ background: #1a1a4a; color: #6f9fcf; }}
  .output-box {{ background: #0a0a1a; border: 1px solid #0f3460; border-radius: 6px; padding: 16px; white-space: pre-wrap; font-family: 'Consolas', monospace; font-size: 0.85em; max-height: 500px; overflow-y: auto; margin-top: 12px; }}
  .stat {{ text-align: center; padding: 16px; }}
  .stat .number {{ font-size: 2.5em; font-weight: bold; color: #e94560; }}
  .stat .label {{ font-size: 0.85em; color: #888; margin-top: 4px; }}
  .stats-row {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 20px; }}
  .stats-row .card {{ flex: 1; min-width: 120px; }}
  .alert {{ padding: 10px 16px; border-radius: 6px; margin-bottom: 12px; }}
  .alert-success {{ background: #1a3a1a; color: #6fcf6f; border: 1px solid #2a5a2a; }}
  .alert-error {{ background: #3a1a1a; color: #cf6f6f; border: 1px solid #5a2a2a; }}
  .block-builder {{ border: 1px dashed #0f3460; border-radius: 6px; padding: 12px; margin-bottom: 8px; }}
  .loading {{ opacity: 0.6; pointer-events: none; }}
  .research-results {{ background: #0a0a1a; border: 1px solid #0f3460; border-radius: 6px; padding: 16px; white-space: pre-wrap; font-family: 'Consolas', monospace; font-size: 0.85em; max-height: 600px; overflow-y: auto; }}
  #msg {{ position: fixed; top: 70px; right: 20px; z-index: 1000; min-width: 280px; }}
</style>
</head>
<body>

<header>
  <h1>⚖️ Legal Document Template System</h1>
  <span class="badge">ORS + Federal District of Oregon</span>
  <span class="badge">{template_count}/{db.MAX_TEMPLATES} templates</span>
</header>

<nav>
  <button class="active" onclick="showPanel('dashboard',this)">📊 Dashboard</button>
  <button onclick="showPanel('templates',this)">📋 Templates</button>
  <button onclick="showPanel('facts',this)">📝 Fact Blocks</button>
  <button onclick="showPanel('defendants',this)">👤 Defendants</button>
  <button onclick="showPanel('files',this)">📁 Files</button>
  <button onclick="showPanel('builder',this)">🏗️ Build Document</button>
  <button onclick="showPanel('research',this)">🔍 Research</button>
  <button onclick="showPanel('packages',this)">📦 Packages</button>
</nav>

<div id="msg"></div>

<!-- DASHBOARD -->
<div id="panel-dashboard" class="panel active">
  <div class="stats-row" id="stats-row">
    <div class="card stat"><div class="number" id="stat-templates">…</div><div class="label">Templates</div></div>
    <div class="card stat"><div class="number" id="stat-facts">…</div><div class="label">Fact Blocks</div></div>
    <div class="card stat"><div class="number" id="stat-defendants">…</div><div class="label">Defendants</div></div>
    <div class="card stat"><div class="number" id="stat-files">…</div><div class="label">Stored Files</div></div>
    <div class="card stat"><div class="number" id="stat-packages">…</div><div class="label">Packages</div></div>
  </div>
  <div class="card">
    <h3>Quick Links</h3>
    <p style="margin-bottom:12px;color:#aaa;">Manage your legal document templates, facts, and defendants from the tabs above.</p>
    <div style="display:flex;gap:10px;flex-wrap:wrap;">
      <button class="btn btn-primary" onclick="showPanel('templates',this)">📋 Templates</button>
      <button class="btn btn-secondary" onclick="showPanel('facts',this)">📝 Add Facts</button>
      <button class="btn btn-secondary" onclick="showPanel('defendants',this)">👤 Defendants</button>
      <button class="btn btn-success" onclick="showPanel('builder',this)">🏗️ Build Document</button>
      <button class="btn btn-secondary" onclick="showPanel('research',this)">🔍 Research</button>
    </div>
  </div>
  <div class="card">
    <h3>About</h3>
    <p style="color:#aaa;line-height:1.7;">
      This system stores up to <strong style="color:#53d8fb;">2,000 legal templates</strong> for Oregon state court (ORS) and
      Federal District of Oregon proceedings. Store verbatim fact blocks, defendant information, and uploaded
      documents. Use the <strong style="color:#e94560;">Build Document</strong> tool to assemble complete motion packages
      with hardcoded cover pages, captions, facts, and law. The
      <strong style="color:#e94560;">Research</strong> tool queries multiple AI models across several rounds to find
      ORS statutes, Federal codes, and case law.
    </p>
  </div>
</div>

<!-- TEMPLATES -->
<div id="panel-templates" class="panel">
  <div class="card">
    <h3>Create New Template</h3>
    <div class="form-row">
      <div class="form-group">
        <label>Template Name *</label>
        <input id="t-name" placeholder="e.g. Motion to Suppress Evidence">
      </div>
      <div class="form-group">
        <label>Category</label>
        <select id="t-cat">
          <option value="ORS">ORS (Oregon State Court)</option>
          <option value="Federal">Federal (District of Oregon)</option>
        </select>
      </div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>Court Type</label>
        <input id="t-court" placeholder="e.g. Multnomah County Circuit Court">
      </div>
      <div class="form-group">
        <label>Tags (comma-separated)</label>
        <input id="t-tags" placeholder="motion, suppress, 4th amendment">
      </div>
    </div>
    <div class="form-group" style="margin-bottom:12px;">
      <label>Description</label>
      <textarea id="t-desc" rows="2" placeholder="Brief description of when to use this template"></textarea>
    </div>
    <h4 style="color:#aaa;margin-bottom:8px;">Content Blocks</h4>
    <div id="block-list"></div>
    <button class="btn btn-secondary btn-sm" onclick="addBlock()" style="margin-bottom:12px;">+ Add Block</button>
    <br>
    <button class="btn btn-primary" onclick="createTemplate()">Save Template</button>
  </div>
  <div class="card">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
      <h3>All Templates</h3>
      <div style="display:flex;gap:8px;">
        <select id="t-filter-cat" onchange="loadTemplates()">
          <option value="">All Categories</option>
          <option value="ORS">ORS</option>
          <option value="Federal">Federal</option>
        </select>
        <input id="t-search" placeholder="Search…" oninput="loadTemplates()" style="width:180px;">
      </div>
    </div>
    <div id="templates-list" class="list-container"><em style="color:#888;">Loading…</em></div>
  </div>
</div>

<!-- FACT BLOCKS -->
<div id="panel-facts" class="panel">
  <div class="card">
    <h3>Add Fact Block</h3>
    <div class="form-row">
      <div class="form-group">
        <label>Title *</label>
        <input id="f-title" placeholder="e.g. Officer Lacked Probable Cause">
      </div>
      <div class="form-group">
        <label>Category</label>
        <input id="f-cat" placeholder="e.g. 4th Amendment, Traffic Stop">
      </div>
    </div>
    <div class="form-group" style="margin-bottom:12px;">
      <label>Verbatim Fact Content *</label>
      <textarea id="f-content" rows="6" placeholder="Paste or type the verbatim fact here…"></textarea>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>Source / Citation</label>
        <input id="f-source" placeholder="e.g. Police Report p.3, Deposition of Officer Smith">
      </div>
      <div class="form-group">
        <label>Tags (comma-separated)</label>
        <input id="f-tags" placeholder="search, seizure, stop">
      </div>
    </div>
    <button class="btn btn-primary" onclick="createFact()">Save Fact Block</button>
  </div>
  <div class="card">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
      <h3>All Fact Blocks</h3>
      <input id="f-search" placeholder="Search…" oninput="loadFacts()" style="width:200px;">
    </div>
    <div id="facts-list" class="list-container"><em style="color:#888;">Loading…</em></div>
  </div>
</div>

<!-- DEFENDANTS -->
<div id="panel-defendants" class="panel">
  <div class="card">
    <h3>Add Defendant / Party</h3>
    <div class="form-row">
      <div class="form-group"><label>Full Name *</label><input id="d-name" placeholder="Last, First Middle"></div>
      <div class="form-group"><label>Case Number</label><input id="d-case" placeholder="22CR12345"></div>
    </div>
    <div class="form-row">
      <div class="form-group"><label>Court</label><input id="d-court" placeholder="Multnomah County Circuit Court"></div>
      <div class="form-group"><label>Date of Birth</label><input id="d-dob" placeholder="MM/DD/YYYY"></div>
    </div>
    <div class="form-row">
      <div class="form-group"><label>Address</label><input id="d-addr" placeholder="123 Main St, Portland OR 97201"></div>
      <div class="form-group"><label>Phone</label><input id="d-phone" placeholder="(503) 555-1234"></div>
    </div>
    <div class="form-group" style="margin-bottom:12px;">
      <label>Charges (one per line)</label>
      <textarea id="d-charges" rows="3" placeholder="ORS 164.395 - Robbery in the Third Degree&#10;ORS 163.195 - Recklessly Endangering Another Person"></textarea>
    </div>
    <div class="form-group" style="margin-bottom:12px;">
      <label>Notes</label>
      <textarea id="d-notes" rows="2" placeholder="Any additional notes…"></textarea>
    </div>
    <button class="btn btn-primary" onclick="createDefendant()">Save Defendant</button>
  </div>
  <div class="card">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
      <h3>All Defendants</h3>
      <input id="d-search" placeholder="Search…" oninput="loadDefendants()" style="width:200px;">
    </div>
    <div id="defendants-list" class="list-container"><em style="color:#888;">Loading…</em></div>
  </div>
</div>

<!-- FILES -->
<div id="panel-files" class="panel">
  <div class="card">
    <h3>Upload Document File</h3>
    <div class="form-row">
      <div class="form-group"><label>File *</label><input type="file" id="file-input"></div>
      <div class="form-group"><label>Category</label><input id="file-cat" placeholder="e.g. Police Reports, Court Orders"></div>
    </div>
    <div class="form-group" style="margin-bottom:12px;">
      <label>Description</label>
      <input id="file-desc" placeholder="Brief description of the file">
    </div>
    <button class="btn btn-primary" onclick="uploadFile()">Upload File</button>
  </div>
  <div class="card">
    <h3>Stored Files</h3>
    <div id="files-list" class="list-container"><em style="color:#888;">Loading…</em></div>
  </div>
</div>

<!-- BUILDER -->
<div id="panel-builder" class="panel">
  <div class="card">
    <h3>🏗️ Build Document Package</h3>
    <div class="form-row">
      <div class="form-group"><label>Package Name *</label><input id="b-name" placeholder="Motion to Suppress - Smith 2024-01"></div>
      <div class="form-group"><label>Motion Title</label><input id="b-title" value="MOTION TO SUPPRESS EVIDENCE"></div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>Template (optional)</label>
        <select id="b-template"><option value="">— Select Template —</option></select>
      </div>
      <div class="form-group">
        <label>Defendant (optional)</label>
        <select id="b-defendant"><option value="">— Select Defendant —</option></select>
      </div>
    </div>
    <div class="form-group" style="margin-bottom:12px;">
      <label>Fact Block IDs to Include (comma-separated numbers)</label>
      <input id="b-facts" placeholder="1, 3, 7">
    </div>
    <div class="form-group" style="margin-bottom:12px;">
      <label>Additional Facts (free text)</label>
      <textarea id="b-addfacts" rows="4" placeholder="Type or paste additional facts here…"></textarea>
    </div>
    <div class="form-group" style="margin-bottom:12px;">
      <label>Additional Law / Statutes</label>
      <textarea id="b-law" rows="4" placeholder="Type statutes, case law, constitutional provisions…"></textarea>
    </div>
    <div class="card" style="background:#0a1628;margin-bottom:12px;">
      <label style="display:flex;align-items:center;gap:8px;cursor:pointer;">
        <input type="checkbox" id="b-research-on"> Include AI Research
      </label>
      <div id="b-research-query-row" style="margin-top:10px;display:none;">
        <label>Research Query</label>
        <input id="b-research-q" placeholder="e.g. Oregon 4th amendment vehicle search without warrant ORS suppression">
        <div style="margin-top:6px;color:#888;font-size:0.82em;">Queries both OpenAI and Google across 2 rounds for maximum legal authority coverage.</div>
      </div>
    </div>
    <button class="btn btn-primary" onclick="buildDocument()" id="build-btn">🏗️ Build Document</button>
  </div>
  <div class="card" id="build-result" style="display:none;">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
      <h3>Generated Document</h3>
      <button class="btn btn-secondary btn-sm" onclick="copyDoc()">📋 Copy</button>
    </div>
    <div class="output-box" id="build-output"></div>
  </div>
</div>

<!-- RESEARCH -->
<div id="panel-research" class="panel">
  <div class="card">
    <h3>🔍 Multi-Model Legal Research</h3>
    <p style="color:#888;margin-bottom:12px;font-size:0.9em;">
      Queries OpenAI and Google across multiple rounds to gather ORS statutes,
      Federal codes, case law, and constitutional authority for your motion.
    </p>
    <div class="form-group" style="margin-bottom:12px;">
      <label>Research Query *</label>
      <textarea id="r-query" rows="3" placeholder="e.g. Oregon 4th amendment rights during traffic stop, suppression of evidence, ORS 131.615, Terry stop requirements District of Oregon"></textarea>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>Research Depth</label>
        <select id="r-depth">
          <option value="1">1 Round (Quick)</option>
          <option value="2" selected>2 Rounds (Recommended)</option>
          <option value="3">3 Rounds (Deep — slower)</option>
        </select>
      </div>
      <div class="form-group">
        <label>Max Tokens per Call</label>
        <select id="r-tokens">
          <option value="1000">1000</option>
          <option value="2000" selected>2000</option>
          <option value="3000">3000</option>
        </select>
      </div>
    </div>
    <div style="margin-bottom:12px;">
      <label style="color:#aaa;font-size:0.85em;">Providers to query:</label>
      <div style="display:flex;gap:12px;margin-top:6px;">
        <label><input type="checkbox" id="r-openai" checked> OpenAI</label>
        <label><input type="checkbox" id="r-google" checked> Google</label>
      </div>
    </div>
    <button class="btn btn-primary" onclick="runResearch()" id="research-btn">🔍 Run Research</button>
  </div>
  <div class="card" id="research-result" style="display:none;">
    <h3>Research Findings</h3>
    <div class="research-results" id="research-output"></div>
  </div>
  <div class="card">
    <h3>Research History</h3>
    <div id="research-history" class="list-container"><em style="color:#888;">Loading…</em></div>
  </div>
</div>

<!-- PACKAGES -->
<div id="panel-packages" class="panel">
  <div class="card">
    <h3>📦 Document Packages</h3>
    <div id="packages-list" class="list-container"><em style="color:#888;">Loading…</em></div>
  </div>
</div>

<script>
// ── Navigation ────────────────────────────────────────────────────────────────
function showPanel(name, btn) {{
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
  document.getElementById('panel-' + name).classList.add('active');
  if (btn) btn.classList.add('active');
  if (name === 'dashboard') loadDashboard();
  if (name === 'templates') loadTemplates();
  if (name === 'facts') loadFacts();
  if (name === 'defendants') loadDefendants();
  if (name === 'files') loadFiles();
  if (name === 'builder') loadBuilderSelects();
  if (name === 'research') loadResearchHistory();
  if (name === 'packages') loadPackages();
}}

// ── Message helper ───────────────────────────────────────────────────────────
function msg(text, type='success') {{
  const el = document.getElementById('msg');
  el.innerHTML = `<div class="alert alert-${{type}}">${{text}}</div>`;
  setTimeout(() => el.innerHTML = '', 4000);
}}

// ── Dashboard ─────────────────────────────────────────────────────────────────
async function loadDashboard() {{
  const [t,f,d,fi,p] = await Promise.all([
    fetch('/legal/templates?limit=1').then(r=>r.json()).catch(()=>({{total:0}})),
    fetch('/legal/facts?limit=1').then(r=>r.json()).catch(()=>({{total:0}})),
    fetch('/legal/defendants?limit=1').then(r=>r.json()).catch(()=>({{defendants:[]}})),
    fetch('/legal/files?limit=1').then(r=>r.json()).catch(()=>({{files:[]}})),
    fetch('/legal/packages?limit=1').then(r=>r.json()).catch(()=>({{packages:[]}})),
  ]);
  document.getElementById('stat-templates').textContent = t.total ?? '–';
  document.getElementById('stat-facts').textContent = f.total ?? '–';
  document.getElementById('stat-defendants').textContent = (d.defendants||[]).length > 0 ? '✓' : '0';
  document.getElementById('stat-files').textContent = (fi.files||[]).length > 0 ? '✓' : '0';
  document.getElementById('stat-packages').textContent = (p.packages||[]).length > 0 ? '✓' : '0';
}}
loadDashboard();

// ── Block builder for templates ───────────────────────────────────────────────
let blocks = [];
function addBlock() {{
  const idx = blocks.length;
  blocks.push({{type:'law',heading:'',content:'',citation:'',note:''}});
  renderBlocks();
}}
function removeBlock(idx) {{
  blocks.splice(idx, 1);
  renderBlocks();
}}
function renderBlocks() {{
  const c = document.getElementById('block-list');
  c.innerHTML = blocks.map((b,i) => `
    <div class="block-builder">
      <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
        <strong style="color:#53d8fb;">Block ${{i+1}}</strong>
        <button class="btn btn-danger btn-sm" onclick="removeBlock(${{i}})">✕</button>
      </div>
      <div class="form-row">
        <div class="form-group"><label>Type</label>
          <select onchange="blocks[${{i}}].type=this.value">
            ${{['law','fact','argument','proof','conclusion','custom'].map(t=>
              `<option ${{b.type===t?'selected':''}} value="${{t}}">${{t}}</option>`).join('')}}
          </select></div>
        <div class="form-group"><label>Heading</label>
          <input value="${{b.heading}}" oninput="blocks[${{i}}].heading=this.value" placeholder="Section heading"></div>
      </div>
      <div class="form-group" style="margin-bottom:8px;"><label>Content</label>
        <textarea rows="3" oninput="blocks[${{i}}].content=this.value" placeholder="Block content…">${{b.content}}</textarea></div>
      <div class="form-row">
        <div class="form-group"><label>Citation</label>
          <input value="${{b.citation}}" oninput="blocks[${{i}}].citation=this.value" placeholder="ORS 131.615, etc."></div>
        <div class="form-group"><label>Note</label>
          <input value="${{b.note}}" oninput="blocks[${{i}}].note=this.value" placeholder="Internal note"></div>
      </div>
    </div>`).join('');
}}

// ── Templates ─────────────────────────────────────────────────────────────────
async function createTemplate() {{
  const name = document.getElementById('t-name').value.trim();
  if (!name) {{ msg('Template name is required','error'); return; }}
  const tags = document.getElementById('t-tags').value.split(',').map(s=>s.trim()).filter(Boolean);
  const body = {{
    name, category: document.getElementById('t-cat').value,
    court_type: document.getElementById('t-court').value,
    description: document.getElementById('t-desc').value,
    content_blocks: blocks, tags
  }};
  const r = await fetch('/legal/templates', {{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(body)}});
  if (r.ok) {{ msg('Template saved!'); blocks=[]; renderBlocks(); loadTemplates(); }}
  else {{ const e=await r.json(); msg(e.detail||'Error','error'); }}
}}

async function loadTemplates() {{
  const cat = document.getElementById('t-filter-cat').value;
  const q = document.getElementById('t-search').value;
  let url = `/legal/templates?limit=100${{cat?'&category='+cat:''}}${{q?'&search='+encodeURIComponent(q):''}}`;
  const data = await fetch(url).then(r=>r.json());
  const el = document.getElementById('templates-list');
  if (!data.templates.length) {{ el.innerHTML='<em style="color:#888;">No templates found.</em>'; return; }}
  el.innerHTML = data.templates.map(t => `
    <div class="list-item">
      <div class="list-item-info">
        <h4>${{t.name}} <span class="tag ${{t.category==='ORS'?'cat-ors':'cat-federal'}}">${{t.category}}</span></h4>
        <small>${{t.court_type || ''}} ${{t.description ? '— '+t.description : ''}}</small><br>
        ${{(t.tags||[]).map(tg=>`<span class="tag">${{tg}}</span>`).join('')}}
        <br><small style="color:#555;">${{t.content_blocks.length}} blocks · ${{t.updated_at?.slice(0,10)}}</small>
      </div>
      <button class="btn btn-danger btn-sm" onclick="deleteTemplate(${{t.id}})">Delete</button>
    </div>`).join('');
}}

async function deleteTemplate(id) {{
  if (!confirm('Delete this template?')) return;
  await fetch('/legal/templates/'+id, {{method:'DELETE'}});
  msg('Template deleted'); loadTemplates();
}}

// ── Facts ────────────────────────────────────────────────────────────────────
async function createFact() {{
  const title = document.getElementById('f-title').value.trim();
  const content = document.getElementById('f-content').value.trim();
  if (!title||!content) {{ msg('Title and content required','error'); return; }}
  const tags = document.getElementById('f-tags').value.split(',').map(s=>s.trim()).filter(Boolean);
  const body = {{title,content,category:document.getElementById('f-cat').value,
    tags,source:document.getElementById('f-source').value}};
  const r = await fetch('/legal/facts',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(body)}});
  if (r.ok) {{ msg('Fact block saved!'); loadFacts(); }}
  else {{ const e=await r.json(); msg(e.detail||'Error','error'); }}
}}

async function loadFacts() {{
  const q = document.getElementById('f-search').value;
  const data = await fetch(`/legal/facts?limit=100${{q?'&search='+encodeURIComponent(q):''}}`).then(r=>r.json());
  const el = document.getElementById('facts-list');
  if (!data.facts.length) {{ el.innerHTML='<em style="color:#888;">No fact blocks found.</em>'; return; }}
  el.innerHTML = data.facts.map(f => `
    <div class="list-item">
      <div class="list-item-info">
        <h4>#${{f.id}} — ${{f.title}}</h4>
        <small>${{f.category}} ${{f.source?'· Source: '+f.source:''}}</small>
        <div style="margin-top:6px;color:#aaa;font-size:0.85em;max-height:60px;overflow:hidden;">${{f.content.slice(0,200)}}${{f.content.length>200?'…':''}}</div>
        ${{(f.tags||[]).map(t=>`<span class="tag">${{t}}</span>`).join('')}}
      </div>
      <button class="btn btn-danger btn-sm" onclick="deleteFact(${{f.id}})">Delete</button>
    </div>`).join('');
}}

async function deleteFact(id) {{
  if (!confirm('Delete this fact block?')) return;
  await fetch('/legal/facts/'+id,{{method:'DELETE'}});
  msg('Fact block deleted'); loadFacts();
}}

// ── Defendants ───────────────────────────────────────────────────────────────
async function createDefendant() {{
  const name = document.getElementById('d-name').value.trim();
  if (!name) {{ msg('Defendant name required','error'); return; }}
  const charges = document.getElementById('d-charges').value.split('\\n').map(s=>s.trim()).filter(Boolean);
  const body = {{name,case_number:document.getElementById('d-case').value,
    court:document.getElementById('d-court').value,charges,
    address:document.getElementById('d-addr').value,dob:document.getElementById('d-dob').value,
    phone:document.getElementById('d-phone').value,notes:document.getElementById('d-notes').value}};
  const r = await fetch('/legal/defendants',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(body)}});
  if (r.ok) {{ msg('Defendant saved!'); loadDefendants(); }}
  else {{ const e=await r.json(); msg(e.detail||'Error','error'); }}
}}

async function loadDefendants() {{
  const q = document.getElementById('d-search').value;
  const data = await fetch(`/legal/defendants?limit=200${{q?'&search='+encodeURIComponent(q):''}}`).then(r=>r.json());
  const el = document.getElementById('defendants-list');
  if (!data.defendants.length) {{ el.innerHTML='<em style="color:#888;">No defendants found.</em>'; return; }}
  el.innerHTML = data.defendants.map(d => `
    <div class="list-item">
      <div class="list-item-info">
        <h4>${{d.name}}</h4>
        <small>Case: ${{d.case_number||'—'}} · Court: ${{d.court||'—'}} · DOB: ${{d.dob||'—'}}</small>
        ${{(d.charges||[]).map(c=>`<div style="font-size:0.8em;color:#888;">• ${{c}}</div>`).join('')}}
      </div>
      <button class="btn btn-danger btn-sm" onclick="deleteDefendant(${{d.id}})">Delete</button>
    </div>`).join('');
}}

async function deleteDefendant(id) {{
  if (!confirm('Delete this defendant?')) return;
  await fetch('/legal/defendants/'+id,{{method:'DELETE'}});
  msg('Defendant deleted'); loadDefendants();
}}

// ── Files ────────────────────────────────────────────────────────────────────
async function uploadFile() {{
  const fi = document.getElementById('file-input').files[0];
  if (!fi) {{ msg('Please select a file','error'); return; }}
  const fd = new FormData();
  fd.append('file', fi);
  fd.append('description', document.getElementById('file-desc').value);
  fd.append('category', document.getElementById('file-cat').value);
  const r = await fetch('/legal/files/upload',{{method:'POST',body:fd}});
  if (r.ok) {{ msg('File uploaded!'); loadFiles(); }}
  else {{ const e=await r.json(); msg(e.detail||'Error','error'); }}
}}

async function loadFiles() {{
  const data = await fetch('/legal/files?limit=200').then(r=>r.json());
  const el = document.getElementById('files-list');
  if (!data.files.length) {{ el.innerHTML='<em style="color:#888;">No files stored yet.</em>'; return; }}
  el.innerHTML = data.files.map(f => `
    <div class="list-item">
      <div class="list-item-info">
        <h4>${{f.original_filename}}</h4>
        <small>${{f.category||''}} · ${{f.file_type}} · ${{(f.file_size/1024).toFixed(1)}} KB · ${{f.created_at?.slice(0,10)}}</small>
        ${{f.description?`<div style="font-size:0.85em;color:#aaa;">${{f.description}}</div>`:''}}
      </div>
      <div style="display:flex;gap:6px;">
        <a class="btn btn-secondary btn-sm" href="/legal/files/${{f.id}}/download" target="_blank">⬇ Download</a>
        <button class="btn btn-danger btn-sm" onclick="deleteFile(${{f.id}})">Delete</button>
      </div>
    </div>`).join('');
}}

async function deleteFile(id) {{
  if (!confirm('Delete this file?')) return;
  await fetch('/legal/files/'+id,{{method:'DELETE'}});
  msg('File deleted'); loadFiles();
}}

// ── Builder ──────────────────────────────────────────────────────────────────
async function loadBuilderSelects() {{
  const [tmpl,defs] = await Promise.all([
    fetch('/legal/templates?limit=200').then(r=>r.json()),
    fetch('/legal/defendants?limit=200').then(r=>r.json()),
  ]);
  const ts = document.getElementById('b-template');
  ts.innerHTML = '<option value="">— Select Template —</option>' +
    tmpl.templates.map(t=>`<option value="${{t.id}}">${{t.name}} (${{t.category}})</option>`).join('');
  const ds = document.getElementById('b-defendant');
  ds.innerHTML = '<option value="">— Select Defendant —</option>' +
    defs.defendants.map(d=>`<option value="${{d.id}}">${{d.name}} — ${{d.case_number||'no case #'}}</option>`).join('');
}}

document.getElementById('b-research-on').addEventListener('change', function() {{
  document.getElementById('b-research-query-row').style.display = this.checked ? 'block' : 'none';
}});

async function buildDocument() {{
  const name = document.getElementById('b-name').value.trim();
  if (!name) {{ msg('Package name required','error'); return; }}
  const btn = document.getElementById('build-btn');
  btn.textContent = '⏳ Building…'; btn.classList.add('loading');
  const factIds = document.getElementById('b-facts').value
    .split(',').map(s=>parseInt(s.trim())).filter(n=>!isNaN(n));
  const body = {{
    package_name: name,
    motion_title: document.getElementById('b-title').value || 'MOTION',
    template_id: parseInt(document.getElementById('b-template').value)||null,
    defendant_id: parseInt(document.getElementById('b-defendant').value)||null,
    fact_block_ids: factIds,
    additional_law: document.getElementById('b-law').value,
    additional_facts: document.getElementById('b-addfacts').value,
    include_research: document.getElementById('b-research-on').checked,
    research_query: document.getElementById('b-research-q').value,
  }};
  const r = await fetch('/legal/build',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(body)}});
  btn.textContent = '🏗️ Build Document'; btn.classList.remove('loading');
  if (r.ok) {{
    const data = await r.json();
    document.getElementById('build-output').textContent = data.document;
    document.getElementById('build-result').style.display = 'block';
    msg(`Package #${{data.package_id}} built — ${{data.character_count}} characters`);
  }} else {{ const e=await r.json(); msg(e.detail||'Build error','error'); }}
}}

function copyDoc() {{
  navigator.clipboard.writeText(document.getElementById('build-output').textContent);
  msg('Copied to clipboard!');
}}

// ── Research ─────────────────────────────────────────────────────────────────
async function runResearch() {{
  const query = document.getElementById('r-query').value.trim();
  if (!query) {{ msg('Research query required','error'); return; }}
  const providers = [];
  if (document.getElementById('r-openai').checked) providers.push('openai');
  if (document.getElementById('r-google').checked) providers.push('google');
  if (!providers.length) {{ msg('Select at least one provider','error'); return; }}
  const btn = document.getElementById('research-btn');
  btn.textContent = '⏳ Researching…'; btn.classList.add('loading');
  const body = {{query, providers, depth:parseInt(document.getElementById('r-depth').value),
    max_tokens:parseInt(document.getElementById('r-tokens').value)}};
  const r = await fetch('/legal/research',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(body)}});
  btn.textContent = '🔍 Run Research'; btn.classList.remove('loading');
  if (r.ok) {{
    const data = await r.json();
    document.getElementById('research-output').textContent = data.merged;
    document.getElementById('research-result').style.display = 'block';
    loadResearchHistory();
    msg(`Research complete — ID #${{data.research_id}}`);
  }} else {{ const e=await r.json(); msg(e.detail||'Research error','error'); }}
}}

async function loadResearchHistory() {{
  const data = await fetch('/legal/research/history?limit=20').then(r=>r.json());
  const el = document.getElementById('research-history');
  if (!data.history.length) {{ el.innerHTML='<em style="color:#888;">No research history yet.</em>'; return; }}
  el.innerHTML = data.history.map(r => `
    <div class="list-item">
      <div class="list-item-info">
        <h4>#${{r.id}} — ${{r.query.slice(0,80)}}${{r.query.length>80?'…':''}}</h4>
        <small>Providers: ${{(r.providers||[]).join(', ')}} · ${{r.created_at?.slice(0,16)}}</small>
      </div>
      <button class="btn btn-secondary btn-sm" onclick="viewResearch(${{r.id}})">View</button>
    </div>`).join('');
}}

async function viewResearch(id) {{
  const data = await fetch('/legal/research/history/'+id).then(r=>r.json());
  document.getElementById('research-output').textContent = data.results?.merged || JSON.stringify(data.results,null,2);
  document.getElementById('research-result').style.display = 'block';
}}

// ── Packages ─────────────────────────────────────────────────────────────────
async function loadPackages() {{
  const data = await fetch('/legal/packages?limit=100').then(r=>r.json());
  const el = document.getElementById('packages-list');
  if (!data.packages.length) {{ el.innerHTML='<em style="color:#888;">No packages yet. Build one first.</em>'; return; }}
  el.innerHTML = data.packages.map(p => `
    <div class="list-item">
      <div class="list-item-info">
        <h4>#${{p.id}} — ${{p.name}}</h4>
        <small>Created: ${{p.created_at?.slice(0,16)}} · ${{p.output_content?.length||0}} characters</small>
      </div>
      <div style="display:flex;gap:6px;">
        <button class="btn btn-secondary btn-sm" onclick="viewPackage(${{p.id}})">View</button>
        <button class="btn btn-danger btn-sm" onclick="deletePackage(${{p.id}})">Delete</button>
      </div>
    </div>`).join('');
}}

async function viewPackage(id) {{
  const data = await fetch('/legal/packages/'+id).then(r=>r.json());
  document.getElementById('build-output').textContent = data.output_content;
  document.getElementById('build-result').style.display = 'block';
  showPanel('builder', document.querySelector('nav button:nth-child(6)'));
}}

async function deletePackage(id) {{
  if (!confirm('Delete this package?')) return;
  await fetch('/legal/packages/'+id,{{method:'DELETE'}});
  msg('Package deleted'); loadPackages();
}}
</script>
</body>
</html>"""
