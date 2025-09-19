import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta, timezone
from supabase import create_client
import hashlib
import time
import re
import secrets
import regex
import plotly.express as px

from functools import wraps

# Define custom colors
color_map = {
    "shahed": "#e65e5e",
    "mohammad": "#80ceff"
}

# Configure page
st.set_page_config(
    page_title="JUST US",
    page_icon="🕵️‍♀️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Supabase configuration
SUPABASE_URL = "https://qvkrvidkgzscjycbmdxu.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InF2a3J2aWRrZ3pzY2p5Y2JtZHh1Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTY4ODY5OTQsImV4cCI6MjA3MjQ2Mjk5NH0.HHAwIvBpxJeAJUpyI0KemV9Et1mezv5Tli-qB1n1PGI"
SUPABASE_KEY1 = "00a23610b042abb6fd627a325568cbc86c112ca183f42a0bcc4237dd34d5e1cf"

# IMPROVED CACHING STRATEGIES

@st.cache_resource(ttl=3600)  # Cache for 1 hour
def init_supabase():
    """Initialize Supabase client with longer caching"""
    return create_client(SUPABASE_URL, SUPABASE_KEY)

@st.cache_resource(ttl=3600)  # Cache for 1 hour
def init_supabase_storage():
    """Initialize separate Supabase client for storage operations"""
    return create_client(SUPABASE_URL, SUPABASE_KEY1)

# Custom caching decorator for database operations
def cache_db_operation(ttl=300, key_prefix="db"):
    """Custom caching decorator for database operations with better invalidation"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Create cache key from function name and arguments
            cache_key = f"{key_prefix}_{func.__name__}_{hash(str(args) + str(kwargs))}"
            
            # Check if we have cached data
            if cache_key in st.session_state:
                cached_data, timestamp = st.session_state[cache_key]
                if time.time() - timestamp < ttl:
                    return cached_data
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            st.session_state[cache_key] = (result, time.time())
            return result
        return wrapper
    return decorator

def generate_session_token():
    """Generate a secure session token"""
    return secrets.token_urlsafe(32)

def save_session_token(username, token):
    """Save session token to database with improved error handling"""
    try:
        supabase = init_supabase()
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        
        # Clean up existing sessions for this user
        supabase.table('user_sessions').delete().eq('username', username).execute()
        
        # Insert new session
        supabase.table('user_sessions').insert({
            'username': username,
            'session_token': token,
            'expires_at': expires_at
        }).execute()
        return True
    except Exception as e:
        st.error(f"Session error: Please try logging in again.")
        return False


def verify_session_token(token):
    """Verify session token and return user data with optimized caching"""
    try:
        supabase = init_supabase()
        session_response = supabase.table('user_sessions').select('*').eq('session_token', token).execute()

        if session_response.data and len(session_response.data) > 0:
            session = session_response.data[0]
            
            expires_at_str = session['expires_at']
            if expires_at_str.endswith('Z'):
                expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
            elif '+' in expires_at_str:
                expires_at = datetime.fromisoformat(expires_at_str)
            else:
                expires_at = datetime.fromisoformat(expires_at_str).replace(tzinfo=timezone.utc)
            
            current_time = datetime.now(timezone.utc)

            if expires_at > current_time:
                user_response = supabase.table('users').select('*').eq('username', session['username']).execute()
                if user_response.data and len(user_response.data) > 0:
                    return user_response.data[0]
            else:
                # Token expired, clean it up
                supabase.table('user_sessions').delete().eq('session_token', token).execute()
        return None
    except Exception:
        return None

@cache_db_operation(ttl=5, key_prefix="cleanup")  # Cache cleanup operations
def cleanup_expired_sessions():
    """Clean up expired session tokens with caching"""
    try:
        supabase = init_supabase()
        current_time = datetime.now(timezone.utc).isoformat()
        supabase.table('user_sessions').delete().lt('expires_at', current_time).execute()
        return True
    except Exception:
        return False

def check_session_from_url():
    """Check for valid session token in URL"""
    query_params = st.query_params
    if 'session_token' in query_params:
        token = query_params['session_token']
        user = verify_session_token(token)
        if user:
            st.session_state.authenticated = True
            st.session_state.user = user
            set_user_context(user['username'])
            return True
        else:
            st.query_params.clear()
            st.session_state.authenticated = False
            st.session_state.user = None
    return False

@cache_db_operation(ttl=60, key_prefix="user_context")
def set_user_context(username):
    """Set the current user context for RLS policies with caching"""
    try:
        supabase = init_supabase()
        supabase.rpc('set_current_user', {'user_name': username}).execute()
        return True
    except Exception:
        return False

@st.cache_data(ttl=120, show_spinner=False, max_entries=50)  # Longer cache for events
def load_events_from_db(username):
    """Load events from Supabase database with optimized caching"""
    try:
        supabase = init_supabase()
        set_user_context(username)
        
        response = supabase.table('our_events').select('*').eq('enabled', True).order('event_date', desc=True).execute()
        
        events = []
        for event in response.data:
            events.append({
                'id': event['id'],
                'title': event['event_title'],
                'date': datetime.strptime(event['event_date'], '%Y-%m-%d').date(),
                'preview': event['preview_text'],
                'description': event['description']
            })
        return events
    except Exception as e:
        st.error(f"Error loading events: {str(e)}")
        return []

def clear_events_cache():
    """Clear events cache when data is modified"""
    # Clear the specific cache
    load_events_from_db.clear()
    # Also clear any related session state cache
    keys_to_remove = [k for k in st.session_state.keys() if k.startswith("db_load_events")]
    for key in keys_to_remove:
        del st.session_state[key]

def save_event_to_db(title, event_date, preview, description, username):
    """Save new event to Supabase database with cache invalidation"""
    try:
        supabase = init_supabase()
        set_user_context(username)
        
        response = supabase.table('our_events').insert({
            'event_title': title,
            'event_date': str(event_date),
            'preview_text': preview,
            'description': description
        }).execute()
        
        # Clear cache after successful save
        clear_events_cache()
        return True
    except Exception as e:
        st.error(f"Error saving event: {str(e)}")
        return False

def update_event_in_db(event_id, title, event_date, preview, description, username):
    """Update existing event in Supabase database with cache invalidation"""
    try:
        supabase = init_supabase()
        set_user_context(username)
        
        response = supabase.table('our_events').update({
            'event_title': title,
            'event_date': str(event_date),
            'preview_text': preview,
            'description': description
        }).eq('id', event_id).execute()
        
        # Clear cache after successful update
        clear_events_cache()
        return True
    except Exception as e:
        st.error(f"Error updating event: {str(e)}")
        return False

def delete_event_from_db(event_id, username):
    """Delete event from database with cache invalidation"""
    try:
        supabase = init_supabase()
        set_user_context(username)

        # Update enabled field instead of deleting
        response = (
            supabase.table('our_events')
            .update({"enabled": False})
            .eq('id', event_id)
            .execute()
        )

        # Clear cache after successful update
        clear_events_cache()
        return True
    except Exception as e:
        st.error(f"Error disabling event: {str(e)}")
        return False

def hash_password(password):
    """Hash password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

@cache_db_operation(ttl=30, key_prefix="auth")  # Short cache for auth
def authenticate_user(username, password):
    """Authenticate user and create session token with caching"""
    try:
        supabase = init_supabase()
        
        hashed_password = hash_password(password)
        
        response = supabase.table('users').select('*').eq('username', username).eq('password_hash', hashed_password).execute()
        
        if response.data and len(response.data) > 0:
            user = response.data[0]
            set_user_context(username)
            
            session_token = generate_session_token()
            if save_session_token(username, session_token):
                st.query_params.update({'session_token': session_token})
                
                # Log the login (don't cache this)
                supabase.table('logins').insert({
                    'username': username,
                }).execute()
                
                return True, user
            else:
                return False, None
        return False, None
    except Exception:
        st.error("Authentication error. Please try again.")
        return False, None

def logout():
    """Logout and clear session with cache cleanup"""
    if st.session_state.get('authenticated') and st.session_state.get('user'):
        try:
            supabase = init_supabase()
            session_token = st.query_params.get('session_token')
            if session_token:
                supabase.table('user_sessions').delete().eq('session_token', session_token).execute()
        except Exception:
            pass
    
    # Clear all session state (including cached data)
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    
    # Clear all caches
    st.cache_data.clear()
    
    st.query_params.clear()
    st.rerun()

@st.cache_data(ttl=60, show_spinner=False)  # Cache regex compilation
def get_arabic_pattern():
    """Get compiled Arabic regex pattern"""
    return re.compile(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]')

def is_arabic_text(text):
    """Detect if text contains Arabic characters with cached pattern"""
    arabic_pattern = get_arabic_pattern()
    return bool(arabic_pattern.search(text))

# OPTIMIZED CSS WITH MINIMAL CHANGES FOR PERFORMANCE
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Amiri:wght@400;700&family=Cairo:wght@300;400;600;700&display=swap');
    
    .main-header {
        text-align: center;
        color: #2c3e50;
        font-size: 3rem;
        font-weight: 700;
        margin-bottom: 1rem;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
        font-family: 'Cairo', sans-serif;
    }
    
    .action-buttons {
        display: flex;
        justify-content: center;
        gap: 1rem;
        margin: 2rem 0;
        flex-wrap: wrap;
    }
    
    .login-container {
        max-width: 400px;
        margin: 2rem auto;
        padding: 3rem;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 20px;
        box-shadow: 0 20px 40px rgba(0,0,0,0.1);
        color: white;
        text-align: center;
    }
    
    .login-header {
        font-size: 2.5rem;
        font-weight: bold;
        margin-bottom: 2rem;
        font-family: 'Cairo', sans-serif;
    }
    
    .event-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 15px;
        padding: 1.5rem;
        margin-bottom: 1rem;
        box-shadow: 0 8px 25px rgba(0,0,0,0.15);
        color: white;
        transition: transform 0.2s ease;
        border: none;
        position: relative;
        overflow: hidden;
    }
    
    .event-card:hover {
        transform: translateY(-2px);
    }
    
    .card-title {
        font-size: 1.4rem;
        font-weight: bold;
        margin-bottom: 0.8rem;
        text-shadow: 1px 1px 2px rgba(0,0,0,0.3);
        font-family: 'Cairo', sans-serif;
        line-height: 1.3;
    }
    
    .card-date {
        font-size: 0.9rem;
        margin-bottom: 0.8rem;
        opacity: 0.9;
        font-family: 'Cairo', sans-serif;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    
    .card-preview {
        font-size: 0.95rem;
        opacity: 0.9;
        line-height: 1.4;
        font-family: 'Cairo', sans-serif;
        margin-bottom: 1rem;
    }
    
    .event-detail-container {
        max-width: 100%;
        margin: 0 auto;
        padding: 1rem;
    }
    
    .event-detail-card {
        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
        border-radius: 25px;
        padding: 2rem;
        margin: 1rem 0;
        box-shadow: 0 20px 40px rgba(0,0,0,0.1);
        color: #2c3e50;
        position: relative;
        overflow: hidden;
        width: 100%;
    }
    
    .event-detail-title {
        color: #2c3e50;
        font-size: 2.5rem;
        font-weight: bold;
        margin-bottom: 1.5rem;
        text-align: center;
        font-family: 'Cairo', sans-serif;
        position: relative;
        z-index: 1;
    }
    
    .event-detail-meta {
        text-align: center;
        color: #7f8c8d;
        font-size: 1.2rem;
        margin-bottom: 2rem;
        font-style: italic;
        font-family: 'Cairo', sans-serif;
        position: relative;
        z-index: 1;
    }
    
    .event-description {
        font-size: 1.2rem;
        line-height: 1.8;
        color: #2c3e50;
        font-family: 'Amiri', 'Cairo', serif;
        position: relative;
        z-index: 1;
        background: rgba(255, 255, 255, 0.7);
        padding: 2rem;
        border-radius: 15px;
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.3);
        width: 100%;
        box-sizing: border-box;
        text-align: justify;
    }
    
    .event-description.arabic {
        direction: rtl;
        text-align: right;
        font-family: 'Amiri', 'Cairo', serif;
    }
    
    .no-events {
        text-align: center;
        padding: 4rem 2rem;
        color: #7f8c8d;
        font-family: 'Cairo', sans-serif;
    }
    
    .no-events h2 {
        font-size: 2rem;
        margin-bottom: 1rem;
    }
    
    .no-events p {
        font-size: 1.1rem;
        opacity: 0.8;
    }
    
    .user-info {
        background: linear-gradient(135deg, #28a745 0%, #20c997 100%);
        color: white;
        padding: 1rem;
        border-radius: 10px;
        margin-bottom: 1rem;
        text-align: center;
        font-family: 'Cairo', sans-serif;
    }
    
    .event-form {
        background: #f8f9fa;
        padding: 2rem;
        border-radius: 15px;
        margin: 1rem 0;
        border: 1px solid #dee2e6;
    }
    
    .form-header {
        text-align: center;
        color: #2c3e50;
        font-size: 1.8rem;
        font-weight: bold;
        margin-bottom: 1.5rem;
        font-family: 'Cairo', sans-serif;
    }
    
    @media (max-width: 768px) {
        .main-header {
            font-size: 2rem;
            margin-bottom: 0.5rem;
        }
        
        .action-buttons {
            flex-direction: column;
            align-items: center;
            gap: 0.5rem;
        }
        
        .event-detail-container {
            padding: 0.5rem;
        }
        
        .event-detail-card {
            padding: 1.5rem;
            margin: 0.5rem 0;
            border-radius: 15px;
        }
        
        .event-detail-title {
            font-size: 1.8rem;
            line-height: 1.2;
        }
        
        .event-description {
            font-size: 1.1rem;
            line-height: 1.6;
            padding: 1.5rem;
        }
        
        .event-card {
            padding: 1.2rem;
        }
        
        .login-container {
            margin: 1rem 0.5rem;
            padding: 2rem 1.5rem;
            width: calc(100% - 1rem);
            box-sizing: border-box;
        }
    }
    
    @media (max-width: 480px) {
        .main-header {
            font-size: 1.8rem;
        }
        
        .event-detail-title {
            font-size: 1.5rem;
        }
        
        .event-description {
            font-size: 1rem;
            padding: 1rem;
        }
        
        .event-form {
            padding: 1rem;
            margin: 0.5rem 0;
        }
    }
</style>
""", unsafe_allow_html=True)

def initialize_session_state():
    """Initialize all session state variables with optimizations"""
    defaults = {
        'authenticated': False,
        'user': None,
        'selected_event': None,
        'show_add_form': False,
        'edit_event_id': None,
        'last_cache_clear': time.time()  # Track cache clearing
    }
    
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value

# Initialize session state first
initialize_session_state()

# Clean up expired sessions and check URL for session token
check_session_from_url()

def login_page():
    """Display login page"""
    st.markdown('<div class="login-container">', unsafe_allow_html=True)
    st.markdown('<h1 class="login-header">🔐 Login</h1>', unsafe_allow_html=True)
    
    with st.form("login_form", clear_on_submit=False):
        username = st.text_input("Username", placeholder="Enter your username")
        password = st.text_input("Password", type="password", placeholder="Enter your password")
        submitted = st.form_submit_button("Login", type="primary", use_container_width=True)
        
        if submitted:
            if username and password:
                with st.spinner("Authenticating..."):
                    success, user = authenticate_user(username, password)
                    if success:
                        st.session_state.authenticated = True
                        st.session_state.user = user
                        st.success("✅ Login successful!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("❌ Invalid username or password")
            else:
                st.error("Please enter both username and password")
    
    st.markdown('</div>', unsafe_allow_html=True)

def display_event_details(event):
    """Display detailed view of selected event with Arabic text support"""
    arabic_class = "arabic" if is_arabic_text(event["description"]) else ""
    
    st.markdown(f'''
    <div class="event-detail-container">
        <div class="event-detail-card">
            <div class="event-detail-title">{event["title"]}</div>
            <div class="event-detail-meta">
                📅 {event["date"].strftime("%B %d, %Y")}
            </div>
            <div class="event-description {arabic_class}">
                {event["description"]}
            </div>
        </div>
    </div>
    ''', unsafe_allow_html=True)

def add_event_form():
    """Display form to add new event"""
    st.markdown('<div class="event-form">', unsafe_allow_html=True)
    st.markdown('<div class="form-header">➕ Add New Event</div>', unsafe_allow_html=True)
    
    with st.form("add_event_form", clear_on_submit=True):
        new_title = st.text_input("Event Title", placeholder="Enter event title")
        new_date = st.date_input("Event Date", value=date.today())
        new_preview = st.text_input("Short Preview", placeholder="Brief description for timeline...")
        new_description = st.text_area("Detailed Description", height=200, 
                                    placeholder="Full description of the event...")
        
        col1, col2 = st.columns(2)
        with col1:
            submitted = st.form_submit_button("💾 Add Event", type="primary", use_container_width=True)
        with col2:
            if st.form_submit_button("❌ Cancel", use_container_width=True):
                st.session_state.show_add_form = False
                st.rerun()
        
        if submitted:
            if new_title and new_preview and new_description:
                with st.spinner("Adding event..."):
                    success = save_event_to_db(new_title, new_date, new_preview, 
                                            new_description, st.session_state.user['username'])
                    if success:
                        st.success("✅ Event added successfully!")
                        st.session_state.show_add_form = False
                        time.sleep(1)
                        st.rerun()
            else:
                st.error("Please fill in all required fields.")
    
    st.markdown('</div>', unsafe_allow_html=True)

def edit_event_form(event):
    """Display form to edit existing event"""
    st.markdown('<div class="event-form">', unsafe_allow_html=True)
    st.markdown('<div class="form-header">✏️ Edit Event</div>', unsafe_allow_html=True)
    
    with st.form("edit_event_form"):
        edit_title = st.text_input("Event Title", value=event['title'])
        edit_date = st.date_input("Event Date", value=event['date'])
        edit_preview = st.text_input("Short Preview", value=event['preview'])
        edit_description = st.text_area("Detailed Description", value=event['description'], height=200)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            save_clicked = st.form_submit_button("💾 Save Changes", type="primary", use_container_width=True)
        with col2:
            if st.form_submit_button("❌ Cancel", use_container_width=True):
                st.session_state.edit_event_id = None
                st.rerun()
        with col3:
            delete_clicked = st.form_submit_button("🗑️ Delete", use_container_width=True)
        
        if save_clicked:
            if edit_title and edit_preview and edit_description:
                with st.spinner("Updating event..."):
                    success = update_event_in_db(event['id'], edit_title, edit_date, edit_preview, 
                                            edit_description, st.session_state.user['username'])
                    if success:
                        st.success("✅ Event updated successfully!")
                        st.session_state.edit_event_id = None
                        time.sleep(1)
                        st.rerun()
            else:
                st.error("Please fill in all required fields.")
        
        if delete_clicked:
            if st.checkbox("Confirm deletion (this cannot be undone)", key="confirm_delete"):
                with st.spinner("Deleting event..."):
                    
                    success = delete_event_from_db(event['id'], st.session_state.user['username'])
                    if success:
                        st.success("✅ Event deleted successfully!")
                        st.session_state.edit_event_id = None
                        st.session_state.selected_event = None
                        time.sleep(1)
                        st.rerun()
            else:
                st.warning("Please confirm deletion to proceed.")
    
    st.markdown('</div>', unsafe_allow_html=True)

def create_event_cards(events):
    """Create event cards with inline edit buttons - optimized"""
    if not events:
        return
    
    for i, event in enumerate(events):
        # Pre-format date to avoid repeated formatting
        formatted_date = event['date'].strftime('%B %d, %Y')
        
        card_html = f'''
        <div class="event-card">
            <div class="card-title">{event['title']}</div>
            <div class="card-date">📅 {formatted_date}</div>
            <div class="card-preview">{event['preview']}</div>
        </div>
        '''
        
        st.markdown(card_html, unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button(f"👁️ View Details", key=f"view_{i}", 
                        type="secondary", use_container_width=True):
                st.session_state.selected_event = i
                st.session_state.edit_event_id = None
                st.rerun()
        
        with col2:
            if st.button(f"✏️ Edit", key=f"edit_{i}", 
                        type="secondary", use_container_width=True):
                st.session_state.selected_event = i
                st.session_state.edit_event_id = event['id']
                st.rerun()
        
        st.markdown("---")

@st.cache_data(ttl=60, show_spinner=False, max_entries=10)  # Cache file reading
def read_file_lines(bucket_name: str, file_path: str):
    """Read a file from Supabase storage line by line into a list with caching"""
    try:

        
        supabase = init_supabase_storage()
 
        response = supabase.storage.from_(bucket_name).download(file_path)


        if response:
            content = response.decode("utf-8")
            lines = content.splitlines()
            return lines
        else:
            print("⚠️ File not found or empty response.")
            return []
    except Exception as e:
        print("❌ Error reading file:", e)
        return []

@st.cache_data(ttl=60, show_spinner=False)  # Cache for 10 minutes, longer for chat processing
def load_chat_data():
    """Load and process chat data with heavy caching"""
    try:
        lines = read_file_lines("our_chats", "Us/chat_logs.txt")
    
        # Prepare lists
        dates, names, messages = [], [], []

        # WhatsApp message pattern: Date - Name: Message
        pattern = re.compile(r'^(\d{2}/\d{2}/\d{4}, \d{2}:\d{2}) - (.*?): (.*)')

        for line in lines:
            match = pattern.match(line)
            if match:
                date, name, message = match.groups()
                dates.append(date)
                names.append(name)
                messages.append(message)
            else:
                # If the line is a continuation of the previous message
                if messages:
                    messages[-1] += '\n' + line.strip()

        # Create DataFrame
        df = pd.DataFrame({
            "Date": dates,
            "Name": names,
            "Message": messages
        })
        df['Date'] = pd.to_datetime(df['Date'], format='%d/%m/%Y, %H:%M')

        df.loc[df['Name'] == '🕵‍♀️', 'Name'] = "Shahed"
        df.loc[df['Name'] == 'Mohammad Al Tarras', 'Name'] = "Mohammad"
        df['Message'] = df['Message'].str.replace(' <This message was edited>', ' ')
        df['Word Count'] = df['Message'].apply(lambda x: len(str(x).split()))

        df['View Once Images'] = df['Message'].apply(lambda x: 1 if x == "null" or x=='' else 0)

        df['Message Count'] = 1
        
        # Count emojis in each message - optimized with cached pattern
        emoji_pattern = get_emoji_pattern()
        df['Emoji Count'] = df['Message'].apply(lambda x: len(emoji_pattern.findall(str(x))))

        df.loc[df['Message'] == "null", 'Message Count'] = 0
        df.loc[df['Message'] == "null", 'Word Count'] = 0
        df["WeekStart"] = df["Date"].dt.to_period("W").apply(lambda r: r.start_time)
        
        return df
    except FileNotFoundError:
        st.error("Chat logs file not found. Please upload the file to enable analytics.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error loading chat data: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=3600, show_spinner=False)  # Cache emoji pattern compilation
def get_emoji_pattern():
    """Get compiled emoji regex pattern with caching"""
    return regex.compile(
        r'[\p{Extended_Pictographic}]',
        flags=regex.UNICODE
    )

@st.cache_data(ttl=300, show_spinner=False, max_entries=20)
def calculate_chat_time(df, max_gap_minutes=3):
    """
    Calculate total chatting time based on consecutive message gaps with caching.
    
    Parameters:
    df: DataFrame with 'Date' column containing timestamps
    max_gap_minutes: Maximum minutes between messages to consider as continuous chat
    
    Returns:
    Dictionary with chat sessions and total time
    """
    
    # Convert Date column to datetime if it's not already
    df = df.copy()
    df['Date'] = pd.to_datetime(df['Date'])
    
    # Sort by date to ensure chronological order
    df = df.sort_values('Date').reset_index(drop=True)
    
    # Calculate time differences between consecutive messages
    df['time_gap'] = df['Date'].diff()
    
    # Convert time gaps to minutes
    df['gap_minutes'] = df['time_gap'].dt.total_seconds() / 60
    
    # Identify chat sessions (where gap is <= max_gap_minutes)
    df['is_new_session'] = (df['gap_minutes'] > max_gap_minutes) | df['gap_minutes'].isna()
    df['session_id'] = df['is_new_session'].cumsum()
    
    # Calculate session details
    sessions = []
    total_chat_time = timedelta(0)
    
    for session_id in df['session_id'].unique():
        session_data = df[df['session_id'] == session_id]
        
        if len(session_data) > 1:  # Only count sessions with multiple messages
            session_start = session_data['Date'].min()
            session_end = session_data['Date'].max()
            session_duration = session_end - session_start
            
            sessions.append({
                'session': session_id,
                'start': session_start,
                'end': session_end,
                'duration': session_duration,
                'duration_minutes': session_duration.total_seconds() / 60,
                'message_count': len(session_data)
            })
            
            total_chat_time += session_duration
    
    return {
        'sessions': sessions,
        'total_chat_time': total_chat_time,
        'total_minutes': total_chat_time.total_seconds() / 60,
        'total_hours': total_chat_time.total_seconds() / 3600,
        'total_days': total_chat_time.total_seconds() / 86400,
        'dataframe_with_sessions': df
    }

@st.cache_data(ttl=300, show_spinner=False, max_entries=10)
def process_chat_data(df, start_date=None, end_date=None, aggregation_period='W'):
    """
    Process chat data for visualization with caching.
    
    Parameters:
    - df: DataFrame with chat data
    - start_date: Start date for filtering (optional)
    - end_date: End date for filtering (optional)
    - aggregation_period: Period for aggregation ('D' for daily, 'W' for weekly, 'M' for monthly)
    
    Returns:
    - processed_df: Aggregated DataFrame ready for visualization
    - summary_stats: Dictionary with summary statistics
    """
    
    if df.empty:
        return pd.DataFrame(), {}
    
    # Ensure Date is datetime
    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"])
    
    # Apply date filters
    if start_date:
        df = df[df["Date"] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df["Date"] <= pd.to_datetime(end_date)]
    
    # Create period column based on aggregation type
    if aggregation_period == 'W':
        df["Period"] = df["Date"].dt.to_period("W").apply(lambda r: r.start_time)
        period_name = "WeekStart"
    elif aggregation_period == 'D':
        df["Period"] = df["Date"].dt.date
        period_name = "Day"
    elif aggregation_period == 'M':
        df["Period"] = df["Date"].dt.to_period("M").apply(lambda r: r.start_time)
        period_name = "MonthStart"
    else:
        raise ValueError("aggregation_period must be 'D', 'W', or 'M'")
    print("aggregating cols....")
    # Define aggregation columns
    agg_columns = {
        "Message Count": "sum" if "Message Count" in df.columns else None,
        "Word Count": "sum" if "Word Count" in df.columns else None,
        "Emoji Count": "sum" if "Emoji Count" in df.columns else None,
        "View Once Images": "sum" if "View Once Images" in df.columns else None
    }
    
    # Remove None values from aggregation
    agg_columns = {k: v for k, v in agg_columns.items() if v is not None}
    
    # Group and aggregate data
    processed_df = df.groupby(["Period", "Name"]).agg(agg_columns).reset_index()
    processed_df.rename(columns={"Period": period_name}, inplace=True)
    print("summary stats....")
    # Calculate summary statistics
    summary_stats = {}
    for col in agg_columns.keys():
        if col in processed_df.columns:
            total = processed_df[col].sum()
            avg_per_period = processed_df.groupby("Name")[col].mean().to_dict()
            summary_stats[col] = {
                "total": total,
                "average_per_person": avg_per_period,
                "date_range": {
                    "start": df["Date"].min(),
                    "end": df["Date"].max()
                }
            }

    
    return processed_df, summary_stats

@st.cache_data(ttl=300, show_spinner=False, max_entries=10)
def process_laughs_data(df, min_laughs=1, start_date=None, end_date=None, aggregation_period="D"):
    """
    Process laugh data specifically for laugh analytics with aggregation.

    Parameters:
    - df: DataFrame with Message column
    - min_laughs: Minimum number of laugh emojis to count as a laugh
    - start_date: Start date for filtering
    - end_date: End date for filtering
    - aggregation_period: 'D' = Daily, 'W' = Weekly, 'M' = Monthly

    Returns:
    - pivot_laughs: Pivot table with aggregated laugh counts
    - laugh_stats: Dictionary with laugh statistics
    """

    if df.empty:
        return pd.DataFrame(), {}

    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"])

    # Apply date filters
    if start_date:
        df = df[df["Date"].dt.date >= start_date]
    if end_date:
        df = df[df["Date"].dt.date <= end_date]

    if df.empty:
        return pd.DataFrame(), {}

    # Count laugh emojis (1 if >= min_laughs in a message, else 0)
    df["Laughs"] = (df["Message"].str.count("😂") >= min_laughs).astype(int)

    # Set datetime index for resampling
    df = df.set_index("Date")

    # Aggregate laughs by period + person
    grouped = (
        df.groupby("Name")
        .resample(aggregation_period)["Laughs"]
        .sum()
        .reset_index()
    )

    # Pivot for wide format
    pivot_laughs = grouped.pivot_table(
        index="Date", columns="Name", values="Laughs", fill_value=0
    )

    # Calculate statistics
    laugh_stats = {}
    for name in pivot_laughs.columns:
        avg_laughs = pivot_laughs[name].mean()
        total_laughs = pivot_laughs[name].sum()
        laugh_stats[name.lower()] = {
            "average": avg_laughs,
            "total": total_laughs,
        }

    return pivot_laughs, laugh_stats

def create_laugh_metric_cards(laugh_stats):
    """Create metric cards specifically for laugh data - optimized"""
    if not laugh_stats:
        st.warning("No laugh data available")
        return
    
    people = list(laugh_stats.keys())
    cols = st.columns(len(people))
    
    for i, person in enumerate(people):
        stats = laugh_stats[person]
        person_color = color_map.get(person.lower(), "#c7cdd1")
        person_name = "SHAHED" if person.lower() == "shahed" else person.upper()
        
        with cols[i]:
            st.markdown(
                f"""
                <div style="background-color:#f0f2f6; padding:15px; border-radius:10px; text-align:center; border-left: 4px solid {person_color};">
                    <span style="font-size:16px; font-weight:bold;">Avg. Laughs {person_name}</span><br>
                    <span style="font-size:28px; font-weight:bold; color:{person_color};">{stats['average']:.1f}</span><br>
                    <span style="font-size:12px; color:#666;">Total: {stats['total']}</span>
                </div>
                """,
                unsafe_allow_html=True
            )

@st.cache_data(ttl=300, show_spinner=False)
def create_trend_visualizations(processed_df, period_column="WeekStart"):
    """Create trend line charts for all metrics with caching"""
    
    if processed_df.empty:
        st.warning("No data available for visualization")
        return
    
    # Get available metrics (exclude Name and period columns)
    metrics = [col for col in processed_df.columns if col not in ["Name", period_column]]
    
    # Create 2x2 layout
    cols = st.columns(2)
    
    for i, metric in enumerate(metrics):
        col = cols[i % 2]  # Alternate between left and right columns
        
        with col:
            fig = px.line(
                processed_df,
                x=period_column,
                y=metric,
                color="Name",
                markers=True,
                color_discrete_map={n: color_map.get(n.lower(), "#c7cdd1") for n in processed_df["Name"].unique()},
                title=f"{metric} Trend"
            )
            
            # Format the chart
            fig.update_layout(
                xaxis_title="Time Period" if i >= 2 else None,
                yaxis_title=metric,
                title_font=dict(size=16, family="Calibri", color="#2c2c2c"),
                font=dict(family="Calibri", size=12, color="#2c2c2c"),
                legend=dict(
                    title=None,
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1
                ),
                margin=dict(l=40, r=20, t=60, b=40),
                height=400
            )
            
            # Format Y-axis
            if "Images" in metric:
                fig.update_yaxes(tickformat=",.0f")
            else:
                fig.update_yaxes(tickformat=",~s")  # 1k, 2k formatting
            
            st.plotly_chart(fig, use_container_width=True)

def create_metric_cards(summary_stats):
    """Create and display metric cards horizontally"""

    if not summary_stats:
        st.warning("No data available")
        return

    # Build metrics list (you already have totals only)
    metrics = [
        ("Total Message Count", summary_stats["Message Count"]["total"]),
        ("Total Word Count", summary_stats["Word Count"]["total"]),
        ("Total Emoji Count", summary_stats["Emoji Count"]["total"]),
    ]

    # Create one row with N columns
    cols = st.columns(len(metrics), gap="small")

    # Card style
    card_style = """
        background-color:#f0f2f6; 
        padding:10px; 
        border-radius:8px; 
        text-align:center; 
        margin:2px;
        min-height: 100px;
        display: flex;
        flex-direction: column;
        justify-content: center;
        box-sizing: border-box;
        width: 100%;
    """

    # Fill columns left to right
    for col, (title, value) in zip(cols, metrics):
        col.markdown(
            f"""
            <div style="{card_style} border-left: 4px solid #333;">
                <div style="font-size:14px; font-weight:bold; color:#333;">{title}</div>
                <div style="font-size:24px; font-weight:bold; color:#333; margin-top:5px;">{value:,}</div>
            </div>
            """,
            unsafe_allow_html=True
        )


def analyze_chat_data(df, start_date=None, end_date=None, aggregation_period=None):
    """
    Complete analysis workflow combining data processing and visualization - optimized.
    
    Parameters:
    - df: Raw chat DataFrame
    - start_date: Start date for analysis
    - end_date: End date for analysis
    """
    
    # Process the data
    processed_df, summary_stats = process_chat_data(df, start_date, end_date,aggregation_period)
    
    if processed_df.empty:
        st.error("No data available for the selected date range")
        return
    
    # Create metric cards for different metrics
    st.subheader("📊 Key Metrics")

    create_metric_cards(summary_stats)   # 👈 call ONCE, not in a loop
    
    
    # Create trend visualizations
    st.subheader("📈 Trends Over Time")
    if aggregation_period=='W':
        aggregation_period1='WeekStart'
    elif aggregation_period=='D':
        aggregation_period1='Day'
    elif aggregation_period=='M':
        aggregation_period1='MonthStart'
    
    create_trend_visualizations(processed_df, aggregation_period1)
    
 

# Main application logic - optimized
def main():
    """Main application logic with proper authentication flow and performance optimizations"""
    
    # Performance monitoring
    start = time.time()
    
    # Check authentication first
    if not st.session_state.authenticated or not st.session_state.user:
        login_page()
        return
    
    # Only proceed if user is authenticated and user data exists
    if st.session_state.user is None:
        st.error("Session error. Please log in again.")
        logout()
        return

    # Lazy load chat data only when analytics tab is accessed
    chats = pd.DataFrame()  # Initialize empty
    
    # User info and logout (now safe because we know user exists)
    col1, col2 = st.columns([4, 1])
    
    with col1:
        username = st.session_state.user.get("username", "Unknown User")
        st.markdown(f'<div class="user-info">👋 Welcome, {username}!</div>', 
                unsafe_allow_html=True)
    with col2:
        if st.button("🚪 Logout", type="secondary", use_container_width=True):
            logout()
            return
    
    # Main tabs
    tab1, tab2 = st.tabs(["📅 Our Events", "📈 Analytics"])
    
    with tab1:
        # Header
    
        st.markdown('<h1 class="main-header">📅 Our Events. MOEEEEWWD</h1>', unsafe_allow_html=True)
        
        # Action buttons
        st.markdown('<div class="action-buttons">', unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 1, 1])
        
        with col2:  # Center the button
            if st.button("➕ Add New Event", type="primary", use_container_width=True):
                st.session_state.show_add_form = True
                st.session_state.selected_event = None
                st.session_state.edit_event_id = None
                st.rerun()
        
        st.markdown('</div>', unsafe_allow_html=True)
        
       # Number of events per page
        EVENTS_PER_PAGE = 10  

        # Load events with progress indicator
        with st.spinner("Loading events..."):
            events_data = load_events_from_db(st.session_state.user['username'])

        # Initialize pagination state
        if "event_page" not in st.session_state:
            st.session_state.event_page = 0

        # Calculate total pages
        total_events = len(events_data)
        total_pages = (total_events // EVENTS_PER_PAGE) + (1 if total_events % EVENTS_PER_PAGE else 0)

        # Apply pagination
        start_idx = st.session_state.event_page * EVENTS_PER_PAGE
        end_idx = start_idx + EVENTS_PER_PAGE
        page_events = events_data[start_idx:end_idx]

        # Show appropriate content
        if st.session_state.show_add_form:
            add_event_form()
        elif st.session_state.selected_event is not None and st.session_state.selected_event < len(events_data):
            # Back button
            if st.button("← Back to Events", type="primary"):
                st.session_state.selected_event = None
                st.session_state.edit_event_id = None
                st.rerun()
            
            event = events_data[st.session_state.selected_event]
            
            if st.session_state.edit_event_id == event['id']:
                edit_event_form(event)
            else:
                display_event_details(event)
        else:
            # Events grid view
            if events_data:
                st.markdown("---")
                st.subheader("📅 Your Events Timeline")
                                # Pagination controls
                col1, col2, col3 = st.columns([1, 2, 1])
                with col1:
                    if st.button("⬅️ Prev", disabled=st.session_state.event_page == 0):
                        st.session_state.event_page -= 1
                        st.rerun()
                with col2:
                    st.markdown(
                        f"<div style='text-align:center;'>Page {st.session_state.event_page+1} of {total_pages}</div>", 
                        unsafe_allow_html=True
                    )
                with col3:
                    if st.button("Next ➡️", disabled=st.session_state.event_page >= total_pages-1):
                        st.session_state.event_page += 1
                        st.rerun()
                
                # Render paginated events
                create_event_cards(page_events)

                # Pagination controls
                col11, col22, col33 = st.columns([1, 2, 1])
                with col11:
                    if st.button("⬅️ Prev ", disabled=st.session_state.event_page == 0):
                        st.session_state.event_page -= 1
                        st.rerun()
                with col22:
                    st.markdown(
                        f"<div style='text-align:center;'>Page {st.session_state.event_page+1} of {total_pages}</div>", 
                        unsafe_allow_html=True
                    )
                with col33:
                    if st.button("Next ➡️ ", disabled=st.session_state.event_page >= total_pages-1):
                        st.session_state.event_page += 1
                        st.rerun()
            else:
                st.markdown("""
                <div class="no-events">
                    <h2>🎯 Create Your First Event</h2>
                    <p>Click "Add New Event" button above to get started!</p>
                </div>
                """, unsafe_allow_html=True)
    
    with tab2:
        st.markdown('<h1 class="main-header">📈 Analytics</h1>', unsafe_allow_html=True)
        
        # Only load chat data when analytics tab is accessed
        if chats.empty:
            try:
                with st.spinner("Loading chat data for analytics..."):
                    chats = load_chat_data()
            except Exception as e:
                st.error(f"Error loading chat data: {e}")
                chats = pd.DataFrame()
        
        # Check if we have chat data
        if chats.empty:
            st.info("No chat data available for analytics. Please ensure 'chat_logs.txt' file is present.")
        else:
            # Sidebar-like filters (kept inline)
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                min_laughs = st.slider(
                    "Minimum 😂 count per message", 1, 5, 1
                )
            
            with col2:
                start_date = st.date_input(
                    "Start date", chats["Date"].min().date()
                )
            
            with col3:
                end_date = st.date_input(
                    "End date", chats["Date"].max().date()
                )
            
            with col4:
                aggregation_period = st.selectbox(
                    "Aggregation Period", 
                    options=['W', 'D', 'M'], 
                    format_func=lambda x: {'W': 'Weekly', 'D': 'Daily', 'M': 'Monthly'}[x],
                    index=0  # Default to Weekly
                )
            
            st.markdown("---")  # Add separator line
            
            st.markdown(
                f"""
                <h3>
                    Showing Data till 
                    <span style="color:#20a808;">{chats.Date.dt.date.max()}</span>
                </h3>
                """,
                unsafe_allow_html=True
            )
            
            # Section 1: Laughs Analytics
            with st.expander("😂 Laughs Analytics", expanded=True):
                with st.spinner("Processing laughs analytics..."):

                       # Laugh analysis (if Message column exists)
                    if "Message" in chats.columns:
                        st.subheader("😂 Laugh Analysis")
                        pivot_laughs, laugh_stats = process_laughs_data(chats, start_date=start_date, end_date=end_date, aggregation_period=aggregation_period)
                        
                        if not pivot_laughs.empty:
                            create_laugh_metric_cards(laugh_stats)
                                
                            # Line chart for laughs
                            st.markdown("**Daily Laugh Trends**")
                            chart_colors = [color_map.get(col.lower(), "#c7cdd1") for col in pivot_laughs.columns]
                            st.line_chart(pivot_laughs, color=chart_colors)
            
            # Section 2: Chat Trends
            with st.expander("💬 Chat Trends", expanded=True):
                with st.spinner("Processing chat trends..."):
                    analyze_chat_data(chats, start_date, end_date, aggregation_period)

            # # Performance monitoring (optional)
            # end_time = time.time()
            # if st.sidebar.checkbox("Show Performance", value=False):
            #     st.sidebar.metric("Page Load Time", f"{end_time - start:.2f}s")

# Run the main application
if __name__ == "__main__":
    main()