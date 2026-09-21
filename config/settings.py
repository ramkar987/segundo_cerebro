from pathlib import Path
import os
from urllib.parse import urlparse, unquote

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'dev-only-change-me')
DEBUG = os.getenv('DJANGO_DEBUG', '1') == '1'
ALLOWED_HOSTS = [h.strip() for h in os.getenv('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if h.strip()]
CSRF_TRUSTED_ORIGINS = [u.strip() for u in os.getenv('DJANGO_CSRF_TRUSTED_ORIGINS', '').split(',') if u.strip()]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'knowledge',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'
TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [BASE_DIR / 'templates'],
    'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
    ]},
}]
WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'


def database_from_env():
    url = os.getenv('DATABASE_URL', '').strip()
    if not url:
        return {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3'}
    parsed = urlparse(url)
    if parsed.scheme not in {'postgres', 'postgresql'}:
        raise ValueError('DATABASE_URL deve ser postgres:// ou postgresql://')
    return {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': unquote(parsed.path.lstrip('/')),
        'USER': unquote(parsed.username or ''),
        'PASSWORD': unquote(parsed.password or ''),
        'HOST': parsed.hostname or 'localhost',
        'PORT': parsed.port or 5432,
        'CONN_MAX_AGE': 60,
    }


DATABASES = {'default': database_from_env()}

AUTH_PASSWORD_VALIDATORS = []
LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Limites iniciais, ajustáveis via ambiente.
MAX_CAPTURE_CHARS = int(os.getenv('MAX_CAPTURE_CHARS', '200000'))
WEB_FETCH_TIMEOUT = int(os.getenv('WEB_FETCH_TIMEOUT', '20'))
WORKER_JOB_DELAY = float(os.getenv('WORKER_JOB_DELAY', '5.0'))

# Transcrição. Sem GROQ_API_KEY a captura continua funcionando; apenas pula áudio.
GROQ_API_KEY = os.getenv('GROQ_API_KEY', '').strip()
GROQ_WHISPER_MODEL = os.getenv('GROQ_WHISPER_MODEL', 'whisper-large-v3-turbo').strip()
TRANSCRIBE_MEDIA = os.getenv('TRANSCRIBE_MEDIA', '1') == '1'
TRANSCRIPTION_LANGUAGE = os.getenv('TRANSCRIPTION_LANGUAGE', 'pt').strip() or 'pt'
MAX_TRANSCRIPTION_BYTES = int(os.getenv('MAX_TRANSCRIPTION_BYTES', str(24 * 1024 * 1024)))

# Leitura visual de posts/carrosséis do Instagram.
GROQ_VISION_MODEL = os.getenv('GROQ_VISION_MODEL', 'qwen/qwen3.8-27b').strip()
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '').strip()
GEMINI_VISION_MODEL = os.getenv(
    'GEMINI_VISION_MODEL',
    'gemini-3.5-flash-lite',
).strip()
GEMINI_TEXT_MODEL = os.getenv(
    'GEMINI_TEXT_MODEL',
    GEMINI_VISION_MODEL,
).strip()
ANALYZE_IMAGES = os.getenv('ANALYZE_IMAGES', '1') == '1'
MAX_INSTAGRAM_IMAGES = int(os.getenv('MAX_INSTAGRAM_IMAGES', '20'))
MAX_VISION_IMAGE_BYTES = int(os.getenv('MAX_VISION_IMAGE_BYTES', str(15 * 1024 * 1024)))


# Análise textual com IA. Usa a mesma GROQ_API_KEY da transcrição.
GROQ_CHAT_MODEL = os.getenv('GROQ_CHAT_MODEL', 'openai/gpt-oss-20b').strip()
ANALYZE_CONTENT = os.getenv('ANALYZE_CONTENT', '1') == '1'
AI_TIMEOUT = int(os.getenv('AI_TIMEOUT', '120'))
GROQ_WORKER_MIN_INTERVAL = float(os.getenv('GROQ_WORKER_MIN_INTERVAL', '20.0'))


# Busca semântica / RAG.
SEMANTIC_SEARCH_ENABLED = os.getenv('SEMANTIC_SEARCH_ENABLED', '1') == '1'
GEMINI_EMBEDDING_MODEL = os.getenv(
    'GEMINI_EMBEDDING_MODEL',
    'gemini-embedding-2',
).strip()
EMBEDDING_DIMENSIONS = int(os.getenv('EMBEDDING_DIMENSIONS', '768'))
EMBEDDING_BATCH_SIZE = int(os.getenv('EMBEDDING_BATCH_SIZE', '20'))
SEMANTIC_CHUNK_CHARS = int(os.getenv('SEMANTIC_CHUNK_CHARS', '1400'))
SEMANTIC_TOP_K = int(os.getenv('SEMANTIC_TOP_K', '24'))
SEMANTIC_MIN_SCORE = float(os.getenv('SEMANTIC_MIN_SCORE', '0.20'))
RAG_CANDIDATE_TOP_K = int(os.getenv('RAG_CANDIDATE_TOP_K', '20'))
RAG_TOP_K = int(os.getenv('RAG_TOP_K', '4'))
RAG_MAX_CHUNKS_PER_ITEM = int(os.getenv('RAG_MAX_CHUNKS_PER_ITEM', '1'))
RAG_RELATIVE_SCORE_DROP = float(os.getenv('RAG_RELATIVE_SCORE_DROP', '0.12'))

LIBRARY_SEMANTIC_CANDIDATES = int(os.getenv('LIBRARY_SEMANTIC_CANDIDATES', '16'))
LIBRARY_SEMANTIC_MAX_RESULTS = int(os.getenv('LIBRARY_SEMANTIC_MAX_RESULTS', '8'))
LIBRARY_SEMANTIC_MIN_RELEVANCE = int(os.getenv('LIBRARY_SEMANTIC_MIN_RELEVANCE', '2'))
LIBRARY_SEMANTIC_RELATIVE_DROP = float(os.getenv('LIBRARY_SEMANTIC_RELATIVE_DROP', '0.10'))
