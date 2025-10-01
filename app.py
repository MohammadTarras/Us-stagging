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
import traceback
from functools import wraps
import base64
from PIL import Image
import io
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
    initial_sidebar_state="expanded"
)

# Supabase configuration
SUPABASE_URL = "https://qvkrvidkgzscjycbmdxu.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InF2a3J2aWRrZ3pzY2p5Y2JtZHh1Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTY4ODY5OTQsImV4cCI6MjA3MjQ2Mjk5NH0.HHAwIvBpxJeAJUpyI0KemV9Et1mezv5Tli-qB1n1PGI"
SUPABASE_KEY1 = "00a23610b042abb6fd627a325568cbc86c112ca183f42a0bcc4237dd34d5e1cf"

# Compile patterns once at module level (not in functions)
WHATSAPP_PATTERN = re.compile(r'^(\d{2}/\d{2}/\d{4}, \d{2}:\d{2}) - (.*?): (.*)')
EMOJI_PATTERN = regex.compile(r'[\p{Extended_Pictographic}]', flags=regex.UNICODE)
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



def encode_image_to_base64(uploaded_file):
    """
    Encode uploaded image to base64 string with compression
    
    Parameters:
    - uploaded_file: Streamlit UploadedFile object
    
    Returns:
    - base64 encoded string or None if error
    """
    try:
        # Read image
        image = Image.open(uploaded_file)
        
        # Resize if too large (max width 1200px)
        max_width = 1200
        if image.width > max_width:
            ratio = max_width / image.width
            new_size = (max_width, int(image.height * ratio))
            image = image.resize(new_size, Image.Resampling.LANCZOS)
        
        # Convert to RGB if necessary (for PNG with transparency)
        if image.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', image.size, (255, 255, 255))
            if image.mode == 'P':
                image = image.convert('RGBA')
            background.paste(image, mask=image.split()[-1] if image.mode in ('RGBA', 'LA') else None)
            image = background
        
        # Save to bytes with compression
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG', quality=85, optimize=True)
        buffer.seek(0)
        
        # Encode to base64
        img_base64 = base64.b64encode(buffer.read()).decode()
        return f"data:image/jpeg;base64,{img_base64}"
    
    except Exception as e:
        st.error(f"Error encoding image: {str(e)}")
        return None


def decode_base64_to_image(base64_string):
    """
    Decode base64 string to display image
    
    Parameters:
    - base64_string: base64 encoded image string
    
    Returns:
    - decoded image data or None
    """
    try:
        if base64_string and base64_string.startswith('data:image'):
            return base64_string
        return None
    except Exception as e:
        return None
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

@st.cache_data(ttl=120, show_spinner=False, max_entries=50)
def load_events_from_db(username):
    """Load events from Supabase database with images"""
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
                'description': event['description'],
                'image': event.get('image_data')  # Include image data
            })
        return events
    except Exception as e:
        st.error(f"Error loading events: {str(e)}")
        return []

# Enhanced clear_events_cache function
def clear_events_cache():
    """Clear events cache when data is modified and reset pagination state"""
    # Clear the specific cache
    load_events_from_db.clear()
    
    # Clear any related session state cache
    keys_to_remove = [k for k in st.session_state.keys() if k.startswith("db_load_events")]
    for key in keys_to_remove:
        del st.session_state[key]
    
    # Reset pagination state when events are modified
    if 'selected_event' in st.session_state:
        st.session_state.selected_event = None
    if 'edit_event_id' in st.session_state:
        st.session_state.edit_event_id = None
    if 'event_page' in st.session_state:
        st.session_state.event_page = 0

def save_event_to_db(title, event_date, preview, description, username, image_base64=None):
    """Save new event to Supabase database with optional image"""
    try:
        supabase = init_supabase()
        set_user_context(username)
        
        event_data = {
            'event_title': title,
            'event_date': str(event_date),
            'preview_text': preview,
            'description': description
        }
        
        # Add image if provided
        if image_base64:
            event_data['image_data'] = image_base64
        
        response = supabase.table('our_events').insert(event_data).execute()
        
        # Clear cache after successful save
        clear_events_cache()
        return True
    except Exception as e:
        st.error(f"Error saving event: {str(e)}")
        return False


def update_event_in_db(event_id, title, event_date, preview, description, username, image_base64=None):
    """Update existing event in Supabase database with optional image"""
    try:
        supabase = init_supabase()
        set_user_context(username)
        
        event_data = {
            'event_title': title,
            'event_date': str(event_date),
            'preview_text': preview,
            'description': description
        }
        
        # Add/update image if provided, or set to None if explicitly removed
        if image_base64 is not None:
            event_data['image_data'] = image_base64
        
        response = supabase.table('our_events').update(event_data).eq('id', event_id).execute()
        
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
        traceback.print_exc()
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
    
    /* Base styles - optimized for both desktop and mobile */
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        max-width: 100%;
    }
    
    /* Main header - responsive typography */
    .main-header {
        text-align: center;
        color: #2c3e50;
        font-size: clamp(2rem, 5vw, 3.5rem);
        font-weight: 700;
        margin-bottom: 1.5rem;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
        font-family: 'Cairo', sans-serif;
        line-height: 1.2;
    }
    
    /* Action buttons - improved responsive layout */
    .action-buttons {
        display: flex;
        justify-content: center;
        gap: 1rem;
        margin: 2rem 0;
        flex-wrap: wrap;
    }
    
    /* Login container - responsive design */
    .login-container {
        max-width: min(400px, 90vw);
        margin: 2rem auto;
        padding: clamp(2rem, 5vw, 3rem);
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 20px;
        box-shadow: 0 20px 40px rgba(0,0,0,0.15);
        color: white;
        text-align: center;
    }
    
    .login-header {
        font-size: clamp(2rem, 4vw, 2.5rem);
        font-weight: bold;
        margin-bottom: 2rem;
        font-family: 'Cairo', sans-serif;
    }
    
    /* Event cards - improved mobile layout */
    .event-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 15px;
        padding: clamp(1rem, 3vw, 1.5rem);
        margin-bottom: 1rem;
        box-shadow: 0 8px 25px rgba(0,0,0,0.15);
        color: white;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
        border: none;
        position: relative;
        overflow: hidden;
    }
    
    .event-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 12px 35px rgba(0,0,0,0.2);
    }
    
    .card-title {
        font-size: clamp(1.1rem, 2.5vw, 1.4rem);
        font-weight: bold;
        margin-bottom: 0.8rem;
        text-shadow: 1px 1px 2px rgba(0,0,0,0.3);
        font-family: 'Cairo', sans-serif;
        line-height: 1.3;
        word-wrap: break-word;
    }
    
    .card-date {
        font-size: clamp(0.8rem, 2vw, 0.9rem);
        margin-bottom: 0.8rem;
        opacity: 0.9;
        font-family: 'Cairo', sans-serif;
        display: flex;
        align-items: center;
        gap: 0.5rem;
        flex-wrap: wrap;
    }
    
    .card-preview {
        font-size: clamp(0.85rem, 2vw, 0.95rem);
        opacity: 0.9;
        line-height: 1.4;
        font-family: 'Cairo', sans-serif;
        margin-bottom: 1rem;
        word-wrap: break-word;
        overflow-wrap: break-word;
    }
    
    /* Event detail container - responsive */
    .event-detail-container {
        max-width: 100%;
        margin: 0 auto;
        padding: clamp(0.5rem, 2vw, 1rem);
    }
    
    .event-detail-card {
        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
        border-radius: clamp(15px, 3vw, 25px);
        padding: clamp(1rem, 4vw, 2rem);
        margin: 1rem 0;
        box-shadow: 0 20px 40px rgba(0,0,0,0.1);
        color: #2c3e50;
        position: relative;
        overflow: hidden;
        width: 100%;
        box-sizing: border-box;
    }
    
    .event-detail-title {
        color: #2c3e50;
        font-size: clamp(1.5rem, 4vw, 2.5rem);
        font-weight: bold;
        margin-bottom: 1.5rem;
        text-align: center;
        font-family: 'Cairo', sans-serif;
        position: relative;
        z-index: 1;
        line-height: 1.2;
        word-wrap: break-word;
    }
    
    .event-detail-meta {
        text-align: center;
        color: #7f8c8d;
        font-size: clamp(1rem, 2.5vw, 1.2rem);
        margin-bottom: 2rem;
        font-style: italic;
        font-family: 'Cairo', sans-serif;
        position: relative;
        z-index: 1;
    }
    
    .event-description {
        font-size: clamp(1rem, 2.2vw, 1.2rem);
        line-height: 1.8;
        color: #2c3e50;
        font-family: 'Amiri', 'Cairo', serif;
        position: relative;
        z-index: 1;
        background: rgba(255, 255, 255, 0.7);
        padding: clamp(1rem, 3vw, 2rem);
        border-radius: 15px;
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.3);
        width: 100%;
        box-sizing: border-box;
        text-align: justify;
        word-wrap: break-word;
        overflow-wrap: break-word;
    }
    
    .event-description.arabic {
        direction: rtl;
        text-align: right;
        font-family: 'Amiri', 'Cairo', serif;
    }
    
    /* No events message */
    .no-events {
        text-align: center;
        padding: clamp(2rem, 6vw, 4rem) 2rem;
        color: #7f8c8d;
        font-family: 'Cairo', sans-serif;
    }
    
    .no-events h2 {
        font-size: clamp(1.5rem, 3vw, 2rem);
        margin-bottom: 1rem;
    }
    
    .no-events p {
        font-size: clamp(1rem, 2vw, 1.1rem);
        opacity: 0.8;
    }
    
    /* User info - responsive */
    .user-info {
        background: linear-gradient(135deg, #28a745 0%, #20c997 100%);
        color: white;
        padding: clamp(0.8rem, 2vw, 1rem);
        border-radius: 10px;
        margin-bottom: 1rem;
        text-align: center;
        font-family: 'Cairo', sans-serif;
        font-size: clamp(0.9rem, 2vw, 1rem);
    }
    
    /* Event form - responsive */
    .event-form {
        background: #f8f9fa;
        padding: clamp(1rem, 3vw, 2rem);
        border-radius: 15px;
        margin: 1rem 0;
        border: 1px solid #dee2e6;
        box-sizing: border-box;
        width: 100%;
    }
    
    .form-header {
        text-align: center;
        color: #2c3e50;
        font-size: clamp(1.3rem, 3vw, 1.8rem);
        font-weight: bold;
        margin-bottom: 1.5rem;
        font-family: 'Cairo', sans-serif;
    }
    
    /* Navigation sidebar styles */
    .css-1d391kg {
        background-color: #f0f2f6;
    }
    
    .css-1lcbmhc {
        color: #2c3e50;
        font-weight: 600;
    }
    
    /* Page indicator */
    .page-indicator {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 0.8rem;
        border-radius: 10px;
        text-align: center;
        font-weight: bold;
        margin-bottom: 1rem;
    }
    
    /* Additional responsive improvements */
    .stButton button {
        width: 100%;
        padding: 0.6rem 1rem;
        border-radius: 8px;
        font-size: clamp(0.85rem, 2vw, 0.95rem);
        font-weight: 500;
        transition: all 0.2s ease;
    }
    
    .stButton button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }
    
    /* Sidebar radio buttons */
    .stRadio > div {
        background-color: white;
        border-radius: 10px;
        padding: 1rem;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    }
    
    /* Mobile-first breakpoints */
    @media (max-width: 480px) {
        .main .block-container {
            padding: 1rem 0.5rem;
        }
        
        .action-buttons {
            flex-direction: column;
            align-items: stretch;
            gap: 0.8rem;
            margin: 1.5rem 0;
        }
        
        .event-card {
            margin-bottom: 1.5rem;
        }
        
        .login-container {
            margin: 1rem 0.5rem;
            border-radius: 15px;
        }
        
        .stColumn {
            margin-bottom: 1rem;
        }
        
        .event-form {
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
        'last_cache_clear': time.time(),  # Track cache clearing
        'current_page': 'Events'  # Track current page
    }
    
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value

# Initialize session state first
initialize_session_state()

# Clean up expired sessions and check URL for session token
check_session_from_url()
def login_page():
    """Display login page with animated counter on successful login"""
    from datetime import date
    import time
    
    # Hardcoded start date
    start_date = date(2025, 6, 7) 
    today = date.today()
    days_known = (today - start_date).days
    
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
                        st.session_state.counter_animated = False  # Set to False so animation plays
                        st.success("✅ Login successful!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("❌ Invalid username or password")
            else:
                st.error("Please enter both username and password")
    
    st.markdown('</div>', unsafe_allow_html=True)
def display_event_details(event):
    """Display detailed view of selected event with image and Arabic text support"""
    arabic_class = "arabic" if is_arabic_text(event["description"]) else ""
    
    st.markdown(f'''
    <div class="event-detail-container">
        <div class="event-detail-card">
            <div class="event-detail-title">{event["title"]}</div>
            <div class="event-detail-meta">
                📅 {event["date"].strftime("%B %d, %Y")}
            </div>
    ''', unsafe_allow_html=True)



    # Display image if available
    if event.get('image'):
        st.markdown(
            f"""
            <style>
                .event-image-container {{
                    margin: 2rem 0;
                    text-align: center;
                }}
                .event-image {{
                    width: 400px;
                    max-width: 100%;
                    height: auto;
                    display: block;
                    margin: 0 auto;
                    border: 3px solid #e83e8c;
                    border-radius: 12px;
                    box-shadow: 0 4px 8px rgba(0,0,0,0.15);
                    transition: all 0.3s ease;
                    cursor: pointer;
                }}
                .event-image:hover {{
                    transform: scale(1.05);
                    box-shadow: 0 8px 16px rgba(232, 62, 140, 0.3);
                    border-color: #ff6b9d;
                }}
                .event-image-caption {{
                    font-size: 0.9rem;
                    color: #666;
                    margin-top: 0.5rem;
                }}
            </style>
            <div class="event-image-container">
                <img src="{event['image']}" 
                    alt="{event['title']}" 
                    class="event-image"
                    onclick="window.open('{event['image']}', '_blank')" />
                <div class="event-image-caption">{event['title']}</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    st.markdown(f'''
            <div class="event-description {arabic_class}">
                {event["description"]}
            </div>
        </div>
    </div>
    ''', unsafe_allow_html=True)



def add_event_form():
    """Display form to add new event with image upload"""
    st.markdown('<div class="event-form">', unsafe_allow_html=True)
    st.markdown('<div class="form-header">➕ Add New Event</div>', unsafe_allow_html=True)
    
    with st.form("add_event_form", clear_on_submit=True):
        new_title = st.text_input("Event Title", placeholder="Enter event title")
        new_date = st.date_input("Event Date", value=date.today())
        new_preview = st.text_input("Short Preview", placeholder="Brief description for timeline...")
        new_description = st.text_area("Detailed Description", height=200, 
                                    placeholder="Full description of the event...")
        
        # Image upload
        uploaded_image = st.file_uploader(
            "Upload Image (Optional)",
            type=['png', 'jpg', 'jpeg'],
            help="Upload an image for this event. It will be compressed automatically."
        )
        
        # Preview uploaded image
        if uploaded_image:
            st.image(uploaded_image, caption="Image Preview", use_container_width=True)
        
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
                    # Encode image if uploaded
                    image_base64 = None
                    if uploaded_image:
                        image_base64 = encode_image_to_base64(uploaded_image)
                        if image_base64 is None:
                            st.error("Failed to process image. Event will be saved without image.")
                    
                    success = save_event_to_db(
                        new_title, new_date, new_preview, 
                        new_description, st.session_state.user['username'],
                        image_base64
                    )
                    if success:
                        st.success("✅ Event added successfully!")
                        st.session_state.show_add_form = False
                        time.sleep(1)
                        st.rerun()
            else:
                st.error("Please fill in all required fields.")
    
    st.markdown('</div>', unsafe_allow_html=True)


def edit_event_form(event):
    """Display form to edit existing event with image support"""
    st.markdown('<div class="event-form">', unsafe_allow_html=True)
    st.markdown('<div class="form-header">✏️ Edit Event</div>', unsafe_allow_html=True)
    
    with st.form("edit_event_form"):
        edit_title = st.text_input("Event Title", value=event['title'])
        edit_date = st.date_input("Event Date", value=event['date'])
        edit_preview = st.text_input("Short Preview", value=event['preview'])
        edit_description = st.text_area("Detailed Description", value=event['description'], height=200)
        
        # Show existing image if available
        if event.get('image'):
            st.markdown("**Current Image:**")
            st.image(event['image'], width=300)
            remove_image = st.checkbox("Remove current image")
        else:
            remove_image = False
            st.info("No image currently attached to this event")
        
        # Image upload
        uploaded_image = st.file_uploader(
            "Upload New Image (Optional)",
            type=['png', 'jpg', 'jpeg'],
            help="Upload a new image to replace the existing one"
        )
        
        # Preview new uploaded image
        if uploaded_image:
            st.image(uploaded_image, caption="New Image Preview", use_container_width=True)
        
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
                    # Determine image data to save
                    image_base64 = None
                    
                    if uploaded_image:
                        # New image uploaded
                        image_base64 = encode_image_to_base64(uploaded_image)
                        if image_base64 is None:
                            st.error("Failed to process new image. Keeping existing image.")
                            image_base64 = event.get('image')
                    elif remove_image:
                        # Remove existing image (set to empty string)
                        image_base64 = ""
                    else:
                        # Keep existing image
                        image_base64 = event.get('image')
                    
                    success = update_event_in_db(
                        event['id'], edit_title, edit_date, edit_preview, 
                        edit_description, st.session_state.user['username'],
                        image_base64
                    )
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

def create_event_cards(events, start_idx=0, events_data=None):
    """Create event cards with small thumbnail images on the left"""
    if not events:
        return
    
    if events_data is None:
        events_data = events
    
    for i, event in enumerate(events):
        global_index = start_idx + i
        
        if not all(key in event for key in ['title', 'date', 'preview', 'id']):
            st.error(f"Event data incomplete for event at index {global_index}")
            continue
        
        try:
            formatted_date = event['date'].strftime('%B %d, %Y')
        except (AttributeError, ValueError):
            formatted_date = str(event['date'])
        
        # Build card HTML with optional image
        if event.get('image'):
            card_html = f'''
            <div class="event-card" style="display: flex; align-items: center; gap: 1rem;">
                <div style="flex-shrink: 0; width: 120px; height: 120px; overflow: hidden; border-radius: 8px;">
                    <img src="{event['image']}" style="width: 100%; height: 100%; object-fit: cover;" />
                </div>
                <div style="flex: 1; min-width: 0;">
                    <div class="card-title">{event['title']}</div>
                    <div class="card-date">📅 {formatted_date}</div>
                    <div class="card-preview">{event['preview']}</div>
                </div>
            </div>
            '''
        else:
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
            view_key = f"view_{event['id']}_{global_index}"
            if st.button(f"👁️ View Details", key=view_key, 
                        type="secondary", use_container_width=True):
                st.session_state.selected_event = global_index
                st.session_state.edit_event_id = None
                st.rerun()
        
        with col2:
            edit_key = f"edit_{event['id']}_{global_index}"
            if st.button(f"✏️ Edit", key=edit_key, 
                        type="secondary", use_container_width=True):
                st.session_state.selected_event = global_index
                st.session_state.edit_event_id = event['id']
                st.rerun()
        
        st.markdown("---")
# ============================================================================
# FILE READING (Increase cache time since chat logs don't change frequently)
# ============================================================================
@st.cache_data(ttl=3600, show_spinner=False, max_entries=5)  # 1 hour cache
def read_file_lines(bucket_name: str, file_path: str):
    """Read a file from Supabase storage with extended caching"""
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

# ============================================================================
# CORE DATA LOADING (Most critical for performance)
# ============================================================================
@st.cache_data(ttl=3600, show_spinner=False)  # 1 hour cache
def load_chat_data():
    """Load and process chat data with comprehensive optimization"""
    try:
        lines = read_file_lines("our_chats", "Us/chat_logs.txt")
        
        if not lines:
            return pd.DataFrame()
    
        dates, names, messages = [], [], []

        for line in lines:
            match = WHATSAPP_PATTERN.match( line)
          
            if match:
                date, name, message = match.groups()
                dates.append(date)
                names.append(name)
                messages.append(message)
            else:
                if messages:
                    messages[-1] += '\n' + line.strip()

        # Create DataFrame with datetime conversion in one step
        df = pd.DataFrame({
            "Date": pd.to_datetime(dates, format='%d/%m/%Y, %H:%M'),
            "Name": names,
            "Message": messages
        })

        # Vectorized name replacements
        df['Name'] = df['Name'].replace({
            '🕵‍♀️': 'Shahed', 
            'Mohammad Al Tarras': 'Mohammad'
        })
        
        # Clean messages (use regex=False for literal string replacement - faster)
        df['Message'] = df['Message'].str.replace(' <This message was edited>', '', regex=False)
        
        # Vectorized boolean operations
        is_null = df['Message'].isin(['null', ''])
        df['View Once Images'] = is_null.astype(int)
        df['Message Count'] = (~df['Message'].eq('null')).astype(int)
        
        # Optimized word count - only for non-null messages
        df['Word Count'] = 0
        valid_mask = ~is_null
        df.loc[valid_mask, 'Word Count'] = df.loc[valid_mask, 'Message'].str.split().str.len()
        

      
        df['Emoji Count'] = df['Message'].apply(lambda x: len(EMOJI_PATTERN.findall(str(x))))
        
        # Pre-calculate all period columns at once
        df["WeekStart"] = df["Date"].dt.to_period("W").apply(lambda r: r.start_time)
        df["DayStart"] = df["Date"].dt.date
        df["MonthStart"] = df["Date"].dt.to_period("M").apply(lambda r: r.start_time)
        return df
        
    except FileNotFoundError:
        st.error("Chat logs file not found. Please upload the file to enable analytics.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error loading chat data: {e}")
        print("❌ Error loading chat data:", e)
        traceback.print_exc()
        return pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False)  # Cache emoji pattern compilation
def get_emoji_pattern():
    """Get compiled emoji regex pattern with caching"""
    return regex.compile(
        r'[\p{Extended_Pictographic}]',
        flags=regex.UNICODE
    )

# ============================================================================
# SESSION CALCULATION (Fully vectorized)
# ============================================================================
@st.cache_data(ttl=600, show_spinner=False, max_entries=20)
def calculate_chat_time(df, max_gap_minutes=3):
    """Optimized chat time calculation using pure vectorized operations"""
    
    if df.empty or len(df) < 2:
        return {
            'sessions': [],
            'total_chat_time': timedelta(0),
            'total_minutes': 0,
            'total_hours': 0,
            'total_days': 0,
            'dataframe_with_sessions': df
        }
    
    # Sort once
    df_sorted = df.sort_values('Date', ignore_index=True)
    
    # Vectorized gap calculation
    time_gaps = df_sorted['Date'].diff()
    gap_minutes = time_gaps.dt.total_seconds() / 60
    
    # Identify sessions
    is_new_session = (gap_minutes > max_gap_minutes) | gap_minutes.isna()
    session_ids = is_new_session.cumsum()
    
    # Add session IDs
    df_sorted = df_sorted.copy()
    df_sorted['session_id'] = session_ids
    
    # Group by session for statistics (vectorized)
    session_stats = df_sorted.groupby('session_id')['Date'].agg(['min', 'max', 'count'])
    session_stats = session_stats[session_stats['count'] > 1]
    
    # Calculate durations
    session_stats['duration'] = session_stats['max'] - session_stats['min']
    session_stats['duration_minutes'] = session_stats['duration'].dt.total_seconds() / 60
    
    # Build sessions list
    sessions = [
        {
            'session': idx,
            'start': row['min'],
            'end': row['max'],
            'duration': row['duration'],
            'duration_minutes': row['duration_minutes'],
            'message_count': row['count']
        }
        for idx, row in session_stats.iterrows()
    ]
    
    total_chat_time = session_stats['duration'].sum()
    
    return {
        'sessions': sessions,
        'total_chat_time': total_chat_time,
        'total_minutes': total_chat_time.total_seconds() / 60,
        'total_hours': total_chat_time.total_seconds() / 3600,
        'total_days': total_chat_time.total_seconds() / 86400,
        'dataframe_with_sessions': df_sorted
    }

# ============================================================================
# DATA PROCESSING (Use pre-calculated periods)
# ============================================================================
@st.cache_data(ttl=600, show_spinner=False, max_entries=30)
def process_chat_data(df, start_date=None, end_date=None, aggregation_period='W'):
    """Optimized processing using pre-calculated period columns"""
    
    if df.empty:
        return pd.DataFrame(), {}
    
    # Filter by date range (avoid unnecessary copy)
    mask = pd.Series(True, index=df.index)
    if start_date:
        mask &= df["Date"] >= pd.to_datetime(start_date)
    if end_date:
        mask &= df["Date"] <= pd.to_datetime(end_date)
    
    filtered_df = df[mask]
    
    if filtered_df.empty:
        return pd.DataFrame(), {}
    
    # Use pre-calculated period columns
    period_map = {
        'W': ('WeekStart', 'WeekStart'),
        'D': ('DayStart', 'Day'),
        'M': ('MonthStart', 'MonthStart')
    }
    
    if aggregation_period not in period_map:
        raise ValueError("aggregation_period must be 'D', 'W', or 'M'")
    
    period_col, period_name = period_map[aggregation_period]
    
    # Define aggregation
    agg_dict = {
        "Message Count": "sum",
        "Word Count": "sum",
        "Emoji Count": "sum",
        "View Once Images": "sum"
    }
    
    # Only include existing columns
    agg_dict = {k: v for k, v in agg_dict.items() if k in filtered_df.columns}
    
    # Group and aggregate
    processed_df = filtered_df.groupby([period_col, "Name"], as_index=False).agg(agg_dict)
    processed_df.rename(columns={period_col: period_name}, inplace=True)
    
    # Calculate summary statistics efficiently
    summary_stats = {}
    for col in agg_dict.keys():
        person_agg = processed_df.groupby("Name")[col].agg(['sum', 'mean'])
        summary_stats[col] = {
            "total": int(person_agg['sum'].sum()),
            "average_per_person": person_agg['mean'].to_dict(),
            "date_range": {
                "start": filtered_df["Date"].min(),
                "end": filtered_df["Date"].max()
            }
        }
    
    return processed_df, summary_stats


# ============================================================================
# LAUGH PROCESSING (Optimized)
# ============================================================================
@st.cache_data(ttl=600, show_spinner=False, max_entries=30)
def process_laughs_data(df, min_laughs=1, start_date=None, end_date=None, aggregation_period="D"):
    """Optimized laugh processing with vectorized operations"""

    if df.empty:
        return pd.DataFrame(), {}

    # Filter by date efficiently
    mask = pd.Series(True, index=df.index)
    if start_date:
        mask &= df["Date"].dt.date >= start_date
    if end_date:
        mask &= df["Date"].dt.date <= end_date
    
    filtered_df = df[mask]

    if filtered_df.empty:
        return pd.DataFrame(), {}

    # Vectorized laugh counting
    filtered_df = filtered_df.copy()
    filtered_df["Laughs"] = (filtered_df["Message"].str.count("😂") >= min_laughs).astype(int)

    # Set index for resampling
    filtered_df = filtered_df.set_index("Date")

    # Aggregate
    grouped = (
        filtered_df.groupby("Name")
        .resample(aggregation_period)["Laughs"]
        .sum()
        .reset_index()
    )

    # Pivot
    pivot_laughs = grouped.pivot_table(
        index="Date", columns="Name", values="Laughs", fill_value=0
    )

    # Calculate statistics
    laugh_stats = {
        name.lower(): {
            "average": float(pivot_laughs[name].mean()),
            "total": int(pivot_laughs[name].sum()),
        }
        for name in pivot_laughs.columns
    }

    return pivot_laughs, laugh_stats

# ============================================================================
# VISUALIZATION FUNCTIONS (Optimized with caching)
# ============================================================================
def create_laugh_metric_cards(laugh_stats):
    """Display laugh metrics - lightweight, no caching needed"""
    if not laugh_stats:
        st.warning("No laugh data available")
        return
    
    people = list(laugh_stats.keys())
    cols = st.columns(len(people))
    
    for i, person in enumerate(people):
        stats = laugh_stats[person]
        person_color = color_map.get(person.lower(), "#c7cdd1")
        person_name = person.upper()
        
        with cols[i]:
            st.metric(
                label=f"Avg. Laughs - {person_name}",
                value=f"{stats['average']:.1f}",
                help=f"Total laughs: {stats['total']}"
            )


@st.cache_data(ttl=600, show_spinner=False)
def create_trend_visualizations(processed_df, period_column="WeekStart"):
    """Create trend visualizations with figure caching"""
    
    if processed_df.empty:
        return None
    
    # Get metrics
    metrics = [col for col in processed_df.columns if col not in ["Name", period_column]]
    
    # Create figures and store them
    figures = []
    
    for metric in metrics:
        fig = px.line(
            processed_df,
            x=period_column,
            y=metric,
            color="Name",
            markers=True,
            color_discrete_map={n: color_map.get(n.lower(), "#c7cdd1") for n in processed_df["Name"].unique()},
            title=f"{metric} Trend"
        )
        
        fig.update_layout(
            xaxis_title="Time Period",
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
        
        if "Images" in metric:
            fig.update_yaxes(tickformat=",.0f")
        else:
            fig.update_yaxes(tickformat=",~s")
        
        figures.append((metric, fig))
    
    return figures

def display_trend_visualizations(figures):
    """Display pre-generated figures in a 2-column layout"""
    if not figures:
        st.warning("No data available for visualization")
        return
    
    cols = st.columns(2)
    for i, (metric, fig) in enumerate(figures):
        with cols[i % 2]:
            st.plotly_chart(fig, use_container_width=True, key=f"trend_{metric}")


def create_metric_cards(summary_stats):
    """Display summary metric cards"""
    if not summary_stats:
        st.warning("No data available")
        return

    metrics_data = [
        ("Total Messages", summary_stats["Message Count"]["total"], "💬"),
        ("Total Words", summary_stats["Word Count"]["total"], "📝"),
        ("Total Emojis", summary_stats["Emoji Count"]["total"], "😀"),
    ]
    
    cols = st.columns(len(metrics_data), gap="small")

    for col, (title, value, icon) in zip(cols, metrics_data):
        with col:
            st.metric(
                label=f"{icon} {title}",
                value=f"{value:,}",
                help=f"Total {title.lower()} in the selected time period"
            )

def analyze_chat_data(df, start_date=None, end_date=None, aggregation_period=None):
    """Complete analysis workflow - optimized"""
    
    processed_df, summary_stats = process_chat_data(df, start_date, end_date, aggregation_period)
    
    if processed_df.empty:
        st.error("No data available for the selected date range")
        return
    
    # Metrics
    st.subheader("📊 Key Metrics")
    create_metric_cards(summary_stats)
    
    # Trends
    st.subheader("📈 Trends Over Time")
    
    period_name_map = {'W': 'WeekStart', 'D': 'Day', 'M': 'MonthStart'}
    period_name = period_name_map.get(aggregation_period, 'WeekStart')
    
    # Generate figures (cached)
    figures = create_trend_visualizations(processed_df, period_name)
    
    # Display figures
    display_trend_visualizations(figures)



# Page navigation functions
def show_events_page():
    """Display the Events page"""
    st.markdown('<div class="page-indicator">📅 Our Events</div>', unsafe_allow_html=True)
    
    # Header
    st.markdown('<h1 class="main-header">📅 Our Events</h1>', unsafe_allow_html=True)
    
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
    total_pages = max(1, (total_events + EVENTS_PER_PAGE - 1) // EVENTS_PER_PAGE)

    # Validate and reset page if necessary
    if st.session_state.event_page >= total_pages:
        st.session_state.event_page = max(0, total_pages - 1)

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
            # Calculate which page the selected event should be on before clearing it
            if events_data and st.session_state.selected_event is not None:
                target_page = st.session_state.selected_event // EVENTS_PER_PAGE
                st.session_state.event_page = target_page
            
            st.session_state.selected_event = None
            st.session_state.edit_event_id = None
            st.rerun()
        
        event = events_data[st.session_state.selected_event]
        
        if st.session_state.edit_event_id == event['id']:
            edit_event_form(event)
        else:
            display_event_details(event)
    else:
        # Reset selected_event if it's invalid
        if st.session_state.selected_event is not None and st.session_state.selected_event >= len(events_data):
            st.session_state.selected_event = None
            st.session_state.edit_event_id = None
        
        # Events grid view
        if events_data:
            st.markdown("---")
            st.subheader("📅 Your Events Timeline")
            
            # Pagination controls at top
            col1, col2, col3 = st.columns([1, 2, 1])
            with col1:
                if st.button("⬅️ Prev", disabled=st.session_state.event_page == 0):
                    st.session_state.event_page -= 1
                    # Clear selection when changing pages
                    st.session_state.selected_event = None
                    st.session_state.edit_event_id = None
                    st.rerun()
            with col2:
                st.markdown(
                    f"<div style='text-align:center;'>Page {st.session_state.event_page+1} of {total_pages}</div>", 
                    unsafe_allow_html=True
                )
            with col3:
                if st.button("Next ➡️", disabled=st.session_state.event_page >= total_pages-1):
                    st.session_state.event_page += 1
                    # Clear selection when changing pages
                    st.session_state.selected_event = None
                    st.session_state.edit_event_id = None
                    st.rerun()
            
            # Render paginated events with FIXED start index and full events_data
            create_event_cards(page_events, start_idx, events_data)

            # Pagination controls at bottom
            col11, col22, col33 = st.columns([1, 2, 1])
            with col11:
                if st.button("⬅️ Prev ", disabled=st.session_state.event_page == 0):
                    st.session_state.event_page -= 1
                    # Clear selection when changing pages
                    st.session_state.selected_event = None
                    st.session_state.edit_event_id = None
                    st.rerun()
            with col22:
                st.markdown(
                    f"<div style='text-align:center;'>Page {st.session_state.event_page+1} of {total_pages}</div>", 
                    unsafe_allow_html=True
                )
            with col33:
                if st.button("Next ➡️ ", disabled=st.session_state.event_page >= total_pages-1):
                    st.session_state.event_page += 1
                    # Clear selection when changing pages
                    st.session_state.selected_event = None
                    st.session_state.edit_event_id = None
                    st.rerun()
        else:
            st.markdown("""
            <div class="no-events">
                <h2>🎯 Create Your First Event</h2>
                <p>Click "Add New Event" button above to get started!</p>
            </div>
            """, unsafe_allow_html=True)

# ============================================================================
# PAGE FUNCTIONS (Keep analytics loading lazy)
# ============================================================================
def show_analytics_page():
    """Display Analytics page with lazy loading"""
    st.markdown('<div class="page-indicator">📈 Analytics Dashboard</div>', unsafe_allow_html=True)
    st.markdown('<h1 class="main-header">📈 Analytics</h1>', unsafe_allow_html=True)
    
    # Load chat data ONCE per session
    if 'chat_data' not in st.session_state:
        try:
            with st.spinner("Loading chat data..."):
                st.session_state.chat_data = load_chat_data()
                print("✅ Chat data loaded successfully")
                print(st.session_state.chat_data.head())
        except Exception as e:
            st.error(f"Error loading chat data: {e}")
            st.session_state.chat_data = pd.DataFrame()
    
    chats = st.session_state.chat_data
    
    if chats.empty:
        st.info("No chat data available for analytics.")
        return
    
    # Get filters
    filters = st.session_state.get('analytics_filters', {
        'min_laughs': 1,
        'start_date': chats["Date"].min().date(),
        'end_date': chats["Date"].max().date(),
        'aggregation_period': 'W'
    })
    
    min_laughs = filters['min_laughs']
    start_date = filters['start_date']
    end_date = filters['end_date']
    aggregation_period = filters['aggregation_period']
    
    st.markdown("---")
    st.markdown(
        f"""<h3>Showing Data till <span style="color:#20a808;">{chats.Date.dt.date.max()}</span></h3>""",
        unsafe_allow_html=True
    )
    
    # Laughs section
    with st.expander("😂 Laughs Analytics", expanded=True):
        if "Message" in chats.columns:
            st.subheader("😂 Laugh Analysis")
            pivot_laughs, laugh_stats = process_laughs_data(
                chats, start_date=start_date, end_date=end_date, 
                min_laughs=min_laughs, aggregation_period=aggregation_period
            )
            
            if not pivot_laughs.empty:
                create_laugh_metric_cards(laugh_stats)
                st.markdown("**Daily Laugh Trends**")
                chart_colors = [color_map.get(col.lower(), "#c7cdd1") for col in pivot_laughs.columns]
                st.line_chart(pivot_laughs, color=chart_colors)
    
    # Chat trends section
    with st.expander("💬 Chat Trends", expanded=True):
        analyze_chat_data(chats, start_date, end_date, aggregation_period)

def main():
    """Main application logic with multi-page navigation"""
    
    # Initialize session state variables
    if 'counter_animated' not in st.session_state:
        st.session_state.counter_animated = False
    
    if 'current_page' not in st.session_state:
        st.session_state.current_page = 'Events'
    
    # Check authentication first
    if not st.session_state.authenticated or not st.session_state.user:
        login_page()
        return
    
    # Only proceed if user is authenticated and user data exists
    if st.session_state.user is None:
        st.error("Session error. Please log in again.")
        logout()
        return

    # Hardcoded start date
    start_date = date(2025, 6, 7) 
    today = date.today()
    days_known = (today - start_date).days

    # Show welcome animation only once after login
    if not st.session_state.counter_animated:
        # Center the animation
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown(f"""
            <div style="text-align: center; margin-top: 3rem;">
                <h2 style="color: #e83e8c;">Welcome Back, {st.session_state.user.get("username", "Unknown User")}!</h2>
            </div>
            """, unsafe_allow_html=True)
            
            counter_placeholder = st.empty()
            
            for i in range(days_known + 1):
                counter_placeholder.markdown(f"""
                    <div style="background: linear-gradient(135deg, #e83e8c 0%, #ff6b9d 100%); 
                                color: white; padding: 2rem; border-radius: 15px; 
                                text-align: center; margin: 2rem 0; box-shadow: 0 4px 6px rgba(0,0,0,0.2);">
                        <div style="font-size: 1.2rem; margin-bottom: 1rem; color: white;">
                            We've known each other for
                        </div>
                        <div style="font-size: 3rem; font-weight: bold; color: white;">
                            {i} days 🤍
                        </div>
                    </div>
                """, unsafe_allow_html=True)
                time.sleep(0.01)
            
            time.sleep(1.5)  # Pause to enjoy the final count
            st.session_state.counter_animated = True
            st.rerun()
    
    # Sidebar navigation
    with st.sidebar:
        st.markdown("### Navigation")
        
        # User info
        username = st.session_state.user.get("username", "Unknown User")
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%); 
                    color: white; padding: 1rem; border-radius: 10px; text-align: center; margin-bottom: 1rem;">
            <strong>👋 Welcome, {username}!</strong>
        </div>
        """, unsafe_allow_html=True)

        # Show static counter in sidebar
        st.markdown(f"""
            <div style="background: linear-gradient(135deg, #e83e8c 0%, #ff6b9d 100%); 
                        padding: 0.8rem; border-radius: 8px; 
                        text-align: center; margin-bottom: 1rem; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <span style="color: white; font-size: 0.9rem;">We've known each other for</span><br>
                <span style="font-size:1.4rem; font-weight:bold; color: white;">
                    {days_known} days 🤍
                </span>
            </div>
        """, unsafe_allow_html=True)
                        
        # Page selection with buttons
        st.markdown("**Choose a page:**")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📅 Events", 
                        type="primary" if st.session_state.current_page == 'Events' else "secondary",
                        use_container_width=True):
                st.session_state.current_page = 'Events'
                st.rerun()
        with col2:
            if st.button("📈 Analytics", 
                        type="primary" if st.session_state.current_page == 'Analytics' else "secondary",
                        use_container_width=True):
                st.session_state.current_page = 'Analytics'
                st.rerun()
        
        st.markdown("---")
        
        # Analytics Filters (only show when on Analytics page)
        if st.session_state.current_page == 'Analytics':
            # Load chat data to get date ranges
            chats = load_chat_data()
            
            if not chats.empty:
                st.markdown("### 🎛️ Analytics Filters")
                
                min_laughs = st.slider(
                    "Minimum 😂 count", 
                    min_value=1, 
                    max_value=5, 
                    value=1
                )
                
                filter_start_date = st.date_input(
                    "Start date", 
                    value=chats["Date"].min().date()
                )
                
                filter_end_date = st.date_input(
                    "End date", 
                    value=chats["Date"].max().date()
                )
                
                aggregation_period = st.selectbox(
                    "Time Period", 
                    options=['D', 'W', 'M'], 
                    format_func=lambda x: {'W': 'Weekly', 'D': 'Daily', 'M': 'Monthly'}[x],
                    index=1  # Default to Weekly
                )
                
                # Store filters in session state
                st.session_state.analytics_filters = {
                    'min_laughs': min_laughs,
                    'start_date': filter_start_date,
                    'end_date': filter_end_date,
                    'aggregation_period': aggregation_period
                }
        
        st.markdown("---")
        
        if st.button("🚪 Logout", type="secondary", use_container_width=True):
            logout()
            return

    # Render the selected page
    if st.session_state.current_page == 'Events':
        show_events_page()
    elif st.session_state.current_page == 'Analytics':
        show_analytics_page()
    else:
        st.info("Please select a page from the sidebar")


if __name__ == "__main__":
    main()