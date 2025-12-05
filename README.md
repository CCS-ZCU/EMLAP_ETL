# EMLAP: Early Modern Latin Alchemical Prints

---

## Authors

* Georgiana Hedesan and collaborators – data curation  
* Vojtěch Kaše and collaborators – processing of machine-readable data

## License

CC-BY-SA 4.0, see attached `LICENSE.md`.

---

## Description

<!-- ZENODO-DESC:BEGIN -->
EMLAP (Early Modern Latin Alchemical Prints) is a corpus of Early Modern Latin alchemical prints. This repository contains machine-readable versions of the corpus together with the code used to produce them.

EMLAP consists of:

1. Manually curated digital transcriptions of works forming the corpus, in the form of an OCR layer over public-domain PDFs of the works, available via a dedicated GUI: https://emlap.flu.cas.cz  
2. Raw, machine-readable text of individual works in the form of TXT files: https://ccs-lab.zcu.cz/emlap_corpus_public/emlap_txts/  
3. Token-level morphologically annotated data for each work, available in a TEI-XML compatible format: https://ccs-lab.zcu.cz/emlap_corpus_public/emlap_lemmatized_xmls/  
4. Token-level morphologically annotated data for the whole corpus in a single file: https://ccs-lab.zcu.cz/emlap_corpus_public/emlap_tokens_df.parquet (see below)  
5. A catalogue of metadata describing individual works (bibliographic, prosopographic, spatial, and thematic information): https://ccs-lab.zcu.cz/emlap_corpus_public/emlap_metadata.csv  
6. Scripts used for automatic cleaning, preprocessing, and preliminary explorations of the transcriptions (`./scripts/`).

1. Manually curated digital transcriptions of works forming the corpus, in the form of an OCR layer over public-domain PDFs of the works, available via a dedicated GUI: https://emlap.flu.cas.cz  
2. Raw, machine-readable text of individual works in the form of TXT files: https://ccs-lab.zcu.cz/emlap_corpus_public/emlap_txts/  
3. Token-level morphologically annotated data for each work, available in a TEI-XML compatible format: https://ccs-lab.zcu.cz/emlap_corpus_public/emlap_lemmatized_xmls/  
4. Token-level morphologically annotated data for the whole corpus in a single file: https://ccs-lab.zcu.cz/emlap_corpus_public/emlap_tokens_df.parquet (see below)  
5. A catalogue of metadata describing individual works (bibliographic, prosopographic, spatial, and thematic information): https://ccs-lab.zcu.cz/emlap_corpus_public/emlap_metadata.csv  
6. Scripts used for automatic cleaning, preprocessing, and preliminary explorations of the transcriptions (`./scripts/`).

For a more extended rationale behind the corpus and its design, see: https://emlap.flu.cas.cz/about.

In its current form, EMLAP covers 100 works and approximately 6.5 million tokens in total.

The ontology of descriptive metadata has been developed within the TOME project (http://tome.flu.cas.cz), making systematic use of GeoNames, CERL, and VIAF authority data as well as specialized alchemical–historical bibliographical catalogues.

The transcriptions were produced using the TRANSKRIBUS tool for automatic character recognition (http://transkribus.org) and then manually curated in two steps: (1) by domain-qualified research collaborators and (2) by a domain expert in the history of alchemy.

The corpus has been developed both for close reading and for distant reading or computational text analysis.

The computational processing pipeline is continuously maintained on GitHub (https://github.com/CCS-ZCU/EMLAP_ETL).

We provide several machine-readable versions of the corpus, with varying levels of complexity and structure suitable for different downstream tasks. These are collected in the directory `data/emlap_corpus_public/`, which is also served directly from our server: https://ccs-lab.zcu.cz/emlap_corpus_public/.
<!-- ZENODO-DESC:END -->

---

## Getting started

To explore the data in their richest form, open the Google Colab notebook
`scripts/emlap-tokens-explorations_colab-ready.ipynb`, for example via:

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/CCS-ZCU/EMLAP_ETL/blob/master/scripts/emlap-tokens-explorations_colab-ready.ipynb)

You do not need to download or install anything locally to start working with the data.

Alternatively, clone the repository and explore the notebooks in the `scripts/` directory.

```bash
git clone https://github.com/CCS-ZCU/EMLAP_ETL.git
cd EMLAP_ETL
# open notebooks in scripts/