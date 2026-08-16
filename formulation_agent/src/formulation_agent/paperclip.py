"""Async wrapper around the `paperclip` CLI.

Paperclip has no machine-readable output mode, so this module owns all of the
text parsing. Everything above it works with typed objects.

Two things here are load-bearing and worth not "simplifying" later:

1. `locate_quote` searches for the quoted text and takes the line number *from
   grep's answer*, rather than trusting the line number a model gave us.
   Physical file offsets do not correspond to the `L<n>` labels (physical line
   18 of one paper is labelled L133), so any arithmetic on line numbers reads
   the wrong text. Searching for the text itself sidesteps that entirely and
   self-corrects the citation.

2. The quote is turned into a whitespace-tolerant regex before searching.
   Extracted full text contains doubled spaces around italicised spans
   ("from  Salmonella typhimurium  with"), so a literal match fails on text
   that is genuinely present.
"""

from __future__ import annotations

import asyncio
import difflib
import json
import os
import re
import shutil
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from .models import Citation

# paperclip prints an OpenSSL/urllib3 warning to stderr on every invocation.
_NOISE = re.compile(r"(urllib3|warnings\.warn|NotOpenSSLWarning)", re.I)

_RESULT_ID = re.compile(r"\[(s_[0-9a-f]+|m_[0-9a-f]+)\]")
# "  PMC12805367 · PMC · 2025-12-06"  /  "  bio_def732a473bb · bioRxiv · 2024-09-17"
_HIT = re.compile(r"^\s{2,}([A-Za-z0-9_]+)\s+·\s+([^·]+?)\s+·\s+(\d{4})-\d{2}-\d{2}\s*$")
# "    PMC11948332 · 2218ms"
_MAP_DOC = re.compile(r"^\s{2,}([A-Za-z0-9_]+)\s+·\s+\d+(?:\.\d+)?\s*ms\s*$")
_GREP_LINE = re.compile(r"^L(\d+):(.*)$")

DEFAULT_SOURCES = "pmc,biorxiv,medrxiv,arxiv"


class PaperclipError(RuntimeError):
    pass


@dataclass
class Hit:
    doc_id: str
    source: str = ""
    year: int | None = None
    title: str = ""


@dataclass
class QuoteCheck:
    """Result of checking a quote against the paper it was attributed to."""

    found: bool
    line: int | None
    line_text: str
    reason: str


@dataclass
class SearchResult:
    result_id: str | None
    hits: list[Hit] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.result_id and self.hits)


def _clean(text: str) -> str:
    return "\n".join(ln for ln in text.splitlines() if not _NOISE.search(ln))


def _id_resolver(known_ids: list[str]):
    """Map an abbreviated document id back to its full form.

    Ambiguous prefixes are left as-is rather than guessed: attributing a quote
    to the wrong paper is worse than failing to resolve it, since the quote
    check would then reject a perfectly good citation for the wrong reason.
    """
    known = [k for k in known_ids if k]

    def resolve(doc_id: str) -> str:
        if not doc_id or doc_id in known:
            return doc_id
        matches = [k for k in known if k.startswith(doc_id)]
        return matches[0] if len(matches) == 1 else doc_id

    return resolve


def _host_env() -> dict[str, str]:
    """Environment for the paperclip child process.

    The paperclip launcher is `#!/usr/bin/env python3` and vendors its
    dependencies outside any project venv. If we inherit our own environment,
    an active virtualenv captures `python3` and paperclip dies on a missing
    import (`ModuleNotFoundError: yaml`) with an empty stdout — which looks
    exactly like "no results" rather than a crash. Strip the venv markers and
    drop its bin directory from PATH so the interpreter resolves the way it
    would in a plain shell.
    """
    env = dict(os.environ)
    venv = env.pop("VIRTUAL_ENV", None)
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    if venv:
        venv_bin = str(Path(venv) / "bin")
        env["PATH"] = os.pathsep.join(
            p for p in env.get("PATH", "").split(os.pathsep) if p and p != venv_bin
        )
    return env


def _fragment(quote: str, max_chars: int = 90) -> str:
    """Pick a distinctive middle slice of the quote to search for.

    Middle rather than start: leading text is often a clause the extractor
    reworded slightly, while the middle tends to be copied verbatim.
    """
    words = quote.split()
    if len(words) <= 6:
        return quote.strip()
    body = " ".join(words[1:-1]) if len(words) > 8 else quote
    if len(body) <= max_chars:
        return body.strip()
    start = max(0, (len(body) - max_chars) // 2)
    slice_ = body[start : start + max_chars]
    # trim to whole words so the regex doesn't start mid-token
    parts = slice_.split()
    if len(parts) > 2:
        slice_ = " ".join(parts[1:-1])
    return slice_.strip()


def _ws_tolerant_pattern(text: str) -> str:
    """Escape regex metacharacters, then let any run of whitespace match."""
    chunks = [re.escape(tok) for tok in text.split()]
    return r"\s+".join(chunks)


_DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−"), "-")
_QUOTES = {ord("‘"): "'", ord("’"): "'", ord("“"): '"', ord("”"): '"'}
_NUM = re.compile(r"\d+(?:\.\d+)?")


def _norm(text: str) -> str:
    """Fold away typography so only substantive differences remain."""
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_DASHES).translate(_QUOTES)
    return " ".join(text.casefold().split())


def _tight(text: str) -> str:
    """`_norm` with all whitespace removed.

    Publishers render the same span as "42 °C" or "42°C", and extracted text
    carries doubled spaces around italics. Comparing with whitespace deleted
    makes those differences invisible while leaving every substantive character
    — crucially every digit — still significant.
    """
    return "".join(_norm(text).split())


def verify_against_line(quote: str, line: str) -> tuple[bool, str]:
    """Check a quote against the line it was located in.

    Locating a *fragment* of a quote is not enough: an extractor can copy the
    opening of a real sentence and alter the number at the end, and a fragment
    match would sail straight through. So once grep tells us which line the
    quote came from, the full quote is compared against that line here.

    Numbers are checked separately and strictly, because an altered quantity is
    both the most damaging failure mode and the easiest to miss in a fuzzy
    string comparison.
    """
    nq, nl = _tight(quote), _tight(line)
    if not nq or not nl:
        return False, "empty text"

    # Every number in the quote must appear in the source line. Checked first
    # and independently: a fabricated quantity is the most damaging failure and
    # the easiest for a fuzzy string comparison to wave through.
    q_nums, l_nums = _NUM.findall(_norm(quote)), set(_NUM.findall(_norm(line)))
    missing = [n for n in q_nums if n not in l_nums]
    if missing:
        return False, f"quantity not in source: {', '.join(missing[:3])}"

    if nq in nl:
        return True, "exact"

    # tolerate minor drift (a clipped clause, a dropped footnote marker)
    longest = difflib.SequenceMatcher(None, nq, nl).find_longest_match(
        0, len(nq), 0, len(nl)
    ).size
    ratio = longest / max(len(nq), 1)
    if ratio >= 0.90:
        return True, f"near-exact ({ratio:.0%})"
    return False, f"quote does not match source text ({ratio:.0%} overlap)"


class Paperclip:
    """Serialised access to the paperclip CLI.

    `concurrency` bounds simultaneous CLI processes; paperclip is a network
    client and the corpus-wide operations are not cheap.
    """

    def __init__(self, binary: str = "paperclip", concurrency: int = 4, timeout: float = 420.0):
        self.binary = shutil.which(binary) or binary
        self.timeout = timeout
        self._sem = asyncio.Semaphore(concurrency)
        self._env = _host_env()
        self.last_stderr = ""
        # A document cited by several claims was re-fetched every time,
        # each fetch costing a subprocess slot the readers need.
        self._citations: dict[str, Citation] = {}

    async def _run(self, *args: str, timeout: float | None = None) -> str:
        async with self._sem:
            proc = await asyncio.create_subprocess_exec(
                self.binary,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._env,
            )
            try:
                out, err = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout or self.timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                raise PaperclipError(f"timed out: paperclip {' '.join(args[:3])}") from None

        stdout = _clean(out.decode("utf-8", "replace"))
        stderr = _clean(err.decode("utf-8", "replace")).strip()
        if proc.returncode not in (0, None) and not stdout:
            self.last_stderr = stderr
            raise PaperclipError(
                f"paperclip {args[0]} exited {proc.returncode}: {stderr[-400:] or '(no output)'}"
            )
        return stdout

    # ---------------------------------------------------------------- search

    async def search(self, query: str, source: str = "pmc", n: int = 6) -> SearchResult:
        """Semantic search against ONE source.

        Pass a single source, not a comma list: `-s pmc,biorxiv` does not union
        the corpora — it comes back with PMC hits only, silently dropping the
        rest. Callers fan out across sources themselves.
        """
        try:
            out = await self._run("search", "-s", source, query, "-n", str(n))
        except PaperclipError:
            return SearchResult(None, [])
        return self._parse_search(out)

    def _parse_search(self, out: str) -> SearchResult:
        rid_match = _RESULT_ID.search(out)
        hits: list[Hit] = []
        lines = out.splitlines()
        for idx, line in enumerate(lines):
            m = _HIT.match(line)
            if not m:
                continue
            doc_id, source, year = m.group(1), m.group(2).strip(), m.group(3)
            title = ""
            # walk back to the most recent numbered entry line for the title
            for back in range(idx - 1, max(-1, idx - 6), -1):
                t = re.match(r"^\s*\d+\.\s+(.*)$", lines[back])
                if t:
                    title = t.group(1).strip()
                    break
            hits.append(
                Hit(doc_id=doc_id, source=source, year=int(year) if year else None, title=title)
            )
        return SearchResult(rid_match.group(1) if rid_match else None, hits)

    async def search_exact(self, term: str, source: str, n: int = 6) -> SearchResult:
        """Full-text boolean search for a literal term.

        Semantic search retrieves on topic and reliably misses exact entity
        names: querying "TlpA coiled-coil thermal bioswitch" returns papers
        about coiled-coils generally while skipping the ones that actually say
        "TlpA". This is the complement — BM25 over full paper text for a quoted
        term — and it is what surfaces the specific protein, gene or reagent a
        claim hangs on.
        """
        term = term.strip().strip('"')
        if not term:
            return SearchResult(None, [])
        try:
            out = await self._run(
                "search", "-s", source, "--bool", "--ranking", "bm25",
                "--full-text", f'"{term}"', "-n", str(n),
            )
        except PaperclipError:
            return SearchResult(None, [])
        return self._parse_search(out)

    # ------------------------------------------------------------------- map

    async def map_schema(
        self,
        result_id: str,
        question: str,
        schema: dict,
        known_ids: list[str] | None = None,
        limit: int | None = None,
        timeout: float | None = None,
    ) -> dict[str, dict]:
        """Run the per-paper reader with a strict JSON schema.

        Returns {doc_id: parsed_json}. Papers whose output failed validation are
        simply absent — paperclip already retried them once.

        `known_ids` are the document ids from the originating search. The map
        display abbreviates long ids (`bio_6af5af36` for `bio_6af5af366c48`), and
        an abbreviated id silently breaks every downstream lookup — the quote
        check and the citation fetch both address papers by exact id. Passing
        the search's ids lets us restore the full form.
        """
        args = ["map", "--from", result_id, question,
                "--output-schema", json.dumps(schema)]
        if limit:
            # Reading is the expensive leg (~10s/paper); cap it explicitly
            # rather than reading whatever the search happened to return.
            args += ["-n", str(limit)]
        out = await self._run(*args, timeout=timeout or max(self.timeout, 600.0))
        resolve = _id_resolver(known_ids or [])
        results: dict[str, dict] = {}
        lines = out.splitlines()
        i = 0
        while i < len(lines):
            m = _MAP_DOC.match(lines[i])
            if not m:
                i += 1
                continue
            doc_id = resolve(m.group(1))
            # JSON may wrap across lines; accumulate until it parses
            buf = ""
            j = i + 1
            while j < len(lines) and j < i + 60:
                candidate = lines[j].strip()
                if _MAP_DOC.match(lines[j]):
                    break
                buf = (buf + " " + candidate).strip() if buf else candidate
                if buf.startswith("{"):
                    try:
                        results[doc_id] = json.loads(buf)
                        break
                    except json.JSONDecodeError:
                        pass
                j += 1
            i = j if j > i else i + 1
        return results

    # ----------------------------------------------------------- quote check

    async def locate_quote(self, doc_id: str, quote: str) -> QuoteCheck:
        """Confirm `quote` really appears in `doc_id`, and return its true line.

        Two stages. A fragment of the quote is used to *locate* a candidate line
        (grep), then the full quote is checked against that line by
        `verify_against_line`. Locating alone is not sufficient — see that
        function for why.
        """
        quote = (quote or "").strip()
        if not quote or len(quote) < 12:
            return QuoteCheck(False, None, "", "quote too short to verify")

        path = f"/papers/{doc_id}/content.lines"
        # progressively shorter fragments; extraction sometimes clips a trailing
        # clause, or the source renders a span with different typography
        attempts = [_fragment(quote, 90), _fragment(quote, 55), _fragment(quote, 34)]
        seen: set[str] = set()
        best: QuoteCheck | None = None

        for frag in attempts:
            if not frag or frag in seen or len(frag) < 12:
                continue
            seen.add(frag)
            try:
                out = await self._run(
                    "grep", "-n", _ws_tolerant_pattern(frag), path, "-m", "3", timeout=180.0
                )
            except PaperclipError:
                continue
            for raw in out.splitlines():
                g = _GREP_LINE.match(raw.strip())
                if not g:
                    continue
                line_no, line_text = int(g.group(1)), g.group(2).strip()
                ok, reason = verify_against_line(quote, line_text)
                if ok:
                    return QuoteCheck(True, line_no, line_text, reason)
                # remember the near miss so the failure can be explained
                best = best or QuoteCheck(False, line_no, line_text, reason)

        return best or QuoteCheck(False, None, "", "quoted text not found in this paper")

    async def read_line(self, doc_id: str, line_no: int) -> str:
        """Return the text of a specific `L<n>` line, or '' if unavailable."""
        try:
            out = await self._run(
                "grep", "-n", r"\S", f"/papers/{doc_id}/content.lines", "-m", "0", timeout=180.0
            )
        except PaperclipError:
            return ""
        for line in out.splitlines():
            g = _GREP_LINE.match(line.strip())
            if g and int(g.group(1)) == line_no:
                return g.group(2).strip()
        return ""

    # -------------------------------------------------------------- metadata

    async def citation(self, doc_id: str) -> Citation:
        cached = self._citations.get(doc_id)
        if cached is not None:
            return cached
        try:
            out = await self._run("cat", f"/papers/{doc_id}/meta.json", timeout=120.0)
            start, end = out.find("{"), out.rfind("}")
            meta = json.loads(out[start : end + 1]) if start >= 0 < end else {}
        except (PaperclipError, json.JSONDecodeError):
            return Citation(doc_id=doc_id)  # not cached: worth retrying later

        raw_authors = meta.get("authors") or ""
        if isinstance(raw_authors, str):
            authors = [a.strip(" *") for a in raw_authors.split(",") if a.strip(" *")]
        else:
            authors = [str(a) for a in raw_authors]

        year: int | None = None
        pub = str(meta.get("pub_date") or "")
        if len(pub) >= 4 and pub[:4].isdigit():
            year = int(pub[:4])

        citation = Citation(
            doc_id=doc_id,
            title=str(meta.get("title") or "").strip(),
            authors=authors,
            journal=str(meta.get("journal_title") or "").strip(),
            year=year,
            doi=str(meta.get("doi") or "").strip(),
            source=str(meta.get("source") or "").strip(),
        )
        self._citations[doc_id] = citation
        return citation

    async def healthcheck(self) -> tuple[bool, str]:
        try:
            out = await self._run("search", "-s", "pmc", "protein", "-n", "1", timeout=120.0)
        except PaperclipError as exc:
            return False, str(exc)
        if "Found" in out or "papers" in out:
            return True, "ok"
        return False, out.strip()[:200] or "unexpected output"
