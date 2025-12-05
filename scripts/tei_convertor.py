import xml.etree.ElementTree as ET

TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"
NSMAP = {"tei": TEI_NS}  # kept for potential future use


def tei(tag: str) -> str:
    """Helper to build TEI namespaced tags."""
    return f"{{{TEI_NS}}}{tag}"


# Default mapping from your tag codes to BCP47-ish / TEI lang codes
LANG_MAP_DEFAULT = {
    "":   "la",   # default Latin
    "GR": "grc",  # Greek
    "G":  "de",   # German
    "F":  "fr",   # French
    "I":  "it",   # Italian
    "H":  "he",   # Hebrew
    "D":  "nl",   # Dutch
}


def get_lang(tag: str, lang_map: dict) -> str:
    """Map your language tag (GR, G, F...) to a language code."""
    return lang_map.get(tag, lang_map.get("", "la"))


class JsonToTeiConverter:
    def __init__(
        self,
        lang_map=None,
        insert_page_breaks: bool = True,
        insert_line_breaks: bool = True,
        margin_as_note: bool = False,
    ):
        self.lang_map = lang_map or LANG_MAP_DEFAULT
        self.insert_page_breaks = insert_page_breaks
        self.insert_line_breaks = insert_line_breaks
        self.margin_as_note = margin_as_note

    # ---------- high-level API ----------

    def convert_many(self, all_sentences, metadata_by_work):
        """
        Convert a list of sentence dicts (with work_id) into
        a dict: work_id -> TEI root element.
        """
        works = {}
        for sent in all_sentences:
            wid = str(sent["work_id"])
            works.setdefault(wid, []).append(sent)

        result = {}
        for wid, sents in works.items():
            sents_sorted = sorted(sents, key=lambda s: s["sent_id"])
            meta = metadata_by_work.get(wid, {})
            result[wid] = self.convert_work(wid, sents_sorted, meta)
        return result

    def convert_work(self, work_id: str, sentences, meta: dict):
        """
        Convert all sentences of one work + its metadata dict
        into a TEI root element (<TEI>).
        """
        # Root <TEI>
        tei_el = ET.Element(tei("TEI"))
        tei_el.set(f"{{{XML_NS}}}id", f"w{work_id}")

        # Header
        header = self.build_header(meta, work_id)
        tei_el.append(header)

        # Text body; default language Latin at <text> level
        text = ET.SubElement(tei_el, tei("text"), {f"{{{XML_NS}}}lang": "la"})
        body = ET.SubElement(text, tei("body"))
        div = ET.SubElement(
            body,
            tei("div"),
            {
                "type": "work",
                f"{{{XML_NS}}}id": f"w{work_id}",
            },
        )
        p = ET.SubElement(div, tei("p"))

        current_page = None
        current_line = None

        for sent in sentences:
            s_attrs = {
                "n": str(sent["sent_id"]),
                f"{{{XML_NS}}}id": f"w{work_id}_s{sent['sent_id']:04d}",
            }

            tokens = sent.get("tokens_data", [])
            all_margin = tokens and all(
                (t.get("ref") or {}).get("blocktype") == "margin"
                for t in tokens
            )

            # If configured, wrap all-margin sentences in <note place="margin">
            if self.margin_as_note and all_margin:
                note = ET.SubElement(p, tei("note"), {"place": "margin"})
                container = ET.SubElement(note, tei("s"), s_attrs)
            else:
                container = ET.SubElement(p, tei("s"), s_attrs)

            for tok_id, tok in enumerate(tokens):
                ref = tok.get("ref", {}) or {}
                page_list = ref.get("page") or [None]
                line_list = ref.get("textblock") or [None]
                page = page_list[0]
                line = line_list[0]

                # Page / line breaks as TEI milestones
                if self.insert_page_breaks and page is not None and page != current_page:
                    ET.SubElement(container, tei("pb"), {"n": str(page + 1)})
                    current_page = page

                if self.insert_line_breaks and line is not None and line != current_line:
                    ET.SubElement(container, tei("lb"), {"n": str(line + 1)})
                    current_line = line

                # word vs punctuation
                el_name = "pc" if tok.get("pos") == "PUNCT" else "w"

                token_id = f"w{work_id}_s{sent['sent_id']:04d}_t{tok_id:03d}"
                attrs = {
                    f"{{{XML_NS}}}id": token_id,
                    "pos": tok.get("pos", ""),
                }

                # lemma only for words, not punctuation
                if el_name == "w":
                    attrs["lemma"] = tok.get("lemma", "")

                # language: only override if non-Latin
                lang_tag = ref.get("tag", "")
                lang_code = get_lang(lang_tag, self.lang_map)
                if lang_code != "la":
                    attrs[f"{{{XML_NS}}}lang"] = lang_code

                # blocktype -> @type, normalized lowercase
                blocktype = ref.get("blocktype")
                if blocktype:
                    attrs["type"] = str(blocktype).lower()

                w_el = ET.SubElement(container, tei(el_name), attrs)
                w_el.text = tok.get("token_text", "")

        return tei_el

    # ---------- header construction ----------

    def build_header(self, meta: dict, work_id: str):
        """
        Build a TEI <teiHeader> for a single work.
        meta is a dict for a single row, keys like:
        'title_full', 'title_short', 'working_title',
        'author_name', 'author_viaf', 'author_cerl', ...
        """
        header = ET.Element(tei("teiHeader"))

        # ---- fileDesc ----
        file_desc = ET.SubElement(header, tei("fileDesc"))

        # 1) titleStmt
        title_stmt = ET.SubElement(file_desc, tei("titleStmt"))

        title_full = meta.get("title_full") or meta.get("TITLE")
        title_short = meta.get("title_short")
        working_title = meta.get("working_title")

        if title_full:
            t_main = ET.SubElement(title_stmt, tei("title"), {"type": "main"})
            t_main.text = str(title_full)

        if title_short and title_short != title_full:
            t_short = ET.SubElement(title_stmt, tei("title"), {"type": "short"})
            t_short.text = str(title_short)

        if working_title:
            t_working = ET.SubElement(title_stmt, tei("title"), {"type": "working"})
            t_working.text = str(working_title)

        # Author
        if meta.get("is_author_known"):
            author_el = ET.SubElement(title_stmt, tei("author"))
            pers = ET.SubElement(author_el, tei("persName"))
            pers.text = str(meta.get("author_name"))

            viaf = meta.get("author_viaf")
            if viaf and str(viaf) != "nan":
                idno_viaf = ET.SubElement(author_el, tei("idno"), {"type": "viaf"})
                idno_viaf.text = (
                    str(int(viaf)) if isinstance(viaf, (int, float)) else str(viaf)
                )

            cerl = meta.get("author_cerl")
            if cerl and str(cerl) != "nan":
                idno_cerl = ET.SubElement(author_el, tei("idno"), {"type": "cerl"})
                idno_cerl.text = str(cerl)

            alt = meta.get("author_name_alternatives")
            if alt and str(alt) != "nan":
                pers_alt = ET.SubElement(author_el, tei("persName"), {"type": "alt"})
                pers_alt.text = str(alt)

            a_comm = meta.get("author_comments")
            if a_comm and str(a_comm) != "nan":
                note = ET.SubElement(author_el, tei("note"))
                note.text = str(a_comm)
        else:
            author_el = ET.SubElement(title_stmt, tei("author"))
            author_el.text = "Anonymous"

        # Translator / editor as respStmt
        if meta.get("is_translator"):
            resp = ET.SubElement(title_stmt, tei("respStmt"))
            r = ET.SubElement(resp, tei("resp"))
            r.text = "translator"
            n = ET.SubElement(resp, tei("name"))
            n.text = str(meta.get("translator_name"))
            t_comm = meta.get("translator_comments")
            if t_comm and str(t_comm) != "nan":
                note = ET.SubElement(resp, tei("note"))
                note.text = str(t_comm)

        if meta.get("is_editor"):
            resp = ET.SubElement(title_stmt, tei("respStmt"))
            r = ET.SubElement(resp, tei("resp"))
            r.text = "editor"
            n = ET.SubElement(resp, tei("name"))
            n.text = str(meta.get("editor_name"))
            e_comm = meta.get("editor_comments")
            if e_comm and str(e_comm) != "nan":
                note = ET.SubElement(resp, tei("note"))
                note.text = str(e_comm)

        # 2) extent (before publicationStmt in TEI fileDesc)
        tokens_n = meta.get("tokens_N")
        if tokens_n and str(tokens_n) != "nan":
            extent = ET.SubElement(file_desc, tei("extent"))
            measure = ET.SubElement(extent, tei("measure"), {"unit": "token"})
            measure.text = str(int(tokens_n))

        # 3) publicationStmt
        pub_stmt = ET.SubElement(file_desc, tei("publicationStmt"))

        # Publisher
        pub_name = meta.get("publisher_name")
        if pub_name and str(pub_name) != "nan":
            pub_el = ET.SubElement(pub_stmt, tei("publisher"))
            org = ET.SubElement(pub_el, tei("orgName"))
            org.text = str(pub_name)

        # Pub place
        place_name = meta.get("place_publication")
        if place_name and str(place_name) != "nan":
            pub_place = ET.SubElement(pub_stmt, tei("pubPlace"))
            pl = ET.SubElement(pub_place, tei("placeName"))
            pl.text = str(place_name)
            geo = meta.get("place_geonames")
            if geo and str(geo) != "nan":
                idno_geo = ET.SubElement(pub_place, tei("idno"), {"type": "geonames"})
                idno_geo.text = (
                    str(int(geo)) if isinstance(geo, (int, float)) else str(geo)
                )

        # Date
        date_el = ET.SubElement(pub_stmt, tei("date"))
        date_pub = meta.get("date_publication")
        not_before = meta.get("date_not_before")
        not_after = meta.get("date_not_after")
        cert = meta.get("date_certainty")

        if not_before or not_after:
            if not_before and str(not_before) != "nan":
                date_el.set("notBefore", str(int(not_before)))
            if not_after and str(not_after) != "nan":
                date_el.set("notAfter", str(int(not_after)))
        elif date_pub and str(date_pub) != "nan":
            date_el.set("when", str(int(date_pub)))
            if cert is not None:
                date_el.set("cert", "high" if bool(cert) else "low")

        if date_pub and str(date_pub) != "nan":
            date_el.text = str(int(date_pub))

        d_comm = meta.get("date_comment")
        if d_comm and str(d_comm) != "nan":
            note = ET.SubElement(pub_stmt, tei("note"))
            note.text = str(d_comm)

        # minimal availability, TEI-style
        availability = ET.SubElement(pub_stmt, tei("availability"))
        p_avail = ET.SubElement(availability, tei("p"))
        p_avail.text = "Generated for scholarly use."

        # 4) sourceDesc
        source_desc = ET.SubElement(file_desc, tei("sourceDesc"))
        bibl = ET.SubElement(source_desc, tei("bibl"))

        if title_full:
            t_bibl = ET.SubElement(bibl, tei("title"))
            t_bibl.text = str(title_full)

        link = meta.get("link")
        if link and str(link) != "nan":
            ref = ET.SubElement(bibl, tei("ref"), {"target": str(link)})
            ref.text = "Digital facsimile"

        if_nosc = meta.get("if_noscemus_id")
        if if_nosc and str(if_nosc) != "nan":
            idno_n = ET.SubElement(bibl, tei("idno"), {"type": "noscemus"})
            idno_n.text = (
                str(int(if_nosc)) if isinstance(if_nosc, (int, float)) else str(if_nosc)
            )

        src_file = meta.get("source_of_file")
        if src_file and str(src_file) != "nan":
            idno_src = ET.SubElement(bibl, tei("idno"), {"type": "source-of-file"})
            idno_src.text = str(src_file)

        origin = meta.get("origin_of_copy")
        if origin and str(origin) != "nan":
            idno_org = ET.SubElement(bibl, tei("idno"), {"type": "origin-of-copy"})
            idno_org.text = str(origin)

        # ---- encodingDesc ----
        encoding_desc = ET.SubElement(header, tei("encodingDesc"))
        p_enc = ET.SubElement(encoding_desc, tei("p"))
        p_enc.text = (
            "Tokenization, lemmatization, and POS tagging produced by the EMLAP "
            "pipeline; TEI P5 export generated from JSON sentence data."
        )

        # ---- profileDesc ----
        profile_desc = ET.SubElement(header, tei("profileDesc"))
        text_class = ET.SubElement(profile_desc, tei("textClass"))

        genre = meta.get("genre")
        if genre and str(genre) != "nan":
            kw_genre = ET.SubElement(text_class, tei("keywords"), {"n": "genre"})
            term = ET.SubElement(kw_genre, tei("term"))
            term.text = str(genre)

        subject = meta.get("subject")
        if subject and str(subject) != "nan":
            kw_subj = ET.SubElement(text_class, tei("keywords"), {"n": "subject"})
            for part in str(subject).split(","):
                term = ET.SubElement(kw_subj, tei("term"))
                term.text = part.strip()

        # ---- revisionDesc ----
        revision_desc = ET.SubElement(header, tei("revisionDesc"))
        change = ET.SubElement(revision_desc, tei("change"))
        change.text = "Automatic export from JSON sentence data to TEI P5."

        return header