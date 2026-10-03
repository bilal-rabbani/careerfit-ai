import streamlit as st

st.set_page_config(page_title="CareerFit AI", page_icon="🎯")

st.title("🎯 CareerFit AI")
st.caption("Match Your Skills. Improve Your CV. Apply with Confidence.")

if "clicks" not in st.session_state:
    st.session_state.clicks = 0

if st.button("Test button"):
    st.session_state.clicks += 1

st.write(f"Button clicked {st.session_state.clicks} times (session_state works).")
