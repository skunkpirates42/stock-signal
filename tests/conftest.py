"""Offline tests must never inherit real account credentials or broker settings."""
import os

for name in ('ALPACA_API_KEY', 'ALPACA_SECRET_KEY', 'ANTHROPIC_API_KEY', 'GROQ_API_KEY'):
    os.environ[name] = ''
os.environ['BROKER'] = 'local'
os.environ['LLM_PROVIDER'] = 'template'
