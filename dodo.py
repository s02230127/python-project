"""Doit tasks for FileOptimizer."""

import os
import shutil
import subprocess
from pathlib import Path

DOIT_CONFIG = {
    'default_tasks': ['lint', 'test', 'docs', 'build'],
}

def task_lint():
    """Run ruff and pydocstyle."""
    return {
        'actions': [
            'ruff check fileoptimizer tests web.py',
            'pydocstyle fileoptimizer tests web.py',
        ],
        'verbosity': 2,
    }

def task_test():
    """Run pytest with coverage."""
    return {
        'actions': [
            'pytest --cov=fileoptimizer --cov=web --cov-report=term-missing tests/'
        ],
        'verbosity': 2,
    }

def task_docs():
    """Build Sphinx documentation."""
    return {
        'actions': [
            'sphinx-build -b html docs/ docs/_build/html',
        ],
        'file_dep': ['docs/conf.py', 'docs/index.rst'],
        'targets': ['docs/_build/html/index.html'],
        'verbosity': 2,
    }

def task_translate():
    """Extract messages and update .po files."""
    return {
        'actions': [
            'pybabel extract -F babel.cfg -o locales/messages.pot .',
            'pybabel update -i locales/messages.pot -d locales',
        ],
        'file_dep': [Path(p) for p in Path('.').rglob('*.py') if 'locales' not in str(p)] + list(Path('templates').rglob('*.html')),
        'targets': ['locales/messages.pot'],
        'verbosity': 2,
    }

def task_compile():
    """Compile .mo files."""
    return {
        'actions': [
            'pybabel compile -d locales',
        ],
        'file_dep': ['locales/ru/LC_MESSAGES/messages.po', 'locales/en/LC_MESSAGES/messages.po'],
        'targets': ['locales/ru/LC_MESSAGES/messages.mo', 'locales/en/LC_MESSAGES/messages.mo'],
        'verbosity': 2,
    }

def task_clean():
    """Remove temporary and build artifacts."""
    return {
        'actions': [
            lambda: shutil.rmtree('tmp', ignore_errors=True),
            lambda: shutil.rmtree('docs/_build', ignore_errors=True),
            lambda: shutil.rmtree('dist', ignore_errors=True),
            lambda: shutil.rmtree('build', ignore_errors=True),
            lambda: shutil.rmtree('fileoptimizer.egg-info', ignore_errors=True),
            lambda: [p.unlink() for p in Path('.').glob('**/*.mo') if p.parent.name == 'LC_MESSAGES'],
        ],
        'verbosity': 2,
    }

def task_build():
    """Build wheel distribution."""
    return {
        'actions': [
            'python -m build --wheel',
        ],
        'file_dep': ['pyproject.toml'] + list(Path('.').rglob('*.py')) + list(Path('templates').rglob('*')) + list(Path('static').rglob('*')),
        'targets': ['dist/*.whl'],
        'verbosity': 2,
    }

def task_install():
    """Install the package in editable mode."""
    return {
        'actions': [
            'pip install -e .',
        ],
        'verbosity': 2,
    }