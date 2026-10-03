import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import uuid
from datetime import datetime

# Set page config
st.set_page_config(page_title="Secret Santa", layout="wide")

# Establish connection to Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# Fetch Data
@st.cache_data(ttl=5) # Cache refreshes every 5 seconds
def load_data():
    users_df = conn.read(worksheet="Users", usecols=[0, 1]).dropna(how="all")
    gifts_df = conn.read(worksheet="Gifts").dropna(how="all")
    
    # Ensure ID column exists as string
    if 'ID' in gifts_df.columns:
        gifts_df['ID'] = gifts_df['ID'].astype(str)
        
    return users_df, gifts_df

users_df, gifts_df = load_data()
user_list = users_df["Name"].dropna().tolist()

# Session State Initialization
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "current_user" not in st.session_state:
    st.session_state.current_user = None

# --- DIALOGS (POP-UPS) ---

@st.dialog("Confirm Identity")
def login_dialog(selected_name):
    st.warning(f"You are logging in as **{selected_name}**.")
    st.write("Only continue if this is really you!")
    col1, col2 = st.columns(2)
    if col1.button("Continue"):
        st.session_state.logged_in = True
        st.session_state.current_user = selected_name
        st.rerun()
    if col2.button("Go Back"):
        st.rerun()

@st.dialog("Delete Gift Idea?")
def delete_dialog(gift_id):
    st.warning("Are you sure you want to delete this idea? This cannot be undone.")
    if st.button("Confirm Delete", type="primary"):
        updated_df = gifts_df[gifts_df['ID'] != gift_id]
        conn.update(worksheet="Gifts", data=updated_df)
        st.cache_data.clear()
        st.rerun()

@st.dialog("Edit Gift Idea")
def edit_dialog(gift_row):
    st.write("Update the fields below:")
    with st.form(key=f"edit_form_{gift_row['ID']}"):
        new_name = st.text_input("Gift Name", value=gift_row['Gift Name'])
        new_url = st.text_input("URL/Link (Optional)", value=gift_row['URL'] if pd.notna(gift_row['URL']) else "")
        new_price = st.text_input("Estimated Price (Optional)", value=gift_row['Price'] if pd.notna(gift_row['Price']) else "")
        new_notes = st.text_area("Notes (Optional)", value=gift_row['Notes'] if pd.notna(gift_row['Notes']) else "")
        
        if st.form_submit_button("Save Changes"):
            # Update the specific row in the dataframe
            gifts_df.loc[gifts_df['ID'] == gift_row['ID'], ['Gift Name', 'URL', 'Price', 'Notes']] = [new_name, new_url, new_price, new_notes]
            conn.update(worksheet="Gifts", data=gifts_df)
            st.cache_data.clear()
            st.rerun()

# --- LOGIN SCREEN ---
if not st.session_state.logged_in:
    st.title("🎄 Secret Santa Hub")
    st.write("Welcome! Please select your name to continue.")
    selected_name = st.selectbox("Who are you?", ["Select your name..."] + user_list)
    
    if selected_name != "Select your name...":
        if st.button("Log In"):
            login_dialog(selected_name)

# --- MAIN APP SCREEN ---
else:
    current_user = st.session_state.current_user
    
    col1, col2 = st.columns([0.8, 0.2])
    col1.title(f"🎄 Welcome, {current_user}!")
    if col2.button("Log Out"):
        st.session_state.logged_in = False
        st.session_state.current_user = None
        st.rerun()

    st.divider()

    # Dropdown to select whose list to view
    view_target = st.selectbox("Whose gift list would you like to view/edit?", ["Select a person..."] + user_list)

    if view_target != "Select a person...":
        st.header(f"Gift Ideas for {view_target}")
        
        # VISIBILITY LOGIC
        if current_user == view_target:
            # Viewing own list: ONLY see self-added items
            visible_gifts = gifts_df[(gifts_df['Recipient'] == view_target) & (gifts_df['Added By'] == current_user)]
            st.info("You can only see the gift ideas you have added for yourself. Ideas added by others are hidden to keep the surprise!")
        else:
            # Viewing someone else's list: See everything
            visible_gifts = gifts_df[gifts_df['Recipient'] == view_target]

        # Display the gifts
        if visible_gifts.empty:
            st.write(f"No visible gift ideas for {view_target} yet.")
        else:
            for _, row in visible_gifts.iterrows():
                with st.container(border=True):
                    c1, c2, c3 = st.columns([0.6, 0.2, 0.2])
                    c1.markdown(f"**{row['Gift Name']}**")
                    if pd.notna(row['URL']) and str(row['URL']).strip() != "":
                        c1.markdown(f"[Link]({row['URL']})")
                    if pd.notna(row['Price']) and str(row['Price']).strip() != "":
                        c1.write(f"💵 {row['Price']}")
                    if pd.notna(row['Notes']) and str(row['Notes']).strip() != "":
                        c1.caption(f"Notes: {row['Notes']}")
                    
                    c1.caption(f"*Added by {row['Added By']}*")
                    
                    # Edit/Delete only allowed if the current user created the entry
                    if row['Added By'] == current_user:
                        if c2.button("Edit", key=f"edit_{row['ID']}"):
                            edit_dialog(row)
                        if c3.button("Delete", key=f"del_{row['ID']}"):
                            delete_dialog(row['ID'])

        st.divider()
        
        # Add New Gift Form
        st.subheader(f"Add a new idea for {view_target}")
        with st.form("add_gift_form", clear_on_submit=True):
            gift_name = st.text_input("Gift Name (Required)")
            gift_url = st.text_input("URL/Link (Optional)")
            gift_price = st.text_input("Estimated Price (Optional)")
            gift_notes = st.text_area("Notes (Optional)")
            
            submitted = st.form_submit_button("Add Idea")
            if submitted:
                if not gift_name.strip():
                    st.error("Please provide a Gift Name.")
                else:
                    new_row = pd.DataFrame([{
                        "ID": str(uuid.uuid4()),
                        "Recipient": view_target,
                        "Gift Name": gift_name,
                        "URL": gift_url,
                        "Price": gift_price,
                        "Notes": gift_notes,
                        "Added By": current_user,
                        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }])
                    
                    updated_df = pd.concat([gifts_df, new_row], ignore_index=True)
                    conn.update(worksheet="Gifts", data=updated_df)
                    st.cache_data.clear()
                    st.success("Gift added!")
                    st.rerun()
