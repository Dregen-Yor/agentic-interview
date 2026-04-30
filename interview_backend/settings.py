"""
面试后端项目的Django设置。

使用Django 5.1.9通过'django-admin startproject'生成。

有关此文件的更多信息，请参阅
https://docs.djangoproject.com/en/5.1/topics/settings/

有关设置及其值的完整列表，请参阅
https://docs.djangoproject.com/en/5.1/ref/settings/
"""

from pathlib import Path
import os
from dotenv import load_dotenv
# 加载环境变量
load_dotenv()

# MongoDB连接配置
MONGO_URI = os.getenv('MONGO_URI')
MONGO_DATABASE_NAME = os.getenv('MONGO_DATABASE_NAME')

# 在项目内构建路径，如：BASE_DIR / 'subdir'
BASE_DIR = Path(__file__).resolve().parent.parent


# 快速开发设置 - 不适合生产环境
# 参见 https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/

# 安全警告：生产环境中保持密钥安全！
# SECRET_KEY 用于 Django 内部签名 + JWT 签发（interview/auth_utils.py），
# 必须通过环境变量注入；缺失时 fail-fast 防止使用默认弱密钥导致 token 可被伪造。
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY 未配置：请在 .env 或环境变量中设置 SECRET_KEY。"
        "切勿使用 'django-insecure-...' 默认开发密钥，否则任何看过仓库的人都能伪造 JWT。"
    )

# 安全警告：生产环境中不要开启调试模式！
DEBUG = True

# 允许的主机列表
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "101.76.218.89", "*"]

# 允许所有跨域请求
CORS_ALLOW_ALL_ORIGINS = True

# 密码哈希算法配置
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.BCryptSHA256PasswordHasher',
    'django.contrib.auth.hashers.BCryptPasswordHasher',
]

# 应用程序定义

INSTALLED_APPS = [
    'daphne',  # ASGI服务器
    'channels',  # WebSocket支持
    'django.contrib.admin',  # 管理界面
    'django.contrib.auth',  # 认证系统
    'django.contrib.contenttypes',  # 内容类型框架
    'django.contrib.sessions',  # 会话框架
    'django.contrib.messages',  # 消息框架
    'django.contrib.staticfiles',  # 静态文件处理
    'corsheaders',  # 跨域资源共享
    'interview',  # 面试应用
]

# 中间件配置
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',  # 安全中间件
    'django.contrib.sessions.middleware.SessionMiddleware',  # 会话中间件
    'corsheaders.middleware.CorsMiddleware',  # 跨域中间件
    'django.middleware.common.CommonMiddleware',  # 通用中间件
    'django.middleware.csrf.CsrfViewMiddleware',  # CSRF保护
    'django.contrib.auth.middleware.AuthenticationMiddleware',  # 认证中间件
    'django.contrib.messages.middleware.MessageMiddleware',  # 消息中间件
    'django.middleware.clickjacking.XFrameOptionsMiddleware',  # 点击劫持保护
]

# 根URL配置
ROOT_URLCONF = 'interview_backend.urls'

# 模板配置
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],  # 模板目录
        'APP_DIRS': True,  # 在应用目录中查找模板
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# WSGI和ASGI应用程序配置
WSGI_APPLICATION = 'interview_backend.wsgi.application'
ASGI_APPLICATION = 'interview_backend.asgi.application'

# Channels层配置（用于WebSocket）
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [("127.0.0.1", 6379)],  # Redis服务器地址
        },
    },
}


# 数据库配置
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',  # SQLite数据库引擎
        'NAME': BASE_DIR / 'db.sqlite3',  # 数据库文件路径
    }
}


# 密码验证
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = []  # 密码验证器（已禁用）


# 国际化配置
# https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = 'en-us'  # 语言代码

TIME_ZONE = 'UTC'  # 时区

USE_I18N = True  # 启用国际化

USE_TZ = True  # 启用时区支持


# 静态文件配置（CSS、JavaScript、图片）
# https://docs.djangoproject.com/en/5.1/howto/static-files/

STATIC_URL = 'static/'  # 静态文件URL前缀

# 默认主键字段类型
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'  # 大整数自动字段


# ====================================================================
# 统一日志配置
# ====================================================================
# 设计目标：
# 1. 项目内所有模块通过 logging.getLogger("interview.xxx") 获取 logger，
#    继承同一份 formatter / handler，避免散落 print + logger 双轨。
# 2. 默认输出到控制台；通过环境变量 INTERVIEW_LOG_FILE 可启用文件 handler。
# 3. INTERVIEW_LOG_LEVEL 控制项目自身（"interview" 命名空间）的日志级别，
#    Django/库的日志保持 WARNING，避免噪音。
# ====================================================================
LOG_LEVEL = os.getenv("INTERVIEW_LOG_LEVEL", "INFO").upper()
LOG_FILE = os.getenv("INTERVIEW_LOG_FILE")

_log_handlers = {
    "console": {
        "class": "logging.StreamHandler",
        "formatter": "verbose",
        "level": LOG_LEVEL,
    },
}

if LOG_FILE:
    _log_handlers["file"] = {
        "class": "logging.handlers.RotatingFileHandler",
        "filename": LOG_FILE,
        "maxBytes": 10 * 1024 * 1024,
        "backupCount": 5,
        "formatter": "verbose",
        "level": LOG_LEVEL,
        "encoding": "utf-8",
    }

_app_handlers = ["console"] + (["file"] if LOG_FILE else [])

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        },
    },
    "handlers": _log_handlers,
    "loggers": {
        # 项目自身命名空间
        "interview": {
            "handlers": _app_handlers,
            "level": LOG_LEVEL,
            "propagate": False,
        },
        # Django 框架日志
        "django": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        # Channels / Daphne 日志
        "daphne": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
}
