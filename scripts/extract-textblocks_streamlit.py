# %%
# run this app by:
# streamlit run extract-textblocks_streamlit.py --server.address localhost --server.port 8060 --browser.gatherUsageStats False

import os
import json
import random
import fitz
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import streamlit as st

# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def _safe_div(a, b, default=0.0):
    """Safe division that guards against zero/None/Nan denominators."""
    try:
        if b in (0, None):
            return default
        return a / b
    except Exception:
        return default

def _coerce_float(v, fallback):
    """Normalize slider default values to a single float."""
    if isinstance(v, (list, tuple)) and v:
        v = v[0]
    try:
        return float(v)
    except Exception:
        return float(fallback)

# ------------------------------------------------------------
# Heuristics
# ------------------------------------------------------------

def check_header(
    textblock, avg_width, avg_left_x,
    header_width_proportion_max=0.8,
    header_left_x_ratio_min=1.2,
    header_uppercase_proportion_min=0.6,
    header_digits_proportion_min=0.6
):
    width_ratio = _safe_div((textblock[2] - textblock[0]), avg_width, default=0.0)
    left_x_ratio = _safe_div(textblock[0], avg_left_x, default=1.0)

    textblock_text = (textblock[4] or "").replace("\n", "")
    L = len(textblock_text)
    if L == 0:
        uppercase_ratio = 0.0
        digits_ratio = 0.0
    else:
        uppercase_ratio = sum(1 for ch in textblock_text if ch.isupper()) / L
        digits_ratio = sum(1 for ch in textblock_text if ch.isdigit()) / L

    tests = [
        (width_ratio < header_width_proportion_max),
        (left_x_ratio > header_left_x_ratio_min),
        (uppercase_ratio > header_uppercase_proportion_min),
        (digits_ratio > header_digits_proportion_min),
    ]
    return sum(tests) >= 2


def check_footer(
    textblock, avg_width, avg_left_x, avg_right_x,
    footer_width_proportion_max=0.5,
    footer_left_x_ratio_min=1.2
):
    width_ratio = _safe_div((textblock[2] - textblock[0]), avg_width, default=0.0)
    left_x_ratio = _safe_div(textblock[0], avg_left_x, default=1.0)
    right_x_ratio = _safe_div(textblock[2], avg_right_x, default=1.0)

    textblock_text = (textblock[4] or "").replace("\n", "")
    L = len(textblock_text)
    digits_ratio = (sum(1 for ch in textblock_text if ch.isdigit()) / L) if L else 0.0

    tests = [
        (width_ratio < footer_width_proportion_max),
        (left_x_ratio > footer_left_x_ratio_min),  # use slider value
        (0.9 < right_x_ratio < 1.1),
        (digits_ratio > 0.6),
    ]
    return sum(tests) >= 2


def check_title(textblock, avg_charn_density, textblock_char_density_ratio_max=0.65):
    width = (textblock[2] - textblock[0])
    if width <= 0:
        return False
    textblock_char_density = len(textblock[4]) / width
    textblock_char_density_ratio = (textblock_char_density / avg_charn_density) if avg_charn_density else 0.0
    return textblock_char_density_ratio < textblock_char_density_ratio_max

# ------------------------------------------------------------
# Drawing / JSON helpers
# ------------------------------------------------------------

patch_color_dict = {
    "title": "green",
    "header": "red",
    "footer": "orange",
    "margin": "yellow",
    "text": "white",
}

def convert_to_json_format(pages_textblocks):
    json_data = []
    for page_blocks in pages_textblocks:
        page_data = []
        for block in page_blocks:
            block_dict = {
                "coordinates": [block[0], block[1], block[2], block[3]],
                "text": block[4],
                "tag": block[5],
            }
            page_data.append(block_dict)
        json_data.append(page_data)
    return json_data


def plot_patch(textblock_annotated, patch_color_dict, ax):
    color = patch_color_dict[textblock_annotated[5]]
    patch = patches.Rectangle(
        (textblock_annotated[0], textblock_annotated[1]),
        textblock_annotated[2] - textblock_annotated[0],
        textblock_annotated[3] - textblock_annotated[1],
        linewidth=0.3, edgecolor=color, facecolor='none'
    )
    ax.add_patch(patch)

# ------------------------------------------------------------
# Core annotation pipeline
# ------------------------------------------------------------

def get_page_annots(textblocks, ax, patch_color_dict=patch_color_dict, params=None):
    if params is None:
        params = {}

    if len(textblocks) < 3:
        return []
    else:
        textblocks_enumerated = [[el[0], el[1], el[2], el[3], el[4], n] for n, el in enumerate(textblocks)]
        textblocks = sorted(textblocks_enumerated, key=lambda x: x[1])
        textblocks = [[el[0], el[1], el[2], el[3], el[4], el[5], n] for n, el in enumerate(textblocks)]
        central_textblocks = textblocks[2:-1]

        # Averages (guard later with _safe_div)
        avg_width = np.mean([rect[2] - rect[0] for rect in central_textblocks]) if central_textblocks else 0.0
        avg_left_x = np.mean([rect[0] for rect in central_textblocks]) if central_textblocks else 0.0
        avg_right_x = np.mean([rect[2] for rect in central_textblocks]) if central_textblocks else 0.0

        try:
            valid = [tb for tb in central_textblocks if (tb[2] - tb[0]) > 0]
            total_chars = sum(len(tb[4]) for tb in valid)
            total_width = sum((tb[2] - tb[0]) for tb in valid)
            avg_charn_density = (total_chars / total_width) if total_width > 0 else 0.0
        except Exception:
            avg_charn_density = 0.0

        textblocks_annotated = []
        for textblock in textblocks:
            annot = "text"
            # header candidates: first two lines
            if textblock[6] in [0, 1]:
                if check_header(
                    textblock,
                    avg_width,
                    avg_left_x,
                    header_width_proportion_max=params["header_width_proportion_max"],
                    header_left_x_ratio_min=params["header_left_x_ratio_min"],
                    header_uppercase_proportion_min=params["header_uppercase_proportion_min"],
                    header_digits_proportion_min=params["header_digits_proportion_min"],
                ):
                    annot = "header"

            # footer candidate: last line
            if textblock[6] == len(textblocks) - 1:
                if check_footer(
                    textblock,
                    avg_width,
                    avg_left_x,
                    avg_right_x,
                    footer_width_proportion_max=params["footer_width_proportion_max"],
                    footer_left_x_ratio_min=params["footer_left_x_ratio_min"],
                ):
                    annot = "footer"

            # title if not header/footer
            if annot not in ("header", "footer"):
                if check_title(
                    textblock,
                    avg_charn_density,
                    textblock_char_density_ratio_max=params["textblock_char_density_ratio_max"],
                ):
                    annot = "title"

            textblocks_annotated.append([
                textblock[0], textblock[1], textblock[2], textblock[3],
                textblock[4], textblock[5], textblock[6], annot
            ])

        textblocks_annotated_reordered = [
            [el[0], el[1], el[2], el[3], el[4], el[7]]
            for el in sorted(textblocks_annotated, key=lambda x: x[5])
        ]

        # marginalia propagation
        margin_in_progress = False
        for tb in textblocks_annotated_reordered:
            if "[M]" in tb[4]:
                tb[4] = tb[4].replace("[M]", "")
                margin_in_progress = True
            if margin_in_progress:
                tb[5] = "margin"
            if "[/M]" in tb[4]:
                tb[4] = tb[4].replace("[/M]", "")
                margin_in_progress = False
            if ax is not None:
                plot_patch(tb, patch_color_dict, ax)

        return textblocks_annotated_reordered


def test_doc_annotations(doc, params, seed):
    random.seed(seed)
    pages_sample = random.sample([p for p in doc], min(8, len(doc)))
    pages_textblocks_annotated = []
    fig, axs = plt.subplots(2, 4, figsize=(8, 5), dpi=150)
    for p, ax in zip(pages_sample, axs.ravel()):
        pix = p.get_pixmap()
        np_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        textblocks = p.get_text_blocks()
        pages_textblocks_annotated.append(
            get_page_annots(textblocks, ax, patch_color_dict, params=params)
        )
        ax.axis('off')
        ax.imshow(np_array)
    return fig, pages_textblocks_annotated


def apply_and_save_annotations(filename, doc, params, dest_dir):
    pages_textblocks_annotated = []
    for p in doc:
        textblocks = p.get_text_blocks()
        annotations = get_page_annots(textblocks, ax=None, params=params)
        pages_textblocks_annotated.append(annotations)

    json_data = convert_to_json_format(pages_textblocks_annotated)
    json_filename = filename.replace('.pdf', '.json')
    with open(os.path.join(dest_dir, json_filename), 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    with open(os.path.join(dest_dir, filename.replace('.pdf', '_params.json')), 'w', encoding='utf-8') as f:
        json.dump(params, f)

# ------------------------------------------------------------
# Defaults (floats for stability)
# ------------------------------------------------------------

DEFAULT_PARAMS = {
    "header_width_proportion_max": 0.8,
    "header_left_x_ratio_min": 1.2,
    "header_uppercase_proportion_min": 0.6,
    "header_digits_proportion_min": 0.6,
    "footer_width_proportion_max": 0.5,
    "footer_left_x_ratio_min": 1.2,
    "textblock_char_density_ratio_max": 0.65,
}

# Edit these paths for your environment
source_dir = "/srv/data/tome/tome-corpus/EMLAP_2025-10-31/pdfs_only/"
#dest_dir = "/srv/data/tome/tome-corpus/EMLAP_2025-10-31/annotated_textblocks/"
dest_dir = "/srv/data/tome/tome-corpus/EMLAP_2025-10-31/annotated_textblocks_dev/"
os.makedirs(dest_dir, exist_ok=True)

# ------------------------------------------------------------
# Streamlit state
# ------------------------------------------------------------

if 'params' not in st.session_state:
    st.session_state.params = DEFAULT_PARAMS.copy()
if 'show_params_editor' not in st.session_state:
    st.session_state.show_params_editor = False
if 'default_params' not in st.session_state:
    st.session_state.default_params = DEFAULT_PARAMS.copy()
if 'current_file_index' not in st.session_state:
    st.session_state.current_file_index = 0
if 'current_samples' not in st.session_state:
    st.session_state.current_samples = None
if 'current_seed' not in st.session_state:
    st.session_state.current_seed = 0
if 'skipped_files' not in st.session_state:
    st.session_state.skipped_files = []

if 'filenames' not in st.session_state:
    st.session_state.filenames = sorted(
        f for f in os.listdir(source_dir) if f.lower().endswith(".pdf")
    )
filenames = st.session_state.filenames

# ------------------------------------------------------------
# UI / Flow
# ------------------------------------------------------------

if st.session_state.current_file_index < len(filenames):
    main_container = st.container()
    with main_container:
        filename = filenames[st.session_state.current_file_index]
        if ".pdf" in filename:
            filepath = os.path.join(source_dir, filename)

            # Skip if already processed
            if os.path.exists(os.path.join(dest_dir, filename.replace('.pdf', '.json'))):
                st.write(f"Skipping {filename} - already processed")
                st.session_state.current_file_index += 1
                st.rerun()

            doc = fitz.open(filepath)
            st.write(f"Processing file: {filename}")

            # draw sample pages
            if st.session_state.current_samples is None:
                fig, samples_annots = test_doc_annotations(
                    doc, st.session_state.params, st.session_state.current_seed
                )
                st.session_state.current_samples = (fig, samples_annots)
            else:
                fig, samples_annots = st.session_state.current_samples

            st.pyplot(fig, use_container_width=True)

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                if st.button("Accept and Save", key=f"accept_{st.session_state.current_file_index}"):
                    apply_and_save_annotations(filename, doc, st.session_state.params, dest_dir)
                    st.session_state.current_file_index += 1
                    st.session_state.current_samples = None
                    st.session_state.current_seed += 1
                    st.session_state.params = st.session_state.default_params.copy()
                    st.rerun()

            with col2:
                if st.button("Another Sample", key=f"resample_{st.session_state.current_file_index}"):
                    st.session_state.current_seed += 1
                    st.session_state.current_samples = None
                    st.rerun()

            with col3:
                if st.button("Add to Skipped"):
                    st.session_state.skipped_files.append(filename)
                    st.session_state.current_file_index += 1
                    st.session_state.current_samples = None
                    st.session_state.current_seed += 1
                    st.session_state.params = st.session_state.default_params.copy()
                    st.rerun()

            with col4:
                if st.button("Revise Parameters", key=f"revise_{st.session_state.current_file_index}"):
                    st.session_state.show_params_editor = True

            if st.session_state.show_params_editor:
                with st.expander("Parameter Settings", expanded=True):
                    new_params = {}

                    # Header parameters
                    st.subheader("Header Parameters")
                    new_params["header_width_proportion_max"] = st.slider(
                        "Header Width Proportion Max", 0.0, 1.0,
                        _coerce_float(st.session_state.params.get("header_width_proportion_max", 0.8), 0.8),
                        step=0.1,
                        key="slider_header_width_proportion_max",
                    )
                    new_params["header_left_x_ratio_min"] = st.slider(
                        "Header Left X Ratio Min", 0.0, 2.0,
                        _coerce_float(st.session_state.params.get("header_left_x_ratio_min", 1.2), 1.2),
                        step=0.1,
                        key="slider_header_left_x_ratio_min",
                    )
                    new_params["header_uppercase_proportion_min"] = st.slider(
                        "Header Uppercase Proportion Min", 0.0, 1.0,
                        _coerce_float(st.session_state.params.get("header_uppercase_proportion_min", 0.6), 0.6),
                        step=0.1,
                        key="slider_header_uppercase_proportion_min",
                    )
                    new_params["header_digits_proportion_min"] = st.slider(
                        "Header Digits Proportion Min", 0.0, 1.0,
                        _coerce_float(st.session_state.params.get("header_digits_proportion_min", 0.6), 0.6),
                        step=0.1,
                        key="slider_header_digits_proportion_min",
                    )

                    # Footer parameters
                    st.subheader("Footer Parameters")
                    new_params["footer_width_proportion_max"] = st.slider(
                        "Footer Width Proportion Max", 0.0, 1.0,
                        _coerce_float(st.session_state.params.get("footer_width_proportion_max", 0.5), 0.5),
                        step=0.1,
                        key="slider_footer_width_proportion_max",
                    )
                    new_params["footer_left_x_ratio_min"] = st.slider(
                        "Footer Left X Ratio Min", 0.0, 2.0,
                        _coerce_float(st.session_state.params.get("footer_left_x_ratio_min", 1.2), 1.2),
                        step=0.1,
                        key="slider_footer_left_x_ratio_min",
                    )

                    # Text block parameters
                    st.subheader("Text Block Parameters")
                    new_params["textblock_char_density_ratio_max"] = st.slider(
                        "Text Block Char Density Ratio Max", 0.0, 1.0,
                        _coerce_float(st.session_state.params.get("textblock_char_density_ratio_max", 0.65), 0.65),
                        step=0.05,
                        key="slider_textblock_char_density_ratio_max",
                    )

                    col_apply, col_cancel = st.columns(2)
                    with col_apply:
                        if st.button("Apply Changes"):
                            st.session_state.params = new_params.copy()
                            st.session_state.current_samples = None
                            st.session_state.show_params_editor = False
                            st.rerun()

                    with col_cancel:
                        if st.button("Cancel"):
                            st.session_state.show_params_editor = False
                            st.rerun()

                    if st.button("Reset to Defaults"):
                        st.session_state.params = st.session_state.default_params.copy()
                        st.session_state.current_samples = None
                        st.session_state.show_params_editor = False
                        st.rerun()

            # Show skipped at the very end
            if st.session_state.current_file_index >= len(filenames):
                st.header("Skipped Files:")
                for idx, skipped_file in enumerate(st.session_state.skipped_files, 1):
                    st.write(f"{idx}. {skipped_file}")
        else:
            st.session_state.current_file_index += 1
            st.session_state.current_samples = None
            st.session_state.current_seed += 1
            st.session_state.params = st.session_state.default_params.copy()
            st.rerun()

# ------------------------------------------------------------
# On-page Parameter Guide
# ------------------------------------------------------------

st.markdown("""
---
### 🧭 Parameter Guide

Below is a quick reference for what each slider controls in the text-block classification:

#### 🟥 Header Parameters
- **Header Width Proportion Max** – Maximum relative width of a line to still count as a header.  
  *Lower values → only narrow lines (short titles) qualify.*
- **Header Left X Ratio Min** – Minimum offset from the left margin; helps detect indented or centered headers.  
  *Increase if headers are shifted right.*
- **Header Uppercase Proportion Min** – Minimum share of uppercase letters in a line.  
  *Raise if headers are mostly ALL CAPS.*
- **Header Digits Proportion Min** – Minimum proportion of digits; useful for numeric or chapter headers.

#### 🟧 Footer Parameters
- **Footer Width Proportion Max** – Maximum relative width for footers.  
  *Lower = stricter (short page numbers only).*
- **Footer Left X Ratio Min** – Minimum left offset ratio for footer detection.  
  *Raise if page numbers are more right-aligned.*

#### 🟩 Text Block Parameters
- **Text Block Char Density Ratio Max** – Ratio of character density compared to average text.  
  *Lower values → fewer titles detected; higher → more generous title recognition.*

---

**Tip:**  
Tight (low) thresholds reduce false positives but may miss headers or titles.  
Loose (high) thresholds include more blocks but can misclassify regular text.

**Color Legend:**  
🟥 Header 🟧 Footer 🟩 Title 🟨 Margin ⬜ Text
""")