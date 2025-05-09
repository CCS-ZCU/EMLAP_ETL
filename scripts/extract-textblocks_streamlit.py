#%%
import fitz
import json
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import random

import os
import pickle
import numpy as np
import ipywidgets as widgets
from IPython.display import display
import matplotlib.pyplot as plt
import streamlit as st

# Set interactive mode and backend for plots
#matplotlib.use('Qt5Agg')  # Or 'TkAgg', depending on your system
#plt.ion()  # Turn on interactive mode in matplotlib
#%%
#print(matplotlib.rcsetup.all_backends)
#%%
#matplotlib.use('TkAgg')  # Switch to TkAgg
#import matplotlib.pyplot as plt
#%%
#%%



#doc = fitz.open("../data/test_pdf+xml/Trevisanus1567_De_alchemia_MDZ_MBS.pdf")
#%%

#%%
def check_header(textblock, avg_width, avg_left_x, header_width_proportion_max=0.8, header_left_x_ratio_min=1.2, header_uppercase_proportion_min = 0.6, header_digits_proportion_min = 0.6):
    width_ratio = (textblock[2] - textblock[0])  / avg_width # thinner than average line
    left_x_ratio = textblock[0] / avg_left_x # more right than average line
    textblock_text = textblock[4].replace("\n", "")
    uppercase_ratio = sum(1 for char in textblock_text if char.isupper()) / len(textblock_text)
    digits_ratio =  sum(1 for char in textblock_text if char.isdigit()) / len(textblock_text)
    if sum([(width_ratio < header_width_proportion_max),(left_x_ratio > header_left_x_ratio_min),(uppercase_ratio > header_uppercase_proportion_min),(digits_ratio > header_digits_proportion_min)]) >= 2: # if first
        return True
    else:
        return False
def check_footer(textblock, avg_width, avg_left_x, avg_right_x, footer_width_proportion_max=0.5, footer_left_x_ratio_min=1.2):
    width_ratio = (textblock[2] - textblock[0])  / avg_width # thinner than average line
    left_x_ratio = textblock[0] / avg_left_x # more right than average line
    right_x_ratio = textblock[2] / avg_right_x # more right than average line
    textblock_text = textblock[4].replace("\n", "")
    digits_ratio =  sum(1 for char in textblock_text if char.isdigit()) / len(textblock_text)
    if sum([(width_ratio < footer_width_proportion_max), (left_x_ratio > 1.2),  (0.9 < right_x_ratio < 1.1),(digits_ratio > 0.6)]) >= 2: # if first
        return True
    else:
        return False
def check_title(textblock, avg_charn_density, textblock_char_density_ratio_max=0.75):
    textblock_char_density = len(textblock[4]) / (textblock[2] - textblock[0])
    if avg_charn_density != 0:
        textblock_char_density_ratio = textblock_char_density / avg_charn_density
    else:
        textblock_char_density_ratio = 0
    if textblock_char_density_ratio < textblock_char_density_ratio_max:
        return True
    else:
        return False
#%%
patch_color_dict = {"title" : "green",
                    "header" : "red",
                    "footer" : "orange",
                    "margin" : "yellow",
                     "text" : "white",
}

def convert_to_json_format(pages_textblocks):
    json_data = []
    for page_blocks in pages_textblocks:
        page_data = []
        for block in page_blocks:
            block_dict = {
                "coordinates": [block[0], block[1],block[2],block[3]],
                "text": block[4],
                "tag": block[5]
            }
            page_data.append(block_dict)
        json_data.append(page_data)
    return json_data


def plot_patch(textblock_annotated, patch_color_dict, ax):
   color = patch_color_dict[textblock_annotated[5]]
   patch = patches.Rectangle((textblock_annotated[0], textblock_annotated[1]),  # Bottom left corner
                              textblock_annotated[2] - textblock_annotated[0],  # Width
                              textblock_annotated[3] - textblock_annotated[1],  # Height
                              linewidth=0.3, edgecolor=color, facecolor='none')
   ax.add_patch(patch) # draw candidate textblocks in black


params = {"header_width_proportion_max" : 0.8,
          "header_left_x_ratio_min" : 1.2,
          "header_uppercase_proportion_min" : 0.6,
          "header_digits_proportion_min" : 0.6,
          "footer_width_proportion_max" : 0.5,
          "footer_left_x_ratio_min" : 1.2,
          "textblock_char_density_ratio_max" : 0.75}

def get_page_annots(textblocks, ax,
                    patch_color_dict=patch_color_dict,
                    params=params):
    if len(textblocks) < 3:
        return []
    else:
        textblocks_enumerated = [[el[0], el[1], el[2], el[3], el[4], n] for n, el in enumerate(textblocks)]
        textblocks = sorted(textblocks_enumerated, key=lambda x: x[1])
        textblocks = [[el[0], el[1], el[2], el[3], el[4], el[5], n] for n, el in enumerate(textblocks)]
        central_textblocks = textblocks[2:-1]
        avg_width = np.mean([rect[2] - rect[0] for rect in central_textblocks])
        avg_left_x = np.mean([rect[0] for rect in central_textblocks])
        avg_right_x = np.mean([rect[2] for rect in central_textblocks])
        try:
            avg_charn = sum([len(textblock[4]) for textblock in central_textblocks]) / len(central_textblocks)
            avg_charn_density = avg_charn / avg_width
        except:
            avg_charn_density = 0
        textblocks_annotated = []
        for textblock in textblocks:
            annot = "text"
            if textblock[6] in [0,1]:
                if check_header(textblock,
                                avg_width,
                                avg_left_x,
                                header_width_proportion_max=params["header_width_proportion_max"],
                                header_left_x_ratio_min=params["header_left_x_ratio_min"],
                                header_uppercase_proportion_min=params["header_uppercase_proportion_min"],
                                header_digits_proportion_min=params["header_digits_proportion_min"]):
                    annot = "header"
            if textblock[6] == len(textblocks) -1:
                if check_footer(textblock,
                                avg_width,
                                avg_left_x,
                                avg_right_x,
                                footer_width_proportion_max=params["footer_width_proportion_max"],
                                footer_left_x_ratio_min=params["footer_left_x_ratio_min"]):
                    annot = "footer"
            if annot != "header" and annot != "footer":
                if check_title(textblock,
                               avg_charn_density,
                               textblock_char_density_ratio_max=params["textblock_char_density_ratio_max"]):
                    annot = "title"
            textblocks_annotated.append([textblock[0], textblock[1], textblock[2], textblock[3], textblock[4], textblock[5], textblock[6], annot])
        textblocks_annotated_reordered = [[el[0], el[1], el[2], el[3], el[4], el[7]] for el in sorted(textblocks_annotated, key=lambda x: x[5])]
        # marginalia to full annotations
        margin_in_progress = False
        for textblock in textblocks_annotated_reordered:
            if "[M]" in textblock[4]:  # Check for the opening marginalia tag
                textblock[4] = textblock[4].replace("[M]", "")  # Remove the tag
                margin_in_progress = True  # Marginalia started

            if margin_in_progress:  # If within a marginalia block
                textblock[5] = "margin"  # Annotate as margin

            if "[/M]" in textblock[4]:  # Check for the closing marginalia tag
                textblock[4] = textblock[4].replace("[/M]", "")  # Remove the tag
                margin_in_progress = False  # Marginalia ended
            if ax != None:
                plot_patch(textblock, patch_color_dict, ax)
        return textblocks_annotated_reordered
#%%


def test_doc_annotations(doc, params, seed):
    random.seed(seed)
    pages_sample = random.sample([p for p in doc], min(8, len(doc)))
    pages_textblocks_annotated = []
    fig, axs = plt.subplots(2,4, figsize=(8, 5), dpi=150)
    for p, ax in zip(pages_sample, axs.ravel()):
        pix = p.get_pixmap()
        np_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n) # if you need an image matrix...
        textblocks = p.get_text_blocks()
        pages_textblocks_annotated.append(get_page_annots(textblocks,ax,
                    patch_color_dict, params=params))
        ax.axis('off')
        ax.imshow(np_array)
    return fig, pages_textblocks_annotated


def apply_and_save_annotations(filename, doc, params, dest_dir):
    pages_textblocks_annotated = []
    for p in doc:
        textblocks = p.get_text_blocks()
        annotations = get_page_annots(textblocks, ax=None, params=params)
        pages_textblocks_annotated.append(annotations)

    # Convert to JSON format and save
    json_data = convert_to_json_format(pages_textblocks_annotated)
    json_filename = filename.replace('.pdf', '.json')
    with open(os.path.join(dest_dir, json_filename), 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    with open(os.path.join(dest_dir, filename.replace('.pdf', '_params.json')), 'w', encoding='utf-8') as f:
        json.dump(params, f)


#%%
params = {"header_width_proportion_max" : 0.8,
          "header_left_x_ratio_min" : 1.2,
          "header_uppercase_proportion_min" : 0.6,
          "header_digits_proportion_min" : 0.6,
          "footer_width_proportion_max" : 0.5,
          "footer_left_x_ratio_min" : 1.2,
          "textblock_char_density_ratio_max" : 0.75}

#%%
source_dir = "/srv/data/tome/tome-corpus/emlap_raw_2025-04-08/"

#dest_dir = "/srv/data/tome/tome-corpus/emlap_annotated_textblocks/"
dest_dir = "/srv/data/tome/tome-corpus/emlap_annotated_tests/"


try:
    os.mkdir(dest_dir)
except:
    pass


# Initialize session state if needed

# Initialize states
if 'params' not in st.session_state:
    st.session_state.params = params.copy()
if 'show_params_editor' not in st.session_state:
    st.session_state.show_params_editor = False
if 'default_params' not in st.session_state:
    st.session_state.default_params = params.copy()
if 'current_file_index' not in st.session_state:
    st.session_state.current_file_index = 0
if 'current_samples' not in st.session_state:
    st.session_state.current_samples = None
if 'current_seed' not in st.session_state:
    st.session_state.current_seed = 0
if 'skipped_files' not in st.session_state:
    st.session_state.skipped_files = []

# Get list of directories once
dirs = list(os.listdir(source_dir))

if st.session_state.current_file_index < len(dirs):
    main_container = st.container()

    with main_container:
        dir = dirs[st.session_state.current_file_index]
        if "." not in dir:
            filename = [f for f in os.listdir(os.path.join(source_dir, dir)) if ".pdf" in f][0]
            filepath = os.path.join(source_dir, dir, filename)
            # Before processing anything
            # Check if already processed
            if os.path.exists(os.path.join(dest_dir, filename.replace('.pdf', '.json'))):
                st.write(f"Skipping {filename} - already processed")
                st.session_state.current_file_index += 1  # Move to next file
                st.rerun()  # Rerun the app to show next file
            doc = fitz.open(filepath)

            st.write(f"Processing file: {filename}")

            # Use session state seed
            if st.session_state.current_samples is None:
                # Use current parameters from session state
                fig, samples_annots = test_doc_annotations(doc, st.session_state.params, st.session_state.current_seed)
                st.session_state.current_samples = (fig, samples_annots)
            else:
                fig, samples_annots = st.session_state.current_samples

            st.pyplot(fig, use_container_width=True)

            col1, col2, col3, col4 = st.columns(4)

            # In the "Accept and Save" button section:
            with col1:
                if st.button("Accept and Save", key=f"accept_{st.session_state.current_file_index}"):
                    apply_and_save_annotations(filename, doc, st.session_state.params, dest_dir)
                    st.session_state.current_file_index += 1
                    st.session_state.current_samples = None
                    st.session_state.current_seed += 1
                    # Reset params to defaults for next file
                    st.session_state.params = st.session_state.default_params.copy()
                    st.rerun()

            with col2:
                if st.button("Another Sample", key=f"resample_{st.session_state.current_file_index}"):
                    st.session_state.current_seed += 1  # Increment seed for new sample
                    st.session_state.current_samples = None
                    st.rerun()
            # Add the "Add to Skipped" button
            with col3:
                if st.button("Add to Skipped"):
                    st.session_state.skipped_files.append(filename)
                    st.session_state.current_file_index += 1
                    st.session_state.current_samples = None
                    st.session_state.current_seed += 1
                    st.session_state.params = st.session_state.default_params.copy()
                    st.rerun()
            # In the "Revise Parameters" section:
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
                        st.session_state.params["header_width_proportion_max"],
                        step=0.1
                    )
                    new_params["header_left_x_ratio_min"] = st.slider(
                        "Header Left X Ratio Min", 0.0, 2.0,
                        st.session_state.params["header_left_x_ratio_min"],
                        step=0.1
                    )
                    new_params["header_uppercase_proportion_min"] = st.slider(
                        "Header Uppercase Proportion Min", 0.0, 1.0,
                        st.session_state.params["header_uppercase_proportion_min"],
                        step=0.1
                    )
                    new_params["header_digits_proportion_min"] = st.slider(
                        "Header Digits Proportion Min", 0.0, 1.0,
                        st.session_state.params["header_digits_proportion_min"],
                        step=0.1
                    )

                    # Footer parameters
                    st.subheader("Footer Parameters")
                    new_params["footer_width_proportion_max"] = st.slider(
                        "Footer Width Proportion Max", 0.0, 1.0,
                        st.session_state.params["footer_width_proportion_max"],
                        step=0.1
                    )
                    new_params["footer_left_x_ratio_min"] = st.slider(
                        "Footer Left X Ratio Min", 0.0, 2.0,
                        st.session_state.params["footer_left_x_ratio_min"],
                        step=0.1
                    )

                    # Text block parameters
                    st.subheader("Text Block Parameters")
                    new_params["textblock_char_density_ratio_max"] = st.slider(
                        "Text Block Char Density Ratio Max", 0.0, 1.0,
                        st.session_state.params["textblock_char_density_ratio_max"],
                        step=0.05
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
            # At the end, display skipped files
            if st.session_state.current_file_index >= len(dirs):
                st.header("Skipped Files:")
                for idx, skipped_file in enumerate(st.session_state.skipped_files, 1):
                    st.write(f"{idx}. {skipped_file}")
        else:
            st.session_state.current_file_index += 1  # Move to next file
            st.session_state.current_samples = None  # Reset samples
            st.session_state.current_seed += 1  # Increment seed
            st.session_state.params = st.session_state.default_params.copy()  # Reset params
            st.rerun()