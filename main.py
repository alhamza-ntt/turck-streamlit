from azure.ai.projects import AIProjectClient
from azure.ai.agents.models import ListSortOrder
import streamlit as st
import pandas as pd
from azure.identity import ClientSecretCredential
import json
import re

tenant_id = st.secrets["AZURE_TENANT_ID"]
client_id = st.secrets["AZURE_CLIENT_ID"]
client_secret = st.secrets["AZURE_CLIENT_SECRET"]

credential = ClientSecretCredential(
    tenant_id=tenant_id,
    client_id=client_id,
    client_secret=client_secret
)
project = AIProjectClient(
    credential=credential,
    endpoint="https://alham-m7a7yvtj-eastus2.services.ai.azure.com/api/projects/alham-m7a7yvtj-eastus2-project"
)


agent = project.agents.get_agent("asst_2avunwDXjGN90k0VPYOLD9gN")
thread = project.agents.threads.create()

def ask_agent(question: str) -> str:
    project.agents.messages.create(
        thread_id=thread.id,
        role="user",
        content=question
    )

    run = project.agents.runs.create_and_process(
        thread_id=thread.id,
        agent_id=agent.id
    )

    if run.status == "failed":
        return f"Run failed: {run.last_error}"

    messages = list(project.agents.messages.list(thread_id=thread.id))
    for msg in messages:
        if msg.role == "assistant" and msg.text_messages:
            return msg.text_messages[-1].text.value

    return "No response found."

def parse_json_from_response(response_text):
    """Extract and parse JSON from LLM response"""
    try:
        # Try to find JSON block in the response
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Look for JSON-like structure without code blocks
            json_match = re.search(r'(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                return None
        
        # Parse the JSON
        return json.loads(json_str)
    except (json.JSONDecodeError, AttributeError):
        return None

def display_json_as_table(json_data):
    """Convert JSON to a nice table format"""
    if not json_data:
        return
    
    def flatten_json(data, parent_key='', sep='_'):
        """Flatten nested JSON for table display"""
        items = []
        if isinstance(data, dict):
            for k, v in data.items():
                new_key = f"{parent_key}{sep}{k}" if parent_key else k
                if isinstance(v, dict):
                    items.extend(flatten_json(v, new_key, sep=sep).items())
                else:
                    items.append((new_key, v))
        return dict(items)
    
    # Create a structured table
    table_data = []
    
    if isinstance(json_data, dict):
        for section_key, section_data in json_data.items():
            if isinstance(section_data, dict):
                # Add section header
                table_data.append({
                    "Category": section_key.replace('_', ' ').title(),
                    "Property": "---",
                    "Value": "---"
                })
                
                # Add section items
                for prop_key, prop_value in section_data.items():
                    table_data.append({
                        "Category": "",
                        "Property": prop_key.replace('_', ' ').title(),
                        "Value": str(prop_value) if prop_value else "N/A"
                    })
            else:
                table_data.append({
                    "Category": "General",
                    "Property": section_key.replace('_', ' ').title(),
                    "Value": str(section_data) if section_data else "N/A"
                })
    
    # Convert to DataFrame and display
    if table_data:
        df_results = pd.DataFrame(table_data)
        
        # Style the table
        st.markdown("### 📊 Compliance Analysis Results")
        
        # Apply custom styling
        styled_df = df_results.style.apply(
            lambda x: ['background-color: #f0f2f6; font-weight: bold' if '---' in str(x['Property']) 
                      else 'background-color: white' for i in x], axis=1
        )
        
        st.dataframe(
            styled_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Category": st.column_config.TextColumn("Category", width="medium"),
                "Property": st.column_config.TextColumn("Property", width="medium"),
                "Value": st.column_config.TextColumn("Value", width="large")
            }
        )

# Streamlit App
#st.set_page_config(page_title="TURCK Assistant", layout="wide")
st.title("TURCK Assistant")

# Read CSV
df = pd.read_csv("extracted_data.csv").fillna('')

# Create two columns
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Data Table")
    
    # Display DataFrame with selection
    event = st.dataframe(
        df,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row"
    )
    
    # Handle row selection
    selected_row_data = None
    if event.selection.rows:
        selected_row_index = event.selection.rows[0]
        selected_row_data = df.iloc[selected_row_index].to_dict()
        st.success(f"Row {selected_row_index + 1} selected!")

with col2:
    st.subheader("Selected Row")
    
    if selected_row_data:
        st.write("**Selected Row:**")
        st.json(selected_row_data)
        
        # Ask agent about the selected row
        if st.button("Send", type="primary"):
            with st.spinner("Searching the web..."):
                response = ask_agent(str(selected_row_data))
                
                # Parse JSON from response
                json_data = parse_json_from_response(response)
                
                # Display results in both columns
                with col1:
                    if json_data:
                        display_json_as_table(json_data)
                        
                        # Also show raw details if available
                        details_match = re.search(r'Details: (.+)', response)
                        if details_match:
                            st.markdown("### 📝 Additional Details")
                            st.info(details_match.group(1))
                    else:
                        st.markdown("### 📄 Raw Results")
                        st.write(response)
                
                # Keep JSON in col2 as well
                st.write("**Results:**")
                if json_data:
                    st.json(json_data)
                    # Show details text below JSON
                    details_match = re.search(r'Details: (.+)', response)
                    if details_match:
                        st.write("**Details:**")
                        st.write(details_match.group(1))
                else:
                    st.write(response)
                
                project.agents.threads.delete(thread.id)

    else:
        st.info("Click on a row in the table to select it")
