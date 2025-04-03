import streamlit as st

st.title("Test Selection")

col1, col2, col3 = st.columns(3)

with col1:
    if st.button("Accept and Save"):
        st.success("Option 1")

with col2:
    if st.button("Another Sample"):
        st.success("Option 2")

with col3:
    if st.button("Revise Parameters"):
        st.success("Option 3")