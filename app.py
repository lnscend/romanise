"""Run: python -m streamlit run app.py"""
import hashlib
import json
from pathlib import Path
import pymupdf as fitz
import streamlit as st
from romanise_pdf import convert_pdf

st.set_page_config(page_title="Songbook Romaniser", page_icon="🎵")
st.title("Songbook Romaniser")
st.write("Upload a songbook, then download a PDF with red Roman-numeral chords.")
st.caption("For selectable-text chord PDFs. Printed keys are preferred; otherwise the key is inferred. Minor keys use their relative major.")
upload = st.file_uploader("Songbook PDF", type=["pdf"])
auto = st.checkbox("Detect unmarked key changes", value=True)
with st.expander("Optional corrections"):
    st.write("Use page and chord numbers from the audit download. A printed or manual key change takes priority over automatic guesses.")
    config_text = st.text_area("Overrides (JSON)", value='{}', help='Example: {"pages":{"4":{"initial_key":"D","changes":[{"chord":79,"key":"E"}]}}}')

if upload is not None:
    data = upload.getvalue()
    fingerprint = hashlib.sha256(data + config_text.encode() + str(auto).encode()).hexdigest()
    if st.session_state.get("fingerprint") != fingerprint:
        st.session_state.pop("converted", None)
    if st.button("Convert songbook", type="primary"):
        try:
            config = json.loads(config_text)
            if not isinstance(config, dict) or not isinstance(config.get("pages", {}), dict):
                raise ValueError('Overrides must be an object with an optional "pages" object.')
            with st.spinner("Converting…"):
                output, report = convert_pdf(data, config, auto)
            st.session_state["converted"] = (output, report)
            st.session_state["fingerprint"] = fingerprint
        except Exception as error:
            st.error("Could not convert: " + str(error))
    if "converted" in st.session_state:
        output, report = st.session_state["converted"]
        candidates = [(p['page'], r) for p in report['pages']
                      for r in p.get('possible_false_positives', [])]
        if candidates:
            with st.expander("Possible false positives — optional exclusions"):
                st.write("These mixed rows were converted by default. Tick a row only if you want to keep its original chords. Instructions remain as text either way.")
                with st.form('review_' + fingerprint):
                    excluded = {}
                    for pn, row in candidates:
                        checked = st.checkbox(
                            f"Keep original — page {pn}: {row['text']}",
                            value=row['excluded'],
                            key=f"exclude_{fingerprint}_{pn}_{row['id']}")
                        if checked:
                            excluded.setdefault(str(pn), []).append(row['id'])
                    regenerate = st.form_submit_button("Regenerate PDF with these exclusions")
                if regenerate:
                    try:
                        config = json.loads(config_text)
                        for pn in {str(pn) for pn, _ in candidates}:
                            page_config = config.setdefault('pages', {}).setdefault(pn, {})
                            review_ids = {r['id'] for p, r in candidates if str(p) == pn}
                            other = set(page_config.get('exclude_rows', [])) - review_ids
                            page_config['exclude_rows'] = sorted(other | set(excluded.get(pn, [])))
                        with st.spinner("Regenerating from the original PDF…"):
                            output, report = convert_pdf(data, config, auto)
                        st.session_state['converted'] = (output, report)
                        st.success("Updated. The downloads and preview below use your selections.")
                    except Exception as error:
                        st.error("Could not regenerate: " + str(error))
        stem = Path(upload.name).stem + "-roman"
        pages = report["pages"]
        with st.expander("Keys used"):
            for page in pages:
                st.write(f"Page {page['page']}: {page.get('initial_key', 'unknown')} — {page.get('key_source', 'not converted')}")
        st.success(f'{sum(p["status"] == "converted" for p in pages)} of {len(pages)} pages converted; {sum(p.get("chords", 0) for p in pages)} chords.')
        st.download_button("Download Roman-numeral PDF", output, stem + ".pdf", "application/pdf")
        st.download_button("Download chord audit / corrections", json.dumps(report, indent=2), stem + ".audit.json", "application/json")
        warnings = [f'Page {p["page"]}: {w}' for p in pages for w in p["warnings"]]
        if warnings:
            with st.expander("Pages and spacing to review", expanded=True):
                for warning in warnings: st.write(warning)
        st.caption("Unmarked key changes are estimates. Review them before using the chart.")
        page_number = st.number_input("Preview page", min_value=1, max_value=len(pages), value=1, step=1)
        with fitz.open(stream=output, filetype="pdf") as doc:
            preview = doc[page_number - 1].get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False).tobytes("png")
        st.image(preview, caption=f"Page {page_number}")
else:
    st.session_state.pop("converted", None)
