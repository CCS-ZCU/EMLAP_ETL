import spacy
import os
import glob
from spacy.tokens import Doc
from spacy.language import Language
import pickle
from unidecode import unidecode
import sddk
import pandas as pd
import re
import sys
import importlib
import json
from spacy.tokens import Token
from spacy.language import Language
import google_conf
import pandas as pd
import json
import fitz
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
import spacy_stanza
import re
import unicodedata
from spacy.tokens import Token, Doc
from spacy.language import Language
from spacy.symbols import ORTH
import spacy
from spacy.tokenizer import Tokenizer
from spacy.util import compile_prefix_regex, compile_suffix_regex, compile_infix_regex

greek_nlp = spacy_stanza.load_pipeline("grc")
de_nlp = spacy.load("de_core_news_sm")   # or md/lg if you prefer
fr_nlp = spacy.load("fr_core_news_sm")
nlp_latin = spacy.load('la_core_web_lg')     # your Latin model


nlp_latin.max_length = 4000000


SYMBOL_PLACEHOLDER = "xyzxyzus"
S_OPEN  = "[S]"
S_CLOSE = "[/S]"


def rebuild_tokenizer_for_latin(nlp):
    prefixes = [r"\("] + list(nlp.Defaults.prefixes)
    suffixes = list(nlp.Defaults.suffixes)
    infixes  = list(nlp.Defaults.infixes)

    nlp.tokenizer = Tokenizer(
        nlp.vocab,
        prefix_search=compile_prefix_regex(prefixes).search,
        suffix_search=compile_suffix_regex(suffixes).search,
        infix_finditer=compile_infix_regex(infixes).finditer,
    )

# apply fix
rebuild_tokenizer_for_latin(nlp_latin)

# ❗ correct special case (single token)
nlp_latin.tokenizer.add_special_case(
    SYMBOL_PLACEHOLDER,
    [{ORTH: SYMBOL_PLACEHOLDER}]
)


LANG_PIPELINES = {
    "GR": greek_nlp,   # Greek
    "G":  de_nlp,      # German
    "F":  fr_nlp,      # French
}

SUPPORTED_LANGUAGE_TAGS = {"GR", "G", "F", "I", "H", "D"}
DEEP_PIPELINE_TAGS      = {"GR", "G", "F"}
SHALLOW_TAGS            = {"I", "H", "D"}

TAG_REGEX = re.compile(r"\[(?P<tag>[A-Za-z]+)]|\[/(?P<etag>[A-Za-z]+)]")
GREEK_RE  = re.compile(r"[\u0370-\u03FF\u1F00-\u1FFF]")



# =============================================================================
# 1. TOKEN / DOC EXTENSIONS
# =============================================================================

for ext, default in [
    ("pages", None),
    ("textblocks", None),
    ("tags", None),
    ("block_type", None),
]:
    if not Token.has_extension(ext):
        Token.set_extension(ext, default=default)

if not Token.has_extension("ml_data"):
    Token.set_extension("ml_data", default={})

if not Doc.has_extension("char_to_source"):
    Doc.set_extension("char_to_source", default=None)


# =============================================================================
# 2. LANGUAGE TAG EXTRACTION (ON PRESANITIZED TEXT)
# =============================================================================

def extract_language_tags_from_block(text: str):
    """
    Builds a per-character language tag map from the (already presanitized)
    textblock string.

    Assumptions about input:
      - Language tags [GR]...[/GR], [G]...[/G], etc. are well-formed and
        properly spaced by the presanitizer.
      - S-tags [S]...[/S] are well-formed and space-isolated.
      - No malformed / dangling bracket sequences remain.

    Rules for each label L in SUPPORTED_LANGUAGE_TAGS:

      - [L] ... [/L]    → normal span
      - [/L] unmatched  → span from block start → position of [/L]
      - [L] unmatched   → span from [L] → block end

    S-tags are ignored completely here.

    Greek Unicode always receives "GR". Markup [GR]...[/GR] is ignored for
    span purposes (we rely on Unicode for Greek).
    """
    tags_map = {}

    # 1) Greek by unicode
    for i, ch in enumerate(text):
        if GREEK_RE.match(ch):
            tags_map.setdefault(i, set()).add("GR")

    # 2) Markup spans (skip GR; already covered by unicode)
    matches = list(TAG_REGEX.finditer(text))

    for label in SUPPORTED_LANGUAGE_TAGS:
        if label == "GR":
            continue  # avoid double-tagging

        open_stack = []

        for m in matches:
            tag  = m.group("tag")
            etag = m.group("etag")

            # skip S-tags entirely
            if tag == "S" or etag == "S":
                continue

            if tag == label:
                open_stack.append(m)
            elif etag == label:
                if open_stack:
                    om = open_stack.pop()
                    start = om.end()
                    end   = m.start()
                    for idx in range(start, end):
                        tags_map.setdefault(idx, set()).add(label)
                else:
                    # unmatched closer: from start of block → this point
                    for idx in range(0, m.start()):
                        tags_map.setdefault(idx, set()).add(label)

        # unmatched openers: from open tag to end of block
        for om in open_stack:
            start = om.end()
            for idx in range(start, len(text)):
                tags_map.setdefault(idx, set()).add(label)

    return tags_map


# =============================================================================
# 3. CLEAN TRANSDUCER (SANITIZED → CLEAN), INLINE S INTERPRETATION
# =============================================================================

def _clean_block_with_mapping(text: str, page_idx: int, tb_idx: int, tb_tag: str):
    """
    Convert a *presanitized* textblock string to:

      - clean_text  (for nlp_latin)
      - char_src    { clean_index → metadata }

    S-placeholders are emitted as *one logical unit* — every char
    receives identical metadata.
    """

    raw_tags = extract_language_tags_from_block(text)

    clean_chars = []
    char_src = {}

    # ---------------------------------------------------------
    # Multi-character emitter (for SYMBOL_PLACEHOLDER)
    # ---------------------------------------------------------
    def emit_string(s, tags_here=None, symbol_text=None):
        if tags_here is None:
            tags_here = set()
        base = len(clean_chars)

        for ch in s:
            clean_chars.append(ch)

        meta = {
            "page_idx": page_idx,
            "textblock_idx": tb_idx,
            "textblock_type": tb_tag,
        }
        if tags_here:
            meta["tags"] = sorted(tags_here)
        if symbol_text is not None:
            meta["symbol"] = symbol_text

        for offset in range(len(s)):
            char_src[base + offset] = meta.copy()

    # single-char emitter
    def emit_char(ch_out, tags_here=None):
        if tags_here is None:
            tags_here = set()
        clean_idx = len(clean_chars)
        clean_chars.append(ch_out)
        meta = {
            "page_idx": page_idx,
            "textblock_idx": tb_idx,
            "textblock_type": tb_tag,
        }
        if tags_here:
            meta["tags"] = sorted(tags_here)
        char_src[clean_idx] = meta

    def emit_symbol(sym_text):
        sym_text = sym_text or SYMBOL_PLACEHOLDER
        emit_string(SYMBOL_PLACEHOLDER, tags_here={"S"}, symbol_text=sym_text)

    i = 0
    n = len(text)

    while i < n:
        ch = text[i]

        # --- S-tags: [S]content[/S] → single SYMBOL_PLACEHOLDER span ---
        if text.startswith(S_OPEN, i):
            start_inner = i + len(S_OPEN)
            end_tag = text.find(S_CLOSE, start_inner)
            if end_tag == -1:
                i += len(S_OPEN)
                continue

            content = text[start_inner:end_tag].strip() or SYMBOL_PLACEHOLDER
            emit_symbol(content)

            i = end_tag + len(S_CLOSE)
            continue

        if text.startswith(S_CLOSE, i):
            i += len(S_CLOSE)
            continue

        # --- language tags: removed here ---
        if ch == "[":
            m = TAG_REGEX.match(text, i)
            if m:
                tag  = m.group("tag")
                etag = m.group("etag")
                # skip all non-S tags
                if (tag and tag != "S") or (etag and etag != "S"):
                    i = m.end()
                    continue

        # --- normal characters ---
        tags_here = set(raw_tags.get(i, set()))
        if GREEK_RE.match(ch):
            tags_here.add("GR")

        # whitespace
        if ch == " ":
            emit_char(" ", tags_here)
            i += 1
            continue

        # NO MORE Latin OCR fixes here: they are now done in sanitization

        ch_out = unicodedata.normalize("NFC", ch)
        emit_char(ch_out, tags_here)
        i += 1

    # --- OPTIONAL: remove leading space safely (unchanged) ---
    if clean_chars and clean_chars[0] == " ":
        clean_chars.pop(0)
        new_src = {}
        for k, v in char_src.items():
            if k == 0:
                continue  # dropped leading space
            new_src[k - 1] = v
        char_src = new_src

    return "".join(clean_chars), char_src

# =============================================================================
# 4. BUILD FULL CLEAN TEXTS
# =============================================================================

def _process_textblocks_for_tags(textblocks, allowed_tags):
    """
    Iterate over nested textblocks[page][tb], pick those whose 'tag'
    is in allowed_tags, and concatenate their cleaned text.

    Returns:
      - clean_full: string
      - mapping:    { global_clean_index → metadata }
    """
    clean_full = ""
    mapping = {}
    offset = 0

    for page_i, page in enumerate(textblocks):
        for tb_i, tb in enumerate(page):
            if tb["tag"] not in allowed_tags:
                continue

            ctext, cmap = _clean_block_with_mapping(
                tb["text"], page_i, tb_i, tb["tag"]
            )

            for local_idx, meta in cmap.items():
                mapping[offset + local_idx] = meta

            clean_full += ctext
            offset += len(ctext)

    return clean_full, mapping


# =============================================================================
# 5. HIGH-LEVEL PROCESSOR (PRESANITIZED INPUT)
# =============================================================================

def process_with_source_tracking(textblocks, nlp):
    """
    Main entry point.

    IMPORTANT: `textblocks` must ALREADY be presanitized externally.
    That is, each tb["text"] is in the normalized tagged form such as:

        ' [S]xyzxyzus[/S] Sal (vel [S]Gemini[/S] [S]xyzxyzus[/S] ) ...'

    This function:
      - builds a 'main' Doc from tags {"text", "title"}
      - builds a 'margin' Doc from tag {"margin"}
      - attaches char→source maps into doc._.char_to_source
      - runs the full nlp pipeline (with our added components)
    """

    # MAIN
    clean_main, src_main = _process_textblocks_for_tags(
        textblocks, {"text", "title"}
    )
    doc_main = nlp.make_doc(clean_main)
    doc_main._.char_to_source = src_main
    for _, proc in nlp.pipeline:
        doc_main = proc(doc_main)

    # MARGINS
    clean_marg, src_marg = _process_textblocks_for_tags(
        textblocks, {"margin"}
    )
    doc_marg = nlp.make_doc(clean_marg)
    doc_marg._.char_to_source = src_marg
    for _, proc in nlp.pipeline:
        doc_marg = proc(doc_marg)

    return doc_main, doc_marg


# =============================================================================
# 6. SOURCE TRACKER
# =============================================================================

@Language.component("source_tracker")
def source_tracker(doc):
    cts = doc._.char_to_source
    if cts is None:
        return doc

    for tok in doc:
        pages = set()
        blocks = set()
        btypes = set()
        tags = set()
        symbol = None

        for i in range(tok.idx, tok.idx + len(tok.text)):
            info = cts.get(i)
            if not info:
                continue
            pages.add(info["page_idx"])
            blocks.add(info["textblock_idx"])
            if info.get("textblock_type"):
                btypes.add(info["textblock_type"])
            ttags = info.get("tags")
            if ttags:
                tags.update(ttags)
            if symbol is None and "symbol" in info:
                symbol = info["symbol"]

        tok._.pages      = sorted(pages) if pages else None
        tok._.textblocks = sorted(blocks) if blocks else None
        tok._.block_type = sorted(btypes)[0] if btypes else "text"
        tok._.tags       = sorted(tags) if tags else None

        if symbol is not None:
            tok._.ml_data = tok._.ml_data or {}
            tok._.ml_data["symbol"] = symbol

    return doc


# =============================================================================
# 7. SENTENCIZER
# =============================================================================

@Language.component("blocktype_sentencizer")
def blocktype_sentencizer(doc):
    """
    Sentence boundaries follow block_type boundaries:
      - first token in doc → sent_start = True
      - whenever block_type changes → new sentence
    """
    prev = None
    for tok in doc:
        bt = getattr(tok._, "block_type", "text")
        if prev is None or bt != prev:
            tok.is_sent_start = True
        prev = bt
    return doc


# =============================================================================
# 8. MULTILINGUAL ENRICHER (WITH CHAR-ALIGNMENT)
# =============================================================================

@Language.component("multilingual_enricher")
def multilingual_enricher(doc):
    """
    For each deep language tag (GR, G, F), collect contiguous spans of tokens
    that carry that tag, run the corresponding external nlp model on each span,
    and align external tokens to our Latin tokens using char overlap.

    For shallow languages (I, H, D), only record presence in tok._.ml_data["languages"].
    """
    spans_by_lang = {L: [] for L in DEEP_PIPELINE_TAGS}

    # collect contiguous spans per language
    for L in DEEP_PIPELINE_TAGS:
        cur = []
        for tok in doc:
            if tok._.tags and L in tok._.tags:
                cur.append(tok)
            else:
                if cur:
                    spans_by_lang[L].append(cur)
                    cur = []
        if cur:
            spans_by_lang[L].append(cur)

    # run external models with char-based alignment
    for L, spanlists in spans_by_lang.items():
        nlp_model = LANG_PIPELINES[L]

        for toklist in spanlists:
            s0 = toklist[0].i
            s1 = toklist[-1].i + 1
            sub = doc[s0:s1]

            gdoc = nlp_model(sub.text)
            g_tokens = list(gdoc)

            for lt in sub:
                if not (lt._.tags and L in lt._.tags):
                    continue

                # relative char span of lt inside sub.text
                rel_start = lt.idx - sub.start_char
                rel_end   = rel_start + len(lt.text)

                best = None
                for gt in g_tokens:
                    gstart = gt.idx
                    gend   = gstart + len(gt.text)
                    if not (gend <= rel_start or gstart >= rel_end):
                        best = gt
                        break

                if best is None:
                    continue

                base = dict(lt._.ml_data or {})
                base.update({
                    "language": L,
                    "lemma": best.lemma_,
                    "pos": best.pos_,
                    "morph": best.morph.to_dict(),
                })
                lt._.ml_data = base
                # override Latin analysis
                lt.lemma_ = best.lemma_
                lt.pos_   = best.pos_

    # shallow languages: I, H, D
    for tok in doc:
        if tok._.tags:
            shallow = set(tok._.tags) & SHALLOW_TAGS
            if shallow:
                tok._.ml_data = tok._.ml_data or {}
                langs = tok._.ml_data.get("languages", [])
                tok._.ml_data["languages"] = sorted(set(langs) | shallow)

    return doc


# =============================================================================
# 9. SYMBOL LEMMA ENRICHER
# =============================================================================

@Language.component("symbol_lemma_enricher")
def symbol_lemma_enricher(doc):
    """
    For S-symbol tokens, set lemma_ to the original symbol text
    from tok._.ml_data["symbol"] (if present).
    """
    for tok in doc:
        if tok._.tags and "S" in tok._.tags:
            md = tok._.ml_data or {}
            sym = md.get("symbol")
            if sym:
                tok.lemma_ = sym
    return doc


# =============================================================================
# 10. PIPE REGISTRATION
# =============================================================================

for comp in [
    "source_tracker",
    "blocktype_sentencizer",
    "multilingual_enricher",
    "symbol_lemma_enricher",
]:
    if comp in nlp_latin.pipe_names:
        nlp_latin.remove_pipe(comp)

if "senter" in nlp_latin.pipe_names:
    nlp_latin.add_pipe("source_tracker", before="senter")
elif "parser" in nlp_latin.pipe_names:
    nlp_latin.add_pipe("source_tracker", before="parser")
else:
    first = nlp_latin.pipe_names[0] if nlp_latin.pipe_names else None
    nlp_latin.add_pipe("source_tracker", before=first)

nlp_latin.add_pipe("blocktype_sentencizer", after="source_tracker")
nlp_latin.add_pipe("multilingual_enricher", last=True)
nlp_latin.add_pipe("symbol_lemma_enricher", last=True)


# 13. SHORT DEBUGGER (ASSUMES PRESANITIZED INPUT)
# =============================================================================

def debug_clean_block(textblocks, page_idx, tb_idx):
    """
    Debug the full path for a *single* textblock:
      sanitized textblock.text → clean → mapping → tokens.
    Assumes textblocks are already presanitized at tb["text"] level.
    """
    tb = textblocks[page_idx][tb_idx]
    s_text = tb["text"]

    print("====== SANITIZED INPUT ======")
    print(repr(s_text), "\n")

    # IMPORTANT: match the actual function signature!
    clean, src = _clean_block_with_mapping(
        text=s_text,          # <--- changed from raw_text=
        page_idx=page_idx,
        tb_idx=tb_idx,
        tb_tag=tb["tag"],
    )

    print("====== CLEAN TEXT ======")
    print(repr(clean), "\n")

    print("====== CLEAN CHAR MAP ======")
    for idx, ch in enumerate(clean):
        meta = src.get(idx, {})
        print(f"{idx:4d}  {repr(ch):3s}  {meta}")
    print()

    # ---- CRUCIAL: attach mapping BEFORE running the pipeline ----
    tmp = nlp_latin.make_doc(clean)
    tmp._.char_to_source = src

    for name, proc in nlp_latin.pipeline:
        tmp = proc(tmp)

    print("====== TOKENIZATION ======")
    for tok in tmp:
        sym = tok._.ml_data.get("symbol") if tok._.ml_data else None
        print(
            f"{repr(tok.text)}  idx={tok.idx}  "
            f"tags={tok._.tags}  symbol={sym}"
        )

    return s_text, clean, src, tmp


SPECIAL_SYMBOL_CHAR = "◉"
PLACEHOLDER = "xyzxyzus"

PUNCT_OPEN  = set("([{«\"“‘")
PUNCT_CLOSE = set(".,;:!?)»\"’]")

def doc_to_sent_dicts(doc, work_id):

    sent_dicts = []

    for sent_id, sent in enumerate(doc.sents):

        rebuilt = []   # list of (token_obj, rendered_text)
        for t in sent:
            raw = t.text

            # SYMBOL → replace with SPECIAL_SYMBOL_CHAR
            if raw == PLACEHOLDER:
                txt = SPECIAL_SYMBOL_CHAR
            else:
                txt = raw.replace(PLACEHOLDER, SPECIAL_SYMBOL_CHAR)
            # -----------------------------------------------------------
            # NEW: apply same word-normalization as lemma/token_text
            # -----------------------------------------------------------
            if txt and txt.isalpha():  # only alphabetic tokens, not symbols or numbers
                if len(txt) > 1:
                    txt = txt[0] + txt[1:].lower()

            if not txt.strip():
                continue

            rebuilt.append((t, txt))

        if not rebuilt:
            continue

        # -----------------------------------------------------
        # 1. Build sentence text with correct punctuation spacing
        # -----------------------------------------------------
        parts = []
        for i, (t, txt) in enumerate(rebuilt):

            if i == 0:
                parts.append(txt)
                continue

            prev_txt = rebuilt[i-1][1]
            first = txt[0]

            if first in PUNCT_CLOSE:
                parts.append(txt)
                continue

            if prev_txt[-1] in PUNCT_OPEN:
                parts.append(txt)
                continue

            parts.append(" " + txt)

        sent_text = "".join(parts)

        # -----------------------------------------------------
        # 2. Compute new token offsets
        # -----------------------------------------------------
        sent_tokens = []
        cursor = 0

        for i, (t, txt_rendered) in enumerate(rebuilt):

            if i == 0:
                start = 0
            else:
                prev_txt = rebuilt[i-1][1]
                first = txt_rendered[0]

                if first in PUNCT_CLOSE:
                    start = cursor
                elif prev_txt[-1] in PUNCT_OPEN:
                    start = cursor
                else:
                    start = cursor + 1

            end = start + len(txt_rendered)
            cursor = end

            # --------------------------------------
            # CORRECTED: lemma / pos logic
            # --------------------------------------
            tags = list(t._.tags) if t._.tags else []
            tag = ""
            if len(tags) > 0:
                if "GR" in tags:
                    tag = "GR"
                else:
                    tag = tags[0]

            ml = t._.ml_data or {}

            is_symbol = (tag == "S") or ("symbol" in ml)

            if is_symbol:
                # REAL ORIGINAL SYMBOL OR fallback
                lemma = ml.get("symbol", SPECIAL_SYMBOL_CHAR)
                pos   = "SYM"
                token_text = SPECIAL_SYMBOL_CHAR

            else:
                # multilingual
                if ml.get("language") in {"GR", "G", "F"}:
                    lemma = ml.get("lemma") or t.lemma_ or txt_rendered
                    pos   = ml.get("pos")   or t.pos_
                else:
                    lemma = t.lemma_ or txt_rendered
                    pos   = t.pos_

                token_text = txt_rendered

            # absolutely never allow placeholder as lemma
            if lemma == PLACEHOLDER:
                lemma = SPECIAL_SYMBOL_CHAR
            if pos not in ["NUM"]:
                if len(lemma) > 1:
                    lemma = lemma[0] + lemma[1:].lower()
                if len(token_text) > 1:
                    token_text = token_text[0] + token_text[1:].lower()
            tok_dict = {
                "token_text": token_text,
                "lemma": lemma,
                "pos": pos,
                "ref": {
                    "page": list(t._.pages) if t._.pages else [],
                    "textblock": list(t._.textblocks) if t._.textblocks else [],
                    "tag": tag,
                    "blocktype": t._.block_type or "text",
                },
                "char_start": start,
                "char_end": end,
            }

            sent_tokens.append(tok_dict)

        sent_dicts.append({
            "work_id": work_id,
            "sent_id": sent_id,
            "sent_text": sent_text,
            "tokens_data": sent_tokens,
        })

    return sent_dicts


def get_token_coordinates(token, textblocks):
    """
    Returns the coordinates (x0, y0, x1, y1) of the ORIGINAL OCR textblock
    that produced the token.

    token.ref MUST contain:
        - "page": [int]
        - "textblock": [int]
    """

    ref = token["ref"]
    if ref is None:
        return None

    page_list = ref.get("page")
    tb_list = ref.get("textblock")

    if not page_list or not tb_list:
        return None

    page_idx = page_list[0]
    tb_idx = tb_list[0]

    try:
        tb = textblocks[page_idx][tb_idx]
        return tb["coordinates"]
    except Exception as e:
        print("Coordinate lookup failed:", e)
        return None

def attach_coordinates_to_sent_dicts(sent_dicts, textblocks):
    for sent in sent_dicts:
        for tok in sent["tokens_data"]:
            tok["coordinates"] = get_token_coordinates(tok, textblocks)
    return sent_dicts


def merge_main_and_margin_sentences(
    sent_dicts_with_coords,
    sent_dicts_margins_with_coords
):
    """
    Returns a *single merged list* of sentence dicts,
    where margin sentences are inserted after the main-text
    sentences whose last-token y0 is VERTICALLY NEAREST
    to the first-token y0 of the margin sentence (on the same page).

    MAIN SENTENCE anchor_y  = last_token.coordinates[1]
    MARGIN SENTENCE anchor_y = first_token.coordinates[1]
    """

    from collections import defaultdict

    main_by_page = defaultdict(list)
    margin_by_page = defaultdict(list)

    # --- 1. Main text: anchor = y of last token ---
    for s in sent_dicts_with_coords:
        if not s.get("tokens_data"):
            continue

        last_tok = s["tokens_data"][-1]
        coords = last_tok.get("coordinates")
        if coords is None:
            continue

        page = last_tok["ref"]["page"][-1]
        s["_anchor_y"] = float(coords[1])  # y0 of last token
        s["_page"] = page
        main_by_page[page].append(s)

    # --- 2. Margins: anchor = y of *first* token ---
    for s in sent_dicts_margins_with_coords:
        if not s.get("tokens_data"):
            continue

        first_tok = s["tokens_data"][0]
        coords = first_tok.get("coordinates")
        if coords is None:
            continue

        page = first_tok["ref"]["page"][0]
        s["_anchor_y"] = float(coords[1])  # y0 of first token
        s["_page"] = page
        margin_by_page[page].append(s)

    merged = []
    all_pages = sorted(set(main_by_page.keys()) | set(margin_by_page.keys()))

    for page in all_pages:
        mains = main_by_page.get(page, [])
        margins = margin_by_page.get(page, [])

        # If there is no main text on this page, just append margins in vertical order
        if not mains:
            for m in sorted(margins, key=lambda s: s["_anchor_y"]):
                merged.append(m)
            continue

        # Sort main sentences by their anchor_y
        mains_sorted = sorted(mains, key=lambda s: s["_anchor_y"])

        # Prepare: list of lists of margins to attach after each main
        attach_after = {i: [] for i in range(len(mains_sorted))}

        # For each margin, find nearest main *on that page*
        for m in margins:
            m_y = m["_anchor_y"]

            best_i = None
            best_dist = float("inf")
            for i, main_s in enumerate(mains_sorted):
                dist = abs(main_s["_anchor_y"] - m_y)
                if dist < best_dist:
                    best_dist = dist
                    best_i = i

            # Attach margin AFTER that main sentence
            attach_after[best_i].append(m)

        # Interleave: main, then all margins attached to it
        out_page = []
        for i, main_s in enumerate(mains_sorted):
            out_page.append(main_s)
            if attach_after[i]:
                out_page.extend(attach_after[i])

        merged.extend(out_page)

    # --- Cleanup temp fields + reassign global sent_id ---
    for new_id, s in enumerate(merged):
        s["sent_id"] = new_id
        s.pop("_anchor_y", None)
        s.pop("_page", None)

    return merged

